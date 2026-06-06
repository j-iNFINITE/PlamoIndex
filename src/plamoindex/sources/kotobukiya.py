"""Kotobukiya source plugin stub.

Kotobukiya sources include:
- kotobukiya: Instruction pages at kotobukiya.co.jp/en/instructions/
- kotobukiya_product: Product detail pages at kotobukiya.co.jp/en/product/detail/

Full collector implementation requires:
1. Crawling kotobukiya.co.jp/en/instructions/ list and detail pages.
2. Extracting PDF URLs (Japanese and English), preview images, product code.
3. Following product detail links from instruction detail pages.
4. Extracting product metadata: category, series, release, price, specs.
5. Confirming manual-to-product relationships via official links.
"""

from __future__ import annotations

from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord
from plamoindex.sources.base import SourcePlugin


class KotobukiyaSource(SourcePlugin):
    """Kotobukiya instruction source plugin.

    Collects manual metadata from kotobukiya.co.jp/en/instructions/.
    """

    @property
    def source_id(self) -> str:
        return "kotobukiya"

    @property
    def display_name(self) -> str:
        return "Kotobukiya Instructions"

    def collect_manuals(self) -> list[ManualRecord]:
        # TODO: Implement Kotobukiya instruction list/detail scraping.
        return []

    def collect_product_sources(self) -> list[ProductSourceRecord]:
        # TODO: Implement Kotobukiya product detail scraping.
        return []

    def collect_products(self) -> list[ProductRecord]:
        # TODO: Implement Kotobukiya product merging.
        return []

    def collect_relationships(self) -> list[RelationshipRecord]:
        # TODO: Implement Kotobukiya manual-product relationship extraction.
        return []
