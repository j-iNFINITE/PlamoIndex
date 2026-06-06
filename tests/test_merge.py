"""Tests for merge logic."""

from __future__ import annotations

from datetime import datetime

import pytest

from plamoindex.curated.loader import CuratedOverrideEntry
from plamoindex.merge import DuplicateKeyError, merge_manuals, merge_product_sources, validate_final_dataset
from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.models.shared import PriceInfo, Provenance, ReleaseInfo


def _make_provenance() -> Provenance:
    return Provenance(collector="test", collection_method="test", collected_at=datetime(2026, 6, 6))


def _make_manual(key: str, source: str = "bandai", sid: str = "1") -> ManualRecord:
    return ManualRecord(
        manual_source_key=key,
        source=source,
        source_type="automated",
        manual_source_id=sid,
        title=f"Test {sid}",
        brand="BANDAI SPIRITS",
        provenance=_make_provenance(),
    )


def _make_product_source(
    key: str, locale: str = "en", source: str = "bandai_schedule_en", pid: str = "01_7017",
) -> ProductSourceRecord:
    return ProductSourceRecord(
        product_source_key=key,
        source=source,
        manufacturer="BANDAI SPIRITS",
        locale=locale,
        product_source_id=pid,
        title=f"Test {pid}",
        provenance=_make_provenance(),
    )


class TestMergeManuals:
    def test_empty(self) -> None:
        result = merge_manuals([], {})
        assert result == []

    def test_automated_only(self) -> None:
        m = _make_manual("bandai:1")
        result = merge_manuals([m], {})
        assert len(result) == 1
        assert result[0].manual_source_key == "bandai:1"

    def test_duplicate_automated(self) -> None:
        m1 = _make_manual("bandai:1")
        m2 = _make_manual("bandai:1")
        with pytest.raises(DuplicateKeyError):
            merge_manuals([m1, m2], {})

    def test_curated_and_automated(self) -> None:
        auto = _make_manual("bandai:1")
        curated = _make_manual("wave:mk-001", source="wave", sid="mk-001")
        result = merge_manuals([auto], {"wave": [curated]})
        assert len(result) == 2

    def test_duplicate_across_sources(self) -> None:
        auto = _make_manual("bandai:1")
        curated = _make_manual("bandai:1", source="curated", sid="1")
        with pytest.raises(DuplicateKeyError):
            merge_manuals([auto], {"curated": [curated]})

    def test_override_applied(self) -> None:
        auto = _make_manual("bandai:1")
        override = CuratedOverrideEntry(
            manual_source_key="bandai:1",
            set={"title": "Overridden Title"},
            reason="test override",
        )
        result = merge_manuals([auto], {}, [override])
        assert result[0].title == "Overridden Title"

    def test_override_missing_target(self) -> None:
        override = CuratedOverrideEntry(
            manual_source_key="bandai:999",
            set={"title": "New"},
            reason="test",
        )
        with pytest.raises(DuplicateKeyError):
            merge_manuals([], {}, [override])


class TestMergeProductSources:
    def test_empty(self) -> None:
        products, rels = merge_product_sources([])
        assert products == []
        assert rels == []

    def test_single_source(self) -> None:
        ps = _make_product_source("bandai-schedule:en:01_7017", locale="en")
        products, rels = merge_product_sources([ps])
        assert len(products) == 1
        assert products[0].product_key == "bandai-product:01_7017"
        assert products[0].titles == {"en": "Test 01_7017"}

    def test_duplicate_source_key(self) -> None:
        ps1 = _make_product_source("bandai-schedule:en:01_7017")
        ps2 = _make_product_source("bandai-schedule:en:01_7017")
        with pytest.raises(DuplicateKeyError):
            merge_product_sources([ps1, ps2])

    def test_multiple_locales_merged(self) -> None:
        ja = _make_product_source(
            "bandai-schedule:ja:01_7017",
            locale="ja",
            source="bandai_schedule_ja",
            pid="01_7017",
        )
        en = _make_product_source(
            "bandai-schedule:en:01_7017",
            locale="en",
            source="bandai_schedule_en",
            pid="01_7017",
        )
        products, rels = merge_product_sources([ja, en])
        assert len(products) == 1
        assert products[0].titles == {"ja": "Test 01_7017", "en": "Test 01_7017"}

    def test_cross_market_releases(self) -> None:
        ja = _make_product_source(
            "bandai-schedule:ja:01_7017", locale="ja", source="bandai_schedule_ja"
        )
        ja.release = ReleaseInfo(
            source="bandai_schedule_ja",
            locale="ja",
            market="jp",
            release_month="2026-06",
            release_date_precision="month",
            raw="2026年06月",
        )
        en = _make_product_source(
            "bandai-schedule:en:01_7017", locale="en", source="bandai_schedule_en"
        )
        en.release = ReleaseInfo(
            source="bandai_schedule_en",
            locale="en",
            market="en-others",
            release_month="2026-07",
            release_date_precision="month",
            raw="Jul, 2026",
        )
        products, _ = merge_product_sources([ja, en])
        assert len(products[0].releases) == 2  # Both releases preserved

    def test_different_prices(self) -> None:
        ja = _make_product_source(
            "bandai-schedule:ja:01_7017", locale="ja", source="bandai_schedule_ja"
        )
        ja.prices = [
            PriceInfo(
                source="bandai_schedule_ja",
                locale="ja",
                amount=4180.0,
                currency="JPY",
                tax_included=True,
            )
        ]
        en = _make_product_source(
            "bandai-schedule:en:01_7017", locale="en", source="bandai_schedule_en"
        )
        en.prices = [
            PriceInfo(
                source="bandai_schedule_en",
                locale="en",
                amount=3800.0,
                currency="JPY",
                tax_included=False,
            )
        ]
        products, _ = merge_product_sources([ja, en])
        assert len(products[0].prices) == 2


class TestValidateFinalDataset:
    def test_empty(self) -> None:
        errors = validate_final_dataset([], [], [], [])
        assert errors == []

    def test_duplicate_manual_keys(self) -> None:
        m1 = _make_manual("bandai:1")
        m2 = _make_manual("bandai:1")
        errors = validate_final_dataset([m1, m2], [], [], [])
        assert any("Duplicate" in e for e in errors)

    def test_relationship_unknown_target(self) -> None:
        rel = RelationshipRecord(
            relationship_key="rel:test",
            from_key="bandai:1",
            to_key="unknown:key",
            relationship="manual_for_product",
            status="matched",
            method="test",
            confidence=0.5,
            matched_fields=["title"],
            provenance=_make_provenance(),
        )
        errors = validate_final_dataset([], [], [], [rel])
        assert any("unknown" in e.lower() for e in errors)

    def test_relationship_candidate_unknown_target_ok(self) -> None:
        """Candidate relationships may reference unresolved targets."""
        rel = RelationshipRecord(
            relationship_key="rel:candidate",
            from_key="bandai:1",
            to_key="unknown:target",
            relationship="manual_for_product",
            status="candidate",
            provenance=_make_provenance(),
        )
        errors = validate_final_dataset([], [], [], [rel])
        assert errors == []  # Candidate allows unknown targets

    def test_confirmed_requires_method_or_reason(self) -> None:
        rel = RelationshipRecord(
            relationship_key="rel:confirmed_no_method",
            from_key="bandai:1",
            to_key="bandai:2",
            relationship="manual_for_product",
            status="confirmed",
            provenance=_make_provenance(),
        )
        errors = validate_final_dataset(
            [_make_manual("bandai:1"), _make_manual("bandai:2")],
            [], [], [rel],
        )
        assert any("method or reason" in e for e in errors)

    def test_matched_requires_fields(self) -> None:
        rel = RelationshipRecord(
            relationship_key="rel:matched_no_fields",
            from_key="bandai:1",
            to_key="bandai:2",
            relationship="manual_for_product",
            status="matched",
            provenance=_make_provenance(),
        )
        errors = validate_final_dataset(
            [_make_manual("bandai:1"), _make_manual("bandai:2")],
            [], [], [rel],
        )
        assert any("matched_fields" in e for e in errors)
