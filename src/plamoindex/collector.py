"""Base collector for source plugins with incremental collection support.

Provides:
- Raw data cache persistence at data/raw/.
- Normalized content hashing for change detection.
- Revalidation window support.
- Load/save helpers for normalized collector data.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plamoindex.fetch import FetchClient, FetchResult

logger = logging.getLogger(__name__)


class CollectorCache:
    """Persistent cache for collection artifacts.

    Stores:
    - Normalized record data (JSON).
    - Content hashes for change detection.
    - Collection timestamps.
    - Response metadata.
    """

    def __init__(self, raw_dir: Path, source_id: str) -> None:
        self._records_dir = raw_dir / source_id / "records"
        self._manifest_path = raw_dir / source_id / "manifest.json"
        self._records_dir.mkdir(parents=True, exist_ok=True)

        self._manifest: dict[str, Any] = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        if self._manifest_path.is_file():
            try:
                with open(self._manifest_path, encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]
            except (json.JSONDecodeError, OSError):
                pass
        return {"pages": {}, "collected_at": None}

    def _save_manifest(self) -> None:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._manifest, f, indent=2, ensure_ascii=False)

    def get_page_hash(self, page_id: str) -> str | None:
        """Get the normalized content hash for a known page."""
        page = self._manifest.get("pages", {}).get(page_id)
        return page.get("content_hash") if page else None

    def put_page(self, page_id: str, content_hash: str, metadata: dict[str, Any] | None = None) -> None:
        """Record a page in the manifest."""
        if "pages" not in self._manifest:
            self._manifest["pages"] = {}
        self._manifest["pages"][page_id] = {
            "content_hash": content_hash,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        self._manifest["collected_at"] = datetime.now(timezone.utc).isoformat()
        self._save_manifest()

    def has_page_changed(self, page_id: str, content_hash: str) -> bool:
        """Check whether a page's content hash differs from the cached hash."""
        cached = self.get_page_hash(page_id)
        return cached is None or cached != content_hash

    def save_records(self, records: list[dict[str, Any]], filename: str) -> None:
        """Save a list of normalized records as JSON."""
        path = self._records_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    def has_records(self, filename: str) -> bool:
        """Return whether a records file exists in this cache."""
        return (self._records_dir / filename).is_file()

    def load_records(self, filename: str) -> list[dict[str, Any]]:
        """Load a list of normalized records from JSON."""
        path = self._records_dir / filename
        if not path.is_file():
            return []
        with open(path, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    def save_record(self, record: dict[str, Any], filename: str) -> None:
        """Save one normalized record as JSON."""
        path = self._records_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

    def load_record(self, filename: str) -> dict[str, Any] | None:
        """Load one normalized record from JSON."""
        path = self._records_dir / filename
        if not path.is_file():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None

    def save_raw_page(self, page_id: str, content: str) -> None:
        """Save raw HTML content for debugging."""
        path = self._records_dir / f"{page_id}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def close(self) -> None:
        """Finalize and save manifest."""
        self._save_manifest()


class BaseCollector(ABC):
    """Base class for source-specific collectors.

    Provides cache access, fetch client reference, and helper methods
    for incremental collection.

    Subclasses must implement:
    - source_id: str property
    - collect_all() -> CollectionResult
    """

    def __init__(
        self,
        fetch_client: FetchClient,
        cache: CollectorCache,
    ) -> None:
        self.fetch = fetch_client
        self.cache = cache

    @property
    @abstractmethod
    def source_id(self) -> str:
        ...

    @abstractmethod
    def collect_all(self) -> CollectionResult:
        """Collect all records from this source.

        Returns:
            CollectionResult with collected manuals, product_sources, and relationships.
        """
        ...

    def fetch_with_cache(
        self,
        url: str,
        page_id: str,
        *,
        headers: dict[str, str] | None = None,
        force: bool = False,
    ) -> FetchResult | None:
        """Fetch a URL with cache/revalidation support.

        If the page content hash hasn't changed, None is returned to indicate
        the cached version is still current.

        Args:
            url: URL to fetch.
            page_id: Stable identifier for the page (used for cache key).
            headers: Optional extra headers.
            force: If True, bypass cache check.

        Returns:
            FetchResult if the page was fetched (new or changed), or None if cached.
        """
        result = self.fetch.fetch(url, headers=headers)

        if not force:
            if not self.cache.has_page_changed(page_id, result.content_hash):
                logger.debug("Page %s unchanged (hash: %s)", page_id, result.content_hash[:12])
                return None

        self.cache.put_page(page_id, result.content_hash)
        return result

    def close(self) -> None:
        """Clean up resources."""
        self.fetch.close()
        self.cache.close()


class CollectionResult:
    """Result of a collection operation from a single source."""

    def __init__(
        self,
        *,
        manuals: list[dict[str, Any]] | None = None,
        product_sources: list[dict[str, Any]] | None = None,
        relationships: list[dict[str, Any]] | None = None,
    ) -> None:
        self.manuals = manuals or []
        self.product_sources = product_sources or []
        self.relationships = relationships or []

    def __add__(self, other: CollectionResult) -> CollectionResult:
        return CollectionResult(
            manuals=self.manuals + other.manuals,
            product_sources=self.product_sources + other.product_sources,
            relationships=self.relationships + other.relationships,
        )
