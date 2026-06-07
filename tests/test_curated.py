"""Tests for curated YAML loader and validator."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from plamoindex.cli import main
from plamoindex.curated.loader import (
    CuratedRecordEntry,
    CuratedVendorFile,
    curated_entry_to_manual_record,
    load_all_curated_product_mappings,
    load_all_curated_product_sources,
    load_all_curated_vendors,
    load_all_overrides,
    load_curated_vendor,
)
from plamoindex.curated.validator import (
    validate_curated_directory,
    validate_mappings_yaml,
    validate_overrides_yaml,
    validate_products_yaml,
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

    def test_load_all_curated_product_sources(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        products_dir = curated_dir / "products"
        products_dir.mkdir(parents=True)

        (products_dir / "hasegawa.yaml").write_text(yaml.dump({
            "source_id": "hasegawa",
            "display_name": "Hasegawa",
            "manufacturer": "HASEGAWA",
            "locale": "ja",
            "market": "jp",
            "products": [
                {
                    "product_id": "bk-001",
                    "title": "1/72 VF-1 Valkyrie",
                    "manufacturer_item_code": "BK-001",
                    "product_url": "https://example.com/bk-001",
                    "category": "plastic model",
                    "brand_line": {"label": "Macross", "slug": "macross"},
                    "series": "Macross",
                    "release_month": "2026-06",
                    "price_amount": 3200,
                    "price_tax_included": True,
                    "manual_source_keys": ["hasegawa:bk-001-manual"],
                    "specs": {"scale": "1/72"},
                    "provenance": {"collector": "qwjhb", "added_at": "2026-06-06"},
                }
            ],
        }))

        product_sources = load_all_curated_product_sources(curated_dir)
        mappings = load_all_curated_product_mappings(curated_dir)

        assert len(product_sources) == 1
        source = product_sources[0]
        assert source.product_source_key == "hasegawa-product:ja:bk-001"
        assert source.source == "hasegawa_product"
        assert source.manufacturer == "HASEGAWA"
        assert source.provenance.collection_method == "manual"
        assert source.release is not None
        assert source.release.release_month == "2026-06"
        assert source.prices is not None
        assert source.prices[0].amount == 3200
        assert source.brand_line is not None
        assert source.brand_line.label == "Macross"
        assert source.specs == {"scale": "1/72"}
        assert len(mappings) == 1
        assert mappings[0].product_key == "hasegawa-product:bk-001"
        assert mappings[0].manual_source_key == "hasegawa:bk-001-manual"

    def test_curated_product_inline_mappings_keep_multiple_manuals(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        products_dir = curated_dir / "products"
        products_dir.mkdir(parents=True)

        (products_dir / "hasegawa.yaml").write_text(yaml.dump({
            "source_id": "hasegawa",
            "display_name": "Hasegawa",
            "manufacturer": "HASEGAWA",
            "products": [
                {
                    "product_id": "bk-001",
                    "title": "1/72 VF-1 Valkyrie",
                    "manual_source_keys": [
                        "hasegawa:bk-001-ja",
                        "hasegawa:bk-001-en",
                    ],
                }
            ],
        }))

        mappings = load_all_curated_product_mappings(curated_dir)

        assert [mapping.manual_source_key for mapping in mappings] == [
            "hasegawa:bk-001-ja",
            "hasegawa:bk-001-en",
        ]

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

    def test_validate_products_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "hasegawa.yaml"
        path.write_text(yaml.dump({
            "source_id": "hasegawa",
            "display_name": "Hasegawa",
            "manufacturer": "HASEGAWA",
            "products": [
                {
                    "product_id": "bk-001",
                    "title": "Test Product",
                    "release_month": "2026-06",
                    "price_amount": 1200,
                }
            ],
        }))

        assert validate_products_yaml(path) == []

    def test_validate_products_yaml_reports_bad_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump({
            "source_id": "hasegawa",
            "display_name": "Hasegawa",
            "manufacturer": "HASEGAWA",
            "products": [
                {
                    "product_id": "bad",
                    "release_month": "202606",
                    "price_amount": "not-a-price",
                    "manual_source_keys": ["missing-colon"],
                }
            ],
        }))

        errors = validate_products_yaml(path)

        assert any("title" in error for error in errors)
        assert any("release_month" in error for error in errors)
        assert any("price_amount" in error for error in errors)
        assert any("manual_source_key" in error for error in errors)

    def test_validate_products_yaml_reports_field_paths_and_examples(self, tmp_path: Path) -> None:
        path = tmp_path / "bad-details.yaml"
        path.write_text(yaml.dump({
            "source_id": "hasegawa",
            "display_name": "Hasegawa",
            "manufacturer": "HASEGAWA",
            "products": [
                {
                    "product_id": "bad",
                    "title": "Bad Product",
                    "product_source_key": "not-a-valid-key",
                    "release_date_precision": "day",
                    "prices": [
                        {"currency": "JPY"},
                        {"amount": "free"},
                    ],
                    "manual_source_keys": [123],
                }
            ],
        }))

        errors = validate_products_yaml(path)

        assert any("products[0].product_source_key" in error and "source-family:locale:id" in error for error in errors)
        assert any("products[0].release_date is required" in error for error in errors)
        assert any("products[0].release_month is required" in error for error in errors)
        assert any("products[0].prices[0].amount is required" in error for error in errors)
        assert any("products[0].prices[1].amount must be numeric" in error and "'free'" in error for error in errors)
        assert any(
            "products[0].manual_source_keys[0]" in error
            and "hasegawa:bk-001-manual" in error
            for error in errors
        )

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


class TestCuratedProductCli:
    def test_curated_product_add_writes_yaml(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        runner = CliRunner()

        result = runner.invoke(
            main,
            [
                "curated",
                "product",
                "add",
                "--curated",
                str(curated_dir),
                "--source-id",
                "hasegawa",
                "--display-name",
                "Hasegawa",
                "--manufacturer",
                "HASEGAWA",
                "--product-id",
                "bk-001",
                "--title",
                "1/72 VF-1 Valkyrie",
            ],
            input=(
                "\n"  # locale
                "\n"  # market
                "BK-001\n"
                "\n"  # product URL
                "\n"  # image URL
                "plastic model\n"
                "Macross\n"
                "Macross\n"
                "\n"  # product series
                "2026-06\n"
                "3200\n"
                "\n"  # price currency default
                "y\n"
                "1/72\n"
                "hasegawa:bk-001-manual\n"
            ),
        )

        assert result.exit_code == 0, result.output
        assert "语言/地区代码" in result.output
        assert "产品页面 URL" in result.output
        assert "已添加产品 'bk-001'" in result.output
        assert "写入摘要" in result.output
        assert "product_source_key: hasegawa-product:ja:bk-001" in result.output
        assert "product_key: hasegawa-product:bk-001" in result.output
        assert "manual mappings: 1" in result.output
        assert "hasegawa:bk-001-manual -> hasegawa-product:bk-001" in result.output
        product_file = curated_dir / "products" / "hasegawa.yaml"
        assert product_file.is_file()
        data = yaml.safe_load(product_file.read_text(encoding="utf-8"))
        assert data["source_id"] == "hasegawa"
        assert data["manufacturer"] == "HASEGAWA"
        product = data["products"][0]
        assert product["product_id"] == "bk-001"
        assert product["manufacturer_item_code"] == "BK-001"
        assert product["price_amount"] == 3200.0
        assert product["specs"] == {"scale": "1/72"}
        assert product["manual_source_keys"] == ["hasegawa:bk-001-manual"]

    def test_curated_product_add_can_select_existing_values(self, tmp_path: Path) -> None:
        curated_dir = tmp_path / "curated"
        vendors_dir = curated_dir / "vendors"
        vendors_dir.mkdir(parents=True)
        vendors_dir.joinpath("wave.yaml").write_text(
            yaml.dump({
                "source_id": "wave",
                "display_name": "WAVE",
                "records": [
                    {
                        "manual_source_key": "wave:mk-001",
                        "manual_source_id": "mk-001",
                        "title": "Scopedog Manual",
                        "brand": "WAVE",
                        "series": "Armored Trooper VOTOMS",
                        "scale": "1/35",
                    }
                ],
            }),
            encoding="utf-8",
        )
        runner = CliRunner()

        result = runner.invoke(
            main,
            [
                "curated",
                "product",
                "add",
                "--curated",
                str(curated_dir),
                "--product-id",
                "mk-002",
                "--title",
                "1/35 Scopedog Turbo Custom",
            ],
            input=(
                "1\n"  # source option
                "\n"  # locale
                "\n"  # market
                "\n"  # manufacturer item code
                "\n"  # product URL
                "\n"  # image URL
                "\n"  # category
                "\n"  # brand line
                "1\n"  # series option
                "\n"  # product series
                "\n"  # release month
                "\n"  # price amount
                "1\n"  # scale option
                "\n"  # manual source keys
            ),
        )

        assert result.exit_code == 0, result.output
        assert "已有数据源" in result.output
        assert "数据源 ID（输入编号选择已有项，或输入新值）" in result.output
        assert "已有系列" in result.output
        assert "系列（输入编号选择已有项，或输入新值）" in result.output
        assert "已有比例" in result.output
        assert "比例（输入编号选择已有项，或输入新值）" in result.output
        assert "product_source_key: wave-product:ja:mk-002" in result.output
        assert "product_key: wave-product:mk-002" in result.output
        assert "manual mappings: 0" in result.output
        product_file = curated_dir / "products" / "wave.yaml"
        data = yaml.safe_load(product_file.read_text(encoding="utf-8"))
        product = data["products"][0]
        assert data["source_id"] == "wave"
        assert data["manufacturer"] == "WAVE"
        assert product["series"] == "Armored Trooper VOTOMS"
        assert product["specs"] == {"scale": "1/35"}
