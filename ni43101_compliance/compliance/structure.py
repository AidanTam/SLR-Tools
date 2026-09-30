"""Knowledge of the NI 43-101 Form 43-101F1 standard structure.

Two jobs:
  1. Detect where each of the 27 standard Items begins in a report, so every
     page can be tagged with the Item it belongs to.
  2. Map a free-text checklist criterion to the Item it most likely concerns.

This is used as a *retrieval boost*, never a hard filter — imperfect detection
degrades gracefully because semantic search still finds the right text.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .models import Page

# (item_id, number, canonical title, keywords for criterion mapping)
ITEMS: List[Tuple[str, int, str, List[str]]] = [
    ("item_1", 1, "Summary", ["summary", "executive summary"]),
    ("item_2", 2, "Introduction", ["introduction", "terms of reference", "purpose"]),
    ("item_3", 3, "Reliance on Other Experts", ["reliance", "other experts", "legal", "disclaimer"]),
    ("item_4", 4, "Property Description and Location", ["property description", "location", "tenure", "claim", "mineral title", "royalt"]),
    ("item_5", 5, "Accessibility, Climate, Local Resources, Infrastructure and Physiography", ["accessibility", "climate", "physiography", "local resources", "infrastructure access"]),
    ("item_6", 6, "History", ["history", "historical", "previous owners", "prior exploration"]),
    ("item_7", 7, "Geological Setting and Mineralization", ["geological setting", "geology", "mineralization", "lithology", "structure"]),
    ("item_8", 8, "Deposit Types", ["deposit type", "deposit model", "genetic model"]),
    ("item_9", 9, "Exploration", ["exploration", "geophysic", "geochem", "survey", "trenching"]),
    ("item_10", 10, "Drilling", ["drilling", "drill hole", "core", "collar", "downhole"]),
    ("item_11", 11, "Sample Preparation, Analyses and Security", ["sample preparation", "assay", "analyses", "sample security", "chain of custody", "qa/qc", "qaqc"]),
    ("item_12", 12, "Data Verification", ["data verification", "verify", "validation", "site visit"]),
    ("item_13", 13, "Mineral Processing and Metallurgical Testing", ["metallurgical", "processing test", "recovery test", "metallurgy"]),
    ("item_14", 14, "Mineral Resource Estimates", ["mineral resource", "resource estimate", "grade estimation", "cut-off grade", "block model", "classification"]),
    ("item_15", 15, "Mineral Reserve Estimates", ["mineral reserve", "reserve estimate", "proven", "probable", "modifying factors"]),
    ("item_16", 16, "Mining Methods", ["mining method", "mine plan", "pit design", "stope", "geotechnical", "dilution"]),
    ("item_17", 17, "Recovery Methods", ["recovery method", "process plant", "flowsheet", "processing plant", "throughput"]),
    ("item_18", 18, "Project Infrastructure", ["infrastructure", "power", "water supply", "tailings", "road", "camp"]),
    ("item_19", 19, "Market Studies and Contracts", ["market study", "market studies", "contracts", "pricing", "commodity price", "offtake"]),
    ("item_20", 20, "Environmental Studies, Permitting and Social or Community Impact", ["environmental", "permitting", "permit", "social", "community", "closure", "reclamation"]),
    ("item_21", 21, "Capital and Operating Costs", ["capital cost", "operating cost", "capex", "opex", "cost estimate"]),
    ("item_22", 22, "Economic Analysis", ["economic analysis", "npv", "irr", "cash flow", "payback", "sensitivity"]),
    ("item_23", 23, "Adjacent Properties", ["adjacent propert", "neighbouring", "neighboring"]),
    ("item_24", 24, "Other Relevant Data and Information", ["other relevant data", "other information"]),
    ("item_25", 25, "Interpretation and Conclusions", ["interpretation", "conclusion", "risks", "uncertaint"]),
    ("item_26", 26, "Recommendations", ["recommendation", "proposed program", "budget", "next steps"]),
    ("item_27", 27, "References", ["references", "bibliography"]),
]

_ITEM_BY_NUM = {num: (iid, title) for iid, num, title, _ in ITEMS}
_TITLE_TOKENS = {
    iid: set(re.findall(r"[a-z]+", title.lower())) for iid, _, title, _ in ITEMS
}

# Heading forms: "Item 14", "14 MINERAL RESOURCE...", "14.0 Mineral Resource..."
_HEADING_RE = re.compile(
    r"^\s*(?:item\s+)?(\d{1,2})(?:\.0)?[\s:.\-]+([A-Za-z][A-Za-z ,/&]+)\s*$",
    re.IGNORECASE,
)
# Some PDF layouts (column-wrapped headings) put the number and title on
# separate lines, e.g. "21.0" then "Capital and Operating Costs" on the next
# line. Catch that pair too, since a single-line-only regex sees neither half
# as a heading on its own.
_HEADING_NUM_ONLY_RE = re.compile(r"^\s*(\d{1,2})(?:\.0)?\s*$")
_HEADING_TITLE_ONLY_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ,/&]+)\s*$")


def _iter_heading_candidates(text: str):
    """Yield (num, title_text, body_line_index) for headings on one line or
    split across two. body_line_index is the first line after the heading."""
    lines = [l.strip() for l in text.splitlines()]
    for i, line in enumerate(lines):
        if not line or len(line) > 90:
            continue
        m = _HEADING_RE.match(line)
        if m:
            yield int(m.group(1)), m.group(2), i + 1
            continue
        m = _HEADING_NUM_ONLY_RE.match(line)
        if not m or i + 1 >= len(lines):
            continue
        nxt = lines[i + 1]
        if not nxt or len(nxt) > 90:
            continue
        mt = _HEADING_TITLE_ONLY_RE.match(nxt)
        if mt:
            yield int(m.group(1)), mt.group(1), i + 2


def _is_item_heading(num: int, title_text: str) -> bool:
    """Confirm the title overlaps the canonical Item title (rejects stray
    numbered lines like "14 samples were collected")."""
    if num not in _ITEM_BY_NUM:
        return False
    iid = _ITEM_BY_NUM[num][0]
    tokens = set(re.findall(r"[a-z]+", title_text.strip().lower()))
    return bool(tokens & _TITLE_TOKENS[iid])


def detect_page_items(pages: List[Page]) -> Dict[int, Tuple[str, str]]:
    """Return {page_number: (item_id, item_title)} best-effort.

    Finds the first plausible start page for each Item, then assigns every page
    to the most recent Item that has started before it.
    """
    starts: Dict[int, int] = {}  # item_number -> start page
    for page in pages:
        for num, title_text, _body in _iter_heading_candidates(page.text):
            if not _is_item_heading(num, title_text):
                continue
            # Keep the earliest start that keeps Items in ascending page order.
            if num not in starts:
                if not starts or page.number >= max(starts.values()):
                    starts[num] = page.number

    if not starts:
        return {}

    ordered = sorted(starts.items(), key=lambda kv: kv[1])  # by start page
    page_items: Dict[int, Tuple[str, str]] = {}
    for idx, (num, start_page) in enumerate(ordered):
        end_page = ordered[idx + 1][1] - 1 if idx + 1 < len(ordered) else pages[-1].number
        iid, title = _ITEM_BY_NUM[num]
        for p in range(start_page, end_page + 1):
            page_items[p] = (iid, title)
    return page_items


_NOT_APPLICABLE_RE = re.compile(r"\bnot\s+applicable\b", re.IGNORECASE)
# Item-specific equivalents: Items 14 and 15 only impose requirements on a
# report that discloses resources/reserves, so opening the section with
# "No Mineral Reserves have been estimated" makes it not applicable. Scoped to
# those Items — the same words opening, say, Item 16 wouldn't mean that.
_ITEM_ABSENT_RE = {
    14: re.compile(
        r"\bno\s+mineral\s+resources?\s+(?:have|has)\s+been\s+(?:estimated|declared|defined|reported)"
        r"|\bthere\s+are\s+(?:currently\s+)?no\s+mineral\s+resources?\b",
        re.IGNORECASE,
    ),
    15: re.compile(
        r"\bno\s+mineral\s+reserves?\s+(?:have|has)\s+been\s+(?:estimated|declared|defined|reported)"
        r"|\bthere\s+are\s+(?:currently\s+)?no\s+mineral\s+reserves?\b",
        re.IGNORECASE,
    ),
}


def not_applicable_items(
    pages: List[Page], page_items: Dict[int, Tuple[str, str]], n_lines: int = 6
) -> Dict[int, int]:
    """Return {item_number: page} for Items whose section opens by declaring
    itself not applicable (e.g. "21.0 Capital and Operating Costs / This
    section is not applicable." in an exploration-stage report), or for Items
    14/15, by stating no resources/reserves have been estimated. Only the
    first few lines after the heading are read, so a passing mention of "not
    applicable" deeper in a real section doesn't count."""
    by_num = {p.number: p for p in pages}
    start_pages: Dict[int, int] = {}
    for pno in sorted(page_items):
        iid = page_items[pno][0]
        num = int(iid.split("_")[1])
        start_pages.setdefault(num, pno)

    result: Dict[int, int] = {}
    for num, pno in start_pages.items():
        page = by_num.get(pno)
        if page is None:
            continue
        lines = [l.strip() for l in page.text.splitlines()]
        for hnum, title, body in _iter_heading_candidates(page.text):
            if hnum != num or not _is_item_heading(hnum, title):
                continue
            opening = " ".join(l for l in lines[body: body + n_lines] if l)
            absent = _ITEM_ABSENT_RE.get(num)
            if _NOT_APPLICABLE_RE.search(opening) or (absent and absent.search(opening)):
                result[num] = pno
            break
    return result


def map_criterion_to_item(text: str) -> Optional[Tuple[str, str]]:
    """Guess which Item a criterion concerns, via keyword scoring."""
    lowered = text.lower()
    best_iid = None
    best_score = 0
    for iid, _num, title, keywords in ITEMS:
        score = sum(2 for kw in keywords if kw in lowered)
        # light bonus for title-word overlap
        score += sum(1 for tok in _TITLE_TOKENS[iid] if len(tok) > 4 and tok in lowered)
        if score > best_score:
            best_score = score
            best_iid = iid
    if best_iid is None or best_score == 0:
        return None
    title = next(t for i, _n, t, _k in ITEMS if i == best_iid)
    return best_iid, title
