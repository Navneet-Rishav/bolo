"""Sarvam AI client: chat (language understanding), speech-to-text and text-to-speech.

Every call has a timeout and is retried with backoff on 429, 5xx and network errors; other 4xx fail fast.
"""

import base64
import time

import httpx

from app.ai.base import AiError, ChatResult, Transcript

BASE_URL = "https://api.sarvam.ai"


class SarvamProvider:
    name = "sarvam"
    is_demo = False
    voice_enabled = True

    def __init__(
        self,
        api_key: str,
        model: str = "sarvam-105b",
        tts_model: str = "bulbul:v4-flash",
        reasoning_effort: str | None = None,
        client: httpx.Client | None = None,
        max_retries: int = 2,
        sleep=time.sleep,
    ) -> None:
        self.model = model
        self.tts_model = tts_model
        self._reasoning = reasoning_effort
        self._http = client or httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(45.0, connect=10.0))
        self._headers = {"api-subscription-key": api_key}
        self._retries = max_retries
        self._sleep = sleep

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        last: AiError | None = None
        for attempt in range(self._retries + 1):
            if attempt:
                self._sleep(2.0 * attempt if last and last.status == 429 else 0.5 * 2**attempt)
            try:
                r = self._http.request(method, path, headers=self._headers, **kw)
            except httpx.TimeoutException:
                last = AiError(f"Sarvam {path} timed out", retryable=True)
                continue
            except httpx.TransportError as e:
                last = AiError(f"Network error calling Sarvam {path}: {type(e).__name__}", retryable=True)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last = AiError(f"Sarvam {path} returned HTTP {r.status_code}", retryable=True, status=r.status_code)
                continue
            if r.status_code >= 400:
                raise AiError(f"Sarvam {path} returned HTTP {r.status_code}: {r.text[:300]}", status=r.status_code)
            return r
        raise last or AiError(f"Sarvam {path} failed", retryable=True)

    def chat(self, task: str, system: str, user: str, schema: dict | None = None) -> ChatResult:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
            "max_tokens": 2048,  # reasoning tokens count toward this
        }
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": schema}
        if self._reasoning:
            body["reasoning_effort"] = self._reasoning
        t0 = time.perf_counter()
        j = self._request("POST", "/v1/chat/completions", json=body).json()
        text = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if not text:
            raise AiError("Sarvam returned an empty message", retryable=True)
        usage = j.get("usage") or {}
        return ChatResult(
            text=text,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            tokens=int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0)),
        )

    def transcribe(self, audio: bytes, filename: str, content_type: str) -> Transcript:
        j = self._request(
            "POST",
            "/speech-to-text",
            files={"file": (filename, audio, content_type)},
            data={"model": "saaras:v4", "mode": "codemix"},
        ).json()
        return Transcript(text=(j.get("transcript") or "").strip(), language=j.get("language_code"))

    def speak(self, text: str, language: str) -> bytes:
        j = self._request(
            "POST", "/text-to-speech", json={"text": text[:1500], "language_code": language, "model": self.tts_model}
        ).json()
        audios = j.get("audios") or []
        if not audios:
            raise AiError("Sarvam TTS returned no audio")
        return base64.b64decode(audios[0])
