"""Tests for dataset builder and output writer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from click.testing import CliRunner

from plamoindex.cli import main
from plamoindex.config import PlamoIndexConfig
from plamoindex.dataset import DatasetResult, build_dataset, collect_sources
from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.models.shared import Provenance
from plamoindex.output.writer import write_dataset
from plamoindex.sources.base import SourceCollection, SourcePlugin
from plamoindex.sources.registry import register_builtin, reset


def _make_provenance() -> Provenance:
    return Provenance(collector="test", collection_method="test", collected_at=datetime(2026, 6, 6))


class _CountingSource(SourcePlugin):
    collect_calls = 0
    load_calls = 0

    @property
    def source_id(self) -> str:
        return "counting"

    @property
    def display_name(self) -> str:
        return "Counting"

    def collect_manuals(self) -> list[ManualRecord]:
        raise AssertionError("collect_manuals should not be called directly")

    def collect_all_records(self) -> SourceCollection:
        type(self).collect_calls += 1
        return SourceCollection(
            manuals=[
                ManualRecord(
                    manual_source_key="counting:1",
                    source="counting",
                    manual_source_id="1",
                    title="Collected",
                    brand="Counting",
                    provenance=_make_provenance(),
                )
            ],
            product_sources=[],
            relationships=[],
        )

    def load_cached_records(self, raw_dir: Path) -> SourceCollection:
        type(self).load_calls += 1
        return SourceCollection(
            manuals=[
                ManualRecord(
                    manual_source_key="counting:cached",
                    source="counting",
                    manual_source_id="cached",
                    title="Cached",
                    brand="Counting",
                    provenance=_make_provenance(),
                )
            ],
            product_sources=[],
            relationships=[],
        )


class TestConfig:
    def test_default_config(self) -> None:
        config = PlamoIndexConfig()
        assert config.schema_version == 1
        assert config.http.timeout_seconds == 30.0
        assert config.output.dist == "dist/"
        assert config.dataset.base_url == "https://manuals.example.com"

    def test_load_from_dict(self) -> None:
        config = PlamoIndexConfig.model_validate({
            "http": {"timeout_seconds": 60},
            "dataset": {"base_url": "https://example.com"},
        })
        assert config.http.timeout_seconds == 60
        assert config.dataset.base_url == "https://example.com"


class TestDatasetResult:
    def test_success(self) -> None:
        result = DatasetResult()
        assert result.success is True
        assert len(result.errors) == 0

    def test_failure(self) -> None:
        result = DatasetResult()
        result.errors.append("something went wrong")
        assert result.success is False


class TestBuildDataset:
    def setup_method(self) -> None:
        _CountingSource.collect_calls = 0
        _CountingSource.load_calls = 0
        reset()
        register_builtin("counting", _CountingSource)

    def teardown_method(self) -> None:
        reset()

    def test_build_with_no_sources(self, tmp_path: Path) -> None:
        """Build with empty config and no source plugins registered."""
        config = PlamoIndexConfig()
        result = build_dataset(config, source_ids=[], curated_dir=tmp_path / "curated", dist_dir=tmp_path / "dist")
        assert result.success is True
        assert result.index_data is not None
        assert result.index_data["counts"]["total"] == 0

    def test_collect_sources_collects_once_per_source(self, tmp_path: Path) -> None:
        result = collect_sources(
            PlamoIndexConfig(),
            source_ids=["counting"],
            raw_dir=tmp_path / "raw",
        )

        assert result.success is True
        assert _CountingSource.collect_calls == 1
        assert len(result.manuals) == 1

    def test_build_loads_cached_records_without_live_collect(self, tmp_path: Path) -> None:
        result = build_dataset(
            PlamoIndexConfig(),
            source_ids=["counting"],
            curated_dir=tmp_path / "curated",
            raw_dir=tmp_path / "raw",
            dist_dir=tmp_path / "dist",
        )

        assert result.success is True
        assert _CountingSource.collect_calls == 0
        assert _CountingSource.load_calls == 1
        assert result.manuals[0].manual_source_key == "counting:cached"


class TestWriteDataset:
    def test_write_minimal(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        index = write_dataset(
            dist_dir=dist_dir,
            manuals=[],
            product_sources=[],
            products=[],
            relationships=[],
        )
        assert (dist_dir / "index.json").is_file()
        assert (dist_dir / "manuals.latest.json").is_file()
        assert (dist_dir / "manuals.compact.v1.json").is_file()
        assert (dist_dir / "schema.v1.json").is_file()
        assert (dist_dir / "sources.json").is_file()
        assert (dist_dir / "checksums.json").is_file()
        assert index["counts"]["total"] == 0

    def test_write_with_manuals(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        manuals = [
            ManualRecord(
                manual_source_key="bandai:1",
                source="bandai",
                manual_source_id="1",
                title="Test Manual",
                brand="BANDAI SPIRITS",
                provenance=_make_provenance(),
            )
        ]
        index = write_dataset(
            dist_dir=dist_dir,
            manuals=manuals,
            product_sources=[],
            products=[],
            relationships=[],
        )
        assert index["counts"]["total"] == 1
        assert index["counts"]["bandai"] == 1

        with open(dist_dir / "manuals.latest.json", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["title"] == "Test Manual"

    def test_write_compact_format(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        manuals = [
            ManualRecord(
                manual_source_key="bandai:1",
                source="bandai",
                manual_source_id="1",
                title="HG 1/144 Test",
                title_en="HG 1/144 TEST",
                brand="BANDAI SPIRITS",
                pdf_url="https://example.com/manual.pdf",
                provenance=_make_provenance(),
            )
        ]
        write_dataset(
            dist_dir=dist_dir,
            manuals=manuals,
            product_sources=[],
            products=[],
            relationships=[],
        )

        with open(dist_dir / "manuals.compact.v1.json", encoding="utf-8") as f:
            compact = json.load(f)
            assert len(compact) == 1
            entry = compact[0]
            assert entry["manual_source_key"] == "bandai:1"
            assert entry["title"] == "HG 1/144 Test"
            assert entry["title_en"] == "HG 1/144 TEST"
            assert entry["pdf_url"] == "https://example.com/manual.pdf"

    def test_write_product_files(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        product_sources = [
            ProductSourceRecord(
                product_source_key="bandai-schedule:en:01_7017",
                source="bandai_schedule_en",
                manufacturer="BANDAI SPIRITS",
                locale="en",
                product_source_id="01_7017",
                title="Test Product",
                provenance=_make_provenance(),
            )
        ]
        products = [
            ProductRecord(
                product_key="bandai-product:01_7017",
                manufacturer="BANDAI SPIRITS",
                titles={"en": "Test Product"},
                provenance=_make_provenance(),
            )
        ]
        relationships = [
            RelationshipRecord(
                relationship_key="rel:test",
                from_key="bandai:1",
                to_key="bandai-product:01_7017",
                relationship="manual_for_product",
                status="candidate",
                provenance=_make_provenance(),
            )
        ]
        write_dataset(
            dist_dir=dist_dir,
            manuals=[],
            product_sources=product_sources,
            products=products,
            relationships=relationships,
        )

        assert (dist_dir / "products.latest.json").is_file()
        assert (dist_dir / "product-sources.bandai.v1.json").is_file()
        assert (dist_dir / "relationships.v1.json").is_file()

    def test_index_schema_version(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        write_dataset(dist_dir=dist_dir, manuals=[], product_sources=[], products=[], relationships=[])

        with open(dist_dir / "index.json", encoding="utf-8") as f:
            index = json.load(f)
            assert index["schema_version"] == 1
            assert "dataset_version" in index
            assert "generator_version" in index
            assert "counts" in index
            assert "sources" in index

    def test_validate_fails_on_checksum_mismatch(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        manuals = [
            ManualRecord(
                manual_source_key="bandai:1",
                source="bandai",
                manual_source_id="1",
                title="Test Manual",
                brand="BANDAI SPIRITS",
                provenance=_make_provenance(),
            )
        ]
        write_dataset(
            dist_dir=dist_dir,
            manuals=manuals,
            product_sources=[],
            products=[],
            relationships=[],
        )
        (dist_dir / "manuals.latest.json").write_text("[]", encoding="utf-8")

        result = CliRunner().invoke(main, ["validate", "--dist", str(dist_dir)])

        assert result.exit_code != 0
        assert "Checksum mismatch" in result.output


class TestSchemaJson:
    def test_generated_schema_exists(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        write_dataset(dist_dir=dist_dir, manuals=[], product_sources=[], products=[], relationships=[])

        with open(dist_dir / "schema.v1.json", encoding="utf-8") as f:
            schema = json.load(f)
            assert schema["title"] == "ManualRecord"
            assert "properties" in schema
