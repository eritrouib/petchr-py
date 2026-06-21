import time
from .exceptions import PetchrRateLimitError


class RateLimiter:
    """Sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float = 1.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: list[float] = []

    def _clean(self):
        now = time.monotonic()
        self._requests = [t for t in self._requests if now - t < self.window_seconds]

    def throttle(self):
        """Raise PetchrRateLimitError if rate limit exceeded."""
        self._clean()
        if len(self._requests) >= self.max_requests:
            oldest = self._requests[0]
            retry_after = self.window_seconds - (time.monotonic() - oldest)
            raise PetchrRateLimitError(retry_after)
        self._requests.append(time.monotonic())

    def wait(self):
        """Block until a request slot is available."""
        while True:
            self._clean()
            if len(self._requests) < self.max_requests:
                self._requests.append(time.monotonic())
                return
            oldest = self._requests[0]
            wait_time = self.window_seconds - (time.monotonic() - oldest)
            if wait_time > 0:
                time.sleep(wait_time)
