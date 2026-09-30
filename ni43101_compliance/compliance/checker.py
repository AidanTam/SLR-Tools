"""Judge a single criterion against the report, using only retrieved excerpts.

This is where the context problem is solved: the model never sees the whole
report, only the handful of most-relevant, page-cited chunks for this one
requirement.
"""

from __future__ import annotations

from typing import List

from .index import ReportIndex
from .llm import OllamaClient
from .models import (
    STATUS_NOT_ADDRESSED,
    VALID_STATUSES,
    Chunk,
    Criterion,
    Finding,
)

_SYSTEM = (
    "You are a QP-assisting compliance reviewer for NI 43-101 technical reports. "
    "You are given ONE requirement and excerpts from the report (each labeled with "
    "its page number). Decide whether the report satisfies the requirement, using "
    "ONLY the excerpts provided. Do not assume facts that are not shown.\n\n"
    "Return ONLY valid JSON:\n"
    "{\n"
    '  "status": "Compliant" | "Partial" | "Non-Compliant" | "Not Addressed",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "evidence": "a short direct quote from the excerpts, or empty",\n'
    '  "pages": [page numbers the evidence came from],\n'
    '  "rationale": "one or two sentences explaining the verdict"\n'
    "}\n\n"
    "Definitions:\n"
    "- Compliant: the requirement is fully and clearly addressed.\n"
    "- Partial: partially addressed, or present but incomplete.\n"
    "- Non-Compliant: addressed but the disclosure is deficient or contradicts the requirement.\n"
    "- Not Addressed: the excerpts contain nothing relevant to the requirement.\n"
    "If the excerpts do not contain the information, prefer 'Not Addressed' over guessing."
)


def _format_excerpts(chunks: List[Chunk]) -> str:
    blocks = []
    for chunk in chunks:
        label = f"[Page {chunk.page}"
        if chunk.item_title:
            label += f" | {chunk.item_title}"
        label += "]"
        blocks.append(f"{label}\n{chunk.text}")
    return "\n\n---\n\n".join(blocks)


def check_criterion(
    criterion: Criterion,
    index: ReportIndex,
    llm: OllamaClient,
    top_k: int,
    item_boost: float,
    max_context_chars: int,
) -> Finding:
    try:
        query_vec = llm.embed(criterion.text)
    except Exception as exc:
        return Finding(
            criterion=criterion,
            status=STATUS_NOT_ADDRESSED,
            confidence=0.0,
            rationale="",
            error=f"Embedding failed: {exc}",
        )

    chunks = index.retrieve(
        query_vec,
        top_k=top_k,
        item_id=criterion.item_id,
        item_boost=item_boost,
        max_chars=max_context_chars,
    )

    if not chunks:
        return Finding(
            criterion=criterion,
            status=STATUS_NOT_ADDRESSED,
            confidence=0.5,
            rationale="No relevant text was retrieved from the report.",
        )

    user = (
        f"Requirement:\n{criterion.text}\n\n"
        f"Report excerpts:\n\n{_format_excerpts(chunks)}"
    )
    try:
        result = llm.chat_json(_SYSTEM, user)
    except Exception as exc:
        return Finding(
            criterion=criterion,
            status=STATUS_NOT_ADDRESSED,
            confidence=0.0,
            rationale="",
            error=f"Verdict generation failed: {exc}",
        )

    status = str(result.get("status", "")).strip()
    if status not in VALID_STATUSES:
        status = STATUS_NOT_ADDRESSED

    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    pages = result.get("pages", [])
    if not isinstance(pages, list):
        pages = []
    clean_pages = []
    for p in pages:
        try:
            clean_pages.append(int(p))
        except (TypeError, ValueError):
            continue
    # Fall back to the pages we actually retrieved from if the model gave none.
    if not clean_pages:
        clean_pages = sorted({c.page for c in chunks[:3]})

    return Finding(
        criterion=criterion,
        status=status,
        confidence=confidence,
        rationale=str(result.get("rationale", "")).strip(),
        evidence=str(result.get("evidence", "")).strip(),
        pages=clean_pages,
    )
