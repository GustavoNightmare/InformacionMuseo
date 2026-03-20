import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

import requests


TRUE_VALUES = {"1", "true", "yes", "on", "si", "sí"}
FALSE_VALUES = {"0", "false", "no", "off"}
GPT_OSS_THINK_LEVELS = {"low", "medium", "high"}


@dataclass
class RequestTarget:
    provider: str
    model: str
    chat_url: str
    headers: Dict[str, str]


class LLMClient:
    """
    Compatible con Ollama local y Ollama Cloud.

    Ejemplos:
    - OLLAMA_PROVIDER=auto
    - OLLAMA_CHAT_MODEL=gpt-oss:20b-cloud   -> usa cloud
    - OLLAMA_CHAT_MODEL=qwen3.5:9b          -> usa local
    """

    def __init__(self):
        self.provider = (os.getenv("OLLAMA_PROVIDER", "auto")
                         or "auto").strip().lower()

        self.local_base_url = self._normalize_base_url(
            os.getenv("OLLAMA_LOCAL_BASE_URL")
            or os.getenv("OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434"
        )
        self.cloud_base_url = self._normalize_base_url(
            os.getenv("OLLAMA_CLOUD_BASE_URL") or "https://ollama.com"
        )

        self.model = (os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
                      or "llama3.1:8b").strip()
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
        self.api_key = (os.getenv("OLLAMA_API_KEY") or "").strip()

        self.connect_timeout = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "10"))
        self.read_timeout = self._parse_read_timeout(
            os.getenv("OLLAMA_READ_TIMEOUT", ""))

        self.think = self._parse_think(
            os.getenv("OLLAMA_THINK", "false"), self.model)

        self.enable_fallback = self._parse_bool(
            os.getenv("OLLAMA_ENABLE_FALLBACK", "true"),
            default=True,
        )
        self.fallback_model = (
            os.getenv("OLLAMA_FALLBACK_MODEL") or "").strip()
        self.fallback_provider = (
            os.getenv("OLLAMA_FALLBACK_PROVIDER", "local") or "local"
        ).strip().lower()
        self.fallback_think = self._parse_think(
            os.getenv("OLLAMA_FALLBACK_THINK", "false"),
            self.fallback_model,
        )

    def chat(self, messages) -> str:
        primary = self._build_target(self.model, self.provider)
        payload = self._build_payload(
            primary.model,
            messages,
            stream=False,
            think_value=self.think,
        )

        try:
            data = self._request_json(primary, payload)
            return ((data.get("message") or {}).get("content") or "").strip()
        except Exception as primary_error:
            fallback = self._get_fallback_target(primary)
            if not fallback:
                raise

            fallback_payload = self._build_payload(
                fallback.model,
                messages,
                stream=False,
                think_value=self.fallback_think,
            )
            try:
                data = self._request_json(fallback, fallback_payload)
                return ((data.get("message") or {}).get("content") or "").strip()
            except Exception as fallback_error:
                raise RuntimeError(
                    "Falló el modelo principal "
                    f"({primary.provider}:{primary.model}) y también el fallback "
                    f"({fallback.provider}:{fallback.model}).\n"
                    f"- Principal: {primary_error}\n"
                    f"- Fallback: {fallback_error}"
                ) from fallback_error

    def stream(self, messages):
        primary = self._build_target(self.model, self.provider)
        state = {"yielded_any": False}

        def mark_yield():
            state["yielded_any"] = True

        try:
            yield from self._stream_from_target(
                primary,
                messages,
                think_value=self.think,
                mark_yield=mark_yield,
            )
            return
        except Exception as primary_error:
            fallback = self._get_fallback_target(primary)
            if not fallback or state["yielded_any"]:
                raise

            try:
                yield from self._stream_from_target(
                    fallback,
                    messages,
                    think_value=self.fallback_think,
                    mark_yield=mark_yield,
                )
            except Exception as fallback_error:
                raise RuntimeError(
                    "Falló el modelo principal "
                    f"({primary.provider}:{primary.model}) y también el fallback "
                    f"({fallback.provider}:{fallback.model}).\n"
                    f"- Principal: {primary_error}\n"
                    f"- Fallback: {fallback_error}"
                ) from fallback_error

    def _stream_from_target(self, target: RequestTarget, messages, think_value, mark_yield):
        payload = self._build_payload(
            target.model, messages, stream=True, think_value=think_value)
        timeout = (self.connect_timeout, self.read_timeout)

        try:
            response = requests.post(
                target.chat_url,
                json=payload,
                headers=target.headers,
                stream=True,
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise RuntimeError(
                f"No se pudo conectar con {target.provider}:{target.model} en {target.chat_url}: {e}"
            ) from e

        if not response.ok:
            raise RuntimeError(self._format_http_error(target, response))

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = obj.get("message") or {}
            content = msg.get("content") or ""
            if content:
                mark_yield()
                yield content

            if obj.get("done"):
                break

    def _request_json(self, target: RequestTarget, payload: dict) -> dict:
        timeout = (self.connect_timeout, self.read_timeout)
        try:
            response = requests.post(
                target.chat_url,
                json=payload,
                headers=target.headers,
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise RuntimeError(
                f"No se pudo conectar con {target.provider}:{target.model} en {target.chat_url}: {e}"
            ) from e

        if not response.ok:
            raise RuntimeError(self._format_http_error(target, response))
        return response.json()

    def _build_payload(self, model: str, messages, stream: bool, think_value) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature},
        }
        if think_value is not None:
            payload["think"] = think_value
        return payload

    def _build_target(self, model: str, provider: str) -> RequestTarget:
        resolved_provider = self._resolve_provider(provider, model)

        if resolved_provider == "cloud":
            if not self.api_key:
                raise RuntimeError(
                    "Falta OLLAMA_API_KEY para usar Ollama Cloud con el modelo "
                    f"{model}."
                )
            base_url = self.cloud_base_url
            headers = {"Authorization": f"Bearer {self.api_key}"}
        else:
            base_url = self.local_base_url
            headers = {}

        return RequestTarget(
            provider=resolved_provider,
            model=model,
            chat_url=f"{base_url}/api/chat",
            headers=headers,
        )

    def _get_fallback_target(self, primary: RequestTarget) -> Optional[RequestTarget]:
        if not self.enable_fallback or not self.fallback_model:
            return None

        try:
            fallback = self._build_target(
                self.fallback_model, self.fallback_provider)
        except Exception:
            return None

        if fallback.model == primary.model and fallback.provider == primary.provider:
            return None

        return fallback

    def _resolve_provider(self, provider: str, model: str) -> str:
        provider = (provider or "auto").strip().lower()
        if provider in {"local", "cloud"}:
            return provider
        if self._looks_like_cloud_model(model):
            return "cloud"
        return "local"

    @staticmethod
    def _looks_like_cloud_model(model: str) -> bool:
        model = (model or "").strip().lower()
        return (
            model.endswith(":cloud")
            or model.endswith("-cloud")
            or ":cloud" in model
            or "-cloud" in model
        )

    @staticmethod
    def _normalize_base_url(raw: str) -> str:
        base = (raw or "").strip().rstrip("/")
        if base.endswith("/api"):
            return base[:-4]
        return base

    @staticmethod
    def _parse_bool(value: str, default: bool = False) -> bool:
        raw = (value or "").strip().lower()
        if not raw:
            return default
        if raw in TRUE_VALUES:
            return True
        if raw in FALSE_VALUES:
            return False
        return default

    @staticmethod
    def _parse_read_timeout(value: str):
        raw = (value or "").strip().lower()
        if raw in {"", "none", "null", "infinite", "inf", "-1"}:
            return None
        return float(raw)

    def _parse_think(self, value: str, model: str):
        raw = (value or "").strip().lower()
        if not raw:
            return None

        if self._is_gpt_oss(model):
            if raw in GPT_OSS_THINK_LEVELS:
                return raw
            if raw in TRUE_VALUES:
                return "medium"
            if raw in FALSE_VALUES:
                return None
            return None

        if raw in TRUE_VALUES:
            return True
        if raw in FALSE_VALUES:
            return False
        if raw in GPT_OSS_THINK_LEVELS:
            return raw
        return None

    @staticmethod
    def _is_gpt_oss(model: str) -> bool:
        return (model or "").strip().lower().startswith("gpt-oss")

    @staticmethod
    def _format_http_error(target: RequestTarget, response: requests.Response) -> str:
        text = (response.text or "").strip()
        detail = text[:800] if text else "sin detalle"
        return (
            f"Ollama error {response.status_code} en {target.provider}:{target.model} "
            f"({target.chat_url}): {detail}"
        )
