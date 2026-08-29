from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.exceptions import ProviderError


class HttpClient:
    """Thin HTTP helper with timeout and bounded retries. No silent fallbacks."""

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)
        self._backoff = backoff_seconds
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return self._request(lambda: self._client.get(url, params=params))

    def _request(self, call: Callable[[], httpx.Response]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = call()
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    raise ProviderError("Provider returned non-JSON payload") from exc
            except (httpx.HTTPError, ProviderError) as exc:
                last_error = exc
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(self._backoff * (2**attempt))
        raise ProviderError(f"HTTP request failed after {self._max_retries} attempts") from last_error
