"""Bandai source plugin.

Integrates Bandai manual and schedule/collection into the plugin API.
Uses BandaiManualCollector and BandaiScheduleCollector for the actual
HTML parsing and crawling logic.
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
from plamoindex.models.shared import PriceInfo, Provenance, ReleaseInfo, TaxonomyRef
from plamoindex.sources.bandai_manual import BandaiManualCollector
from plamoindex.sources.bandai_schedule import BandaiScheduleCollector
from plamoindex.sources.base import SourcePlugin


class BandaiSource(SourcePlugin):
    """Bandai manual and schedule/product source plugin.

    Collects:
    - Manual metadata from manual.bandai-hobby.net.
    - Schedule/product metadata from bandai-hobby.net (ja, en, zh-Hans).
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
        return "bandai"

    @property
    def display_name(self) -> str:
        return "Bandai Manuals & Schedule"

    def collect_manuals(self) -> list[ManualRecord]:
        """Collect Bandai manual records."""
        config = self._config or PlamoIndexConfig()
        raw_dir = self._raw_dir or Path(config.raw.path)
        raw_dir.mkdir(parents=True, exist_ok=True)

        fetch_client = FetchClient(config)
        cache = CollectorCache(raw_dir, "bandai_manual")
        collector = BandaiManualCollector(fetch_client, cache)

        try:
            result = collector.collect_all()
            return [_manual_dict_to_record(m) for m in result.manuals]
        finally:
            collector.close()

    def collect_product_sources(self) -> list[ProductSourceRecord]:
        """Collect Bandai schedule/product source records."""
        config = self._config or PlamoIndexConfig()
        raw_dir = self._raw_dir or Path(config.raw.path)
        raw_dir.mkdir(parents=True, exist_ok=True)

        fetch_client = FetchClient(config)
        cache = CollectorCache(raw_dir, "bandai_schedule")
        collector = BandaiScheduleCollector(fetch_client, cache)

        try:
            result = collector.collect_all()
            return [_product_source_dict_to_record(ps) for ps in result.product_sources]
        finally:
            collector.close()

    def collect_products(self) -> list[ProductRecord]:
        """Product merging is handled by merge.py, not here."""
        return []

    def collect_relationships(self) -> list[RelationshipRecord]:
        """Bandai relationship inference is handled by merge.py."""
        return []


def _manual_dict_to_record(d: dict[str, Any]) -> ManualRecord:
    """Convert a collector dict to a ManualRecord."""
    now = d.get("collected_at", "2026-06-06T00:00:00Z")

    # Parse release date
    release_date = d.get("release_date")
    release_month = d.get("release_month")
    release_precision = d.get("release_date_precision", None)

    # Determine keywords for search tokens
    tokens = []
    title_ja = d.get("title_ja", "")
    title_en = d.get("title_en", "")
    if title_ja:
        tokens.append(title_ja)
    if title_en:
        tokens.append(title_en)

    localized = {}
    if title_ja:
        localized["ja"] = title_ja
    if title_en:
        localized["en"] = title_en

    normalized = {}
    if title_ja:
        normalized["ja"] = "".join(title_ja.split()).lower()
    if title_en:
        normalized["en"] = "".join(title_en.split()).lower()

    return ManualRecord(
        manual_source_key=f"bandai:{d.get('manual_id', '')}",
        source="bandai",
        source_type="automated",
        manual_source_id=str(d.get("manual_id", "")),
        title=title_ja or d.get("title", ""),
        title_en=title_en,
        localized_titles=localized if localized else None,
        normalized_titles=normalized if normalized else None,
        brand="BANDAI SPIRITS",
        manufacturer_item_code=d.get("product_code"),
        source_url=d.get("source_url"),
        pdf_url=d.get("pdf_url"),
        release_date_raw=d.get("release_date_raw"),
        release_date=release_date,
        release_month=release_month,
        release_date_precision=release_precision,
        image_url=d.get("image_url"),
        provenance=Provenance(
            collector="bandai_manual",
            collection_method="scrape",
            collected_at=datetime.fromisoformat(now) if isinstance(now, str) else now,
        ),
        search_tokens=tokens if tokens else None,
        raw=d,
    )


def _product_source_dict_to_record(d: dict[str, Any]) -> ProductSourceRecord:
    """Convert a collector dict to a ProductSourceRecord."""
    locale = d.get("locale", "en")
    source_id = d.get("product_id", d.get("cn_id", ""))
    source_name = d.get("source", f"bandai_schedule_{locale}")

    # Build product source key
    if locale == "zh-Hans":
        key = f"bandai-schedule:zh-Hans:{source_id}"
    else:
        key = f"bandai-schedule:{locale}:{source_id}"

    # Market mapping
    market_map = {"ja": "jp", "en": "en-others", "zh-Hans": "cn"}
    market = market_map.get(locale, locale)

    # Taxonomy
    brand_line = None
    series = None
    taxonomy_list = d.get("taxonomy")
    if taxonomy_list:
        for t in taxonomy_list:
            if t.get("kind") == "brand":
                brand_line = _make_taxonomy_ref(t)
            elif t.get("kind") == "series":
                series = _make_taxonomy_ref(t)

    # Release
    release = None
    release_month = d.get("release_month") or d.get("release_month_detail")
    release_raw = d.get("release_raw")
    if release_month:
        release = ReleaseInfo(
            source=source_name,
            locale=locale,
            market=market,
            release_month=release_month,
            release_date_precision=d.get("release_date_precision", "month"),
            raw=release_raw,
        )

    # Price
    prices = []
    price_amount = d.get("price_amount")
    if price_amount is not None:
        prices.append(
            PriceInfo(
                source=source_name,
                locale=locale,
                market=market,
                amount=price_amount,
                currency="JPY",
                tax_included=d.get("price_tax_included", True),
                raw=d.get("price_raw"),
            )
        )

    now = d.get("collected_at", "2026-06-06T00:00:00Z")

    return ProductSourceRecord(
        product_source_key=key,
        source=source_name,
        manufacturer="BANDAI SPIRITS",
        locale=locale,
        market=market,
        product_source_id=source_id,
        product_url=d.get("product_url"),
        title=d.get("title", ""),
        normalized_title=_normalize_title(d.get("title", "")),
        image_url=d.get("image_url"),
        brand_line=brand_line,
        series=series,
        release=release,
        prices=prices if prices else None,
        provenance=Provenance(
            collector=source_name,
            collection_method="scrape",
            collected_at=datetime.fromisoformat(now) if isinstance(now, str) else now,
        ),
        raw=d,
    )


def _make_taxonomy_ref(t: dict[str, Any]) -> TaxonomyRef:
    """Build a TaxonomyRef from a taxonomy dict."""
    return TaxonomyRef(
        kind=t.get("kind"),
        slug=t.get("slug"),
        id=t.get("id"),
        label=t.get("label", ""),
        url=t.get("url"),
    )


def _normalize_title(title: str) -> str | None:
    """Normalize a title by stripping whitespace and lowercasing."""
    if not title:
        return None
    return "".join(title.split()).lower()


