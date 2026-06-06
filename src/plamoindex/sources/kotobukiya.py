"""Kotobukiya source plugin.

Integrates Kotobukiya instruction and product collection into the plugin API.
Uses KotobukiyaCollector for the actual HTML parsing and crawling logic.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from plamoindex.collector import CollectorCache
from plamoindex.config import PlamoIndexConfig
from plamoindex.fetch import FetchClient
from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.models.shared import (
    PriceInfo,
    Provenance,
    ReleaseInfo,
    TaxonomyRef,
)
from plamoindex.sources.base import SourcePlugin
from plamoindex.sources.kotobukiya_collector import KotobukiyaCollector


class KotobukiyaSource(SourcePlugin):
    """Kotobukiya instruction and product source plugin.

    Collects:
    - Instruction/manual metadata from kotobukiya.co.jp/en/instructions/.
    - Product metadata from kotobukiya.co.jp/en/product/detail/.
    - Confirmed manual-product relationships.
    """

    def __init__(self) -> None:
        self._config: PlamoIndexConfig | None = None
        self._raw_dir: Path | None = None

    def configure(self, config: PlamoIndexConfig, raw_dir: Path | None = None) -> None:
        """Configure the source plugin with runtime settings."""
        self._config = config
        self._raw_dir = raw_dir

    @property
    def source_id(self) -> str:
        return "kotobukiya"

    @property
    def display_name(self) -> str:
        return "Kotobukiya Instructions & Products"

    def collect_manuals(self) -> list[ManualRecord]:
        """Collect Kotobukiya instruction/manual records."""
        config = self._config or PlamoIndexConfig()
        raw_dir = self._raw_dir or Path(config.raw.path)
        raw_dir.mkdir(parents=True, exist_ok=True)

        fetch_client = FetchClient(config)
        cache = CollectorCache(raw_dir, "kotobukiya")
        collector = KotobukiyaCollector(fetch_client, cache)

        try:
            result = collector.collect_all()
            return [_manual_dict_to_record(m) for m in result.manuals]
        finally:
            collector.close()

    def collect_product_sources(self) -> list[ProductSourceRecord]:
        """Collect Kotobukiya product source records."""
        config = self._config or PlamoIndexConfig()
        raw_dir = self._raw_dir or Path(config.raw.path)
        raw_dir.mkdir(parents=True, exist_ok=True)

        fetch_client = FetchClient(config)
        cache = CollectorCache(raw_dir, "kotobukiya")
        collector = KotobukiyaCollector(fetch_client, cache)

        try:
            result = collector.collect_all()
            return [_product_source_dict_to_record(ps) for ps in result.product_sources]
        finally:
            collector.close()

    def collect_products(self) -> list[ProductRecord]:
        """Product merging is handled by merge.py."""
        return []

    def collect_relationships(self) -> list[RelationshipRecord]:
        """Collect Kotobukiya confirmed relationships."""
        config = self._config or PlamoIndexConfig()
        raw_dir = self._raw_dir or Path(config.raw.path)
        raw_dir.mkdir(parents=True, exist_ok=True)

        fetch_client = FetchClient(config)
        cache = CollectorCache(raw_dir, "kotobukiya")
        collector = KotobukiyaCollector(fetch_client, cache)

        try:
            result = collector.collect_all()
            return [_relationship_dict_to_record(r) for r in result.relationships]
        finally:
            collector.close()


def _manual_dict_to_record(d: dict[str, Any]) -> ManualRecord:
    """Convert a collector dict to a ManualRecord."""
    now = d.get("collected_at", "2026-06-06T00:00:00Z")

    title = d.get("title", "")
    instruction_id = str(d.get("instruction_id", ""))

    # Build related products from relationships
    related_products = None

    return ManualRecord(
        manual_source_key=f"kotobukiya:{instruction_id}",
        source="kotobukiya",
        source_type="automated",
        manual_source_id=instruction_id,
        title=title,
        brand="KOTOBUKIYA",
        manufacturer_item_code=d.get("manufacturer_item_code"),
        source_url=d.get("source_url"),
        pdf_url=d.get("pdf_url"),
        pdf_urls=d.get("pdf_urls"),
        image_url=d.get("image_url"),
        manual_preview_images=d.get("manual_preview_images"),
        languages=d.get("languages"),
        related_products=related_products,
        provenance=Provenance(
            collector="kotobukiya",
            collection_method="scrape",
            collected_at=(
                datetime.fromisoformat(now) if isinstance(now, str) else now
            ),
        ),
        raw=d,
    )


def _product_source_dict_to_record(d: dict[str, Any]) -> ProductSourceRecord:
    """Convert a collector dict to a ProductSourceRecord."""
    now = d.get("collected_at", "2026-06-06T00:00:00Z")
    product_id = d.get("product_source_id", d.get("product_id", ""))

    # Release
    release_data = d.get("release")
    release = None
    if release_data and isinstance(release_data, dict):
        release = ReleaseInfo(
            source=release_data.get("source", "kotobukiya_product"),
            locale=release_data.get("locale", "en"),
            market=release_data.get("market", "jp-shop"),
            release_month=release_data.get("release_month"),
            release_date_precision=release_data.get("release_date_precision", "month"),
            raw=release_data.get("raw"),
        )

    # Prices
    prices = None
    price_list = d.get("prices")
    if price_list and isinstance(price_list, list):
        prices = [
            PriceInfo(
                source=p.get("source", "kotobukiya_product"),
                locale=p.get("locale", "en"),
                market=p.get("market", "jp-shop"),
                amount=p.get("amount", 0.0),
                currency=p.get("currency", "JPY"),
                tax_included=p.get("tax_included", False),
                raw=p.get("raw"),
            )
            for p in price_list
        ]

    # Category/series
    category = None
    series = None
    product_series = None
    cat_data = d.get("category")
    if cat_data and isinstance(cat_data, dict):
        category = TaxonomyRef(
            label=cat_data.get("label", ""),
            kind="category",
            url=cat_data.get("url"),
        )
    series_data = d.get("series")
    if series_data and isinstance(series_data, dict):
        series = TaxonomyRef(
            label=series_data.get("label", ""),
            kind="series",
            url=series_data.get("url"),
        )
    ps_data = d.get("product_series")
    if ps_data and isinstance(ps_data, dict):
        product_series = TaxonomyRef(
            label=ps_data.get("label", ""),
            kind="product_series",
            url=ps_data.get("url"),
        )

    # Specs
    specs = d.get("specs") or {}
    scale = d.get("scale") or specs.get("scale")
    if scale:
        specs["scale"] = scale

    return ProductSourceRecord(
        product_source_key=f"kotobukiya-product:en:{product_id}",
        source="kotobukiya_product",
        manufacturer="KOTOBUKIYA",
        locale="en",
        market="jp-shop",
        product_source_id=product_id,
        product_url=d.get("product_url"),
        title=d.get("title", ""),
        manufacturer_item_code=d.get("manufacturer_item_code"),
        category=category,
        series=series,
        product_series=product_series,
        release=release,
        prices=prices,
        specs=specs if specs else None,
        provenance=Provenance(
            collector="kotobukiya_product",
            collection_method="scrape",
            collected_at=(
                datetime.fromisoformat(now) if isinstance(now, str) else now
            ),
        ),
        raw=d,
    )


def _relationship_dict_to_record(d: dict[str, Any]) -> RelationshipRecord:
    """Convert a collector dict to a RelationshipRecord."""
    now = d.get("collection_date", d.get("collected_at", "2026-06-06T00:00:00Z"))
    from_key = d.get("from_key", "")
    to_key = d.get("to_key", "")
    rel_type = d.get("relationship", "manual_for_product")
    status = d.get("status", "confirmed")

    relationship_key = f"rel:{rel_type}:{from_key}:{to_key}"

    provenance_data = d.get("provenance", {})
    if isinstance(provenance_data, dict):
        collected_at_str = provenance_data.get("collected_at", now)
        collected_at = (
            datetime.fromisoformat(collected_at_str)
            if isinstance(collected_at_str, str)
            else collected_at_str
        )
    else:
        collected_at = datetime.fromisoformat(now) if isinstance(now, str) else now

    return RelationshipRecord(
        relationship_key=relationship_key,
        from_key=from_key,
        to_key=to_key,
        relationship=rel_type,
        status=status,
        method=d.get("method"),
        confidence=d.get("confidence"),
        matched_fields=d.get("matched_fields"),
        provenance=Provenance(
            collector=provenance_data.get("collector", "kotobukiya"),
            collection_method=provenance_data.get("collection_method", "scrape"),
            collected_at=collected_at,
        ),
    )
