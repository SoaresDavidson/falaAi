"""Cliente Ollama que implementa a porta Llm."""

import json

import httpx


class OllamaLlm:
    def __init__(self, url: str, modelo: str, num_ctx: int = 16384, timeout_s: float = 1800):
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.num_ctx = num_ctx
        self.timeout_s = timeout_s

    def json(self, sistema: str, usuario: str, schema: dict) -> dict:
        corpo = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "format": schema,
            "stream": False,
            "keep_alive": "5m",
            "options": {"num_ctx": self.num_ctx, "temperature": 0.7},
        }
        resposta = httpx.post(f"{self.url}/api/chat", json=corpo, timeout=self.timeout_s)
        resposta.raise_for_status()
        return json.loads(resposta.json()["message"]["content"])

    def descarregar(self) -> None:
        resposta = httpx.post(
            f"{self.url}/api/generate",
            json={"model": self.modelo, "keep_alive": 0},
            timeout=self.timeout_s,
        )
        resposta.raise_for_status()
