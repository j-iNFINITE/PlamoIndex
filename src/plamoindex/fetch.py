"""HTTP fetch layer with polite crawling controls.

Provides a shared HTTP client with:
- Configurable timeouts, headers, user-agent
- Randomized delay with jitter between requests (per domain)
- Sequential (low-concurrency) fetching per domain by default
- Retry with exponential backoff for transient/rate-limit errors
- Normalized content hashing for cache/revalidation decisions
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from plamoindex.config import PlamoIndexConfig

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a single HTTP fetch operation."""

    url: str
    status_code: int
    headers: dict[str, str]
    text: str
    content_hash: str
    elapsed: float
    from_cache: bool = False


@dataclass
class FetchStats:
    """Per-domain fetch statistics for diagnostics."""

    requests: int = 0
    cache_hits: int = 0
    errors: int = 0
    retries: int = 0
    rate_limits: int = 0
    total_elapsed: float = 0.0


class FetchError(Exception):
    """Raised when a fetch operation fails after all retries."""


class FetchClient:
    """Shared HTTP fetch client with polite crawling controls.

    Features:
    - Configurable user-agent and default headers.
    - Per-domain delay with random jitter.
    - Sequential per-domain request ordering (no concurrent same-domain fetches).
    - Retry with exponential backoff for 429, 408, 5xx, and connection errors.
    - Normalized content hashing (whitespace-stable).
    """

    def __init__(
        self,
        config: PlamoIndexConfig,
        *,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.config = config
        self._client = httpx.Client(
            timeout=httpx.Timeout(config.http.timeout_seconds),
            follow_redirects=True,
        )
        self._default_headers: dict[str, str] = {
            "User-Agent": config.http.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8,zh-CN;q=0.7",
            "Accept-Encoding": "gzip, deflate",
        }
        if default_headers:
            self._default_headers.update(default_headers)

        self._stats: dict[str, FetchStats] = {}
        self._last_request_time: dict[str, float] = {}

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        """Fetch a URL with polite crawling controls.

        Applies per-domain delay with jitter, retries on errors, and
        normalizes content for consistent hashing.

        Args:
            url: The URL to fetch.
            headers: Optional extra headers for this request.

        Returns:
            FetchResult with response data.

        Raises:
            FetchError: If all retries are exhausted.
        """
        domain = urlparse(url).hostname or "unknown"
        if domain not in self._stats:
            self._stats[domain] = FetchStats()

        stats = self._stats[domain]
        merged_headers = dict(self._default_headers)
        if headers:
            merged_headers.update(headers)

        last = self._last_request_time.get(domain, 0.0)
        elapsed_since_last = time.monotonic() - last

        # Apply per-domain delay with random jitter
        delay_config = self._get_domain_delay(domain)
        jitter = random.uniform(-delay_config.jitter_seconds, delay_config.jitter_seconds)
        total_delay = max(0.0, delay_config.delay_seconds + jitter - elapsed_since_last)
        if total_delay > 0:
            logger.debug("Waiting %.2fs before fetching %s (domain: %s)", total_delay, url, domain)
            time.sleep(total_delay)

        start = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1 + self.config.http.retry_count):
            try:
                response = self._client.get(url, headers=merged_headers)

                if response.status_code in (403, 408, 429, 500, 502, 503, 504):
                    stats.rate_limits += 1
                    retry_after = _parse_retry_after(response)
                    backoff = retry_after or (2 ** attempt * delay_config.backoff_base)
                    logger.warning(
                        "Transient or rate-limited response on %s (status %d). Backing off %.1fs.",
                        url, response.status_code, backoff,
                    )
                    time.sleep(backoff)
                    stats.retries += 1
                    last_error = FetchError(f"HTTP {response.status_code} for {url}")
                    continue

                if response.status_code >= 500:
                    backoff = 2 ** attempt * delay_config.backoff_base
                    logger.warning(
                        "Server error %d on %s. Retrying in %.1fs.",
                        response.status_code, url, backoff,
                    )
                    time.sleep(backoff)
                    stats.retries += 1
                    last_error = FetchError(f"HTTP {response.status_code} for {url}")
                    continue

                if response.status_code < 200 or response.status_code >= 300:
                    stats.errors += 1
                    raise FetchError(f"HTTP {response.status_code} for {url}")

                # Successful response
                text = response.text
                content_hash = _normalized_hash(text)
                elapsed = time.monotonic() - start
                stats.requests += 1
                stats.total_elapsed += elapsed

                result_headers: dict[str, str] = {}
                for k, v in response.headers.items():
                    result_headers[k] = str(v)

                self._last_request_time[domain] = time.monotonic()

                return FetchResult(
                    url=url,
                    status_code=response.status_code,
                    headers=result_headers,
                    text=text,
                    content_hash=content_hash,
                    elapsed=elapsed,
                )

            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                backoff = 2 ** attempt * delay_config.backoff_base
                logger.warning(
                    "Connection error on %s: %s. Retrying in %.1fs.",
                    url, exc, backoff,
                )
                time.sleep(backoff)
                stats.retries += 1
                stats.errors += 1

        raise FetchError(
            f"Failed to fetch {url} after {1 + self.config.http.retry_count} attempts."
        ) from last_error

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Return per-domain fetch statistics for diagnostics."""
        return {
            domain: {
                "requests": s.requests,
                "cache_hits": s.cache_hits,
                "errors": s.errors,
                "retries": s.retries,
                "rate_limits": s.rate_limits,
                "total_elapsed": round(s.total_elapsed, 3),
            }
            for domain, s in self._stats.items()
        }

    def _get_domain_delay(self, domain: str) -> _DomainDelayConfig:
        """Get delay configuration for a domain.

        Checks source-specific settings in config, falls back to HTTP defaults.
        """
        # Try to match domain to a source setting
        for source_id, source_cfg in self.config.sources.items():
            if source_id in domain or domain in source_id or source_id.replace("_", "") in domain:
                return _DomainDelayConfig(
                    delay_seconds=source_cfg.get("delay_seconds", self.config.http.delay_seconds),
                    jitter_seconds=source_cfg.get("jitter_seconds", self.config.http.jitter_seconds),
                    backoff_base=source_cfg.get("backoff_base", self.config.http.backoff_base),
                )
        return _DomainDelayConfig(
            delay_seconds=self.config.http.delay_seconds,
            jitter_seconds=self.config.http.jitter_seconds,
            backoff_base=self.config.http.backoff_base,
        )


@dataclass
class _DomainDelayConfig:
    """Per-domain delay and backoff configuration."""

    delay_seconds: float = 1.0
    jitter_seconds: float = 0.5
    backoff_base: float = 1.0


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Parse Retry-After header, supporting both seconds and HTTP-date."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        # HTTP-date format - not supported in v0.1, fall back to default backoff
        return None


def _normalized_hash(text: str) -> str:
    """Compute a whitespace-normalized hash of HTML content.

    Strips leading/trailing whitespace, normalizes internal whitespace,
    then returns the SHA-256 hex digest. This helps avoid cache busting
    due to insignificant HTML whitespace changes.

    Args:
        text: Raw HTML text.

    Returns:
        SHA-256 hex digest of normalized text.
    """
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
