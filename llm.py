import os
import json
import requests


class LLMClient:
    """
    Ollama /api/chat:
    - chat(messages) -> str
    - stream(messages) -> generator[str]
    Ignora cualquier "thinking" y devuelve solo message.content
    """

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.chat_url = os.getenv(
            "OLLAMA_CHAT_URL", self.base_url.rstrip("/") + "/api/chat")
        self.model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")

        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))

        # Para modelos "thinking" (Qwen, etc.): lo apagamos
        self.think = os.getenv(
            "OLLAMA_THINK", "false").lower() in ("1", "true", "yes")

    def chat(self, messages) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "think": self.think,  # false recomendado
            "options": {"temperature": self.temperature},
        }
        r = requests.post(self.chat_url, json=payload, timeout=(10, None))
        if not r.ok:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text}")
        data = r.json()
        return ((data.get("message") or {}).get("content") or "").strip()

    def stream(self, messages):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "think": self.think,  # false recomendado
            "options": {"temperature": self.temperature},
        }

        r = requests.post(self.chat_url, json=payload,
                          stream=True, timeout=(10, None))
        if not r.ok:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text}")

        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            obj = json.loads(line)
            msg = obj.get("message") or {}
            content = msg.get("content") or ""
            if content:
                yield content
            if obj.get("done"):
                break
