"""Tests for the HTTP fetch layer."""

from __future__ import annotations

import httpx
import pytest

from plamoindex.config import HttpSettings, PlamoIndexConfig
from plamoindex.fetch import FetchClient, FetchError, _normalized_hash


class _FakeHttpClient:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.calls = 0

    def get(self, url: str, headers: dict[str, str]) -> httpx.Response:
        self.calls += 1
        return httpx.Response(self.status_code, text="not ok")

    def close(self) -> None:
        pass


class TestNormalizedHash:
    def test_basic(self) -> None:
        h1 = _normalized_hash("hello world")
        h2 = _normalized_hash("hello  world")
        assert h1 == h2

    def test_different_content(self) -> None:
        h1 = _normalized_hash("hello world")
        h2 = _normalized_hash("goodbye world")
        assert h1 != h2


class TestFetchClient:
    def test_init(self) -> None:
        config = PlamoIndexConfig(http=HttpSettings(timeout_seconds=10.0))
        client = FetchClient(config)
        assert client._client.timeout.connect == 10.0
        client.close()

    def test_config_defaults(self) -> None:
        config = PlamoIndexConfig()
        client = FetchClient(config)
        assert "User-Agent" in client._default_headers
        assert "plamoindex" in client._default_headers["User-Agent"]
        client.close()

    def test_403_is_not_treated_as_success(self) -> None:
        config = PlamoIndexConfig(
            http=HttpSettings(
                delay_seconds=0,
                jitter_seconds=0,
                backoff_base=0,
                retry_count=0,
            )
        )
        client = FetchClient(config)
        fake = _FakeHttpClient(403)
        client._client = fake  # type: ignore[assignment]

        with pytest.raises(FetchError):
            client.fetch("https://example.com/blocked")

        assert fake.calls == 1
        assert client.get_stats()["example.com"]["rate_limits"] == 1
        client.close()

    def test_404_is_not_treated_as_success(self) -> None:
        config = PlamoIndexConfig(
            http=HttpSettings(delay_seconds=0, jitter_seconds=0, retry_count=0)
        )
        client = FetchClient(config)
        fake = _FakeHttpClient(404)
        client._client = fake  # type: ignore[assignment]

        with pytest.raises(FetchError):
            client.fetch("https://example.com/missing")

        assert fake.calls == 1
        client.close()
