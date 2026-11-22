"""Thin client for the Gemini REST API, called only from the backend (NFR-11).

Only the minimum data is sent: asset names, descriptions, specifications and
categories. No user names, emails or financial figures go out (NFR-12).
"""
from __future__ import annotations

from typing import Optional

import json
import time

import httpx

from ..config import settings

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class AIServiceUnavailable(RuntimeError):
    """The external AI service is not configured, failed, timed out or returned bad output."""


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 embedding_model: Optional[str] = None, timeout: Optional[float] = None):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.embedding_model = embedding_model or settings.gemini_embedding_model
        self.timeout = timeout or settings.ai_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    RETRYABLE = {429, 500, 502, 503, 504}  # busy or temporary errors worth one more try

    def _post(self, path: str, payload: dict) -> dict:
        """POST with quick retries on 'busy' errors, all inside one overall time budget.

        The whole call, retries included, never takes longer than `timeout`
        seconds (10 s by default, FR-AI-9). After that the caller falls back
        to the local rules.
        """
        if not self.configured:
            raise AIServiceUnavailable("No AI service key is configured on the server.")
        model = path.split(":")[0].removeprefix("models/")
        deadline = time.monotonic() + self.timeout
        last_status = None
        attempt = 0
        while True:
            attempt += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                if last_status is not None:
                    raise AIServiceUnavailable(f"{model} returned HTTP {last_status} after {attempt - 1} tries.")
                raise AIServiceUnavailable(f"{model} timed out after {self.timeout:.0f} s.")
            try:
                resp = httpx.post(f"{BASE_URL}/{path}", json=payload, timeout=remaining,
                                  headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
            except httpx.TimeoutException as exc:
                raise AIServiceUnavailable(f"{model} timed out after {self.timeout:.0f} s.") from exc
            except httpx.HTTPError as exc:
                raise AIServiceUnavailable(f"AI service could not be reached ({exc.__class__.__name__}).") from exc
            if resp.status_code == 200:
                return resp.json()
            last_status = resp.status_code
            if resp.status_code not in self.RETRYABLE or attempt >= 3:
                raise AIServiceUnavailable(f"{model} returned HTTP {resp.status_code}.")
            time.sleep(min(0.8 * attempt, max(0.0, deadline - time.monotonic() - 0.5)))

    def generate_json(self, prompt: str) -> dict:
        data = self._post(f"models/{self.model}:generateContent", {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        })
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            raise AIServiceUnavailable("AI service returned an unreadable answer.") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = f"models/{self.embedding_model}"
        data = self._post(f"{model}:batchEmbedContents", {
            "requests": [{"model": model, "content": {"parts": [{"text": t[:2000]}]}} for t in texts],
        })
        try:
            vectors = [e["values"] for e in data["embeddings"]]
        except (KeyError, TypeError) as exc:
            raise AIServiceUnavailable("AI service returned unreadable embeddings.") from exc
        if len(vectors) != len(texts):
            raise AIServiceUnavailable("AI service returned the wrong number of embeddings.")
        return vectors
