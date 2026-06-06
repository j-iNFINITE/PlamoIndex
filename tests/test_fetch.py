"""Tests for the HTTP fetch layer."""

from __future__ import annotations

from plamoindex.config import HttpSettings, PlamoIndexConfig
from plamoindex.fetch import FetchClient, _normalized_hash


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
