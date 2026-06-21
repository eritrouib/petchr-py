class PetchrError(Exception):
    """Base exception for petchr."""

    def __init__(self, message: str, status_code=None, response=None, attempt=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.attempt = attempt


class PetchrTimeoutError(PetchrError):
    """Raised when a request times out."""

    def __init__(self, timeout: float):
        super().__init__(f"Request timed out after {timeout}s")
        self.timeout = timeout


class PetchrRateLimitError(PetchrError):
    """Raised when client-side rate limit is exceeded."""

    def __init__(self, retry_after: float):
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.2f}s")
        self.retry_after = retry_after
        self.status_code = 429
