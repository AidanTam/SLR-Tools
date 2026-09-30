"""Core data structures passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# The four compliance states. "Not Addressed" matters because reports arrive
# at any stage of completion — missing is different from wrong.
STATUS_COMPLIANT = "Compliant"
STATUS_PARTIAL = "Partial"
STATUS_NON_COMPLIANT = "Non-Compliant"
STATUS_NOT_ADDRESSED = "Not Addressed"
# The requirement is conditional and its condition doesn't hold (e.g. no
# historical estimate is disclosed, or the report states the section is not
# applicable). Mirrors the "N/A" option in the SLR checklist's own dropdown.
STATUS_NOT_APPLICABLE = "Not Applicable"

VALID_STATUSES = {
    STATUS_COMPLIANT,
    STATUS_PARTIAL,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
}


@dataclass
class Page:
    """One page of the source report."""
    number: int          # 1-based page number as it appears in the file
    text: str


@dataclass
class Criterion:
    """One atomic requirement extracted from a company checklist."""
    id: str
    text: str
    category: str = ""      # optional grouping label from the checklist
    item_id: str = ""       # mapped NI 43-101 Item, e.g. "item_14" (may be empty)
    item_title: str = ""


@dataclass
class Chunk:
    """A retrievable slice of the report, with exact page attribution."""
    text: str
    page: int
    item_id: str = ""
    item_title: str = ""


@dataclass
class Finding:
    """The verdict for one criterion."""
    criterion: Criterion
    status: str
    confidence: float           # 0.0 - 1.0, model's self-reported confidence
    rationale: str
    evidence: str = ""          # quoted text from the report supporting the verdict
    pages: List[int] = field(default_factory=list)
    error: str = ""             # populated if the check failed to run
    method: str = "llm"         # "python" (deterministic, no model call) or "llm"
