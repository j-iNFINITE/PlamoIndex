"""Merge logic for combining automated, curated, and product records.

Handles:
1. Merging automated and curated manual records.
2. Applying curated overrides to automated records.
3. Detecting duplicate keys.
4. Product source merging into product records (ja/en by shared id).
5. Curated mapping support for product relationships.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping

from plamoindex.curated.loader import CuratedMappingEntry, CuratedOverrideEntry
from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.models.shared import ManualRelationRef, PriceInfo, ProductRelationRef, Provenance, ReleaseInfo


class DuplicateKeyError(ValueError):
    """Raised when a duplicate key is found during merge."""


# Mapping: manufacturer -> key prefix
_MANUFACTURER_PRODUCT_PREFIX: dict[str, str] = {
    "BANDAI SPIRITS": "bandai-product",
    "KOTOBUKIYA": "kotobukiya-product",
}

# Mapping: source prefix -> manufacturer
_SOURCE_MANUFACTURER: dict[str, str] = {
    "bandai_schedule_ja": "BANDAI SPIRITS",
    "bandai_schedule_en": "BANDAI SPIRITS",
    "bandai_schedule_zh": "BANDAI SPIRITS",
    "kotobukiya_product": "KOTOBUKIYA",
}

# Mapping: manufacturer -> locale (for product key fallback)
_MANUFACTURER_DEFAULT_LOCALE: dict[str, str] = {
    "BANDAI SPIRITS": "en",
    "KOTOBUKIYA": "en",
}


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
    curated_mappings: list[CuratedMappingEntry] | None = None,
) -> tuple[list[ProductRecord], list[RelationshipRecord]]:
    """Merge product source records into merged product records.

    Merging rules:
    - Bandai ja/en product sources sharing the same product_source_id are merged.
    - Bandai Chinese (zh-Hans) product sources remain candidate-level unless
      a curated mapping confirms them.
    - Kotobukiya product sources pass through as single-source products.
    - Curated mappings can promote Chinese candidates to confirmed status.

    Args:
        product_sources: List of ProductSourceRecord instances.
        curated_mappings: Optional list of curated mapping entries.

    Returns:
        Tuple of (merged ProductRecord list, RelationshipRecord list).
    """
    seen: dict[str, ProductSourceRecord] = {}
    for ps in product_sources:
        if ps.product_source_key in seen:
            raise DuplicateKeyError(f"Duplicate product_source_key: {ps.product_source_key}")
        seen[ps.product_source_key] = ps

    products: list[ProductRecord] = []
    relationships: list[RelationshipRecord] = []

    # Build curated mapping lookup: zh_schedule_key -> product_key
    curated_zh_to_product: dict[str, str] = {}
    curated_product_to_zh: dict[str, str] = {}
    curated_confirmations: list[CuratedMappingEntry] = []
    if curated_mappings:
        for mapping in curated_mappings:
            if mapping.zh_schedule_key and mapping.product_key:
                curated_zh_to_product[mapping.zh_schedule_key] = mapping.product_key
                curated_product_to_zh[mapping.product_key] = mapping.zh_schedule_key
            curated_confirmations.append(mapping)

    # Group by manufacturer + product_source_id for ja/en merging
    source_groups: dict[str, list[ProductSourceRecord]] = {}
    for ps in product_sources:
        if ps.locale == "zh-Hans":
            # Chinese sources are NOT auto-merged; handled separately
            continue
        group_key = f"{ps.manufacturer}:{ps.product_source_id}"
        if group_key not in source_groups:
            source_groups[group_key] = []
        source_groups[group_key].append(ps)

    # Merge grouped (non-Chinese) sources
    for group_key, sources in source_groups.items():
        manufacturer = sources[0].manufacturer
        product_prefix = _get_product_prefix(manufacturer)
        product_id = sources[0].product_source_id
        product_key = f"{product_prefix}:{product_id}"

        if len(sources) == 1:
            source = sources[0]
            taxonomy = _taxonomy_by_locale_from_source(source)
            product = ProductRecord(
                product_key=product_key,
                manufacturer=manufacturer,
                source_type=_product_source_type(sources),
                titles={source.locale: source.title},
                normalized_titles=(
                    {source.locale: source.normalized_title} if source.normalized_title else None
                ),
                manufacturer_item_codes=(
                    [source.manufacturer_item_code] if source.manufacturer_item_code else None
                ),
                source_ids={source.source: source.product_source_id},
                product_urls={source.locale: source.product_url} if source.product_url else None,
                taxonomy_by_locale={source.locale: taxonomy} if taxonomy else None,
                releases=[source.release] if source.release else None,
                prices=source.prices,
                provenance=Provenance(
                    collector="product_merge",
                    collection_method="merge",
                    collected_at=source.provenance.collected_at,
                ),
                related_product_sources=[source.product_source_key],
            )
            products.append(product)
        else:
            # Multiple sources (ja + en) - merge
            titles: dict[str, str | None] = {}
            normalized_titles: dict[str, str | None] = {}
            source_ids: dict[str, str] = {}
            product_urls: dict[str, str] = {}
            releases: list[ReleaseInfo] = []
            prices: list[PriceInfo] = []
            manufacturer_item_codes: list[str] = []
            taxonomy_by_locale: dict[str, dict[str, Any]] = {}

            for source in sources:
                titles[source.locale] = source.title
                if source.normalized_title:
                    normalized_titles[source.locale] = source.normalized_title
                if (
                    source.manufacturer_item_code
                    and source.manufacturer_item_code not in manufacturer_item_codes
                ):
                    manufacturer_item_codes.append(source.manufacturer_item_code)
                source_ids[source.source] = source.product_source_id
                if source.product_url:
                    product_urls[source.locale] = source.product_url
                if source.release:
                    releases.append(source.release)
                if source.prices:
                    prices.extend(source.prices)
                locale_tax = _taxonomy_by_locale_from_source(source)
                if locale_tax:
                    taxonomy_by_locale[source.locale] = locale_tax

            # Check for curated Chinese mapping
            related_product_sources = [s.product_source_key for s in sources]
            if product_key in curated_product_to_zh:
                related_product_sources.append(curated_product_to_zh[product_key])

            product = ProductRecord(
                product_key=product_key,
                manufacturer=manufacturer,
                source_type=_product_source_type(sources),
                titles=titles,
                normalized_titles=normalized_titles if normalized_titles else None,
                manufacturer_item_codes=(
                    manufacturer_item_codes if manufacturer_item_codes else None
                ),
                source_ids=source_ids if source_ids else None,
                product_urls=product_urls if product_urls else None,
                releases=releases if releases else None,
                prices=prices if prices else None,
                taxonomy_by_locale=taxonomy_by_locale if taxonomy_by_locale else None,
                related_product_sources=related_product_sources if related_product_sources else None,
                provenance=Provenance(
                    collector="product_merge",
                    collection_method="merge",
                    collected_at=sources[0].provenance.collected_at,
                ),
            )
            products.append(product)

    # Handle Chinese sources after ja/en products exist, so curated mappings can
    # merge into the already-created Bandai product instead of creating a
    # duplicate product_key.
    zh_sources: list[ProductSourceRecord] = [ps for ps in product_sources if ps.locale == "zh-Hans"]
    for zh_source in zh_sources:
        if zh_source.product_source_key in curated_zh_to_product:
            product_key = curated_zh_to_product[zh_source.product_source_key]
            _merge_into_bandai_product(products, product_key, zh_source)
        else:
            manufacturer_slug = _get_product_prefix(zh_source.manufacturer)
            product_key = f"{manufacturer_slug}:{zh_source.product_source_id}"
            product = ProductRecord(
                product_key=product_key,
                manufacturer=zh_source.manufacturer,
                source_type=_product_source_type([zh_source]),
                titles={zh_source.locale: zh_source.title},
                normalized_titles=(
                    {zh_source.locale: zh_source.normalized_title}
                    if zh_source.normalized_title
                    else None
                ),
                source_ids={zh_source.source: zh_source.product_source_id},
                product_urls={zh_source.locale: zh_source.product_url} if zh_source.product_url else None,
                releases=[zh_source.release] if zh_source.release else None,
                prices=zh_source.prices,
                provenance=Provenance(
                    collector="product_merge",
                    collection_method="merge",
                    collected_at=zh_source.provenance.collected_at,
                ),
                related_product_sources=[zh_source.product_source_key],
            )
            products.append(product)

    for mapping in curated_confirmations:
        if mapping.manual_source_key and mapping.product_key:
            relationships.append(_relationship_from_curated_mapping(mapping))

    return products, relationships


def _get_product_prefix(manufacturer: str) -> str:
    """Get the product key prefix for a manufacturer."""
    prefix = _MANUFACTURER_PRODUCT_PREFIX.get(manufacturer)
    if prefix:
        return prefix
    # Fallback: lowercase with underscores
    return manufacturer.lower().replace(" ", "_") + "-product"


def _merge_into_bandai_product(
    products: list[ProductRecord],
    product_key: str,
    zh_source: ProductSourceRecord,
) -> None:
    """Merge a Chinese product source into an existing Bandai product record, or create new one."""
    # Find existing product with this key
    for product in products:
        if product.product_key == product_key:
            # Merge Chinese data into existing product
            if zh_source.locale not in product.titles:
                product.titles[zh_source.locale] = zh_source.title
            if zh_source.normalized_title:
                if product.normalized_titles is None:
                    product.normalized_titles = {}
                product.normalized_titles[zh_source.locale] = zh_source.normalized_title
            if zh_source.source:
                if product.source_ids is None:
                    product.source_ids = {}
                product.source_ids[zh_source.source] = zh_source.product_source_id
            if zh_source.product_url:
                if product.product_urls is None:
                    product.product_urls = {}
                product.product_urls[zh_source.locale] = zh_source.product_url
            if zh_source.release:
                if product.releases is None:
                    product.releases = []
                product.releases.append(zh_source.release)
            if zh_source.prices:
                if product.prices is None:
                    product.prices = []
                product.prices.extend(zh_source.prices)
            if product.related_product_sources is None:
                product.related_product_sources = []
            if zh_source.product_source_key not in product.related_product_sources:
                product.related_product_sources.append(zh_source.product_source_key)
            return

    # If no existing product found, create new one
    product = ProductRecord(
        product_key=product_key,
        manufacturer=zh_source.manufacturer,
        source_type=_product_source_type([zh_source]),
        titles={zh_source.locale: zh_source.title},
        source_ids={zh_source.source: zh_source.product_source_id} if zh_source.source else None,
        releases=[zh_source.release] if zh_source.release else None,
        prices=zh_source.prices,
        related_product_sources=[zh_source.product_source_key],
        provenance=Provenance(
            collector="product_merge",
            collection_method="merge",
            collected_at=zh_source.provenance.collected_at,
        ),
    )
    products.append(product)


def _product_source_type(sources: list[ProductSourceRecord]) -> str:
    """Determine merged product source_type from contributing product sources."""
    methods = {source.provenance.collection_method for source in sources}
    if methods == {"manual"}:
        return "curated"
    if "manual" in methods:
        return "hybrid"
    return "automated"


def _taxonomy_by_locale_from_source(source: ProductSourceRecord) -> dict[str, Any]:
    """Collect taxonomy refs from a product source for ProductRecord output."""
    taxonomy: dict[str, Any] = {}
    if source.category:
        taxonomy["category"] = source.category
    if source.brand_line:
        taxonomy["brand_line"] = source.brand_line
    if source.series:
        taxonomy["series"] = source.series
    if source.product_series:
        taxonomy["product_series"] = source.product_series
    return taxonomy


def _relationship_from_curated_mapping(mapping: CuratedMappingEntry) -> RelationshipRecord:
    """Build a manual-product relationship from a curated mapping."""
    if not mapping.manual_source_key:
        raise ValueError("Curated mapping relationship requires manual_source_key")

    method = mapping.method or "curated_mapping"
    status = mapping.status
    matched_fields = ["curated.mapping"] if status == "matched" else None

    return RelationshipRecord(
        relationship_key=f"rel:manual-product:{mapping.manual_source_key}:{mapping.product_key}",
        from_key=mapping.manual_source_key,
        to_key=mapping.product_key,
        relationship="manual_for_product",
        status=status,
        method=method,
        confidence=mapping.confidence,
        matched_fields=matched_fields,
        reason=mapping.reason,
        provenance=Provenance(
            collector="curated_mapping",
            collection_method="manual",
            collected_at=datetime.now(timezone.utc),
        ),
    )


def infer_manual_product_relationships(
    manuals: list[ManualRecord],
    products: list[ProductRecord],
    curated_mappings: list[CuratedMappingEntry] | None = None,
    existing_relationships: list[RelationshipRecord] | None = None,
) -> list[RelationshipRecord]:
    """Infer high-confidence manual-product relationships after product merge."""
    relationships: list[RelationshipRecord] = []
    existing_keys = {
        rel.relationship_key for rel in (existing_relationships or [])
    }
    products_by_key = {product.product_key: product for product in products}
    manuals_by_key = {manual.manual_source_key: manual for manual in manuals}
    bandai_products = [
        product for product in products if product.manufacturer == "BANDAI SPIRITS"
    ]

    for manual in manuals:
        if manual.source != "bandai":
            continue

        for product in bandai_products:
            matched_fields = _manual_product_title_matches(manual, product)
            if not matched_fields:
                continue
            matched_locales = _matched_title_locales(matched_fields)
            method = (
                "official_bilingual_title_match"
                if matched_locales == {"ja", "en"}
                else f"official_{next(iter(matched_locales))}_title_match"
            )
            confidence = 0.97 if matched_locales == {"ja", "en"} else 0.93
            rel = _make_manual_product_relationship(
                manual=manual,
                product=product,
                status="matched",
                method=method,
                confidence=confidence,
                matched_fields=matched_fields,
            )
            if rel.relationship_key not in existing_keys:
                relationships.append(rel)
                existing_keys.add(rel.relationship_key)
            _attach_embedded_relationship(manual, product, rel)

    for mapping in curated_mappings or []:
        if not mapping.manual_source_key:
            continue
        mapped_product = products_by_key.get(mapping.product_key)
        mapped_manual = manuals_by_key.get(mapping.manual_source_key)
        if mapped_product is None or mapped_manual is None:
            continue
        rel = _relationship_from_curated_mapping(mapping)
        if rel.relationship_key not in existing_keys:
            relationships.append(rel)
            existing_keys.add(rel.relationship_key)
        _attach_embedded_relationship(mapped_manual, mapped_product, rel)

    return relationships


def _localized_title(manual: ManualRecord, locale: str) -> str | None:
    """Return a localized manual title if available."""
    if manual.localized_titles:
        return manual.localized_titles.get(locale)
    return None


def _manual_product_title_matches(
    manual: ManualRecord,
    product: ProductRecord,
) -> list[str]:
    """Return title fields where manual and product match by the same locale."""
    matched_fields: list[str] = []
    for locale in ("ja", "en"):
        manual_fields = _manual_title_match_values(manual, locale)
        product_fields = _product_title_match_values(product, locale)
        for manual_field, manual_value in manual_fields:
            for product_field, product_value in product_fields:
                if manual_value and manual_value == product_value:
                    matched_fields.extend([manual_field, product_field])
                    break
            if matched_fields and matched_fields[-2] == manual_field:
                break
    return matched_fields


def _matched_title_locales(matched_fields: list[str]) -> set[str]:
    """Return locales represented by matched manual title fields."""
    locales: set[str] = set()
    for field in matched_fields:
        if not field.startswith("manual."):
            continue
        if field == "manual.title":
            locales.add("ja")
        elif field == "manual.title_en":
            locales.add("en")
        else:
            locales.add(field.rsplit(".", 1)[-1])
    return locales


def _manual_title_match_values(
    manual: ManualRecord,
    locale: str,
) -> list[tuple[str, str]]:
    """Return comparable manual title values for one locale."""
    values: list[tuple[str, str]] = []
    normalized_title = _normalized_title_for_locale(manual.normalized_titles, locale)
    if normalized_title:
        values.append((f"manual.normalized_titles.{locale}", normalized_title))

    title = _localized_title(manual, locale)
    field = f"manual.localized_titles.{locale}"
    if locale == "ja" and not title:
        title = manual.title
        field = "manual.title"
    elif locale == "en" and not title:
        title = manual.title_en
        field = "manual.title_en"
    normalized_title = _normalize_match_title(title)
    if normalized_title:
        values.append((field, normalized_title))
    return values


def _product_title_match_values(
    product: ProductRecord,
    locale: str,
) -> list[tuple[str, str]]:
    """Return comparable product title values for one locale."""
    values: list[tuple[str, str]] = []
    normalized_title = _normalized_title_for_locale(product.normalized_titles, locale)
    if normalized_title:
        values.append((f"product.normalized_titles.{locale}", normalized_title))
    normalized_title = _normalize_match_title(product.titles.get(locale))
    if normalized_title:
        values.append((f"product.titles.{locale}", normalized_title))
    return values


def _normalized_title_for_locale(
    normalized_titles: Mapping[str, str | None] | None,
    locale: str,
) -> str:
    """Return a comparable normalized title from schema-normalized fields."""
    if not normalized_titles:
        return ""
    title = normalized_titles.get(locale)
    if not title:
        return ""
    return "".join(title.split()).casefold()


def _normalize_match_title(title: str | None) -> str:
    """Normalize titles for conservative exact matching."""
    if not title:
        return ""
    return re.sub(r"[\W_]+", "", title, flags=re.UNICODE).casefold()


def _make_manual_product_relationship(
    manual: ManualRecord,
    product: ProductRecord,
    status: str,
    method: str,
    confidence: float,
    matched_fields: list[str] | None = None,
) -> RelationshipRecord:
    """Build a manual-product RelationshipRecord."""
    return RelationshipRecord(
        relationship_key=f"rel:manual-product:{manual.manual_source_key}:{product.product_key}",
        from_key=manual.manual_source_key,
        to_key=product.product_key,
        relationship="manual_for_product",
        status=status,
        method=method,
        confidence=confidence,
        matched_fields=matched_fields,
        provenance=Provenance(
            collector="relationship_inference",
            collection_method="inference",
            collected_at=datetime.now(timezone.utc),
        ),
    )


def _attach_embedded_relationship(
    manual: ManualRecord,
    product: ProductRecord,
    relationship: RelationshipRecord,
) -> None:
    """Mirror a standalone relationship into manual/product embedded refs."""
    manual_refs = manual.related_products or []
    if not any(ref.product_key == product.product_key for ref in manual_refs):
        manual_refs.append(
            ProductRelationRef(
                product_key=product.product_key,
                relationship=relationship.relationship,
                status=relationship.status,
                method=relationship.method,
                confidence=relationship.confidence,
            )
        )
        manual.related_products = manual_refs

    product_refs = product.related_manuals or []
    if not any(ref.manual_source_key == manual.manual_source_key for ref in product_refs):
        product_refs.append(
            ManualRelationRef(
                manual_source_key=manual.manual_source_key,
                relationship=relationship.relationship,
                status=relationship.status,
                method=relationship.method,
                confidence=relationship.confidence,
            )
        )
        product.related_manuals = product_refs


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
