"""HTTP client for the VITALA RAG service (rag/, a separate local process).

The backend never imports the RAG code: it runs in its own Python 3.12
environment with the embedding model and indexes. Any failure to reach it
becomes RagUnavailable, which the API reports as 503 instead of an answer.
Request bodies are never logged.
"""

from typing import Any

import httpx


class RagUnavailable(RuntimeError):
    """The RAG service is not running, timed out, or returned an error."""


class RagClient:
    def __init__(self, base_url: str, timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise RagUnavailable(f"RAG service unreachable ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise RagUnavailable(f"RAG service returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise RagUnavailable("RAG service returned invalid JSON") from None

    def health(self) -> dict:
        return self._call("GET", "/health")

    def chat(self, question: str, patient_context: dict | None = None) -> dict:
        body: dict[str, Any] = {"question": question}
        if patient_context is not None:
            body["patient_context"] = patient_context
        return self._call("POST", "/v1/chat", json=body)
