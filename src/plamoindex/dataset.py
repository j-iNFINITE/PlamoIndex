"""Dataset builder.

Orchestrates the complete data pipeline:
1. Collect from source plugins.
2. Load curated records, overrides, and mappings.
3. Merge records.
4. Validate final dataset.
5. Write dist files.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plamoindex.config import PlamoIndexConfig
from plamoindex.curated.loader import (
    load_all_curated_vendors,
    load_all_mappings,
    load_all_overrides,
)
from plamoindex.merge import (
    merge_manuals,
    merge_product_sources,
    validate_final_dataset,
)
from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.output.writer import write_dataset
from plamoindex.sources.base import SourceCollection
from plamoindex.sources.registry import get_source, list_sources


class DatasetResult:
    """Result of a dataset build operation."""

    def __init__(self) -> None:
        self.manuals: list[ManualRecord] = []
        self.product_sources: list[ProductSourceRecord] = []
        self.products: list[ProductRecord] = []
        self.relationships: list[RelationshipRecord] = []
        self.errors: list[str] = []
        self.source_statuses: dict[str, dict[str, Any]] = {}
        self.index_data: dict[str, Any] | None = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


def build_dataset(
    config: PlamoIndexConfig,
    source_ids: list[str] | None = None,
    curated_dir: Path | None = None,
    dist_dir: Path | None = None,
    raw_dir: Path | None = None,
    collect_live: bool = False,
) -> DatasetResult:
    """Build the full dataset.

    Pipeline:
    1. Collect from source plugins.
    2. Load curated records, overrides, and mappings.
    3. Merge records.
    4. Validate final dataset.
    5. Write dist files.

    Args:
        config: PlamoIndex configuration.
        source_ids: List of source IDs to collect. None = all sources.
        curated_dir: Path to curated/ directory. None = use config.
        dist_dir: Path to dist/ directory. None = use config.
        raw_dir: Path to raw/ directory for cached collection data. None = use config.
        collect_live: If True, collect live source data. If False, load raw cache.

    Returns:
        DatasetResult with build results.
    """
    result = DatasetResult()

    if source_ids is None:
        source_ids = list_sources()

    if curated_dir is None:
        curated_dir = Path(config.curated.path)

    if dist_dir is None:
        dist_dir = Path(config.output.dist)

    if raw_dir is None:
        raw_dir = Path(config.raw.path)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1: Load source records from raw cache by default. Live collection is
    # performed by collect_sources() and by `plamoindex collect`.
    for sid in source_ids:
        try:
            plugin = get_source(sid)

            # Configure plugin with raw path if it supports it
            if hasattr(plugin, "configure"):
                plugin.configure(config, raw_dir)

            collection = (
                plugin.collect_all_records()
                if collect_live
                else plugin.load_cached_records(raw_dir)
            )

            result.manuals.extend(collection.manuals)
            result.product_sources.extend(collection.product_sources)
            result.relationships.extend(collection.relationships)

            result.source_statuses[sid] = {
                "status": "ok" if collection.record_count else "missing",
                "record_count": len(collection.manuals),
                "product_source_count": len(collection.product_sources),
                "relationship_count": len(collection.relationships),
                "collected_at": generated_at,
            }
        except Exception as exc:
            result.source_statuses[sid] = {
                "status": "failed",
                "error": str(exc),
                "record_count": 0,
            }

    # Step 2: Load curated data
    try:
        curated_vendors = load_all_curated_vendors(curated_dir)
        curated_overrides = load_all_overrides(curated_dir)
        curated_mappings = load_all_mappings(curated_dir)
    except Exception as exc:
        result.errors.append(f"Failed to load curated data: {exc}")
        curated_vendors = {}
        curated_overrides = []
        curated_mappings = []

    # Step 3: Merge records
    try:
        merged_manuals = merge_manuals(result.manuals, curated_vendors, curated_overrides)
        result.manuals = merged_manuals
    except ValueError as exc:
        result.errors.append(f"Merge failed: {exc}")

    try:
        merged_products, merged_rels = merge_product_sources(
            result.product_sources,
            curated_mappings=curated_mappings,
        )
        result.products = merged_products
        result.relationships.extend(merged_rels)
    except ValueError as exc:
        result.errors.append(f"Product merge failed: {exc}")

    # Infer cross-family manual-product relationships after product merge.
    try:
        from plamoindex.merge import infer_manual_product_relationships

        inferred_rels = infer_manual_product_relationships(
            result.manuals,
            result.products,
            curated_mappings=curated_mappings,
            existing_relationships=result.relationships,
        )
        result.relationships.extend(inferred_rels)
    except ValueError as exc:
        result.errors.append(f"Relationship inference failed: {exc}")

    # Step 4: Validate
    validation_errors = validate_final_dataset(
        result.manuals,
        result.products,
        result.product_sources,
        result.relationships,
    )
    result.errors.extend(validation_errors)

    if (
        source_ids
        and not result.manuals
        and not result.products
        and not result.product_sources
        and not curated_vendors
    ):
        result.errors.append("No automated or curated records available to build dataset.")

    # Step 5: Write dist files (if no fatal validation errors or if we have data)
    if not result.errors or (result.manuals or result.products):
        try:
            dataset_version = datetime.now(timezone.utc).strftime("%Y.%m.%d")
            result.index_data = write_dataset(
                dist_dir=dist_dir,
                manuals=result.manuals,
                product_sources=result.product_sources,
                products=result.products,
                relationships=result.relationships,
                dataset_version=dataset_version,
                base_url=config.dataset.base_url,
                source_statuses=result.source_statuses,
            )
        except Exception as exc:
            result.errors.append(f"Output write failed: {exc}")

    return result


def collect_sources(
    config: PlamoIndexConfig,
    source_ids: list[str] | None = None,
    raw_dir: Path | None = None,
) -> DatasetResult:
    """Collect live source data once per source and persist raw cache records."""
    result = DatasetResult()

    if source_ids is None:
        source_ids = list_sources()

    if raw_dir is None:
        raw_dir = Path(config.raw.path)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for sid in source_ids:
        try:
            plugin = get_source(sid)
            if hasattr(plugin, "configure"):
                plugin.configure(config, raw_dir)
            collection: SourceCollection = plugin.collect_all_records()
            result.manuals.extend(collection.manuals)
            result.product_sources.extend(collection.product_sources)
            result.relationships.extend(collection.relationships)
            result.source_statuses[sid] = {
                "status": "ok",
                "record_count": len(collection.manuals),
                "product_source_count": len(collection.product_sources),
                "relationship_count": len(collection.relationships),
                "collected_at": generated_at,
            }
        except Exception as exc:
            result.source_statuses[sid] = {
                "status": "failed",
                "error": str(exc),
                "record_count": 0,
                "product_source_count": 0,
                "relationship_count": 0,
            }
            result.errors.append(f"Source '{sid}' failed: {exc}")

    return result
