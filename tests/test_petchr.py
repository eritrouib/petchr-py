import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from petchr import Petchr, PetchrError, PetchrTimeoutError, RateLimiter, petch


def make_response(body, status=200, content_type="application/json"):
    resp = MagicMock()
    resp.status = status
    resp.url = "https://example.com/api"
    resp.read.return_value = json.dumps(body).encode() if isinstance(body, dict) else body.encode()
    resp.headers.get_content_type.return_value = content_type
    resp.headers.get_content_charset.return_value = "utf-8"
    resp.headers.__iter__ = MagicMock(return_value=iter([]))
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestPetch:
    @patch("urllib.request.urlopen")
    def test_basic_get(self, mock_urlopen):
        mock_urlopen.return_value = make_response({"hello": "world"})
        resp = petch("https://example.com/api", retry=0)
        assert resp.data == {"hello": "world"}
        assert resp.status_code == 200

    @patch("urllib.request.urlopen")
    def test_json_body_sets_content_type(self, mock_urlopen):
        mock_urlopen.return_value = make_response({"ok": True})
        petch("https://example.com/api", method="POST", json={"name": "test"}, retry=0)
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Content-type") == "application/json"
        assert json.loads(req.data) == {"name": "test"}

    @patch("urllib.request.urlopen")
    def test_params_appended_to_url(self, mock_urlopen):
        mock_urlopen.return_value = make_response({})
        petch("https://example.com/api", params={"page": 1, "q": "hello", "empty": None}, retry=0)
        url = mock_urlopen.call_args[0][0].full_url
        assert "page=1" in url
        assert "q=hello" in url
        assert "empty" not in url

    @patch("urllib.request.urlopen")
    def test_base_url(self, mock_urlopen):
        mock_urlopen.return_value = make_response({})
        petch("/users", base_url="https://api.example.com", retry=0)
        url = mock_urlopen.call_args[0][0].full_url
        assert url.startswith("https://api.example.com/users")

    @patch("urllib.request.urlopen")
    def test_text_response(self, mock_urlopen):
        resp = make_response("hello plain", content_type="text/plain")
        mock_urlopen.return_value = resp
        result = petch("https://example.com/text", retry=0)
        assert result.data == "hello plain"

    @patch("urllib.request.urlopen")
    def test_raises_on_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com", code=404, msg="Not Found", hdrs=None, fp=None
        )
        with pytest.raises(PetchrError) as exc:
            petch("https://example.com/api", retry=0)
        assert exc.value.status_code == 404


class TestRetry:
    @patch("petchr.client.time.sleep")
    @patch("urllib.request.urlopen")
    def test_retries_on_503(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [
            urllib.error.HTTPError(url="", code=503, msg="", hdrs=None, fp=None),
            urllib.error.HTTPError(url="", code=503, msg="", hdrs=None, fp=None),
            make_response({"ok": True}),
        ]
        resp = petch("https://example.com/api", retry=3, retry_delay=0.01)
        assert resp.data == {"ok": True}
        assert mock_urlopen.call_count == 3

    @patch("petchr.client.time.sleep")
    @patch("urllib.request.urlopen")
    def test_raises_after_exhausting_retries(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=503, msg="", hdrs=None, fp=None
        )
        with pytest.raises(PetchrError):
            petch("https://example.com/api", retry=2, retry_delay=0.01)
        assert mock_urlopen.call_count == 3

    @patch("petchr.client.time.sleep")
    @patch("urllib.request.urlopen")
    def test_on_retry_called(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [
            urllib.error.HTTPError(url="", code=503, msg="", hdrs=None, fp=None),
            make_response({"ok": True}),
        ]
        on_retry = MagicMock()
        petch("https://example.com/api", retry=2, retry_delay=0.01, on_retry=on_retry)
        assert on_retry.call_count == 1

    @patch("urllib.request.urlopen")
    def test_no_retry_on_404(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=404, msg="", hdrs=None, fp=None
        )
        with pytest.raises(PetchrError) as exc:
            petch("https://example.com/api", retry=3)
        assert mock_urlopen.call_count == 1
        assert exc.value.status_code == 404


class TestTimeout:
    @patch("urllib.request.urlopen")
    def test_raises_timeout_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        with pytest.raises(PetchrTimeoutError):
            petch("https://example.com/api", timeout=1, retry=0)


class TestPetchrClient:
    @patch("urllib.request.urlopen")
    def test_instance_with_defaults(self, mock_urlopen):
        mock_urlopen.return_value = make_response({"id": 1})
        api = Petchr(
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer token"},
            retry=0,
        )
        api.get("/users/1")
        req = mock_urlopen.call_args[0][0]
        assert "api.example.com/users/1" in req.full_url
        assert req.get_header("Authorization") == "Bearer token"

    @patch("urllib.request.urlopen")
    def test_merges_headers(self, mock_urlopen):
        mock_urlopen.return_value = make_response({})
        api = Petchr(headers={"Authorization": "Bearer token"}, retry=0)
        api.get("https://example.com/api", headers={"X-Custom": "yes"})
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer token"
        assert req.get_header("X-custom") == "yes"

    @patch("urllib.request.urlopen")
    def test_convenience_methods(self, mock_urlopen):
        for method in ["get", "post", "put", "patch", "delete"]:
            mock_urlopen.return_value = make_response({})
            api = Petchr(retry=0)
            getattr(api, method)("https://example.com/api")
            req = mock_urlopen.call_args[0][0]
            assert req.method == method.upper()


class TestRateLimiter:
    def test_allows_requests_within_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)
        for _ in range(5):
            limiter.throttle()

    def test_raises_when_limit_exceeded(self):
        from petchr import PetchrRateLimitError
        limiter = RateLimiter(max_requests=2, window_seconds=1.0)
        limiter.throttle()
        limiter.throttle()
        with pytest.raises(PetchrRateLimitError):
            limiter.throttle()
