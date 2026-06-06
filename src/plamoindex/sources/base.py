"""Abstract base class for plamoindex source plugins.

Every source is a plugin. Each source plugin defines how to collect manual
records, product source records, and optionally merged product records from
an official source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from plamoindex.models.manual import ManualRecord
from plamoindex.models.product import ProductRecord, ProductSourceRecord
from plamoindex.models.relationship import RelationshipRecord


@dataclass
class SourceCollection:
    """All normalized records produced by a source in one pass."""

    manuals: list[ManualRecord]
    product_sources: list[ProductSourceRecord]
    relationships: list[RelationshipRecord]

    @classmethod
    def empty(cls) -> "SourceCollection":
        """Return an empty source collection."""
        return cls(manuals=[], product_sources=[], relationships=[])

    @property
    def record_count(self) -> int:
        """Return the total records in this collection."""
        return len(self.manuals) + len(self.product_sources) + len(self.relationships)


class SourcePlugin(ABC):
    """Base class for all plamoindex source plugins.

    Subclasses must define source_id, display_name, and implement the
    collect_manuals and collect_product_sources methods.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Return the unique source identifier (e.g., 'bandai', 'kotobukiya')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Return a human-readable source name (e.g., 'Bandai Manuals')."""
        ...

    @abstractmethod
    def collect_manuals(self) -> list[ManualRecord]:
        """Collect and return manual records from this source.

        Returns:
            A list of normalized ManualRecord instances.
        """
        ...

    def collect_product_sources(self) -> list[ProductSourceRecord]:
        """Collect and return product source records from this source.

        Returns:
            A list of ProductSourceRecord instances.

        Base implementation returns an empty list. Override when the source
        provides product/schedule metadata.
        """
        return []

    def collect_products(self) -> list[ProductRecord]:
        """Collect and return merged product records from this source.

        Returns:
            A list of ProductRecord instances.

        Base implementation returns an empty list. Override when the source
        provides its own product merging logic.
        """
        return []

    def collect_relationships(self) -> list[RelationshipRecord]:
        """Collect and return relationship records from this source.

        Returns:
            A list of RelationshipRecord instances.

        Base implementation returns an empty list. Override when the source
        has explicit relationship data.
        """
        return []

    def collect_all_records(self) -> SourceCollection:
        """Collect all normalized records from this source in one pass.

        Source plugins with multiple record families should override this to
        avoid crawling the same website repeatedly.
        """
        return SourceCollection(
            manuals=self.collect_manuals(),
            product_sources=self.collect_product_sources(),
            relationships=self.collect_relationships(),
        )

    def load_cached_records(self, raw_dir: Path) -> SourceCollection:
        """Load normalized records previously written by collection.

        Base implementation returns no records. Source plugins that support
        `build --raw` override this.
        """
        return SourceCollection.empty()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.source_id}>"
