"""Shared schema models for provenance, releases, prices, taxonomy, and relationships."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Provenance metadata tracking the origin and lifecycle of a record."""

    collector: str = Field(..., description="Name of the collector (source plugin or process)")
    collection_method: str = Field(
    ..., description="Method used to collect the data (scrape, manual, merge, inference)"
)
    collected_at: datetime = Field(..., description="ISO-8601 timestamp when the record was collected")
    updated_at: datetime | None = Field(default=None, description="ISO-8601 timestamp when the record was last updated")


class ReleaseInfo(BaseModel):
    """Market-source-specific release date information.

    Rules:
    - release_date is set only when precision is 'day'.
    - release_month is set for 'month' or 'day' precision.
    - Do not invent a day for month-only sources.
    """

    source: str = Field(..., description="Source plugin identifier (e.g., bandai_schedule_ja)")
    locale: str = Field(..., description="Locale code (e.g., ja, en, zh-Hans)")
    market: str | None = Field(default=None, description="Market identifier (e.g., jp, en-others)")
    release_date: str | None = Field(
        default=None,
        description="Release date in YYYY-MM-DD format (day precision only)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    release_month: str | None = Field(
        default=None,
        description="Release month in YYYY-MM format",
        pattern=r"^\d{4}-\d{2}$",
    )
    release_date_precision: Literal["day", "month", "year", "unknown"] = Field(
        default="month",
        description="Precision of the release date: day, month, year, or unknown",
    )
    raw: str | None = Field(default=None, description="Raw release date text as seen on the source page")


class PriceInfo(BaseModel):
    """Market-source-specific price information.

    Rules:
    - Keep tax-included and tax-excluded prices as separate entries.
    - Preserve raw text as seen on the source page.
    """

    source: str = Field(..., description="Source plugin identifier")
    locale: str = Field(..., description="Locale code")
    market: str | None = Field(default=None, description="Market identifier")
    amount: float = Field(..., description="Numeric price amount")
    currency: str = Field(..., description="Currency code (e.g., JPY, USD)")
    tax_included: bool = Field(..., description="Whether the price includes tax")
    price_region: str | None = Field(default=None, description="Region this price applies to (e.g., JP)")
    raw: str | None = Field(default=None, description="Raw price text as seen on the source page")


class TaxonomyRef(BaseModel):
    """Reference to a taxonomy term (brand_line, series, category, or product_series).

    At minimum, label must be provided. Other fields provide source-local context
    for the taxonomy term.
    """

    taxonomy_key: str | None = Field(default=None, description="Globally unique taxonomy key")
    kind: str | None = Field(default=None, description="Taxonomy kind: brand, series, category, product_series")
    slug: str | None = Field(default=None, description="URL slug for the taxonomy term")
    id: str | None = Field(default=None, description="Source-local numeric or string identifier")
    line_code: str | None = Field(default=None, description="Product line code (e.g., HG, RG, MG)")
    line_name: str | None = Field(default=None, description="Product line display name (e.g., HIGH GRADE)")
    label: str = Field(..., description="Human-readable label for the taxonomy term")
    url: str | None = Field(default=None, description="Official source URL for the taxonomy term")


class IgnoredDifference(BaseModel):
    """Records a field difference that was intentionally ignored during relationship matching."""

    field: str = Field(..., description="Name of the field where a difference was ignored")
    reason: str | None = Field(default=None, description="Reason the difference was ignored")


class ProductRelationRef(BaseModel):
    """Embedded reference from a manual record to a related product."""

    product_key: str = Field(..., description="Merged product key (e.g., bandai-product:01_7017)")
    relationship: str = Field(default="manual_for_product", description="Type of relationship")
    status: str = Field(..., description="Relationship status: confirmed, matched, candidate, rejected, unmapped")
    method: str | None = Field(default=None, description="Method used to determine the relationship")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence score 0.0-1.0")


class ManualRelationRef(BaseModel):
    """Embedded reference from a product record to a related manual."""

    manual_source_key: str = Field(..., description="Manual source key (e.g., bandai:5119)")
    relationship: str = Field(default="manual_for_product", description="Type of relationship")
    status: str = Field(..., description="Relationship status: confirmed, matched, candidate, rejected, unmapped")
    method: str | None = Field(default=None, description="Method used to determine the relationship")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
