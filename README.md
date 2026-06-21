# petchr

A zero-dependency HTTP client for Python with retry, timeout, and rate-limiting built in.

```bash
pip install petchr
```

> **Requires Python 3.9+**

---

## Why petchr?

`requests` is great but has no built-in retry or rate-limiting. `httpx` is modern but requires extra packages for resilience. `petchr` wraps Python's built-in `urllib` with everything you need — zero dependencies.

| Feature | urllib | requests | **petchr** |
|---|---|---|---|
| Zero dependencies | ✅ | ❌ | ✅ |
| Auto-retry w/ backoff | ❌ | ❌ | ✅ |
| Timeout | ✅ | ✅ | ✅ |
| Rate limiting | ❌ | ❌ | ✅ |
| JSON body shorthand | ❌ | ✅ | ✅ |
| Query params object | ❌ | ✅ | ✅ |
| Shared instance config | ❌ | ✅ | ✅ |

---

## Quick Start

```python
from petchr import petch

resp = petch("https://api.example.com/users/1")
print(resp.data)  # parsed JSON
```

---

## Instance API

```python
from petchr import Petchr

api = Petchr(
    base_url="https://api.example.com",
    headers={"Authorization": f"Bearer {token}"},
    timeout=10.0,
    retry=3,
)

user = api.get("/users/1")
post = api.post("/posts", json={"title": "Hello"})
api.delete("/posts/123")
```

---

## Retry

```python
resp = petch("https://api.example.com/data",
    retry=5,
    retry_delay=1.0,       # initial delay in seconds
    retry_backoff=2.0,     # exponential multiplier
    retry_max_delay=30.0,  # cap
    retry_on={429, 503},   # status codes to retry
    on_retry=lambda attempt, err, resp: print(f"Retry {attempt}"),
)
```

---

## Timeout

```python
from petchr import PetchrTimeoutError

try:
    resp = petch("https://slow-api.example.com", timeout=5.0)
except PetchrTimeoutError as e:
    print(f"Timed out after {e.timeout}s")
```

---

## Rate Limiting

```python
from petchr import Petchr, RateLimiter

api = Petchr(
    base_url="https://api.example.com",
    rate_limiter=RateLimiter(max_requests=10, window_seconds=1.0),
)
```

---

## Error Handling

```python
from petchr import petch, PetchrError, PetchrTimeoutError, PetchrRateLimitError

try:
    resp = petch("https://api.example.com/users/1")
except PetchrTimeoutError as e:
    print(f"Timed out after {e.timeout}s")
except PetchrRateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except PetchrError as e:
    print(f"HTTP {e.status_code}: {e}")
```

---

## License

MIT
