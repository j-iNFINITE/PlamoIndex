"""Tests for the base collector layer."""

from __future__ import annotations

from pathlib import Path

from plamoindex.collector import CollectionResult, CollectorCache


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
        loaded = cache.load_records("test_records.json")
        assert loaded == records
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
