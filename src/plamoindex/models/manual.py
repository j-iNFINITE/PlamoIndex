"""ManualRecord schema model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from plamoindex.models.shared import ProductRelationRef, Provenance

__all__ = ["ManualRecord"]


class ManualRecord(BaseModel):
    """A normalized manual record representing one manual/instruction page.

    This is the primary dataset contract for downstream manual search.
    Manual identity (manual_source_key) is source-local and must not be treated
    as product identity.

    Rules:
    - brand is the manufacturer/official brand, not the product line.
    - Product-level metadata (prices, releases, taxonomy) belongs in ProductRecord.
    - related_products provides relationship metadata, not catalog_product_id.
    """

    schema_version: int = Field(default=1, description="Data contract version")

    # Identity fields
    manual_source_key: str = Field(
        ...,
        description="Globally unique manual source key (e.g., 'bandai:5119')",
        pattern=r"^[a-z][a-z0-9_-]*:[a-zA-Z0-9_.-]+$",
    )
    source: str = Field(..., description="Source plugin identifier (e.g., 'bandai', 'kotobukiya')")
    source_type: str = Field(
        default="automated",
        description="Source type: automated, curated, hybrid, or external",
    )
    manual_source_id: str = Field(..., description="Source-local manual identifier")

    # Title fields
    title: str = Field(..., description="Primary title (usually Japanese for Bandai)")
    title_en: str | None = Field(default=None, description="English title if available")
    localized_titles: dict[str, str] | None = Field(
        default=None,
        description="Locale-keyed title map (e.g., {'ja': '...', 'en': '...'})",
    )
    normalized_titles: dict[str, str] | None = Field(
        default=None,
        description="Locale-keyed normalized (whitespace/punctuation-stripped) titles",
    )

    # Manufacturer / product code fields
    brand: str = Field(..., description="Manufacturer or official brand name")
    manufacturer_item_code: str | None = Field(
        default=None,
        description="Manufacturer product/SKU code (e.g., 'PV256')",
    )

    # Source URL fields
    source_url: str | None = Field(default=None, description="Official manual detail page URL")
    pdf_url: str | None = Field(default=None, description="Primary PDF URL (preferred language)")
    pdf_urls: dict[str, str] | None = Field(
        default=None,
        description="Language-keyed PDF URL map",
    )

    # Image fields
    image_url: str | None = Field(default=None, description="Primary product/manual image URL")
    manual_preview_images: list[str] | None = Field(
        default=None,
        description="List of manual preview image URLs",
    )

    # Release fields
    release_date_raw: str | None = Field(default=None, description="Raw release date text from source")
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
    release_date_precision: Literal["day", "month", "year", "unknown"] | None = Field(
        default=None,
        description="Release date precision: day, month, year, or unknown",
    )

    # Classification fields
    languages: list[str] | None = Field(default=None, description="List of language codes for the manual PDF")
    manual_type: str | None = Field(default=None, description="Type of manual (e.g., 'assembly')")
    availability: str | None = Field(default=None, description="Availability status (e.g., 'available')")

    # Catalog / product mapping
    catalog_product_id: str | None = Field(
        default=None,
        description="Confirmed catalog product ID (deprecated in favor of related_products)",
    )
    catalog_mapping_status: str | None = Field(
        default=None,
        description="Catalog mapping status: unmapped, candidate, confirmed, rejected",
    )

    # Relationships
    related_products: list[ProductRelationRef] | None = Field(
        default=None,
        description="List of related product references",
    )

    # Search / aliases
    aliases: list[str] | None = Field(default=None, description="Alternative names for this manual")
    search_tokens: list[str] | None = Field(default=None, description="Pre-computed search tokens")

    # Provenance and raw data
    provenance: Provenance = Field(..., description="Provenance metadata")
    raw: dict[str, Any] | None = Field(default=None, description="Raw source metadata for auditability")

    @model_validator(mode="after")
    def validate_release_precision(self) -> "ManualRecord":
        """Validate release date fields based on precision."""
        prec = self.release_date_precision
        if prec == "day" and not self.release_date:
            raise ValueError("release_date is required when release_date_precision is 'day'")
        if prec in ("month", "day") and not self.release_month:
            raise ValueError("release_month is required when release_date_precision is 'month' or 'day'")
        return self
