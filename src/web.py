"""Polite HTTP access: one session, identifying User-Agent, throttling, retries."""

from __future__ import annotations

import time

import requests

from src.config import USER_AGENT


class PoliteSession:
    """Thin wrapper around requests.Session that respects API rate limits.

    Every request waits at least `min_interval_s` after the previous one.
    HTTP 429 and 5xx responses are retried with exponential backoff
    (or the server's Retry-After header, if present).
    """

    def __init__(self, min_interval_s: float = 0.5, max_retries: int = 5,
                 timeout_s: float = 30.0) -> None:
        """Create the session.

        Args:
            min_interval_s: Minimum pause between two requests (seconds).
            max_retries: Retries for 429/5xx responses and connection errors.
            timeout_s: Timeout per request (seconds).
        """
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._last_request = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self.n_requests = 0

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        """GET a URL with throttling and retries.

        Args:
            url: Absolute URL.
            params: Query parameters.

        Returns:
            Successful response (status 2xx).

        Raises:
            requests.HTTPError: If the request still fails after all retries.
        """
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval_s - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            self.n_requests += 1
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout_s)
            except requests.ConnectionError:
                if attempt == self.max_retries:
                    raise
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == self.max_retries:
                    resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2 ** (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")
