"""Merge logic for combining automated, curated, and product records.

Handles:
1. Merging automated and curated manual records.
2. Applying curated overrides to automated records.
3. Detecting duplicate keys.
4. Product source merging into product records.
"""

from __future__ import annotations

from typing import Any

from plamoindex.curated.loader import CuratedOverrideEntry
from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.models.shared import PriceInfo, ReleaseInfo


class DuplicateKeyError(ValueError):
    """Raised when a duplicate key is found during merge."""


def merge_manuals(
    automated: list[ManualRecord],
    curated_by_source: dict[str, list[ManualRecord]],
    overrides: list[CuratedOverrideEntry] | None = None,
) -> list[ManualRecord]:
    """Merge automated and curated manual records, applying overrides.

    Args:
        automated: List of automated ManualRecords from source plugins.
        curated_by_source: Dict mapping source_id to curated ManualRecords.
        overrides: List of curated overrides to apply.

    Returns:
        Merged list of ManualRecords.

    Raises:
        DuplicateKeyError: If duplicate manual_source_keys are found.
    """
    seen: dict[str, ManualRecord] = {}

    # Add automated records
    for record in automated:
        key = record.manual_source_key
        if key in seen:
            raise DuplicateKeyError(f"Duplicate automated manual_source_key: {key}")
        seen[key] = record

    # Add curated records
    for source_id, curated_list in curated_by_source.items():
        for record in curated_list:
            key = record.manual_source_key
            if key in seen:
                raise DuplicateKeyError(
                    f"Duplicate manual_source_key '{key}' from curated source '{source_id}' "
                    f"conflicts with existing record from '{seen[key].source}'. "
                    f"Use overrides instead of duplicate records."
                )
            seen[key] = record

    # Apply overrides
    if overrides:
        for override in overrides:
            key = override.manual_source_key
            if key not in seen:
                raise DuplicateKeyError(
                    f"Override target '{key}' not found. Cannot apply override."
                )
            for field_path, value in override.set.items():
                _set_field(seen[key], field_path, value)

    return list(seen.values())


def _set_field(record: ManualRecord, field_path: str, value: Any) -> None:
    """Set a field on a ManualRecord by dotted path.

    Args:
        record: The ManualRecord to modify.
        field_path: Dotted field path (e.g., 'aliases', 'provenance.collector').
        value: Value to set.
    """
    parts = field_path.split(".")
    obj: Any = record
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


def merge_product_sources(
    product_sources: list[ProductSourceRecord],
) -> tuple[list[ProductRecord], list[RelationshipRecord]]:
    """Merge product source records into product records.

    For v0.1, this is a placeholder that does basic identity checks.
    Full merging logic will be implemented when source collectors exist.

    Args:
        product_sources: List of ProductSourceRecord instances.

    Returns:
        Tuple of (merged ProductRecord list, RelationshipRecord list).
    """
    # v0.1: Basic dedup and simple conversion per source
    seen: dict[str, ProductSourceRecord] = {}
    for ps in product_sources:
        if ps.product_source_key in seen:
            raise DuplicateKeyError(f"Duplicate product_source_key: {ps.product_source_key}")
        seen[ps.product_source_key] = ps

    products: list[ProductRecord] = []
    relationships: list[RelationshipRecord] = []

    # Group product sources by shared product identifiers
    source_groups: dict[str, list[ProductSourceRecord]] = {}
    for ps in product_sources:
        # For Bandai ja/en, group by product_source_id (shared 01_xxxx)
        group_key = f"{ps.manufacturer}:{ps.product_source_id}"
        if group_key not in source_groups:
            source_groups[group_key] = []
        source_groups[group_key].append(ps)

    for group_key, sources in source_groups.items():
        if len(sources) == 1:
            # Single source - create product record directly
            source = sources[0]
            manufacturer_slug = source.manufacturer.lower().replace(" ", "_")
            product = ProductRecord(
                product_key=f"{manufacturer_slug}-product:{source.product_source_id}",
                manufacturer=source.manufacturer,
                source_type="automated",
                titles={source.locale: source.title},
                normalized_titles=(
                    {source.locale: source.normalized_title} if source.normalized_title else None
                ),
                source_ids={source.source: source.product_source_id},
                product_urls={source.locale: source.product_url} if source.product_url else None,
                releases=[source.release] if source.release else None,
                prices=source.prices,
                provenance=source.provenance,
            )
            products.append(product)
        else:
            # Multiple sources (e.g., ja + en) - merge
            product_key = f"{sources[0].manufacturer.lower().replace(' ', '_')}-product:{sources[0].product_source_id}"
            titles: dict[str, str | None] = {}
            normalized_titles: dict[str, str | None] = {}
            source_ids: dict[str, str] = {}
            product_urls: dict[str, str] = {}
            releases: list[ReleaseInfo] = []
            prices: list[PriceInfo] = []

            for source in sources:
                titles[source.locale] = source.title
                normalized_titles[source.locale] = source.normalized_title
                source_ids[source.source] = source.product_source_id
                if source.product_url:
                    product_urls[source.locale] = source.product_url
                if source.release:
                    releases.append(source.release)
                if source.prices:
                    prices.extend(source.prices)

            product = ProductRecord(
                product_key=product_key,
                manufacturer=sources[0].manufacturer,
                source_type="automated",
                titles=titles,
                normalized_titles=normalized_titles if any(normalized_titles.values()) else None,
                source_ids=source_ids,
                product_urls=product_urls if product_urls else None,
                releases=releases if releases else None,
                prices=prices if prices else None,
                provenance=sources[0].provenance,
            )
            products.append(product)

    return products, relationships


def validate_final_dataset(
    manuals: list[ManualRecord],
    products: list[ProductRecord],
    product_sources: list[ProductSourceRecord],
    relationships: list[RelationshipRecord],
) -> list[str]:
    """Validate the final merged dataset.

    Checks:
    - Duplicate keys within each record type.
    - Relationship targets reference existing records (unless status is candidate).

    Args:
        manuals: All manual records.
        products: All product records.
        product_sources: All product source records.
        relationships: All relationship records.

    Returns:
        List of validation error messages. Empty if valid.
    """
    errors: list[str] = []

    # Collect known keys
    manual_keys = {m.manual_source_key for m in manuals}
    product_keys = {p.product_key for p in products}
    product_source_keys = {ps.product_source_key for ps in product_sources}
    all_keys = manual_keys | product_keys | product_source_keys

    # Check duplicate keys within each type
    _check_duplicates(errors, [m.manual_source_key for m in manuals], "manual_source_key")
    _check_duplicates(errors, [p.product_key for p in products], "product_key")
    _check_duplicates(errors, [ps.product_source_key for ps in product_sources], "product_source_key")
    _check_duplicates(errors, [r.relationship_key for r in relationships], "relationship_key")

    # Validate relationships
    for rel in relationships:
        if rel.status != "candidate":
            if rel.from_key not in all_keys:
                errors.append(
                    f"Relationship '{rel.relationship_key}' references unknown from_key: "
                    f"'{rel.from_key}' (status: {rel.status})"
                )
            if rel.to_key not in all_keys:
                errors.append(
                    f"Relationship '{rel.relationship_key}' references unknown to_key: "
                    f"'{rel.to_key}' (status: {rel.status})"
                )

        if rel.status == "confirmed":
            if not rel.method and not rel.reason:
                errors.append(
                    f"Confirmed relationship '{rel.relationship_key}' has no method or reason"
                )

        if rel.status == "matched":
            if not rel.method or rel.confidence is None or not rel.matched_fields:
                errors.append(
                    f"Matched relationship '{rel.relationship_key}' requires method, "
                    f"confidence, and matched_fields"
                )

    return errors


def _check_duplicates(errors: list[str], keys: list[str], label: str) -> None:
    """Check for duplicate keys and add error messages.

    Args:
        errors: Error list to append to.
        keys: List of key strings.
        label: Human-readable label for the key type.
    """
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            errors.append(f"Duplicate {label}: '{key}'")
        seen.add(key)
