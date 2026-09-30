"""Thin client for a local Ollama server (chat + embeddings).

No third-party SDK — just the documented HTTP API — so the only thing to
install is Ollama itself.
"""

from __future__ import annotations

import json
from typing import List, Tuple

import requests


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        chat_model: str = "qwen2.5:7b-instruct",
        embed_model: str = "nomic-embed-text",
        temperature: float = 0.0,
        timeout: int = 600,
    ):
        self.host = host.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.host}{path}"
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.host}. "
                f"Start it with `ollama serve` (or launch the Ollama app)."
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise OllamaError(f"Ollama request to {path} failed: {exc}\n{resp.text}") from exc

    def chat_json(self, system: str, user: str) -> dict:
        """Chat completion constrained to valid JSON (Ollama `format: json`)."""
        data = self._post(
            "/api/chat",
            {
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": self.temperature},
            },
        )
        content = data.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Model did not return valid JSON:\n{content}") from exc

    def embed(self, text: str) -> List[float]:
        data = self._post("/api/embeddings", {"model": self.embed_model, "prompt": text})
        vec = data.get("embedding")
        if not vec:
            raise OllamaError(f"Empty embedding returned for text of length {len(text)}.")
        return vec

    def health(self) -> Tuple[bool, List[str]]:
        """Return (reachable, list-of-installed-model-names)."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=15)
            resp.raise_for_status()
            return True, [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return False, []
