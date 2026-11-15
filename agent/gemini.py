"""Minimal Gemini generateContent client (standard library only).

Sends a document (PDF or image) plus instructions and gets back JSON that matches a response schema.
Retries transient errors (429 / 5xx / timeouts) and can fall back to a second model.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import load_env

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
TRANSIENT = {429, 500, 502, 503, 504}


class GeminiError(RuntimeError):
    pass


@dataclass
class GeminiResult:
    data: dict
    model: str
    seconds: float
    input_tokens: int
    output_tokens: int
    attempts: int


class Gemini:
    def __init__(self, api_key: str, models: list[str], timeout: float = 90, tries_per_model: int = 2):
        if not api_key:
            raise GeminiError("GEMINI_API_KEY is empty; add it to .env")
        self.api_key = api_key
        self.models = models
        self.timeout = timeout
        self.tries_per_model = tries_per_model

    @classmethod
    def from_env(cls, models: list[str] | None = None) -> "Gemini":
        env = load_env()
        return cls(env.get("GEMINI_API_KEY", ""), models or ["gemini-flash-latest", "gemini-flash-lite-latest"])

    def _post(self, model: str, body: dict) -> dict:
        req = urllib.request.Request(
            API.format(model=model),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def extract(self, file: Path, instructions: str, schema: dict, temperature: float = 0.0) -> GeminiResult:
        mime = MIME.get(file.suffix.lower())
        if not mime:
            raise GeminiError(f"unsupported file type: {file.suffix}")
        body = {
            "systemInstruction": {"parts": [{"text": instructions}]},
            "contents": [{
                "role": "user",
                "parts": [
                    {"inlineData": {"mimeType": mime, "data": base64.b64encode(file.read_bytes()).decode()}},
                    {"text": "Extract this invoice."},
                ],
            }],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        attempts, last_error = 0, ""
        for model in self.models:
            for i in range(self.tries_per_model):
                attempts += 1
                start = time.perf_counter()
                try:
                    resp = self._post(model, body)
                except urllib.error.HTTPError as e:
                    last_error = f"{model}: HTTP {e.code} {e.read().decode(errors='replace')[:200]}"
                    if e.code not in TRANSIENT:
                        raise GeminiError(last_error) from None
                    time.sleep(2 * (i + 1))
                    continue
                except (urllib.error.URLError, TimeoutError) as e:
                    last_error = f"{model}: {type(e).__name__} {e}"
                    time.sleep(2 * (i + 1))
                    continue
                seconds = time.perf_counter() - start
                try:
                    text = resp["candidates"][0]["content"]["parts"][0]["text"]
                    data = json.loads(text)
                except (KeyError, IndexError, json.JSONDecodeError) as e:
                    last_error = f"{model}: unusable response ({type(e).__name__})"
                    continue
                usage = resp.get("usageMetadata", {})
                return GeminiResult(
                    data=data,
                    model=resp.get("modelVersion", model),
                    seconds=round(seconds, 2),
                    input_tokens=usage.get("promptTokenCount", 0),
                    output_tokens=usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0),
                    attempts=attempts,
                )
        raise GeminiError(f"all models failed after {attempts} attempts; last error: {last_error}")
