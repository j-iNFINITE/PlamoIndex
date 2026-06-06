"""Dataset output writer.

Writes the final dataset to JSON files in the dist/ directory.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.output.checksums import compute_checksums


def _pydantic_to_dict(obj: Any) -> Any:
    """Serialize a Pydantic model or list of models to a JSON-compatible dict.

    Handles BaseModel instances and lists of BaseModel instances.

    Args:
        obj: Pydantic model, list, or other JSON-serializable value.

    Returns:
        JSON-compatible Python value.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", exclude_none=True)
    if isinstance(obj, list):
        return [_pydantic_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _pydantic_to_dict(v) for k, v in obj.items()}
    return obj


def _write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write data as pretty-printed JSON to a file.

    Args:
        path: Output file path.
        data: JSON-serializable data.
        indent: JSON indentation level.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")


def _generate_json_schema() -> dict[str, Any]:
    """Generate a JSON Schema representation of ManualRecord.

    Returns:
        JSON Schema dict.
    """
    schema = ManualRecord.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ManualRecord",
        "description": "Schema for plamoindex manual records",
        **schema,
    }


def write_dataset(
    dist_dir: Path,
    manuals: list[ManualRecord],
    product_sources: list[ProductSourceRecord],
    products: list[ProductRecord],
    relationships: list[RelationshipRecord],
    dataset_version: str | None = None,
    base_url: str = "https://manuals.example.com",
    source_statuses: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write the full dataset to the dist/ directory.

    Args:
        dist_dir: Output directory for dist files.
        manuals: All manual records.
        product_sources: All product source records.
        products: All merged product records.
        relationships: All relationship records.
        dataset_version: Dataset version string (defaults to today's date).
        base_url: Base URL for dataset references.
        source_statuses: Real per-source status dict. If None, fabricated.

    Returns:
        Dict with index.json contents (for CLI output).
    """
    dist_dir.mkdir(parents=True, exist_ok=True)

    if dataset_version is None:
        dataset_version = datetime.now(timezone.utc).strftime("%Y.%m.%d")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Categorize manuals by source
    bandai_manuals = [m for m in manuals if m.source == "bandai"]
    kotobukiya_manuals = [m for m in manuals if m.source == "kotobukiya"]
    curated_manuals = [m for m in manuals if m.source_type == "curated"]

    # Categorize products
    bandai_products = [
        p for p in products
        if p.manufacturer == "BANDAI SPIRITS" or p.product_key.startswith("bandai")
    ]
    kotobukiya_products = [
        p for p in products
        if p.manufacturer == "KOTOBUKIYA" or p.product_key.startswith("kotobukiya")
    ]

    # Categorize product sources
    bandai_product_sources = [ps for ps in product_sources if ps.source.startswith("bandai")]
    kotobukiya_product_sources = [ps for ps in product_sources if ps.source.startswith("kotobukiya")]

    # Use real source statuses or fabricate defaults
    if source_statuses is None:
        source_statuses = {
            "bandai": {
                "status": "ok",
                "record_count": len(bandai_manuals),
                "collected_at": generated_at,
            },
            "kotobukiya": {
                "status": "ok",
                "record_count": len(kotobukiya_manuals),
                "collected_at": generated_at,
            },
        }

    # Build compact manual records (used by downstream for search)
    compact_manuals = [
        {
            "manual_source_key": m.manual_source_key,
            "source": m.source,
            "title": m.title,
            "title_en": m.title_en,
            "brand": m.brand,
            "pdf_url": m.pdf_url,
            "source_url": m.source_url,
            "image_url": m.image_url,
            "release_date": m.release_date or m.release_month,
            "languages": m.languages,
            "manual_type": m.manual_type,
        }
        for m in manuals
    ]

    # Write manuals.latest.json
    _write_json(dist_dir / "manuals.latest.json", _pydantic_to_dict(manuals))

    # Write manuals.compact.v1.json
    _write_json(dist_dir / "manuals.compact.v1.json", compact_manuals)

    # Write manuals.bandai.v1.json
    _write_json(dist_dir / "manuals.bandai.v1.json", _pydantic_to_dict(bandai_manuals))

    # Write manuals.kotobukiya.v1.json
    _write_json(dist_dir / "manuals.kotobukiya.v1.json", _pydantic_to_dict(kotobukiya_manuals))

    # Write manuals.curated.v1.json
    _write_json(dist_dir / "manuals.curated.v1.json", _pydantic_to_dict(curated_manuals))

    # Write sources.json
    _write_json(dist_dir / "sources.json", source_statuses)

    # Write schema.v1.json
    _write_json(dist_dir / "schema.v1.json", _generate_json_schema())

    # Write product files
    _write_json(dist_dir / "products.latest.json", _pydantic_to_dict(products))
    _write_json(dist_dir / "products.compact.v1.json", _pydantic_to_dict(products))
    _write_json(dist_dir / "products.bandai.v1.json", _pydantic_to_dict(bandai_products))
    _write_json(dist_dir / "products.kotobukiya.v1.json", _pydantic_to_dict(kotobukiya_products))
    _write_json(dist_dir / "product-sources.bandai.v1.json", _pydantic_to_dict(bandai_product_sources))
    _write_json(dist_dir / "product-sources.kotobukiya.v1.json", _pydantic_to_dict(kotobukiya_product_sources))
    _write_json(dist_dir / "relationships.v1.json", _pydantic_to_dict(relationships))

    # Build and write index.json (before checksums so checksums can include it)
    index_data: dict[str, Any] = {
        "schema_version": 1,
        "dataset_version": dataset_version,
        "generator_version": "0.1.0",
        "generated_at": generated_at,
        "base_url": base_url,
        "files": {
            "full": "/manuals.latest.json",
            "compact": "/manuals.compact.v1.json",
            "bandai": "/manuals.bandai.v1.json",
            "kotobukiya": "/manuals.kotobukiya.v1.json",
            "curated": "/manuals.curated.v1.json",
            "schema": "/schema.v1.json",
            "checksums": "/checksums.json",
            "products": {
                "full": "/products.latest.json",
                "compact": "/products.compact.v1.json",
                "bandai": "/products.bandai.v1.json",
                "kotobukiya": "/products.kotobukiya.v1.json",
            },
            "product_sources": {
                "bandai": "/product-sources.bandai.v1.json",
                "kotobukiya": "/product-sources.kotobukiya.v1.json",
            },
            "relationships": "/relationships.v1.json",
        },
        "counts": {
            "total": len(manuals),
            "bandai": len(bandai_manuals),
            "kotobukiya": len(kotobukiya_manuals),
            "curated": len(curated_manuals),
            "products": len(products),
            "product_sources": len(product_sources),
            "relationships": len(relationships),
        },
        "sources": source_statuses,
    }
    _write_json(dist_dir / "index.json", index_data)

    # Compute checksums for all published files (excluding checksums.json itself,
    # which cannot contain its own hash). index.json is included since it was
    # written above.
    dist_files = [
        "index.json",
        "manuals.latest.json",
        "manuals.compact.v1.json",
        "manuals.bandai.v1.json",
        "manuals.kotobukiya.v1.json",
        "manuals.curated.v1.json",
        "sources.json",
        "schema.v1.json",
        "products.latest.json",
        "products.compact.v1.json",
        "products.bandai.v1.json",
        "products.kotobukiya.v1.json",
        "product-sources.bandai.v1.json",
        "product-sources.kotobukiya.v1.json",
        "relationships.v1.json",
    ]
    checksums = compute_checksums(dist_dir, dist_files)
    _write_json(dist_dir / "checksums.json", checksums)

    return index_data
