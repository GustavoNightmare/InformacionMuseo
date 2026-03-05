import os
import json
import requests


class LLMClient:
    """
    Interfaz:
      - chat(messages)  -> str          (no streaming)
      - stream(messages) -> generator  (streaming por chunks)

    messages: lista de dicts:
      [{ "role": "system"|"user"|"assistant", "content": "..." }, ...]
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "ollama")

        # Usamos /api/generate (como `ollama run`), más estable que /api/chat en algunos casos.
        self.ollama_url = os.getenv("OLLAMA_GEN_URL", "http://127.0.0.1:11434/api/generate")

        # Usa exactamente el modelo que tienes en Ollama (ej: llama3.1:8b)
        self.ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")

        # Contexto y longitud de salida (ajusta si quieres)
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "180"))  # reduce latencia

    # ------------------ API pública ------------------

    def chat(self, messages) -> str:
        """Respuesta completa (sin streaming)."""
        if self.provider != "ollama":
            raise NotImplementedError("Por ahora solo Ollama. Luego conectamos OpenAI.")

        prompt = self._messages_to_prompt(messages)
        return self._generate_ollama(prompt, stream=False)

    def stream(self, messages):
        """Genera la respuesta por partes (streaming)."""
        if self.provider != "ollama":
            raise NotImplementedError("Por ahora solo Ollama. Luego conectamos OpenAI.")

        prompt = self._messages_to_prompt(messages)
        yield from self._generate_ollama_stream(prompt)

    # ------------------ Helpers ------------------

    def _messages_to_prompt(self, messages) -> str:
        """
        Convierte messages a un prompt tipo texto:
        - junta system en un bloque
        - junta conversación con prefijos Usuario/Asistente
        """
        system_parts = []
        convo_parts = []

        for m in messages:
            role = (m.get("role") or "").strip()
            content = (m.get("content") or "").strip()
            if not content:
                continue

            if role == "system":
                system_parts.append(content)
            elif role == "user":
                convo_parts.append(f"Usuario: {content}")
            elif role == "assistant":
                convo_parts.append(f"Asistente: {content}")

        system_block = "\n\n".join(system_parts).strip()
        convo_block = "\n".join(convo_parts).strip()

        prompt = ""
        if system_block:
            prompt += "INSTRUCCIONES Y CONTEXTO:\n" + system_block + "\n\n"
        if convo_block:
            prompt += "CONVERSACIÓN:\n" + convo_block + "\n\n"
        prompt += "Asistente:"

        return prompt

    def _base_payload(self, prompt: str, stream: bool) -> dict:
        return {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }

    def _generate_ollama(self, prompt: str, stream: bool = False) -> str:
        """
        Llama a /api/generate sin streaming y devuelve `response`.
        Importante: timeout=(10, None) -> 10s conexión, sin límite lectura (evita cortar a 3 min).
        """
        payload = self._base_payload(prompt, stream=False)

        r = requests.post(self.ollama_url, json=payload, timeout=(10, None))
        if not r.ok:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text}")

        data = r.json()
        return (data.get("response") or "").strip()

    def _generate_ollama_stream(self, prompt: str):
        """
        Streaming NDJSON de Ollama (/api/generate con stream=true).
        Va yield-eando trozos de texto.
        """
        payload = self._base_payload(prompt, stream=True)

        r = requests.post(self.ollama_url, json=payload, stream=True, timeout=(10, None))
        if not r.ok:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text}")

        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            obj = json.loads(line)

            chunk = obj.get("response", "")
            if chunk:
                yield chunk

            if obj.get("done"):
                break