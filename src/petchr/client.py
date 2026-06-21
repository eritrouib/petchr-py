from __future__ import annotations

import json as _json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .exceptions import PetchrError, PetchrTimeoutError
from .rate_limiter import RateLimiter

DEFAULT_RETRY_ON = {429, 502, 503, 504}


def _backoff(attempt: int, delay: float, backoff: float, max_delay: float) -> float:
    raw = delay * (backoff ** (attempt - 1))
    jitter = raw * 0.2 * (random.random() * 2 - 1)
    return min(raw + jitter, max_delay)


def petch(
    url: str,
    *,
    method: str = "GET",
    base_url: str | None = None,
    params: dict[str, Any] | None = None,
    json: Any = None,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    # Retry
    retry: int = 3,
    retry_delay: float = 0.5,
    retry_backoff: float = 2.0,
    retry_max_delay: float = 10.0,
    retry_on: set[int] | None = None,
    should_retry: Callable[[int, int], bool] | None = None,
    # Rate limiting
    rate_limiter: RateLimiter | None = None,
    # Hooks
    on_request: Callable[[str, dict], None] | None = None,
    on_response: Callable[[urllib.request.Request, Any], None] | None = None,
    on_retry: Callable[[int, Exception | None, Any], None] | None = None,
) -> "PetchrResponse":
    """Make an HTTP request with retry, timeout, and rate-limiting."""

    if rate_limiter:
        rate_limiter.wait()

    # Build URL
    if base_url:
        url = urllib.parse.urljoin(base_url, url)
    if params:
        filtered = {k: str(v) for k, v in params.items() if v is not None}
        url = f"{url}?{urllib.parse.urlencode(filtered)}"

    # Build headers
    req_headers = headers.copy() if headers else {}
    body = data

    if json is not None:
        body = _json.dumps(json).encode()
        req_headers.setdefault("Content-Type", "application/json")

    _retry_on = retry_on if retry_on is not None else DEFAULT_RETRY_ON
    max_attempts = retry + 1

    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        if on_request:
            on_request(url, {"method": method, "headers": req_headers})

        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                content_type = resp.headers.get_content_type()

                if "json" in content_type:
                    response_data = _json.loads(raw)
                else:
                    response_data = raw.decode(resp.headers.get_content_charset("utf-8"))

                result = PetchrResponse(
                    data=response_data,
                    status_code=resp.status,
                    headers=dict(resp.headers),
                    url=resp.url,
                )

                if on_response:
                    on_response(req, result)

                return result

        except urllib.error.HTTPError as e:
            status = e.code

            if status in _retry_on and attempt < max_attempts:
                do_retry = should_retry(status, attempt) if should_retry else True
                if do_retry:
                    last_error = PetchrError(
                        f"Request failed with status {status}",
                        status_code=status,
                        attempt=attempt,
                    )
                    if on_retry:
                        on_retry(attempt, last_error, None)
                    time.sleep(_backoff(attempt, retry_delay, retry_backoff, retry_max_delay))
                    continue

            raise PetchrError(
                f"Request failed with status {status}",
                status_code=status,
                attempt=attempt,
            ) from e

        except TimeoutError as e:
            raise PetchrTimeoutError(timeout) from e

        except urllib.error.URLError as e:
            if "timed out" in str(e.reason).lower():
                raise PetchrTimeoutError(timeout) from e

            if attempt < max_attempts:
                last_error = PetchrError(str(e), attempt=attempt)
                if on_retry:
                    on_retry(attempt, last_error, None)
                time.sleep(_backoff(attempt, retry_delay, retry_backoff, retry_max_delay))
                continue

            raise PetchrError(str(e), attempt=attempt) from e

    raise last_error or PetchrError("Request failed after all retry attempts")


class PetchrResponse:
    """Parsed HTTP response."""

    def __init__(self, data: Any, status_code: int, headers: dict, url: str):
        self.data = data
        self.status_code = status_code
        self.headers = headers
        self.url = url

    def __repr__(self):
        return f"<PetchrResponse [{self.status_code}]>"


class Petchr:
    """
    A configured petchr client instance.

    Example:
        api = Petchr(base_url="https://api.example.com", headers={"Authorization": "Bearer token"})
        response = api.get("/users/1")
    """

    def __init__(
        self,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        retry: int = 3,
        retry_delay: float = 0.5,
        retry_backoff: float = 2.0,
        retry_max_delay: float = 10.0,
        retry_on: set[int] | None = None,
        rate_limiter: RateLimiter | None = None,
        on_request: Callable | None = None,
        on_response: Callable | None = None,
        on_retry: Callable | None = None,
    ):
        self.base_url = base_url
        self.headers = headers or {}
        self.timeout = timeout
        self.retry = retry
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        self.retry_max_delay = retry_max_delay
        self.retry_on = retry_on
        self.rate_limiter = rate_limiter
        self.on_request = on_request
        self.on_response = on_response
        self.on_retry = on_retry

    def request(self, method: str, url: str, **kwargs) -> PetchrResponse:
        merged_headers = {**self.headers, **kwargs.pop("headers", {})}
        return petch(
            url,
            method=method,
            base_url=kwargs.pop("base_url", self.base_url),
            headers=merged_headers,
            timeout=kwargs.pop("timeout", self.timeout),
            retry=kwargs.pop("retry", self.retry),
            retry_delay=kwargs.pop("retry_delay", self.retry_delay),
            retry_backoff=kwargs.pop("retry_backoff", self.retry_backoff),
            retry_max_delay=kwargs.pop("retry_max_delay", self.retry_max_delay),
            retry_on=kwargs.pop("retry_on", self.retry_on),
            rate_limiter=kwargs.pop("rate_limiter", self.rate_limiter),
            on_request=kwargs.pop("on_request", self.on_request),
            on_response=kwargs.pop("on_response", self.on_response),
            on_retry=kwargs.pop("on_retry", self.on_retry),
            **kwargs,
        )

    def get(self, url: str, **kwargs) -> PetchrResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> PetchrResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> PetchrResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs) -> PetchrResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs) -> PetchrResponse:
        return self.request("DELETE", url, **kwargs)
