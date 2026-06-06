"""RelationshipRecord schema model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from plamoindex.models.shared import IgnoredDifference, Provenance

_ALLOWED_STATUSES = frozenset({"confirmed", "matched", "candidate", "rejected", "unmapped"})


class RelationshipRecord(BaseModel):
    """A standalone relationship record connecting two entities.

    Relationships connect manuals, product source records, and merged products.
    They provide explicit audit trails for how entities relate to each other.

    Status meanings:
    - confirmed: explicit official link or curated confirmed mapping.
    - matched: high-confidence automatic match.
    - candidate: plausible but needs review.
    - rejected: explicitly rejected candidate.
    - unmapped: no candidate.
    """

    schema_version: int = Field(default=1, description="Data contract version")

    # Identity fields
    relationship_key: str = Field(
        ...,
        description="Globally unique relationship key (e.g., 'rel:manual-product:bandai:5119:bandai-product:01_7017')",
    )
    from_key: str = Field(..., description="Source entity key (manual_source_key or product_key)")
    to_key: str = Field(..., description="Target entity key (manual_source_key or product_key)")

    # Relationship type and status
    relationship: str = Field(..., description="Type of relationship (e.g., 'manual_for_product')")
    status: str = Field(
        ...,
        description="Relationship status: confirmed, matched, candidate, rejected, unmapped",
    )

    # Match details
    method: str | None = Field(default=None, description="Method used to determine the relationship")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    matched_fields: list[str] | None = Field(
        default=None,
        description="Fields that matched between the two entities",
    )
    ignored_differences: list[IgnoredDifference] | None = Field(
        default=None,
        description="Field differences intentionally ignored",
    )
    reason: str | None = Field(default=None, description="Human-readable reason for the relationship")

    # Provenance
    provenance: Provenance = Field(..., description="Provenance metadata")

    def model_post_init(self, __context: Any) -> None:
        """Validate relationship status after init."""
        if self.status not in _ALLOWED_STATUSES:
            allowed = ", ".join(sorted(_ALLOWED_STATUSES))
            raise ValueError(f"Invalid status '{self.status}'. Allowed: {allowed}")
        return super().model_post_init(__context)
