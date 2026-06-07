"""Tests for the base collector layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from plamoindex.collector import CollectionResult, CollectorCache
from plamoindex.fetch import FetchResult
from plamoindex.sources.bandai import _product_source_dict_to_record
from plamoindex.sources.bandai_manual import BandaiManualCollector
from plamoindex.sources.bandai_manual import _parse_list_page as parse_bandai_manual_list
from plamoindex.sources.bandai_schedule import (
    BandaiScheduleCollector,
    _parse_en_schedule_page,
    _parse_ja_schedule_page,
    _parse_zh_schedule_page,
)
from plamoindex.sources.bandai_schedule import (
    _parse_product_detail as parse_bandai_product_detail,
)
from plamoindex.sources.kotobukiya import KotobukiyaSource
from plamoindex.sources.kotobukiya_collector import (
    KotobukiyaCollector,
    _parse_instruction_detail,
    _parse_instruction_list,
)
from plamoindex.sources.kotobukiya_collector import (
    _parse_product_detail as parse_kotobukiya_product_detail,
)


class _RepeatingFetch:
    def __init__(self, html: str) -> None:
        self.html = html
        self.calls = 0

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResult:
        self.calls += 1
        return FetchResult(
            url=url,
            status_code=200,
            headers={},
            text=self.html,
            content_hash=f"hash-{self.calls}",
            elapsed=0,
        )

    def close(self) -> None:
        pass


class _NoopFetch:
    def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResult:
        raise AssertionError(f"Unexpected fetch call: {url}")

    def close(self) -> None:
        pass


class _RecordingFetch:
    def __init__(self, html: str) -> None:
        self.html = html
        self.urls: list[str] = []

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResult:
        self.urls.append(url)
        return FetchResult(
            url=url,
            status_code=200,
            headers={},
            text=self.html,
            content_hash=f"hash-{len(self.urls)}",
            elapsed=0,
        )

    def close(self) -> None:
        pass


class TestCollectorCache:
    def test_init_creates_dirs(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "test_source")
        assert cache._records_dir.exists()
        assert cache._manifest == {"pages": {}, "collected_at": None}
        cache.close()

    def test_page_hash_lifecycle(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "test")
        assert cache.get_page_hash("page1") is None

        cache.put_page("page1", "abc123")
        assert cache.get_page_hash("page1") == "abc123"
        cache.close()

    def test_has_page_changed(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "test")
        assert cache.has_page_changed("page1", "newhash") is True

        cache.put_page("page1", "samehash")
        assert cache.has_page_changed("page1", "samehash") is False
        assert cache.has_page_changed("page1", "different") is True
        cache.close()

    def test_save_load_records(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "test")
        records = [{"id": "1", "value": "test"}]
        cache.save_records(records, "test_records.json")
        assert cache.has_records("test_records.json") is True
        loaded = cache.load_records("test_records.json")
        assert loaded == records
        cache.close()

    def test_save_load_single_record(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "test")
        record = {"id": "1", "value": "test"}

        cache.save_record(record, "detail-1.json")

        assert cache.load_record("detail-1.json") == record
        assert cache.load_record("missing.json") is None
        cache.close()

    def test_load_nonexistent_records(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "test")
        loaded = cache.load_records("nonexistent.json")
        assert loaded == []
        cache.close()

    def test_manifest_persists(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "test")
        cache.put_page("page1", "hash1")
        cache.put_page("page2", "hash2")
        cache.close()

        # Re-open and verify
        cache2 = CollectorCache(tmp_path, "test")
        assert cache2.get_page_hash("page1") == "hash1"
        assert cache2.get_page_hash("page2") == "hash2"
        cache2.close()


class TestCollectionResult:
    def test_empty(self) -> None:
        result = CollectionResult()
        assert result.manuals == []
        assert result.product_sources == []
        assert result.relationships == []

    def test_with_data(self) -> None:
        result = CollectionResult(
            manuals=[{"id": "1"}],
            product_sources=[{"id": "ps1"}],
            relationships=[{"from": "a", "to": "b"}],
        )
        assert len(result.manuals) == 1
        assert len(result.product_sources) == 1
        assert len(result.relationships) == 1

    def test_addition(self) -> None:
        r1 = CollectionResult(manuals=[{"id": "1"}])
        r2 = CollectionResult(product_sources=[{"id": "ps1"}])
        combined = r1 + r2
        assert len(combined.manuals) == 1
        assert len(combined.product_sources) == 1


class TestBandaiManualPagination:
    def test_repeated_page_signature_stops_collection(self, tmp_path: Path) -> None:
        html = """
        <div class="manual-item">
          <a href="/menus/detail/1">HG 1/144 Test</a>
          <span class="title-en">HG 1/144 TEST</span>
        </div>
        """
        fetch = _RepeatingFetch(html)
        cache = CollectorCache(tmp_path, "bandai_manual")
        collector = BandaiManualCollector(fetch, cache)  # type: ignore[arg-type]

        entries = collector._collect_list_pages()

        assert fetch.calls == 2
        assert len(entries) == 1
        assert entries[0]["manual_id"] == "1"
        collector.close()


class TestBandaiScheduleWindow:
    def test_product_source_conversion_strips_source_id_whitespace(self) -> None:
        record = _product_source_dict_to_record({
            "source": "bandai_schedule_ja",
            "locale": "ja",
            "product_id": "item-1000112530 ",
            "title": "Test Product",
            "collected_at": "2026-06-06T00:00:00+00:00",
        })

        assert record.product_source_key == "bandai-schedule:ja:item-1000112530"
        assert record.product_source_id == "item-1000112530"

    def test_explicit_month_range_overrides_rolling_window(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        collector = BandaiScheduleCollector(
            _NoopFetch(),  # type: ignore[arg-type]
            cache,
            start_month="198007",
            end_month="198009",
        )

        assert collector._get_month_window() == ["198007", "198008", "198009"]
        collector.close()

    def test_explicit_month_range_can_be_limited_to_next_missing_chunk(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        for locale in ("ja", "en", "zh"):
            cache.save_records([], f"{locale}-198007.json")
        collector = BandaiScheduleCollector(
            _NoopFetch(),  # type: ignore[arg-type]
            cache,
            start_month="198007",
            end_month="198010",
            max_months_per_run=2,
        )

        assert collector._get_month_window() == ["198008", "198009"]
        collector.close()

    def test_limited_month_range_revalidates_newest_chunk_when_complete(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        for month in ("198007", "198008", "198009", "198010"):
            for locale in ("ja", "en", "zh"):
                cache.save_records([], f"{locale}-{month}.json")
        collector = BandaiScheduleCollector(
            _NoopFetch(),  # type: ignore[arg-type]
            cache,
            start_month="198007",
            end_month="198010",
            max_months_per_run=2,
        )

        assert collector._get_month_window() == ["198009", "198010"]
        collector.close()

    def test_locale_month_window_uses_locale_specific_cache(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        cache.save_records([], "ja-198007.json")
        collector = BandaiScheduleCollector(
            _NoopFetch(),  # type: ignore[arg-type]
            cache,
            start_month="198007",
            end_month="198010",
            max_months_per_run=2,
        )

        assert collector._get_locale_month_window("ja") == ["198008", "198009"]
        assert collector._get_locale_month_window("en") == ["198007", "198008"]
        collector.close()

    def test_zh_locale_window_skips_months_before_default_site_start(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        collector = BandaiScheduleCollector(
            _NoopFetch(),  # type: ignore[arg-type]
            cache,
            start_month="198007",
            end_month="198912",
            max_months_per_run=6,
        )

        assert collector._get_locale_month_window("zh-Hans") == [
            "198909",
            "198910",
            "198911",
            "198912",
        ]
        collector.close()

    def test_locale_start_month_can_be_overridden(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        collector = BandaiScheduleCollector(
            _NoopFetch(),  # type: ignore[arg-type]
            cache,
            start_month="198007",
            end_month="198912",
            max_months_per_run=3,
            locale_start_months={"zh-Hans": "1988-01"},
        )

        assert collector._get_locale_month_window("zh-Hans") == [
            "198801",
            "198802",
            "198803",
        ]
        collector.close()

    def test_collect_all_merges_schedule_product_sources_with_existing_cache(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        cache.save_records(
            [
                {
                    "source": "bandai_schedule_ja",
                    "locale": "ja",
                    "product_id": "01_0001",
                    "title": "Existing",
                }
            ],
            "product_sources.json",
        )
        collector = BandaiScheduleCollector(_NoopFetch(), cache)  # type: ignore[arg-type]

        monkeypatch.setattr(
            collector,
            "_collect_ja_schedule",
            lambda: CollectionResult(
                product_sources=[
                    {
                        "source": "bandai_schedule_ja",
                        "locale": "ja",
                        "product_id": "01_0002",
                        "title": "Current",
                    }
                ],
            ),
        )
        monkeypatch.setattr(collector, "_collect_en_schedule", lambda: CollectionResult())
        monkeypatch.setattr(collector, "_collect_zh_schedule", lambda: CollectionResult())

        result = collector.collect_all()

        assert {
            record["product_id"]
            for record in result.product_sources
        } == {"01_0001", "01_0002"}
        assert {
            record["product_id"]
            for record in cache.load_records("product_sources.json")
        } == {"01_0001", "01_0002"}
        collector.close()

    def test_bandai_schedule_detail_uses_cached_record_without_fetch(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        cached_detail = {"taxonomy": [{"kind": "brand", "label": "HG"}]}
        cache.save_record(cached_detail, "product-detail-ja-01_0001.json")
        collector = BandaiScheduleCollector(_NoopFetch(), cache)  # type: ignore[arg-type]

        detail = collector._fetch_product_detail(
            "01_0001",
            "https://bandai-hobby.net/item/{product_id}/",
            "ja",
        )

        assert detail == cached_detail
        collector.close()

    def test_zh_month_fetch_uses_hyphenated_month_url(self, tmp_path: Path) -> None:
        html = """
        <a class="c-card p-card -landscape" href="/index/index/detail/id/42">
          <div class="p-card__tit">测试商品</div>
        </a>
        """
        fetch = _RecordingFetch(html)
        cache = CollectorCache(tmp_path, "bandai_schedule")
        collector = BandaiScheduleCollector(fetch, cache)  # type: ignore[arg-type]

        entries = collector._fetch_zh_month("198909")

        assert fetch.urls == [
            "https://bandaihobbysite.cn/index/index/schedule/month/1989-09"
        ]
        assert entries[0]["release_month"] == "1989-09"
        collector.close()

    def test_zh_schedule_collects_the_configured_month_window(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = CollectorCache(tmp_path, "bandai_schedule")
        collector = BandaiScheduleCollector(_NoopFetch(), cache)  # type: ignore[arg-type]
        months_seen: list[str] = []

        monkeypatch.setattr(
            collector,
            "_get_locale_month_window",
            lambda locale: ["198909", "198910"],
        )

        def fetch_zh_month(year_month: str) -> list[dict[str, str]]:
            months_seen.append(year_month)
            return [
                {
                    "cn_id": year_month,
                    "product_source_id": year_month,
                    "locale": "zh-Hans",
                    "title": f"ZH {year_month}",
                }
            ]

        monkeypatch.setattr(collector, "_fetch_zh_month", fetch_zh_month)
        monkeypatch.setattr(collector, "_fetch_zh_product_detail", lambda cn_id: None)

        result = collector._collect_zh_schedule()

        assert months_seen == ["198909", "198910"]
        assert [entry["cn_id"] for entry in result.product_sources] == [
            "198909",
            "198910",
        ]
        collector.close()


class TestKotobukiyaCollectorRelationships:
    def test_bandai_manual_detail_uses_cached_record_without_fetch(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "bandai_manual")
        cached_detail = {"product_code": "5061234"}
        cache.save_record(cached_detail, "detail-5119.json")
        collector = BandaiManualCollector(_NoopFetch(), cache)  # type: ignore[arg-type]

        detail = collector._fetch_detail("5119")

        assert detail == cached_detail
        collector.close()

    def test_kotobukiya_instruction_detail_uses_cached_record_without_fetch(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "kotobukiya")
        cached_detail = {"product_link": "https://www.kotobukiya.co.jp/en/product/detail/p1/"}
        cache.save_record(cached_detail, "instruction-detail-538.json")
        collector = KotobukiyaCollector(_NoopFetch(), cache)  # type: ignore[arg-type]

        detail = collector._fetch_detail("538")

        assert detail == cached_detail
        collector.close()

    def test_kotobukiya_product_detail_uses_cached_record_without_fetch(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "kotobukiya")
        cached_detail = {"title": "Cached Product"}
        cache.save_record(cached_detail, "product-detail-p1.json")
        collector = KotobukiyaCollector(_NoopFetch(), cache)  # type: ignore[arg-type]

        detail = collector._fetch_product_detail("p1")

        assert detail == cached_detail
        collector.close()

    def test_duplicate_product_sources_are_saved_once(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = CollectorCache(tmp_path, "kotobukiya")
        collector = KotobukiyaCollector(_NoopFetch(), cache)  # type: ignore[arg-type]
        product_link = "https://www.kotobukiya.co.jp/en/product/detail/p4934054083237/"
        fetch_calls: list[str] = []

        monkeypatch.setattr(
            collector,
            "_collect_list_pages",
            lambda: [
                {"instruction_id": "538", "title": "Manual 1", "product_link": product_link},
                {"instruction_id": "228", "title": "Manual 2", "product_link": product_link},
            ],
        )
        monkeypatch.setattr(collector, "_fetch_detail", lambda instruction_id: {})

        def fetch_product_detail(product_id: str) -> dict[str, str]:
            fetch_calls.append(product_id)
            return {"title": "Shared Product"}

        monkeypatch.setattr(collector, "_fetch_product_detail", fetch_product_detail)

        result = collector.collect_all()

        assert fetch_calls == ["p4934054083237"]
        assert [p["product_source_key"] for p in result.product_sources] == [
            "kotobukiya-product:en:p4934054083237"
        ]
        assert [r["from_key"] for r in result.relationships] == [
            "kotobukiya:538",
            "kotobukiya:228",
        ]
        assert {r["to_key"] for r in result.relationships} == {
            "kotobukiya-product:p4934054083237"
        }
        collector.close()

    def test_relationship_is_not_emitted_when_product_source_cannot_be_built(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = CollectorCache(tmp_path, "kotobukiya")
        collector = KotobukiyaCollector(_NoopFetch(), cache)  # type: ignore[arg-type]

        monkeypatch.setattr(
            collector,
            "_collect_list_pages",
            lambda: [
                {
                    "instruction_id": "291",
                    "title": "Manual",
                    "product_link": "https://www.kotobukiya.co.jp/en/product/detail/p4934054261000/",
                }
            ],
        )
        monkeypatch.setattr(collector, "_fetch_detail", lambda instruction_id: {})
        monkeypatch.setattr(
            collector,
            "_fetch_product_detail",
            lambda product_id: {"title": "Unusable Product"},
        )
        monkeypatch.setattr(collector, "_build_product_source", lambda product_id, detail: None)

        result = collector.collect_all()

        assert result.product_sources == []
        assert result.relationships == []
        collector.close()


class TestKotobukiyaCachedRecords:
    def test_load_cached_records_dedupes_product_sources(self, tmp_path: Path) -> None:
        cache = CollectorCache(tmp_path, "kotobukiya")
        product = {
            "product_source_id": "p4934054083237",
            "product_source_key": "kotobukiya-product:en:p4934054083237",
            "source": "kotobukiya_product",
            "manufacturer": "KOTOBUKIYA",
            "locale": "en",
            "market": "jp-shop",
            "title": "Shared Product",
            "collected_at": "2026-06-06T00:00:00+00:00",
        }
        cache.save_records(
            [
                {"instruction_id": "538", "title": "Manual 1"},
                {"instruction_id": "228", "title": "Manual 2"},
            ],
            "manuals.json",
        )
        cache.save_records([product, product.copy()], "product_sources.json")
        cache.save_records(
            [
                {
                    "from_key": "kotobukiya:538",
                    "to_key": "kotobukiya-product:p4934054083237",
                    "relationship": "manual_for_product",
                    "status": "confirmed",
                    "method": "official_instruction_detail_product_link",
                },
                {
                    "from_key": "kotobukiya:228",
                    "to_key": "kotobukiya-product:p4934054083237",
                    "relationship": "manual_for_product",
                    "status": "confirmed",
                    "method": "official_instruction_detail_product_link",
                },
            ],
            "relationships.json",
        )
        cache.close()

        collection = KotobukiyaSource().load_cached_records(tmp_path)

        assert len(collection.product_sources) == 1
        assert len(collection.relationships) == 2
        assert collection.product_sources[0].product_source_key == (
            "kotobukiya-product:en:p4934054083237"
        )


class TestLiveHtmlParserShapes:
    def test_bandai_manual_result_card_splits_titles_and_release(self) -> None:
        html = """
        <div class="bl_result_item">
          <a href="/menus/detail/5119">
            <div class="bl_result_img"><img src="https://bandai-hobby.net/images/2815163.jpg"></div>
            <div class="bl_result_detail">
              <div class="bl_result_name">
                HG 1/144 メッサーＭ０１型 (ガウマン機)
                <span class="bl_result_name_en">HG 1/144 MESSER TYPE-M01 (GAWMAN USE）</span>
              </div>
              <dl class="bl_result_caption"><dt>発売日</dt><dd>2026年5月30日発売</dd></dl>
            </div>
          </a>
        </div>
        """

        entries = parse_bandai_manual_list(html, "https://manual.bandai-hobby.net/menus?page=1")

        assert len(entries) == 1
        entry = entries[0]
        assert entry["manual_id"] == "5119"
        assert entry["title_ja"] == "HG 1/144 メッサーＭ０１型 (ガウマン機)"
        assert entry["title_en"] == "HG 1/144 MESSER TYPE-M01 (GAWMAN USE）"
        assert entry["release_date"] == "2026-05-30"
        assert entry["release_month"] == "2026-05"

    def test_bandai_ja_schedule_card_uses_card_fields(self) -> None:
        html = """
        <a class="c-card p-card -landscape" href="https://bandai-hobby.net/item/01_7185/">
          <div class="p-card__img"><img alt="プラコロ進化セット フシギバナ 01" src="/img.jpg"></div>
          <div class="p-card__explain -landscape">
            <div class="p-card__tit">プラコロ進化セット フシギバナ 01</div>
            <div class="p-card__under">
              <div class="p-card__price">2,530円(税10%込)</div>
              <div class="p-card_date">2026年12月</div>
            </div>
          </div>
        </a>
        """

        entries = _parse_ja_schedule_page(html, "202612")

        assert len(entries) == 1
        entry = entries[0]
        assert entry["product_id"] == "01_7185"
        assert entry["title_ja"] == "プラコロ進化セット フシギバナ 01"
        assert entry["title_ja"] == entry["title"]
        assert entry["price_amount"] == 2530.0
        assert entry["release_month"] == "2026-12"

    def test_bandai_en_schedule_card_uses_card_fields(self) -> None:
        html = """
        <a class="c-card p-card -landscape" href="https://global.bandai-hobby.net/en-others/item/01_7204/">
          <div class="p-card__img"><img alt="GUNDAM ASSEMBLE DELUXE SET 02 [DX02]" src="/img.jpg"></div>
          <div class="p-card__explain -landscape">
            <div class="p-card__tit">GUNDAM ASSEMBLE DELUXE SET 02 [DX02]</div>
            <div class="p-card__under">
              <div class="p-card__price">13,000Yen</div>
              <div class="p-card_date">Dec, 2026</div>
            </div>
          </div>
        </a>
        """

        entries = _parse_en_schedule_page(html, "202612")

        assert len(entries) == 1
        entry = entries[0]
        assert entry["product_id"] == "01_7204"
        assert entry["title_en"] == "GUNDAM ASSEMBLE DELUXE SET 02 [DX02]"
        assert entry["price_amount"] == 13000.0
        assert entry["release_month"] == "2026-12"

    def test_bandai_zh_schedule_card_uses_card_fields(self) -> None:
        html = """
        <a class="c-card p-card -landscape" href="/index/index/detail/id/3428">
          <div class="p-card__img"><img alt="HG 兽犬" src="/product.jpg"></div>
          <div class="p-card__explain -landscape">
            <div class="p-card__tit">HG 兽犬</div>
            <div class="p-card__under">
              <div class="p-card__price">日本地区建议零售价：<br>4,180日元(含税)</div>
              <div class="p-card_date">2026年06月发售</div>
            </div>
          </div>
        </a>
        """

        entries = _parse_zh_schedule_page(html)

        assert len(entries) == 1
        entry = entries[0]
        assert entry["cn_id"] == "3428"
        assert entry["title_zh"] == "HG 兽犬"
        assert entry["price_amount"] == 4180.0
        assert entry["release_month"] == "2026-06"

    def test_bandai_product_detail_uses_product_metadata_rows(self) -> None:
        html = """
        <html>
          <body>
            <div class="pg-products__details">
              <dl class="pg-products__detail">
                <dt class="pg-products__label"><span>価格</span></dt>
                <dd class="pg-products__labelTxt">2,530 円(税10%込)</dd>
                <dt class="pg-products__label"><span>発売日</span></dt>
                <dd class="pg-products__labelTxt">2026年12月</dd>
              </dl>
            </div>
            <div class="copyright">©2006-2020</div>
            <a class="c-card__flat p-card__flat" href="https://bandai-hobby.net/brand/plakoro/">
              <span class="p-card__flatTit">プラコロ</span>
            </a>
            <a class="c-card__flat p-card__flat" href="https://bandai-hobby.net/series/pokemon/">
              <span class="p-card__flatTit">ポケットモンスター</span>
            </a>
          </body>
        </html>
        """

        detail = parse_bandai_product_detail(
            html,
            "https://bandai-hobby.net/item/01_7185/",
            "ja",
            "01_7185",
        )

        assert detail["release_month"] == "2026-12"
        assert detail["release_raw"] == "2026年12月"
        assert detail["price_amount"] == 2530.0
        assert detail["price_tax_included"] is True
        assert detail["taxonomy"] == [
            {
                "label": "プラコロ",
                "url": "https://bandai-hobby.net/brand/plakoro/",
                "kind": "brand",
                "slug": "plakoro",
            },
            {
                "label": "ポケットモンスター",
                "url": "https://bandai-hobby.net/series/pokemon/",
                "kind": "series",
                "slug": "pokemon",
            },
        ]

    def test_kotobukiya_instruction_card_uses_card_fields(self) -> None:
        html = """
        <li class="manualList_item">
          <div class="manualList_itemInner">
            <div class="manualList_card">
              <p class="manualList_work"><span>MEGAMI DEVICE</span></p>
              <p class="manualList_title">ASRA ARCHER Modelers Edition</p>
              <dl class="manualList_proNumber"><dt>Product Code：</dt><dd>PV256</dd></dl>
              <div class="manualList_footer">
                <div class="manualList_manual">
                  <a class="btn" href="/en/instructions/detail/538/"><span>Instructions (JPN/ENG)</span></a>
                </div>
                <div class="manualList_more">
                  <a href="/en/product/detail/p4934054063482/"><span>Product Details</span></a>
                </div>
              </div>
            </div>
            <div class="manualList_hero">
              <img src="/files_thumbnail/product/PV256_eye.jpg/300.jpg">
            </div>
          </div>
        </li>
        """

        entries = _parse_instruction_list(html, "https://www.kotobukiya.co.jp/en/instructions/")

        assert len(entries) == 1
        entry = entries[0]
        assert entry["instruction_id"] == "538"
        assert entry["title"] == "ASRA ARCHER Modelers Edition"
        assert entry["image_url"] == "https://www.kotobukiya.co.jp/files_thumbnail/product/PV256_eye.jpg/300.jpg"
        assert entry["manufacturer_item_code"] == "PV256"
        assert entry["languages"] == ["ja", "en"]
        assert entry["product_link"] == "https://www.kotobukiya.co.jp/en/product/detail/p4934054063482/"

    def test_kotobukiya_instruction_detail_prefers_view_product_details_link(self) -> None:
        html = """
        <html>
          <head><title>Instruction Manuals｜ASRA ARCHER Modelers Edition｜KOTOBUKIYA</title></head>
          <body>
            <aside><a href="/en/product/detail/p4934054083237/">CREST CR-C98E2 Assault Type</a></aside>
            <article class="contents_main">
              <h1>Instruction Manuals｜ASRA ARCHER Modelers Edition</h1>
              <a href="/en/instructions/dl-ja/token/">Instructions (JPN)</a>
              <a href="/en/instructions/dl-en/token/">Instructions (ENG)</a>
              <a class="btn btn-color01" href="/en/product/detail/p4934054063482/">
                <span>View Product Details</span>
              </a>
            </article>
          </body>
        </html>
        """

        detail = _parse_instruction_detail(
            html,
            "https://www.kotobukiya.co.jp/en/instructions/detail/538/",
            "538",
        )

        assert detail["title"] == "ASRA ARCHER Modelers Edition"
        assert detail["product_link"] == "https://www.kotobukiya.co.jp/en/product/detail/p4934054063482/"
        assert detail["pdf_urls"] == {
            "ja": "https://www.kotobukiya.co.jp/en/instructions/dl-ja/token/",
            "en": "https://www.kotobukiya.co.jp/en/instructions/dl-en/token/",
        }

    def test_kotobukiya_product_detail_uses_header_and_spec_table(self) -> None:
        html = """
        <html>
          <body>
            <h1>ASRA ARCHER Modelers Edition</h1>
            <div class="detailHeader_side">
              <dl class="detailHeader_set detailHeader_set-release">
                <dt>Release Month</dt><dd>2024.12</dd>
              </dl>
              <dl class="detailHeader_set detailHeader_set-price">
                <dt>Price</dt>
                <dd>
                  <span class="detailHeader_price detailHeader_price-taxIn">
                    <small>JPY </small>19,800<small> incl. tax</small>
                  </span>
                  <span class="detailHeader_price detailHeader_price-taxEx">
                    <small>JPY </small>18,000<small> excl. tax</small>
                  </span>
                </dd>
              </dl>
            </div>
            <div class="grid grid-specTable">
              <table>
                <tr><th>Series</th><td><a href="/en/title/megamidevice/">MEGAMI DEVICE</a></td></tr>
                <tr><th>Product Series</th><td><a href="/en/series/unpainted-figures/">Unpainted Figures</a></td></tr>
                <tr><th>Scale</th><td>2/1</td></tr>
                <tr><th>Size</th><td>360mm tall</td></tr>
                <tr><th>Specifications</th><td><ul><li>Unpainted Figure / Kit</li></ul></td></tr>
                <tr><th>Product Material</th><td>PVC (Phthalate-free)・ABS</td></tr>
                <tr><th>Age Rating</th><td>Ages 15 and up</td></tr>
                <tr><th>Sculptor(s)</th><td>BRAIN, KOTOBUKIYA</td></tr>
                <tr><th>Product Code</th><td>PV256</td></tr>
              </table>
            </div>
            <div class="blogList_txt">Release Month 2025.11 Price JPY 1</div>
          </body>
        </html>
        """

        detail = parse_kotobukiya_product_detail(
            html,
            "https://www.kotobukiya.co.jp/en/product/detail/p4934054063482/",
            "p4934054063482",
        )

        assert detail["title"] == "ASRA ARCHER Modelers Edition"
        assert detail["release"]["release_month"] == "2024-12"
        assert detail["prices"] == [
            {
                "source": "kotobukiya_product",
                "locale": "en",
                "market": "jp-shop",
                "amount": 19800.0,
                "currency": "JPY",
                "tax_included": True,
                "raw": "JPY 19,800 incl. tax",
            },
            {
                "source": "kotobukiya_product",
                "locale": "en",
                "market": "jp-shop",
                "amount": 18000.0,
                "currency": "JPY",
                "tax_included": False,
                "raw": "JPY 18,000 excl. tax",
            },
        ]
        assert detail["series"] == {
            "label": "MEGAMI DEVICE",
            "kind": "series",
            "url": "https://www.kotobukiya.co.jp/en/title/megamidevice/",
        }
        assert detail["product_series"] == {
            "label": "Unpainted Figures",
            "kind": "product_series",
            "url": "https://www.kotobukiya.co.jp/en/series/unpainted-figures/",
        }
        assert detail["specs"]["scale"] == "2/1"
        assert detail["specs"]["specifications"] == ["Unpainted Figure / Kit"]
        assert detail["specs"]["sculptors"] == ["BRAIN", "KOTOBUKIYA"]
        assert detail["manufacturer_item_code"] == "PV256"
