"""Audit coverage for external boundaries, exercised with deterministic stubs.

Every collaborator that would leave the process (``httpx``, ``trafilatura``, the
geopy ``Nominatim`` client, ``asyncio.sleep`` and ``time.sleep``) is replaced by
a fake, so no test here performs a network, provider, feed or geocoder call.

The assertions document the behaviour established by reading the current
implementation bodies; where that behaviour is surprising the test says so.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import sys
from typing import Any

import httpx
import pytest
import trafilatura
from geopy.exc import GeocoderServiceError, GeocoderTimedOut

from src.ai import baseline_workflow as bw
from src.ai import utils as ai_utils
from src.ingester.newsapi import NewsAPIClient
from src.ingester.url_capture import fetch_article_content


# --------------------------------------------------------------------------- #
# NewsAPI adapter (src/ingester/newsapi.py)
# --------------------------------------------------------------------------- #


class _FakeNewsAPIResponse:
    """Stand-in for ``httpx.Response`` used by the NewsAPI adapter."""

    def __init__(
        self,
        payload: Any = None,
        *,
        status_code: int = 200,
        json_error: BaseException | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://newsapi.org/v2/everything")
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )

    def json(self) -> Any:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class _FakeNewsAPIHttpClient:
    """Stand-in for ``httpx.Client``; records every request and never dials out."""

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout
        self.response: Any = _FakeNewsAPIResponse({})
        self.get_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.closed = False

    def get(
        self, url: str, params: dict[str, Any] | None = None
    ) -> _FakeNewsAPIResponse:
        self.get_calls.append((url, params))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def newsapi(monkeypatch: pytest.MonkeyPatch):
    """Build a NewsAPIClient whose transport is a deterministic fake."""
    monkeypatch.setattr(httpx, "Client", _FakeNewsAPIHttpClient)

    def build(
        payload: Any = None,
        *,
        status_code: int = 200,
        json_error: BaseException | None = None,
        api_key: str | None = "test-key",
        base_url: str = "https://newsapi.org/v2",
    ) -> tuple[NewsAPIClient, _FakeNewsAPIHttpClient]:
        client = NewsAPIClient(api_key=api_key, base_url=base_url)
        fake = client.client
        assert isinstance(fake, _FakeNewsAPIHttpClient)
        fake.response = _FakeNewsAPIResponse(
            payload, status_code=status_code, json_error=json_error
        )
        return client, fake

    return build


def test_newsapi_without_key_returns_empty_before_any_request(
    newsapi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing key is a safe empty result, not an exception and not a request."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    client, fake = newsapi(api_key=None)

    assert client.api_key is None
    assert client.fetch_everything(query="anything") == []
    assert fake.get_calls == []


def test_newsapi_success_maps_articles_and_request_params(newsapi) -> None:
    payload = {
        "status": "ok",
        "articles": [
            {
                "title": "Headline",
                "url": "https://publisher.example/story",
                "content": "Full body",
                "description": "Short description",
                "publishedAt": "2026-01-02T03:04:05Z",
                "author": "Reporter",
                "source": {"name": "Publisher"},
                # A non-API field must not leak into the mapped article.
                "unexpected": "ignored",
            },
            {
                "title": "Description only",
                "url": "https://publisher.example/second",
                "description": "Fallback body",
                "source": {"name": "Second"},
            },
        ],
    }
    client, fake = newsapi(payload)

    articles = client.fetch_everything(
        query="climate", sources="bbc", language="fr", page_size=5
    )

    assert fake.get_calls == [
        (
            "https://newsapi.org/v2/everything",
            {
                "apiKey": "test-key",
                "language": "fr",
                "pageSize": 5,
                "q": "climate",
                "sources": "bbc",
            },
        )
    ]
    assert len(articles) == 2
    first = articles[0]
    assert first["title"] == "Headline"
    assert first["link"] == "https://publisher.example/story"
    assert first["content"] == "Full body"
    assert first["author"] == "Reporter"
    assert first["source_name"] == "Publisher"
    assert first["source_type"] == "api"
    assert first["source_url"] == "newsapi"
    assert first["timestamp"] == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    # Missing content falls back to description; missing date becomes "now".
    second = articles[1]
    assert second["content"] == "Fallback body"
    assert second["author"] == ""
    assert second["timestamp"].tzinfo is not None


def test_newsapi_optional_query_params_are_omitted_when_not_supplied(newsapi) -> None:
    client, fake = newsapi({"status": "ok", "articles": []})

    assert client.fetch_everything() == []
    _, params = fake.get_calls[0]
    assert params == {"apiKey": "test-key", "language": "en", "pageSize": 50}


def test_newsapi_custom_base_url_is_used(newsapi) -> None:
    client, fake = newsapi({"status": "ok", "articles": []}, base_url="https://n.test/v9")

    client.fetch_everything(query="x")

    assert fake.get_calls[0][0] == "https://n.test/v9/everything"


def test_newsapi_error_status_payload_returns_empty_list(newsapi) -> None:
    client, _ = newsapi({"status": "error", "message": "apiKeyInvalid"})

    assert client.fetch_everything() == []


def test_newsapi_http_failures_return_empty_list(newsapi) -> None:
    client, fake = newsapi({"status": "ok", "articles": []}, status_code=500)

    assert client.fetch_everything() == []
    assert len(fake.get_calls) == 1


def test_newsapi_timeout_returns_empty_list(newsapi) -> None:
    client, fake = newsapi()
    fake.response = httpx.TimeoutException("timed out")

    assert client.fetch_everything() == []


def test_newsapi_malformed_payloads_return_empty_list(newsapi) -> None:
    # A non-mapping top-level payload fails on ``data.get`` and is swallowed.
    client, _ = newsapi(["not", "a", "mapping"])
    assert client.fetch_everything() == []

    # Undecodable JSON is also swallowed.
    client, _ = newsapi(json_error=ValueError("invalid json"))
    assert client.fetch_everything() == []

    # A missing "articles" key is an empty (not failing) result.
    client, _ = newsapi({"status": "ok"})
    assert client.fetch_everything() == []


def test_newsapi_malformed_articles_are_omitted_not_fabricated(newsapi) -> None:
    payload = {
        "status": "ok",
        "articles": [
            {"title": "Valid", "url": "https://ok.example/1"},
            None,
            "not-an-article",
            {"title": "Null source", "source": None},
        ],
    }
    client, _ = newsapi(payload)

    articles = client.fetch_everything()

    assert [article["title"] for article in articles] == ["Valid"]
    assert articles[0]["content"] == ""


def test_newsapi_close_delegates_to_http_client(newsapi) -> None:
    client, fake = newsapi({"status": "ok", "articles": []})

    client.close()

    assert fake.closed is True


# --------------------------------------------------------------------------- #
# URL capture adapter (src/ingester/url_capture.py)
# --------------------------------------------------------------------------- #

_ARTICLE_HTML = (
    "<html><head><title>Document Title</title></head><body>"
    "<article><p>" + ("Long sentence. " * 30) + "</p></article>"
    "</body></html>"
)

_MINIMAL_HTML = "<html><body><h1>Heading</h1><p>short body</p></body></html>"


class _FakeMetadata:
    """Stand-in for the ``Document`` returned by ``trafilatura.extract_metadata``."""

    def __init__(self, title: str | None = None) -> None:
        self.title = title


class _FakeAsyncResponse:
    def __init__(self, text: str = "", *, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.invalid/article")
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )


class _FakeAsyncClient:
    """Async context manager standing in for ``httpx.AsyncClient``."""

    def __init__(
        self,
        response: Any,
        calls: dict[str, list[Any]],
        **kwargs: Any,
    ) -> None:
        calls["client_kwargs"].append(kwargs)
        self._response = response
        self._calls = calls

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False

    async def get(self, url: str) -> Any:
        self._calls["urls"].append(url)
        if isinstance(self._response, BaseException):
            raise self._response
        return self._response


def _install_async_client(
    monkeypatch: pytest.MonkeyPatch, response: Any
) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"client_kwargs": [], "urls": []}

    def factory(**kwargs: Any) -> _FakeAsyncClient:
        return _FakeAsyncClient(response, calls, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return calls


def _forbid_async_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(**kwargs: Any) -> Any:
        raise AssertionError("fallback HTTP client must not be constructed")

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_url_capture_primary_trafilatura_success_maps_title_and_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: _ARTICLE_HTML)
    monkeypatch.setattr(trafilatura, "extract", lambda downloaded, **kwargs: "C" * 250)
    metadata_calls: list[tuple[str, str | None]] = []

    def _fake_extract_metadata(
        downloaded: str, default_url: str | None = None, **kwargs: Any
    ) -> Any:
        metadata_calls.append((downloaded, default_url))
        return _FakeMetadata("Metadata Title")

    monkeypatch.setattr(trafilatura, "extract_metadata", _fake_extract_metadata)
    _forbid_async_client(monkeypatch)

    result = asyncio.run(fetch_article_content("https://www.example.com/story"))

    # The supported parser is consulted once with the configured default URL.
    assert metadata_calls == [(_ARTICLE_HTML, "https://www.example.com/story")]
    assert result["title"] == "Metadata Title"
    assert result["content"] == "C" * 250
    assert result["link"] == "https://www.example.com/story"
    assert result["url"] == "https://www.example.com/story"
    assert result["author"] == ""
    assert result["source_name"] == "example.com"
    assert result["source_url"] == "https://www.example.com"
    assert result["source_type"] == "manual"
    assert isinstance(datetime.fromisoformat(result["timestamp"]), datetime)


@pytest.mark.parametrize(
    "metadata",
    [None, _FakeMetadata()],
    ids=["no-document", "untitled-document"],
)
def test_url_capture_primary_success_uses_placeholder_title_without_metadata(
    monkeypatch: pytest.MonkeyPatch, metadata: _FakeMetadata | None
) -> None:
    """Without a published title the adapter states the placeholder, not a guess."""
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: _ARTICLE_HTML)
    monkeypatch.setattr(trafilatura, "extract", lambda downloaded, **kwargs: "C" * 250)
    monkeypatch.setattr(trafilatura, "extract_metadata", lambda *a, **k: metadata)
    _forbid_async_client(monkeypatch)

    result = asyncio.run(fetch_article_content("https://example.com/story"))

    assert result["title"] == "Untitled Article"
    assert result["content"] == "C" * 250


def test_url_capture_metadata_failure_does_not_fabricate_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: _ARTICLE_HTML)
    monkeypatch.setattr(trafilatura, "extract", lambda downloaded, **kwargs: "C" * 250)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("metadata extraction failed")

    monkeypatch.setattr(trafilatura, "extract_metadata", _boom)
    _forbid_async_client(monkeypatch)

    result = asyncio.run(fetch_article_content("https://example.com/story"))

    assert result["title"] == "Untitled Article"
    assert result["content"] == "C" * 250


@pytest.mark.parametrize("extracted", [None, "", "too short"])
def test_url_capture_short_or_empty_extraction_falls_back_to_beautifulsoup(
    monkeypatch: pytest.MonkeyPatch, extracted: str | None
) -> None:
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: _ARTICLE_HTML)
    monkeypatch.setattr(
        trafilatura, "extract", lambda downloaded, **kwargs: extracted
    )
    calls = _install_async_client(
        monkeypatch, _FakeAsyncResponse(_ARTICLE_HTML)
    )

    result = asyncio.run(fetch_article_content("https://www.example.com/story"))

    assert calls["client_kwargs"] == [{"timeout": 30.0, "follow_redirects": True}]
    assert calls["urls"] == ["https://www.example.com/story"]
    assert result["title"] == "Document Title"
    assert result["content"].startswith("Long sentence.")
    assert len(result["content"]) > 200
    assert result["source_name"] == "example.com"


def test_url_capture_falls_back_when_trafilatura_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``None`` in sys.modules makes ``from trafilatura import ...`` raise
    # ImportError, which the adapter treats as "fall back to BeautifulSoup".
    monkeypatch.setitem(sys.modules, "trafilatura", None)
    calls = _install_async_client(monkeypatch, _FakeAsyncResponse(_ARTICLE_HTML))

    result = asyncio.run(fetch_article_content("https://example.com/story"))

    assert calls["urls"] == ["https://example.com/story"]
    assert result["title"] == "Document Title"
    assert result["source_type"] == "manual"


def test_url_capture_fallback_without_article_selectors_uses_paragraphs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: None)
    _install_async_client(monkeypatch, _FakeAsyncResponse(_MINIMAL_HTML))

    result = asyncio.run(fetch_article_content("https://example.com/story"))

    assert result["title"] == "Heading"
    assert result["content"] == "short body"


def test_url_capture_fallback_uses_placeholder_title_when_page_has_no_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: None)
    _install_async_client(
        monkeypatch, _FakeAsyncResponse("<html><body><p>body only</p></body></html>")
    )

    result = asyncio.run(fetch_article_content("https://example.com/story"))

    assert result["title"] == "Untitled Article"
    assert result["content"] == "body only"


def test_url_capture_fallback_fetch_error_propagates_to_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback path calls ``raise_for_status`` and does not swallow it."""
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: None)
    _install_async_client(
        monkeypatch, _FakeAsyncResponse("gone", status_code=404)
    )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(fetch_article_content("https://example.com/story"))


def test_url_capture_fallback_transport_error_propagates_to_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: None)
    _install_async_client(monkeypatch, httpx.ConnectError("connection refused"))

    with pytest.raises(httpx.ConnectError):
        asyncio.run(fetch_article_content("https://example.com/story"))


def test_url_capture_primary_fetch_failure_falls_back_to_beautifulsoup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A network failure in ``trafilatura.fetch_url`` degrades to the fallback.

    Only the primary attempt is caught; the fallback fetch is a separate,
    error-propagating path (see the transport-error tests below).
    """

    def _boom(url: str) -> str:
        raise OSError("network down")

    monkeypatch.setattr(trafilatura, "fetch_url", _boom)
    calls = _install_async_client(monkeypatch, _FakeAsyncResponse(_ARTICLE_HTML))

    result = asyncio.run(fetch_article_content("https://www.example.com/story"))

    assert calls["urls"] == ["https://www.example.com/story"]
    assert calls["client_kwargs"] == [{"timeout": 30.0, "follow_redirects": True}]
    assert result["title"] == "Document Title"
    assert result["content"].startswith("Long sentence.")
    assert result["source_type"] == "manual"


def test_url_capture_primary_extraction_failure_falls_back_to_beautifulsoup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception raised by ``trafilatura.extract`` also degrades to the fallback."""
    monkeypatch.setattr(trafilatura, "fetch_url", lambda url: _ARTICLE_HTML)

    def _boom(downloaded: str, **kwargs: Any) -> str:
        raise ValueError("parser exploded")

    monkeypatch.setattr(trafilatura, "extract", _boom)
    calls = _install_async_client(monkeypatch, _FakeAsyncResponse(_ARTICLE_HTML))

    result = asyncio.run(fetch_article_content("https://www.example.com/story"))

    assert calls["urls"] == ["https://www.example.com/story"]
    assert result["title"] == "Document Title"
    assert result["content"].startswith("Long sentence.")


def test_url_capture_primary_failure_does_not_mask_fallback_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catching the primary attempt must not swallow the fallback's own failure."""

    def _boom(url: str) -> str:
        raise OSError("network down")

    monkeypatch.setattr(trafilatura, "fetch_url", _boom)
    _install_async_client(monkeypatch, httpx.ConnectError("connection refused"))

    with pytest.raises(httpx.ConnectError):
        asyncio.run(fetch_article_content("https://example.com/story"))


# --------------------------------------------------------------------------- #
# Retry helper (src/ai/utils.py::call_with_retry)
# --------------------------------------------------------------------------- #


@pytest.fixture
def retry_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace ``asyncio.sleep`` so backoff is recorded, never waited."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ai_utils.asyncio, "sleep", _fake_sleep)
    return sleeps


def test_call_with_retry_transient_failure_then_success(retry_sleeps) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def flaky(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        if len(calls) < 2:
            raise RuntimeError("HTTP 500 server error")
        return "ok"

    result = asyncio.run(
        ai_utils.call_with_retry(
            flaky, "argument", keyword="value", max_retries=3, initial_delay=2.0
        )
    )

    assert result == "ok"
    assert len(calls) == 2
    assert calls[0] == (("argument",), {"keyword": "value"})
    assert retry_sleeps == [2.0]


def test_call_with_retry_non_retryable_fails_fast_without_sleep(retry_sleeps) -> None:
    calls: list[int] = []

    async def invalid_prompt() -> str:
        calls.append(1)
        raise ValueError("invalid prompt")

    with pytest.raises(ValueError, match="invalid prompt"):
        asyncio.run(
            ai_utils.call_with_retry(invalid_prompt, max_retries=3, initial_delay=1.0)
        )

    assert len(calls) == 1
    assert retry_sleeps == []


@pytest.mark.parametrize("message", ["HTTP 401 Unauthorized", "HTTP 403 Forbidden"])
def test_call_with_retry_auth_errors_fail_fast_without_sleep(
    retry_sleeps, message: str
) -> None:
    calls: list[int] = []

    async def auth_error() -> str:
        calls.append(1)
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match=message.split()[-1]):
        asyncio.run(
            ai_utils.call_with_retry(auth_error, max_retries=3, initial_delay=1.0)
        )

    assert len(calls) == 1
    assert retry_sleeps == []


def test_call_with_retry_exhausted_attempts_raise_after_exponential_backoff(
    retry_sleeps,
) -> None:
    calls: list[int] = []

    async def always_failing() -> str:
        calls.append(1)
        raise RuntimeError("request timeout")

    with pytest.raises(RuntimeError, match="request timeout"):
        asyncio.run(
            ai_utils.call_with_retry(
                always_failing, max_retries=3, initial_delay=0.5
            )
        )

    assert len(calls) == 3
    # Deterministic exponential backoff: initial_delay * (2 ** attempt).
    assert retry_sleeps == [0.5, 1.0]


def test_call_with_retry_zero_attempts_raises_without_calling(
    retry_sleeps,
) -> None:
    calls: list[int] = []

    async def should_not_run() -> str:
        calls.append(1)
        return "never"

    with pytest.raises(RuntimeError, match="Unexpected error in retry logic"):
        asyncio.run(
            ai_utils.call_with_retry(
                should_not_run, max_retries=0, initial_delay=1.0
            )
        )

    assert calls == []
    assert retry_sleeps == []


# --------------------------------------------------------------------------- #
# Geocoder (src/ai/baseline_workflow.py)
# --------------------------------------------------------------------------- #


class _FakeLocation:
    def __init__(
        self,
        *,
        latitude: float = 31.5,
        longitude: float = 34.45,
        address: dict[str, Any] | None = None,
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.raw = {"address": {} if address is None else address}


@pytest.fixture
def geocoder(monkeypatch: pytest.MonkeyPatch):
    """Install a fake Nominatim and reset the module-level cache/client."""
    bw._geocode_location_cached.cache_clear()
    state: dict[str, Any] = {}

    def install(geocode: Any) -> dict[str, Any]:
        state["calls"] = []

        class _FakeNominatim:
            def __init__(self, **kwargs: Any) -> None:
                self.init_kwargs = kwargs
                self.calls: list[tuple[str, dict[str, Any]]] = []
                state["instance"] = self
                state["calls"] = self.calls

            def geocode(self, text: str, **kwargs: Any) -> Any:
                self.calls.append((text, kwargs))
                return geocode(text, kwargs)

        monkeypatch.setattr(bw, "Nominatim", _FakeNominatim)
        monkeypatch.setattr(bw, "_geolocator", None)
        return state

    yield install
    bw._geocode_location_cached.cache_clear()


@pytest.fixture
def geocode_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr(bw.time, "sleep", sleeps.append)
    return sleeps


def test_geocode_cache_hit_does_not_geocode_twice(geocoder) -> None:
    state = geocoder(lambda text, kwargs: _FakeLocation())

    first = bw._geocode_location("Gaza")
    second = bw._geocode_location("Gaza")

    assert first == bw.GeoResult(country_code="PS", lat=31.5, lon=34.45)
    assert second == first
    assert len(state["calls"]) == 1
    assert state["calls"][0] == (
        "Gaza",
        {"timeout": 10, "addressdetails": True},
    )
    assert state["instance"].init_kwargs == {
        "user_agent": "triangulate-investigation-toolkit"
    }
    assert bw._geocode_location_cached.cache_info().hits == 1


def test_geocode_cache_key_is_stripped_so_padding_shares_one_entry(
    geocoder,
) -> None:
    """The cache key is the normalised text, so padding is not a second entry."""
    state = geocoder(lambda text, kwargs: _FakeLocation())

    assert bw._geocode_location("  Gaza  ") == bw._geocode_location("Gaza")
    assert [text for text, _ in state["calls"]] == ["Gaza"]
    assert bw._geocode_location_cached.cache_info().hits == 1
    assert bw._geocode_location_cached.cache_info().misses == 1


def test_geocode_empty_input_returns_none_without_calling(geocoder) -> None:
    state = geocoder(lambda text, kwargs: _FakeLocation())

    assert bw._geocode_location("   ") is None
    assert state["calls"] == []


@pytest.mark.parametrize(
    "error",
    [
        GeocoderTimedOut("timed out"),
        GeocoderServiceError("service unavailable"),
        ValueError("unexpected"),
    ],
)
def test_geocode_boundary_failures_return_none(geocoder, error: Exception) -> None:
    def _raise(text: str, kwargs: dict[str, Any]) -> Any:
        raise error

    geocoder(_raise)

    assert bw._geocode_location("Gaza") is None


def test_geocode_missing_country_code_is_inferred_from_address_text(geocoder) -> None:
    geocoder(lambda text, kwargs: _FakeLocation(address={"country": "israel"}))

    # Keyword matching on the query text wins; use a neutral text so the
    # address-derived country is what resolves the code.
    assert bw._geocode_location("Some Village") == bw.GeoResult(
        country_code="IL", lat=31.5, lon=34.45
    )


def test_geocode_with_retry_requeries_after_a_cached_miss(
    geocoder, geocode_sleeps
) -> None:
    """A cached ``None`` must not swallow the retry: the second attempt asks again."""
    answers: list[Any] = [None, _FakeLocation()]
    state = geocoder(lambda text, kwargs: None if not answers else answers.pop(0))

    # The first (memoised) attempt records a miss...
    assert bw._geocode_location("Gaza") is None
    assert len(state["calls"]) == 1

    # ...and the retry still reaches Nominatim instead of replaying that miss.
    assert bw._geocode_with_retry("Gaza") == bw.GeoResult("PS", 31.5, 34.45)
    assert [text for text, _ in state["calls"]] == ["Gaza", "Gaza"]
    assert geocode_sleeps == [1.5]


def test_geocode_with_retry_first_attempt_success_does_not_retry(
    geocoder, geocode_sleeps
) -> None:
    state = geocoder(lambda text, kwargs: _FakeLocation())

    assert bw._geocode_with_retry("Gaza") == bw.GeoResult("PS", 31.5, 34.45)
    assert len(state["calls"]) == 1
    assert geocode_sleeps == []


def test_geocode_with_retry_exhausted_attempts_return_none(geocoder, geocode_sleeps) -> None:
    state = geocoder(lambda text, kwargs: None)

    assert bw._geocode_with_retry("Gaza") is None
    # Two attempts, each one a real query, separated by a single sleep.
    assert len(state["calls"]) == 2
    assert geocode_sleeps == [1.5]
    assert bw._geocode_location_cached.cache_info().misses == 1


def test_extract_location_maps_non_empty_geocode_result(
    geocoder, geocode_sleeps
) -> None:
    calls = geocoder(lambda text, kwargs: _FakeLocation())
    event_data: dict[str, Any] = {"claims": [{"where": "Gaza"}]}

    result = bw._extract_location(event_data, {})

    assert result["location_country_code"] == "PS"
    assert result["location_lat"] == 31.5
    assert result["location_lon"] == 34.45
    assert calls["calls"] == [("Gaza", {"timeout": 10, "addressdetails": True})]
    assert geocode_sleeps == []


def test_extract_location_falls_back_to_source_metadata_country(geocoder) -> None:
    calls = geocoder(lambda text, kwargs: _FakeLocation())

    result = bw._extract_location(
        {"claims": []}, {"source_metadata": {"country": "Ukraine"}}
    )

    assert calls["calls"][0][0] == "Ukraine"
    assert result["location_country_code"] == "UA"


def test_extract_location_failure_sets_explicit_none_location(
    geocoder, geocode_sleeps
) -> None:
    """Failure keeps the location keys present but None rather than omitting."""

    def _raise(text: str, kwargs: dict[str, Any]) -> Any:
        raise GeocoderTimedOut("timed out")

    state = geocoder(_raise)

    result = bw._extract_location({"claims": [{"where": "Nowhere"}]}, {})

    assert result["location_country_code"] is None
    assert result["location_lat"] is None
    assert result["location_lon"] is None
    # The retry bypasses the memoised miss, so Nominatim is asked twice.
    assert geocode_sleeps == [1.5]
    assert len(state["calls"]) == 2


def test_extract_location_without_candidate_text_skips_geocoding(
    geocoder, geocode_sleeps
) -> None:
    state = geocoder(lambda text, kwargs: _FakeLocation())

    result = bw._extract_location({"claims": [{"where": "a"}]}, {})

    assert state["calls"] == []
    assert result["location_country_code"] is None
    assert geocode_sleeps == []
