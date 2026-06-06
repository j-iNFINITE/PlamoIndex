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
from plamoindex.models.shared import Provenance


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


class CuratedVendorFile(BaseModel):
    """Schema for curated/vendors/*.yaml files."""

    source_id: str
    display_name: str
    source_type: str = "curated"
    records: list[CuratedRecordEntry] = []


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
