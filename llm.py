import os
import json
import requests


class LLMClient:
    """
    - chat(messages) -> str (sin streaming)
    - stream(messages) -> generator (streaming por chunks)
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "ollama")
        self.ollama_url = os.getenv(
            "OLLAMA_GEN_URL", "http://127.0.0.1:11434/api/generate")
        self.ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")

        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "180"))
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

        # Para que no “alucine” conversaciones
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))

        # Si intenta poner “Usuario:” cortamos
        self.stop = ["\nUsuario:", "Usuario:",
                     "\nUser:", "User:", "\nFuente:", "Fuente:"]

    def chat(self, messages) -> str:
        if self.provider != "ollama":
            raise NotImplementedError("Por ahora solo Ollama.")
        prompt = self._messages_to_prompt(messages)
        return self._generate(prompt)

    def stream(self, messages):
        if self.provider != "ollama":
            raise NotImplementedError("Por ahora solo Ollama.")
        prompt = self._messages_to_prompt(messages)
        yield from self._generate_stream(prompt)

    def _messages_to_prompt(self, messages) -> str:
        """
        Junta TODOS los system en un bloque (instrucciones + contexto),
        y toma el ÚLTIMO mensaje del usuario como pregunta.
        Sin etiquetas 'Usuario:'/'Asistente:' para evitar loops.
        """
        system_parts = []
        last_user = ""

        for m in messages:
            role = (m.get("role") or "").strip()
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                last_user = content  # nos quedamos con el último user

        system_block = "\n\n".join(system_parts).strip()

        prompt = (
            "INSTRUCCIONES Y CONTEXTO (úsalos como fuente):\n"
            f"{system_block}\n\n"
            "PREGUNTA:\n"
            f"{last_user}\n\n"
            "RESPUESTA (solo la respuesta, sin 'Usuario:' ni 'Asistente:', sin preguntas adicionales):\n"
        )
        return prompt

    def _payload(self, prompt: str, stream: bool) -> dict:
        return {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": stream,
            "raw": True,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                "temperature": self.temperature,
                "stop": self.stop,
            },
        }

    def _generate(self, prompt: str) -> str:
        payload = self._payload(prompt, stream=False)
        r = requests.post(self.ollama_url, json=payload, timeout=(10, None))
        if not r.ok:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text}")
        return (r.json().get("response") or "").strip()

    def _generate_stream(self, prompt: str):
        payload = self._payload(prompt, stream=True)
        r = requests.post(self.ollama_url, json=payload,
                          stream=True, timeout=(10, None))
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
