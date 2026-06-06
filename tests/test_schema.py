"""Tests for Pydantic schema models."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.models.shared import (
    IgnoredDifference,
    ManualRelationRef,
    PriceInfo,
    ProductRelationRef,
    Provenance,
    ReleaseInfo,
    TaxonomyRef,
)


def _make_provenance() -> Provenance:
    return Provenance(
        collector="test",
        collection_method="test",
        collected_at=datetime(2026, 6, 6),
    )


# ---- Provenance ----

class TestProvenance:
    def test_minimal(self) -> None:
        p = Provenance(collector="bandai", collection_method="scrape", collected_at=datetime(2026, 6, 6))
        assert p.collector == "bandai"
        assert p.updated_at is None

    def test_with_updated(self) -> None:
        p = Provenance(
            collector="bandai",
            collection_method="scrape",
            collected_at=datetime(2026, 6, 6),
            updated_at=datetime(2026, 6, 7),
        )
        assert p.updated_at is not None


# ---- ReleaseInfo ----

class TestReleaseInfo:
    def test_minimal_month(self) -> None:
        r = ReleaseInfo(
            source="bandai_schedule_ja",
            locale="ja",
            release_month="2026-06",
            release_date_precision="month",
        )
        assert r.release_month == "2026-06"

    def test_day_precision(self) -> None:
        r = ReleaseInfo(
            source="bandai",
            locale="ja",
            release_date="2026-05-30",
            release_month="2026-05",
            release_date_precision="day",
        )
        assert r.release_date == "2026-05-30"

    def test_raw_text(self) -> None:
        r = ReleaseInfo(
            source="bandai_schedule_ja",
            locale="ja",
            release_month="2026-06",
            release_date_precision="month",
            raw="2026年06月",
        )
        assert r.raw == "2026年06月"

    def test_invalid_date_pattern(self) -> None:
        with pytest.raises(ValidationError):
            ReleaseInfo(
                source="test",
                locale="ja",
                release_date="not-a-date",
                release_date_precision="day",
            )

    def test_invalid_month_pattern(self) -> None:
        with pytest.raises(ValidationError):
            ReleaseInfo(
                source="test",
                locale="ja",
                release_month="2026/06",
                release_date_precision="month",
            )


# ---- PriceInfo ----

class TestPriceInfo:
    def test_tax_included(self) -> None:
        p = PriceInfo(
            source="bandai_schedule_ja",
            locale="ja",
            amount=4180.0,
            currency="JPY",
            tax_included=True,
            raw="4,180円(税10%込)",
        )
        assert p.amount == 4180.0
        assert p.tax_included is True

    def test_tax_excluded(self) -> None:
        p = PriceInfo(
            source="bandai_schedule_en",
            locale="en",
            amount=3800.0,
            currency="JPY",
            tax_included=False,
            raw="3,800Yen",
        )
        assert p.tax_included is False


# ---- TaxonomyRef ----

class TestTaxonomyRef:
    def test_brand_line(self) -> None:
        t = TaxonomyRef(
            taxonomy_key="bandai-schedule:en:brand:hg",
            kind="brand",
            slug="hg",
            line_code="HG",
            line_name="HIGH GRADE",
            label="HG [HIGH GRADE]",
            url="https://global.bandai-hobby.net/en-others/brand/hg/",
        )
        assert t.line_code == "HG"
        assert t.label == "HG [HIGH GRADE]"

    def test_series(self) -> None:
        t = TaxonomyRef(
            taxonomy_key="bandai-schedule:en:series:endlesswaltz",
            kind="series",
            slug="endlesswaltz",
            label="MOBILE SUIT GUNDAM WING series",
            url="https://global.bandai-hobby.net/en-others/series/endlesswaltz/",
        )
        assert t.kind == "series"

    def test_minimal_label_only(self) -> None:
        t = TaxonomyRef(label="Figures")
        assert t.label == "Figures"
        assert t.kind is None


# ---- RelationshipRef types ----

class TestProductRelationRef:
    def test_minimal(self) -> None:
        ref = ProductRelationRef(
            product_key="bandai-product:01_7017",
            status="matched",
            method="title_match",
            confidence=0.97,
        )
        assert ref.product_key == "bandai-product:01_7017"
        assert ref.confidence == 0.97

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ProductRelationRef(product_key="x", status="matched", confidence=1.5)


class TestManualRelationRef:
    def test_minimal(self) -> None:
        ref = ManualRelationRef(
            manual_source_key="bandai:5119",
            status="confirmed",
        )
        assert ref.manual_source_key == "bandai:5119"


# ---- ManualRecord ----

class TestManualRecord:
    def test_minimal_bandai(self) -> None:
        record = ManualRecord(
            manual_source_key="bandai:5119",
            source="bandai",
            source_type="automated",
            manual_source_id="5119",
            title="HG 1/144 メッサーＭ０１型 (ガウマン機)",
            brand="BANDAI SPIRITS",
            provenance=_make_provenance(),
        )
        assert record.manual_source_key == "bandai:5119"
        assert record.schema_version == 1

    def test_with_bilingual_titles(self) -> None:
        record = ManualRecord(
            manual_source_key="bandai:5119",
            source="bandai",
            manual_source_id="5119",
            title="HG 1/144 メッサーＭ０１型 (ガウマン機)",
            title_en="HG 1/144 MESSER TYPE-M01 (GAWMAN USE)",
            localized_titles={
                "ja": "HG 1/144 メッサーＭ０１型 (ガウマン機)",
                "en": "HG 1/144 MESSER TYPE-M01 (GAWMAN USE)",
            },
            brand="BANDAI SPIRITS",
            provenance=_make_provenance(),
        )
        assert record.title_en is not None
        assert record.localized_titles is not None

    def test_with_release_day(self) -> None:
        record = ManualRecord(
            manual_source_key="bandai:5119",
            source="bandai",
            manual_source_id="5119",
            title="test",
            brand="BANDAI SPIRITS",
            release_date="2026-05-30",
            release_month="2026-05",
            release_date_precision="day",
            provenance=_make_provenance(),
        )
        assert record.release_date == "2026-05-30"

    def test_with_release_month_only(self) -> None:
        record = ManualRecord(
            manual_source_key="bandai:5119",
            source="bandai",
            manual_source_id="5119",
            title="test",
            brand="BANDAI SPIRITS",
            release_month="2026-06",
            release_date_precision="month",
            provenance=_make_provenance(),
        )
        assert record.release_month == "2026-06"
        assert record.release_date is None

    def test_day_precision_requires_date(self) -> None:
        with pytest.raises(ValidationError):
            ManualRecord(
                manual_source_key="bandai:5119",
                source="bandai",
                manual_source_id="5119",
                title="test",
                brand="BANDAI SPIRITS",
                release_date_precision="day",
                provenance=_make_provenance(),
            )

    def test_with_related_products(self) -> None:
        record = ManualRecord(
            manual_source_key="bandai:5119",
            source="bandai",
            manual_source_id="5119",
            title="test",
            brand="BANDAI SPIRITS",
            related_products=[
                ProductRelationRef(
                    product_key="bandai-product:01_7017",
                    status="matched",
                    method="bilingual_title_match",
                    confidence=0.97,
                )
            ],
            provenance=_make_provenance(),
        )
        assert len(record.related_products) == 1
        assert record.related_products[0].product_key == "bandai-product:01_7017"

    def test_with_language_specific_pdfs(self) -> None:
        record = ManualRecord(
            manual_source_key="kotobukiya:538",
            source="kotobukiya",
            manual_source_id="538",
            title="ASRA ARCHER Modelers Edition",
            brand="KOTOBUKIYA",
            pdf_url="https://kotobukiya.co.jp/en/instructions/dl-ja/hash",
            pdf_urls={
                "ja": "https://kotobukiya.co.jp/en/instructions/dl-ja/hash",
                "en": "https://kotobukiya.co.jp/en/instructions/dl-en/hash",
            },
            provenance=_make_provenance(),
        )
        assert record.pdf_urls is not None
        assert "en" in record.pdf_urls

    def test_manual_source_key_pattern(self) -> None:
        with pytest.raises(ValidationError):
            ManualRecord(
                manual_source_key="invalid-key",
                source="test",
                manual_source_id="1",
                title="test",
                brand="test",
                provenance=_make_provenance(),
            )

    def test_kotobukiya_record(self) -> None:
        record = ManualRecord(
            manual_source_key="kotobukiya:538",
            source="kotobukiya",
            source_type="automated",
            manual_source_id="538",
            title="ASRA ARCHER Modelers Edition",
            brand="KOTOBUKIYA",
            manufacturer_item_code="PV256",
            source_url="https://www.kotobukiya.co.jp/en/instructions/detail/538/",
            provenance=_make_provenance(),
        )
        assert record.manufacturer_item_code == "PV256"


# ---- ProductSourceRecord ----

class TestProductSourceRecord:
    def test_bandai_en(self) -> None:
        record = ProductSourceRecord(
            product_source_key="bandai-schedule:en:01_7017",
            source="bandai_schedule_en",
            manufacturer="BANDAI SPIRITS",
            locale="en",
            market="en-others",
            product_source_id="01_7017",
            product_url="https://global.bandai-hobby.net/en-others/item/01_7017/",
            title="HG 1/144 GUNDAM SANDROCK CUSTOM EW",
            brand_line=TaxonomyRef(
                taxonomy_key="bandai-schedule:en:brand:hg",
                kind="brand",
                slug="hg",
                line_code="HG",
                line_name="HIGH GRADE",
                label="HG [HIGH GRADE]",
            ),
            release=ReleaseInfo(
                source="bandai_schedule_en",
                locale="en",
                market="en-others",
                release_month="2026-06",
                release_date_precision="month",
                raw="Jun, 2026",
            ),
            prices=[
                PriceInfo(
                    source="bandai_schedule_en",
                    locale="en",
                    market="en-others",
                    amount=3800.0,
                    currency="JPY",
                    tax_included=False,
                    raw="3,800Yen",
                )
            ],
            provenance=_make_provenance(),
        )
        assert record.product_source_key == "bandai-schedule:en:01_7017"
        assert record.brand_line is not None
        assert record.brand_line.line_code == "HG"
        assert record.release is not None
        assert len(record.prices) == 1

    def test_bandai_chinese(self) -> None:
        record = ProductSourceRecord(
            product_source_key="bandai-schedule:zh-Hans:3236",
            source="bandai_schedule_zh",
            manufacturer="BANDAI SPIRITS",
            locale="zh-Hans",
            product_source_id="3236",
            title="HG 1/144 飞翼高达零式",
            brand_line=TaxonomyRef(label="HG", kind="brand"),
            release=ReleaseInfo(
                source="bandai_schedule_zh",
                locale="zh-Hans",
                release_month="2026-06",
                release_date_precision="month",
            ),
            provenance=_make_provenance(),
        )
        assert record.locale == "zh-Hans"


# ---- ProductRecord ----

class TestProductRecord:
    def test_bandai_merged(self) -> None:
        record = ProductRecord(
            product_key="bandai-product:01_7017",
            manufacturer="BANDAI SPIRITS",
            source_type="automated",
            titles={
                "ja": "HG 1/144 サンドロックカスタムEW",
                "en": "HG 1/144 GUNDAM SANDROCK CUSTOM EW",
            },
            releases=[
                ReleaseInfo(
                    source="bandai_schedule_ja",
                    locale="ja",
                    market="jp",
                    release_month="2026-06",
                    release_date_precision="month",
                    raw="2026年06月",
                ),
                ReleaseInfo(
                    source="bandai_schedule_en",
                    locale="en",
                    market="en-others",
                    release_month="2026-07",
                    release_date_precision="month",
                    raw="Jul, 2026",
                ),
            ],
            provenance=_make_provenance(),
        )
        assert record.product_key == "bandai-product:01_7017"
        assert len(record.releases) == 2

    def test_cross_market_release_differences(self) -> None:
        """Different markets may have different release months - this must not fail."""
        record = ProductRecord(
            product_key="bandai-product:01_7017",
            manufacturer="BANDAI SPIRITS",
            titles={"ja": "test", "en": "test"},
            releases=[
                ReleaseInfo(
                    source="bandai_schedule_ja",
                    locale="ja",
                    market="jp",
                    release_month="2026-06",
                    release_date_precision="month",
                ),
                ReleaseInfo(
                    source="bandai_schedule_en",
                    locale="en",
                    market="en-others",
                    release_month="2026-07",
                    release_date_precision="month",
                ),
            ],
            provenance=_make_provenance(),
        )
        months = {r.release_month for r in record.releases if r.release_month}
        assert len(months) == 2  # Different months are fine

    def test_kotobukiya_product(self) -> None:
        record = ProductRecord(
            product_key="kotobukiya-product:p4934054063482",
            manufacturer="KOTOBUKIYA",
            titles={"en": "ASRA ARCHER Modelers Edition"},
            releases=[
                ReleaseInfo(
                    source="kotobukiya_product",
                    locale="en",
                    market="jp-shop",
                    release_month="2024-12",
                    release_date_precision="month",
                    raw="2024.12",
                )
            ],
            prices=[
                PriceInfo(
                    source="kotobukiya_product",
                    locale="en",
                    market="jp-shop",
                    amount=19800.0,
                    currency="JPY",
                    tax_included=True,
                    raw="JPY 19,800 incl. tax",
                ),
                PriceInfo(
                    source="kotobukiya_product",
                    locale="en",
                    market="jp-shop",
                    amount=18000.0,
                    currency="JPY",
                    tax_included=False,
                    raw="JPY 18,000 excl. tax",
                ),
            ],
            provenance=_make_provenance(),
        )
        assert len(record.prices) == 2
        tax_included = [p for p in record.prices if p.tax_included]
        tax_excluded = [p for p in record.prices if not p.tax_included]
        assert len(tax_included) == 1
        assert len(tax_excluded) == 1

    def test_product_key_pattern(self) -> None:
        with pytest.raises(ValidationError):
            ProductRecord(
                product_key="invalid",
                manufacturer="test",
                titles={"en": "test"},
                provenance=_make_provenance(),
            )


# ---- RelationshipRecord ----

class TestRelationshipRecord:
    def test_matched(self) -> None:
        rel = RelationshipRecord(
            relationship_key="rel:manual-product:bandai:5119:bandai-product:01_7017",
            from_key="bandai:5119",
            to_key="bandai-product:01_7017",
            relationship="manual_for_product",
            status="matched",
            method="bilingual_title_match",
            confidence=0.97,
            matched_fields=["manual.title_ja", "manual.title_en", "product.title_ja", "product.title_en"],
            provenance=_make_provenance(),
        )
        assert rel.status == "matched"
        assert rel.confidence == 0.97

    def test_confirmed(self) -> None:
        rel = RelationshipRecord(
            relationship_key="rel:manual-product:kotobukiya:538:kotobukiya-product:p4934054063482",
            from_key="kotobukiya:538",
            to_key="kotobukiya-product:p4934054063482",
            relationship="manual_for_product",
            status="confirmed",
            method="official_instruction_detail_product_link",
            confidence=1.0,
            provenance=_make_provenance(),
        )
        assert rel.status == "confirmed"

    def test_candidate(self) -> None:
        """Candidate relationships don't require method or confidence."""
        rel = RelationshipRecord(
            relationship_key="rel:manual-product:bandai:5119:bandai-product:zh_candidate",
            from_key="bandai:5119",
            to_key="bandai-product:zh_candidate",
            relationship="manual_for_product",
            status="candidate",
            provenance=_make_provenance(),
        )
        assert rel.status == "candidate"

    def test_with_ignored_differences(self) -> None:
        rel = RelationshipRecord(
            relationship_key="rel:manual-product:bandai:5119:bandai-product:01_7017",
            from_key="bandai:5119",
            to_key="bandai-product:01_7017",
            relationship="manual_for_product",
            status="matched",
            method="bilingual_title_match",
            confidence=0.97,
            matched_fields=["title_ja", "title_en"],
            ignored_differences=[
                IgnoredDifference(
                    field="en_release_month",
                    reason="cross-market release dates may differ",
                )
            ],
            provenance=_make_provenance(),
        )
        assert len(rel.ignored_differences) == 1

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            RelationshipRecord(
                relationship_key="rel:test",
                from_key="a",
                to_key="b",
                relationship="manual_for_product",
                status="invalid_status",
                provenance=_make_provenance(),
            )
