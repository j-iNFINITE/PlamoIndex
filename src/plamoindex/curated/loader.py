"""Curated YAML data loader.

Loads curated vendor records, overrides, aliases, and mappings from YAML files.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductSourceRecord
from plamoindex.models.shared import PriceInfo, Provenance, ReleaseInfo, TaxonomyRef


class CuratedRecordEntry(BaseModel):
    """A single curated record entry loaded from YAML."""

    manual_source_key: str
    manual_source_id: str
    title: str
    title_en: str | None = None
    brand: str
    series: str | None = None
    scale: str | None = None
    manufacturer_item_code: str | None = None
    source_url: str | None = None
    pdf_url: str | None = None
    image_url: str | None = None
    languages: list[str] | None = None
    notes: str | None = None
    provenance: dict[str, Any] | None = None


class CuratedOverrideEntry(BaseModel):
    """A single curated override that patches an automated record."""

    manual_source_key: str
    set: dict[str, Any]
    reason: str


class CuratedMappingEntry(BaseModel):
    """A curated mapping entry connecting product sources to merged products.

    Used to confirm or promote relationships that automated matching cannot
    establish, especially Bandai Chinese schedule records.
    """

    product_key: str
    zh_schedule_key: str | None = None
    ja_schedule_key: str | None = None
    en_schedule_key: str | None = None
    manual_source_key: str | None = None
    status: str = "confirmed"
    method: str | None = None
    reason: str | None = None
    confidence: float | None = None


class CuratedPriceEntry(BaseModel):
    """Human-friendly price entry for curated product YAML."""

    amount: float
    currency: str = "JPY"
    tax_included: bool = True
    locale: str | None = None
    market: str | None = None
    price_region: str | None = None
    raw: str | None = None


class CuratedProductEntry(BaseModel):
    """A single human-curated product metadata entry."""

    product_id: str
    product_source_id: str | None = None
    product_source_key: str | None = None
    source: str | None = None
    manufacturer: str | None = None
    locale: str | None = None
    market: str | None = None
    title: str
    normalized_title: str | None = None
    manufacturer_item_code: str | None = None
    product_url: str | None = None
    image_url: str | None = None
    image_urls: list[str] | None = None
    category: str | dict[str, Any] | None = None
    brand_line: str | dict[str, Any] | None = None
    series: str | dict[str, Any] | None = None
    product_series: str | dict[str, Any] | None = None
    release_date: str | None = None
    release_month: str | None = None
    release_date_precision: str | None = None
    release_raw: str | None = None
    price_amount: float | None = None
    price_currency: str = "JPY"
    price_tax_included: bool = True
    price_raw: str | None = None
    prices: list[CuratedPriceEntry] | None = None
    description: str | None = None
    specs: dict[str, Any] | None = None
    manual_source_keys: list[str] | None = None
    notes: str | None = None
    provenance: dict[str, Any] | None = None


class CuratedVendorFile(BaseModel):
    """Schema for curated/vendors/*.yaml files."""

    source_id: str
    display_name: str
    source_type: str = "curated"
    records: list[CuratedRecordEntry] = []


class CuratedProductsFile(BaseModel):
    """Schema for curated/products/*.yaml files."""

    source_id: str
    display_name: str
    manufacturer: str
    source_type: str = "curated"
    locale: str = "ja"
    market: str | None = None
    products: list[CuratedProductEntry] = []


class CuratedOverridesFile(BaseModel):
    """Schema for curated/overrides.yaml."""

    overrides: list[CuratedOverrideEntry] = []


class CuratedMappingsFile(BaseModel):
    """Schema for curated/mappings.yaml."""

    mappings: list[CuratedMappingEntry] = []


class CuratedAliasesFile(BaseModel):
    """Schema for curated/aliases.yaml."""

    aliases: dict[str, list[str]] = {}


def load_curated_vendor(path: Path) -> CuratedVendorFile:
    """Load a single curated vendor YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        CuratedVendorFile instance.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return CuratedVendorFile.model_validate(data)


def load_curated_products(path: Path) -> CuratedProductsFile:
    """Load a single curated product YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return CuratedProductsFile.model_validate(data)


def load_curated_overrides(path: Path) -> CuratedOverridesFile:
    """Load curated overrides YAML file.

    Args:
        path: Path to the overrides YAML file.

    Returns:
        CuratedOverridesFile instance.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return CuratedOverridesFile.model_validate(data or {"overrides": []})


def load_curated_mappings(path: Path) -> CuratedMappingsFile:
    """Load curated mappings YAML file.

    Args:
        path: Path to the mappings YAML file.

    Returns:
        CuratedMappingsFile instance.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return CuratedMappingsFile.model_validate(data or {"mappings": []})


def load_all_mappings(curated_dir: Path) -> list[CuratedMappingEntry]:
    """Load all curated mappings from curated directory.

    Args:
        curated_dir: Path to curated/ directory.

    Returns:
        List of CuratedMappingEntry.
    """
    mappings_path = curated_dir / "mappings.yaml"
    if not mappings_path.is_file():
        return []
    mappings_file = load_curated_mappings(mappings_path)
    return mappings_file.mappings


def load_curated_aliases(path: Path) -> CuratedAliasesFile:
    """Load curated aliases YAML file.

    Args:
        path: Path to the aliases YAML file.

    Returns:
        CuratedAliasesFile instance.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return CuratedAliasesFile.model_validate(data or {"aliases": {}})


def curated_entry_to_manual_record(entry: CuratedRecordEntry) -> ManualRecord:
    """Convert a curated YAML entry to a ManualRecord.

    Args:
        entry: CuratedRecordEntry from YAML.

    Returns:
        Normalized ManualRecord instance.
    """
    source_id = entry.manual_source_key.split(":")[0]
    provenance_data = entry.provenance or {}

    collected_at: datetime
    if "added_at" in provenance_data:
        collected_at = datetime.fromisoformat(provenance_data["added_at"])
    else:
        collected_at = datetime.now()

    return ManualRecord(
        manual_source_key=entry.manual_source_key,
        source=source_id,
        source_type="curated",
        manual_source_id=entry.manual_source_id,
        title=entry.title,
        title_en=entry.title_en,
        brand=entry.brand,
        manufacturer_item_code=entry.manufacturer_item_code,
        source_url=entry.source_url,
        pdf_url=entry.pdf_url,
        image_url=entry.image_url,
        languages=entry.languages,
        provenance=Provenance(
            collector=provenance_data.get("collector", "curated"),
            collection_method="manual",
            collected_at=collected_at,
        ),
    )


def curated_product_entry_to_product_source_record(
    entry: CuratedProductEntry,
    product_file: CuratedProductsFile,
) -> ProductSourceRecord:
    """Convert a curated product YAML entry to a ProductSourceRecord."""
    product_source_id = entry.product_source_id or entry.product_id
    locale = entry.locale or product_file.locale
    market = entry.market or product_file.market
    manufacturer = entry.manufacturer or product_file.manufacturer
    source = entry.source or f"{product_file.source_id}_product"
    product_source_key = (
        entry.product_source_key
        or f"{product_file.source_id}-product:{locale}:{product_source_id}"
    )
    now = _curated_collected_at(entry.provenance)

    return ProductSourceRecord(
        product_source_key=product_source_key,
        source=source,
        manufacturer=manufacturer,
        locale=locale,
        market=market,
        product_source_id=product_source_id,
        product_url=entry.product_url,
        title=entry.title,
        normalized_title=entry.normalized_title or _normalize_title(entry.title),
        manufacturer_item_code=entry.manufacturer_item_code,
        image_url=entry.image_url,
        image_urls=entry.image_urls,
        category=_taxonomy_ref(entry.category, "category"),
        brand_line=_taxonomy_ref(entry.brand_line, "brand_line"),
        series=_taxonomy_ref(entry.series, "series"),
        product_series=_taxonomy_ref(entry.product_series, "product_series"),
        release=_release_info(entry, source, locale, market),
        prices=_price_infos(entry, source, locale, market),
        description=entry.description,
        specs=entry.specs,
        provenance=Provenance(
            collector=(entry.provenance or {}).get("collector", product_file.source_id),
            collection_method="manual",
            collected_at=now,
        ),
        raw=entry.model_dump(mode="json", exclude_none=True),
    )


def curated_product_entry_to_mappings(
    entry: CuratedProductEntry,
    product_file: CuratedProductsFile,
) -> list[CuratedMappingEntry]:
    """Create manual-product mappings declared inline on a curated product."""
    if not entry.manual_source_keys:
        return []
    product_key = _product_key_for_curated_entry(entry, product_file)
    return [
        CuratedMappingEntry(
            product_key=product_key,
            manual_source_key=manual_source_key,
            status="confirmed",
            method="curated_product.manual_source_keys",
            reason="Manual source key declared on curated product metadata",
            confidence=1.0,
        )
        for manual_source_key in entry.manual_source_keys
    ]


def load_all_curated_vendors(curated_dir: Path) -> dict[str, list[ManualRecord]]:
    """Load all curated vendor records from a directory.

    Args:
        curated_dir: Path to curated/ directory containing vendors/ subdirectory.

    Returns:
        Dict mapping source_id to list of ManualRecord instances.
    """
    result: dict[str, list[ManualRecord]] = {}
    vendors_dir = curated_dir / "vendors"
    if not vendors_dir.is_dir():
        return result

    for yaml_file in sorted(vendors_dir.glob("*.yaml")):
        vendor = load_curated_vendor(yaml_file)
        records = [curated_entry_to_manual_record(entry) for entry in vendor.records]
        result[vendor.source_id] = records

    return result


def load_all_curated_product_sources(curated_dir: Path) -> list[ProductSourceRecord]:
    """Load all curated product source records from curated/products/*.yaml."""
    products_dir = curated_dir / "products"
    if not products_dir.is_dir():
        return []

    records: list[ProductSourceRecord] = []
    for yaml_file in sorted(products_dir.glob("*.yaml")):
        product_file = load_curated_products(yaml_file)
        records.extend(
            curated_product_entry_to_product_source_record(entry, product_file)
            for entry in product_file.products
        )
    return records


def load_all_curated_product_mappings(curated_dir: Path) -> list[CuratedMappingEntry]:
    """Load manual-product mappings declared inside curated product files."""
    products_dir = curated_dir / "products"
    if not products_dir.is_dir():
        return []

    mappings: list[CuratedMappingEntry] = []
    for yaml_file in sorted(products_dir.glob("*.yaml")):
        product_file = load_curated_products(yaml_file)
        for entry in product_file.products:
            mappings.extend(curated_product_entry_to_mappings(entry, product_file))
    return mappings


def load_all_overrides(curated_dir: Path) -> list[CuratedOverrideEntry]:
    """Load overrides from curated directory.

    Args:
        curated_dir: Path to curated/ directory.

    Returns:
        List of CuratedOverrideEntry.
    """
    overrides_path = curated_dir / "overrides.yaml"
    if not overrides_path.is_file():
        return []
    overrides_file = load_curated_overrides(overrides_path)
    return overrides_file.overrides


def load_all_aliases(curated_dir: Path) -> dict[str, list[str]]:
    """Load aliases from curated directory.

    Args:
        curated_dir: Path to curated/ directory.

    Returns:
        Dict mapping source_id to list of aliases.
    """
    aliases_path = curated_dir / "aliases.yaml"
    if not aliases_path.is_file():
        return {}
    aliases_file = load_curated_aliases(aliases_path)
    return aliases_file.aliases


def _curated_collected_at(provenance_data: dict[str, Any] | None) -> datetime:
    provenance_data = provenance_data or {}
    if "added_at" in provenance_data:
        return datetime.fromisoformat(provenance_data["added_at"])
    return datetime.now()


def _taxonomy_ref(value: str | dict[str, Any] | None, default_kind: str) -> TaxonomyRef | None:
    if value is None:
        return None
    if isinstance(value, str):
        return TaxonomyRef(kind=default_kind, label=value)
    label = value.get("label") or value.get("line_name") or value.get("slug") or value.get("id")
    if not label:
        return None
    return TaxonomyRef(
        taxonomy_key=value.get("taxonomy_key"),
        kind=value.get("kind", default_kind),
        slug=value.get("slug"),
        id=value.get("id"),
        line_code=value.get("line_code"),
        line_name=value.get("line_name"),
        label=str(label),
        url=value.get("url"),
    )


def _release_info(
    entry: CuratedProductEntry,
    source: str,
    locale: str,
    market: str | None,
) -> ReleaseInfo | None:
    if not (entry.release_date or entry.release_month or entry.release_raw):
        return None
    precision = entry.release_date_precision
    if precision is None:
        if entry.release_date:
            precision = "day"
        elif entry.release_month:
            precision = "month"
        else:
            precision = "unknown"
    return ReleaseInfo(
        source=source,
        locale=locale,
        market=market,
        release_date=entry.release_date,
        release_month=entry.release_month,
        release_date_precision=precision,  # type: ignore[arg-type]
        raw=entry.release_raw,
    )


def _price_infos(
    entry: CuratedProductEntry,
    source: str,
    locale: str,
    market: str | None,
) -> list[PriceInfo] | None:
    prices: list[PriceInfo] = []
    if entry.price_amount is not None:
        prices.append(
            PriceInfo(
                source=source,
                locale=locale,
                market=market,
                amount=entry.price_amount,
                currency=entry.price_currency,
                tax_included=entry.price_tax_included,
                raw=entry.price_raw,
            )
        )

    for price in entry.prices or []:
        prices.append(
            PriceInfo(
                source=source,
                locale=price.locale or locale,
                market=price.market or market,
                amount=price.amount,
                currency=price.currency,
                tax_included=price.tax_included,
                price_region=price.price_region,
                raw=price.raw,
            )
        )

    return prices or None


def _product_key_for_curated_entry(
    entry: CuratedProductEntry,
    product_file: CuratedProductsFile,
) -> str:
    manufacturer = entry.manufacturer or product_file.manufacturer
    product_source_id = entry.product_source_id or entry.product_id
    return f"{_manufacturer_product_prefix(manufacturer)}:{product_source_id}"


def _manufacturer_product_prefix(manufacturer: str) -> str:
    special = {
        "BANDAI SPIRITS": "bandai-product",
        "KOTOBUKIYA": "kotobukiya-product",
    }
    prefix = special.get(manufacturer)
    if prefix:
        return prefix
    return manufacturer.lower().replace(" ", "_") + "-product"


def _normalize_title(title: str) -> str | None:
    if not title:
        return None
    return "".join(title.split()).lower()
