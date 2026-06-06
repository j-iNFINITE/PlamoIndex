"""ProductSourceRecord and ProductRecord schema models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from plamoindex.models.shared import (
    ManualRelationRef,
    PriceInfo,
    Provenance,
    ReleaseInfo,
    TaxonomyRef,
)

__all__ = ["ProductSourceRecord", "ProductRecord"]


class ProductSourceRecord(BaseModel):
    """A source-local product detail or schedule entry record.

    Product source records represent one official source/locale product page
    or schedule entry before merging into a product view.

    Rules:
    - product_source_key is source- and locale-local.
    - locale identifies the language/market source.
    - raw preserves all source-specific fields not yet captured by the schema.
    """

    schema_version: int = Field(default=1, description="Data contract version")

    # Identity fields
    product_source_key: str = Field(
        ...,
        description="Globally unique product source key (e.g., 'bandai-schedule:en:01_7017')",
        pattern=r"^[a-z][a-z0-9_-]*:[a-z]{2,}(-[A-Z][a-z]+)?:[a-zA-Z0-9_.-]+$",
    )
    source: str = Field(..., description="Source plugin identifier (e.g., 'bandai_schedule_en')")
    manufacturer: str = Field(..., description="Manufacturer or brand name")

    # Locale and market
    locale: str = Field(..., description="Locale code (e.g., 'ja', 'en', 'zh-Hans')")
    market: str | None = Field(default=None, description="Market identifier (e.g., 'jp', 'en-others')")

    # Source identifiers
    product_source_id: str = Field(..., description="Source-local product identifier")
    product_url: str | None = Field(default=None, description="Official product detail page URL")

    # Title fields
    title: str = Field(..., description="Product title in the source locale")
    normalized_title: str | None = Field(default=None, description="Normalized (whitespace/punctuation-stripped) title")
    manufacturer_item_code: str | None = Field(
        default=None,
        description="Manufacturer item/SKU code",
    )

    # Image fields
    image_url: str | None = Field(default=None, description="Primary product image URL")
    image_urls: list[str] | None = Field(default=None, description="All product image URLs")

    # Taxonomy fields
    category: TaxonomyRef | None = Field(default=None, description="Product category reference")
    brand_line: TaxonomyRef | None = Field(default=None, description="Product line/brand reference")
    series: TaxonomyRef | None = Field(default=None, description="Series/work reference")
    product_series: TaxonomyRef | None = Field(default=None, description="Product series/type reference")

    # Release and pricing
    release: ReleaseInfo | None = Field(default=None, description="Release information")
    prices: list[PriceInfo] | None = Field(default=None, description="Price entries (tax-included and tax-excluded)")

    # Description and specs
    description: str | None = Field(default=None, description="Product description text")
    specs: dict[str, Any] | None = Field(
        default=None, description="Product specifications (scale, size, material, etc.)"
    )

    # Provenance and raw data
    provenance: Provenance = Field(..., description="Provenance metadata")
    raw: dict[str, Any] | None = Field(default=None, description="Raw source metadata for auditability")


class ProductRecord(BaseModel):
    """A merged product record combining source-local product source records.

    Merged products represent one inferred or confirmed product across
    source-local records.

    Rules:
    - releases is a list because release month can differ by market/source.
    - prices is a list because price tax treatment and source market differ.
    - Chinese Bandai product sources remain candidate merges unless curated or
      a future official bridge field confirms them.
    - taxonomy_by_locale preserves source-local taxonomy per locale.
    """

    schema_version: int = Field(default=1, description="Data contract version")

    # Identity fields
    product_key: str = Field(
        ...,
        description="Merged product key (e.g., 'bandai-product:01_7017')",
        pattern=r"^[a-z][a-z0-9_-]+-product:[a-zA-Z0-9_.-]+$",
    )
    manufacturer: str = Field(..., description="Manufacturer or brand name")
    source_type: str = Field(
        default="automated",
        description="Source type: automated, curated, hybrid, or external",
    )

    # Title fields by locale
    titles: dict[str, str | None] = Field(
        ...,
        description="Locale-keyed title map (e.g., {'ja': '...', 'en': '...', 'zh-Hans': null})",
    )
    normalized_titles: dict[str, str | None] | None = Field(
        default=None,
        description="Locale-keyed normalized titles",
    )

    # Manufacturer codes
    manufacturer_item_codes: list[str] | None = Field(
        default=None,
        description="All known manufacturer item/SKU codes",
    )

    # Source mapping
    source_ids: dict[str, str] | None = Field(
        default=None,
        description="Map of source plugin to product source ID",
    )
    product_urls: dict[str, str] | None = Field(
        default=None,
        description="Map of locale to product detail URL",
    )

    # Taxonomy by locale
    taxonomy_by_locale: dict[str, dict[str, TaxonomyRef]] | None = Field(
        default=None,
        description="Taxonomy references grouped by locale and kind",
    )

    # Release and pricing (list because markets differ)
    releases: list[ReleaseInfo] | None = Field(default=None, description="Release entries by market/source")
    prices: list[PriceInfo] | None = Field(default=None, description="Price entries by market/source")

    # Relationships
    related_manuals: list[ManualRelationRef] | None = Field(
        default=None,
        description="Related manual references",
    )
    related_product_sources: list[str] | None = Field(
        default=None,
        description="List of related product source keys",
    )

    # Provenance and raw data
    provenance: Provenance = Field(..., description="Provenance metadata")
    raw: dict[str, Any] | None = Field(default=None, description="Raw metadata for auditability")
