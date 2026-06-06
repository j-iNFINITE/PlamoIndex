"""Bandai source plugin stub.

Bandai sources include:
- bandai: Manual pages at manual.bandai-hobby.net
- bandai_schedule_ja: Japanese schedule at bandai-hobby.net/schedule/
- bandai_schedule_en: English schedule at global.bandai-hobby.net/en-others/schedule/
- bandai_schedule_zh: Chinese schedule at bandaihobbysite.cn/schedule

Full collector implementation requires:
1. Crawling manual.bandai-hobby.net list pages and detail pages.
2. Crawling bandai-hobby.net/schedule/ month pages and detail pages.
3. Crawling global.bandai-hobby.net/en-others/schedule/ month pages and detail pages.
4. Crawling bandaihobbysite.cn/schedule month pages and detail pages.
5. Normalizing titles (Japanese, English, Chinese).
6. Parsing taxonomy from detail pages (brand_line, series).
7. Manual-to-product association using bilingual title pairs.
"""

from __future__ import annotations

from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.sources.base import SourcePlugin


class BandaiSource(SourcePlugin):
    """Bandai manual source plugin.

    Collects manual metadata from manual.bandai-hobby.net.
    """

    @property
    def source_id(self) -> str:
        return "bandai"

    @property
    def display_name(self) -> str:
        return "Bandai Manuals"

    def collect_manuals(self) -> list[ManualRecord]:
        # TODO: Implement Bandai manual list/detail scraping.
        return []

    def collect_product_sources(self) -> list[ProductSourceRecord]:
        # TODO: Implement Bandai schedule/product scraping (ja/en/zh).
        return []

    def collect_products(self) -> list[ProductRecord]:
        # TODO: Implement Bandai product merging from ja/en shared ids.
        return []

    def collect_relationships(self) -> list[RelationshipRecord]:
        # TODO: Implement Bandai manual-product association.
        return []
