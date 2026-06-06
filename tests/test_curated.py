"""Tests for curated YAML loader and validator."""

from __future__ import annotations

from pathlib import Path

import yaml

from plamoindex.curated.loader import (
    CuratedRecordEntry,
    CuratedVendorFile,
    curated_entry_to_manual_record,
    load_all_curated_vendors,
    load_all_overrides,
    load_curated_vendor,
)
from plamoindex.curated.validator import (
    validate_curated_directory,
    validate_mappings_yaml,
    validate_overrides_yaml,
    validate_vendor_yaml,
)


class TestCuratedLoader:
    def test_load_vendor_file(self, tmp_path: Path) -> None:
        vendor_file = tmp_path / "wave.yaml"
        vendor_file.write_text(yaml.dump({
            "source_id": "wave",
            "display_name": "WAVE",
            "records": [
                {
                    "manual_source_key": "wave:mk-001",
                    "manual_source_id": "mk-001",
                    "title": "1/35 Scopedog",
                    "brand": "WAVE",
                }
            ],
        }))

        vendor = load_curated_vendor(vendor_file)
        assert vendor.source_id == "wave"
        assert len(vendor.records) == 1

    def test_convert_entry_to_record(self) -> None:
        entry = CuratedRecordEntry(
            manual_source_key="wave:mk-001",
            manual_source_id="mk-001",
            title="1/35 Scopedog",
            brand="WAVE",
        )
        record = curated_entry_to_manual_record(entry)
        assert record.manual_source_key == "wave:mk-001"
        assert record.source == "wave"
        assert record.source_type == "curated"

    def test_load_all_vendors_empty_dir(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        (curated_dir / "vendors").mkdir()

        result = load_all_curated_vendors(curated_dir)
        assert result == {}

    def test_load_all_vendors(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        vendors_dir = curated_dir / "vendors"
        vendors_dir.mkdir(parents=True)

        (vendors_dir / "wave.yaml").write_text(yaml.dump({
            "source_id": "wave",
            "display_name": "WAVE",
            "records": [
                {
                    "manual_source_key": "wave:mk-001",
                    "manual_source_id": "mk-001",
                    "title": "1/35 Scopedog",
                    "brand": "WAVE",
                }
            ],
        }))

        result = load_all_curated_vendors(curated_dir)
        assert "wave" in result
        assert len(result["wave"]) == 1

    def test_load_overrides_empty(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        overrides = load_all_overrides(curated_dir)
        assert overrides == []

    def test_load_overrides(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        (curated_dir / "overrides.yaml").write_text(yaml.dump({
            "overrides": [
                {
                    "manual_source_key": "bandai:1",
                    "set": {"title": "New Title"},
                    "reason": "Test override",
                }
            ],
        }))

        overrides = load_all_overrides(curated_dir)
        assert len(overrides) == 1
        assert overrides[0].manual_source_key == "bandai:1"

    def test_curated_vendor_file_schema(self) -> None:
        vendor = CuratedVendorFile(
            source_id="test",
            display_name="Test",
            records=[
                CuratedRecordEntry(
                    manual_source_key="test:1",
                    manual_source_id="1",
                    title="Test",
                    brand="Test",
                )
            ],
        )
        assert len(vendor.records) == 1


class TestCuratedValidator:
    def test_validate_vendor_file_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "valid.yaml"
        path.write_text(yaml.dump({
            "source_id": "wave",
            "display_name": "WAVE",
            "records": [
                {
                    "manual_source_key": "wave:mk-001",
                    "manual_source_id": "mk-001",
                    "title": "Test",
                    "brand": "WAVE",
                }
            ],
        }))
        errors = validate_vendor_yaml(path)
        assert errors == []

    def test_validate_vendor_missing_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.yaml"
        path.write_text(yaml.dump({
            "source_id": "wave",
            # missing display_name
            "records": [
                {
                    "manual_source_id": "mk-001",
                    "title": "Test",
                    # missing manual_source_key
                    # missing brand
                }
            ],
        }))
        errors = validate_vendor_yaml(path)
        assert len(errors) >= 3  # display_name, manual_source_key, brand

    def test_validate_vendor_duplicate_key(self, tmp_path: Path) -> None:
        path = tmp_path / "dup.yaml"
        path.write_text(yaml.dump({
            "source_id": "test",
            "display_name": "Test",
            "records": [
                {"manual_source_key": "test:1", "manual_source_id": "1", "title": "A", "brand": "T"},
                {"manual_source_key": "test:1", "manual_source_id": "2", "title": "B", "brand": "T"},
            ],
        }))
        errors = validate_vendor_yaml(path)
        assert any("Duplicate" in e for e in errors)

    def test_validate_overrides_missing_target(self, tmp_path: Path) -> None:
        path = tmp_path / "overrides.yaml"
        path.write_text(yaml.dump({
            "overrides": [
                {"manual_source_key": "nonexistent:1", "set": {"title": "X"}, "reason": "test"},
            ],
        }))
        errors = validate_overrides_yaml(path, known_keys=set())
        assert any("not found" in e for e in errors)

    def test_validate_mappings_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "mappings.yaml"
        path.write_text(yaml.dump({
            "mappings": [
                {
                    "product_key": "bandai-product:01_7017",
                    "zh_schedule_key": "bandai-schedule:zh-Hans:3236",
                    "status": "confirmed",
                    "reason": "Chinese title matches official product",
                }
            ],
        }))
        from plamoindex.curated.loader import load_curated_mappings
        mappings = load_curated_mappings(path)
        assert len(mappings.mappings) == 1
        assert mappings.mappings[0].product_key == "bandai-product:01_7017"
        assert mappings.mappings[0].status == "confirmed"

    def test_validate_mappings_missing_confirmed_reason(self, tmp_path: Path) -> None:
        path = tmp_path / "mappings.yaml"
        path.write_text(yaml.dump({
            "mappings": [
                {
                    "product_key": "bandai-product:01_7017",
                    "zh_schedule_key": "bandai-schedule:zh-Hans:3236",
                    "status": "confirmed",
                }
            ],
        }))

        errors = validate_mappings_yaml(path)

        assert any("requires 'reason' or 'method'" in error for error in errors)

    def test_validate_directory_includes_mappings(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        (curated_dir / "mappings.yaml").write_text(yaml.dump({
            "mappings": [
                {
                    "product_key": "bandai-product:01_7017",
                    "zh_schedule_key": "bandai-schedule:zh-Hans:3236",
                    "status": "invalid",
                    "reason": "bad status",
                }
            ],
        }))

        results = validate_curated_directory(curated_dir)

        assert str(curated_dir / "mappings.yaml") in results

    def test_load_all_mappings_empty(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        from plamoindex.curated.loader import load_all_mappings
        mappings = load_all_mappings(curated_dir)
        assert mappings == []

    def test_load_all_mappings(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        curated_dir.mkdir()
        (curated_dir / "mappings.yaml").write_text(yaml.dump({
            "mappings": [
                {
                    "product_key": "bandai-product:01_7017",
                    "zh_schedule_key": "bandai-schedule:zh-Hans:3236",
                    "status": "confirmed",
                    "reason": "Match confirmed",
                }
            ],
        }))
        from plamoindex.curated.loader import load_all_mappings
        mappings = load_all_mappings(curated_dir)
        assert len(mappings) == 1

    def test_validate_directory(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        vendors_dir = curated_dir / "vendors"
        vendors_dir.mkdir(parents=True)

        (vendors_dir / "wave.yaml").write_text(yaml.dump({
            "source_id": "wave",
            "display_name": "WAVE",
            "records": [
                {
                    "manual_source_key": "wave:mk-001",
                    "manual_source_id": "mk-001",
                    "title": "Test",
                    "brand": "WAVE",
                }
            ],
        }))

        results = validate_curated_directory(curated_dir)
        assert results == {}
