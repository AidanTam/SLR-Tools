"""Deterministic checks: cross-references inside the report resolve.

Late edits are what break these. A figure gets renumbered, a section is
merged, and "see Figure 14-3" or "refer to Section 13.2" now points at
nothing (or at the wrong thing). Three checks:

* every "Figure x-y" / "Table x-y" mentioned in the text has a caption;
* figure and table captions are unique and run in sequence within a chapter;
* every "Section 13.2" mentioned in the text is a heading that exists.

Like every check here it is a heuristic over extracted text. References to
other documents ("Table 5 of Smith (2019)", "Section 1.5 of NI 43-101") are
skipped, and a flag means "look at this", not "this is wrong".
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_NEEDS_REVIEW,
    Finding,
    Page,
)

ITEM_ID = "consistency"
ITEM_TITLE = "Cross-Document Consistency (Automated)"

# Fewer captions than this and the report probably doesn't number its figures
# in a way we can read, so a comparison would only produce noise.
MIN_CAPTIONS = 5

_NUM = r"\d{1,2}(?:\s?[-–.]\s?\d{1,3})?"
# "Figure 4-1: Title", "Table 14.3 - Title", "Figure 4-1 Title" (short line).
_CAPTION_RE = re.compile(
    r"^\s*(Figure|Table)\s+(" + _NUM + r")\s*(?P<sep>[:.\-–—]\s*)?(?P<title>\S.*)?$",
    re.IGNORECASE,
)
_SENTENCE_VERBS = re.compile(
    r"\b(shows?|shown|presents?|summari[sz]es?|lists?|provides?|illustrates?|indicates?|"
    r"is|are|was|were|has|have|will|can|may|should|contains?|details?|gives?|outlines?|"
    r"describes?|compares?|below|above|respectively|also|herein|follows?)\b",
    re.IGNORECASE,
)
_CONTINUED_RE = re.compile(r"cont(?:inued|['’]d|\.)", re.IGNORECASE)

_REF_RE = re.compile(
    r"\b(Figures?|Tables?|Fig\.)\s+(" + _NUM + r")"
    r"((?:\s*(?:,|and|&|to|through|[-–])\s*" + _NUM + r")*)",
    re.IGNORECASE,
)
# "Table 5 of Smith (2019)", "Figure 3 in NI 43-101", "Table 1 of Form 43-101F1".
_EXTERNAL_TAIL_RE = re.compile(
    r"^\s*(?:of|in|from)\s+(?:the\s+)?(?:[A-Z][\w&.\-]*[\s,]+){0,4}"
    r"(?:\(?\d{4}|et\s+al|NI\s?43|National\s+Instrument|Form|Instrument|CIM|Companion)",
)
_SECTION_REF_RE = re.compile(r"\b(?:Sections?|Item)\s+(\d{1,2}(?:\.\d{1,2}){0,4})(?:\.0)?(?![\d.]*\d)")
_HEADING_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,4})(?:\.0)?\s+[A-Z][A-Za-z]")
_SECTION_EXTERNAL_RE = re.compile(
    r"^\s*(?:of|in|from)\s+(?:the\s+)?(?:NI|National|Form|Instrument|CIM|Companion|[A-Z][a-z]+\s+(?:\(|et\s+al))"
)


def _key(num: str) -> str:
    """Canonical caption number: "4 - 1" and "4.1" both become "4-1"."""
    return re.sub(r"\s*[-–.]\s*", "-", num.strip())


def _list_pages(pages: List[Page]) -> set:
    from .structural_checks import _list_like_pages
    return _list_like_pages(pages)


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------

def _caption_match(line: str):
    """The caption match for a line, or None if it isn't a real caption.

    "Table 14-10: Title" (colon or dash) is a caption. So is a line that is
    only the label ("Figure 20-1", title on the next line). Anything else, such
    as the wrapped sentence "Table 14-10. A regular block size ...", must look
    like a short title and not a sentence."""
    m = _CAPTION_RE.match(line)
    if not m:
        return None
    title = (m.group("title") or "").strip()
    sep = (m.group("sep") or "").strip()
    if sep in (":", "-", "–", "—"):
        return m
    if not title:
        return m if not sep else None  # label-only line
    if (
        len(title) <= 70
        and title[0].isupper()
        and title[-1] not in ".,;"
        and not _SENTENCE_VERBS.search(title)
    ):
        return m
    return None


def _captions(pages: List[Page], skip: set) -> Dict[Tuple[str, str], List[Tuple[int, str]]]:
    """(kind, number) -> [(page, title)] for every caption line."""
    out: Dict[Tuple[str, str], List[Tuple[int, str]]] = defaultdict(list)
    for p in pages:
        if p.number in skip:
            continue
        for line in p.text.splitlines():
            m = _caption_match(line)
            if m:
                out[(m.group(1).title(), _key(m.group(2)))].append(
                    (p.number, (m.group("title") or "").strip())
                )
    return out


# ---------------------------------------------------------------------------
# Check 1: references resolve
# ---------------------------------------------------------------------------

def _uses_chapter_numbers(captions) -> bool:
    keys = [k[1] for k in captions]
    return sum("-" in k for k in keys) > len(keys) / 2


def check_figure_table_references(pages: List[Page]) -> Finding:
    from .structural_checks import _finding

    text = "Every Figure and Table mentioned in the text has a caption"
    skip = _list_pages(pages)
    caps = _captions(pages, skip)
    n_caps = len(caps)
    if n_caps < MIN_CAPTIONS:
        return _finding(
            "PY-XREF-FIGTAB", text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            f"Only {n_caps} figure/table caption(s) were recognised, too few to cross-check "
            "the report's references against.",
        )
    chaptered = _uses_chapter_numbers(caps)

    dangling: Dict[Tuple[str, str], Set[int]] = defaultdict(set)
    checked = 0
    for p in pages:
        if p.number in skip:
            continue
        for m in _REF_RE.finditer(p.text):
            line_start = p.text.rfind("\n", 0, m.start()) + 1
            line_end = p.text.find("\n", m.start())
            line = p.text[line_start: len(p.text) if line_end == -1 else line_end]
            if p.text[line_start: m.start()].strip() == "" and _caption_match(line):
                continue  # this is the caption line itself
            if _EXTERNAL_TAIL_RE.match(p.text[m.end(): m.end() + 80]):
                continue
            kind = "Figure" if m.group(1).lower().startswith("fig") else "Table"
            nums = [m.group(2)] + re.findall(_NUM, m.group(3) or "")
            for n in nums:
                key = _key(n)
                if ("-" in key) != chaptered:
                    continue  # a different numbering style: likely another document's
                checked += 1
                if (kind, key) not in caps:
                    dangling[(kind, key)].add(p.number)

    if not checked:
        return _finding(
            "PY-XREF-FIGTAB", text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            f"{n_caps} captions were found but no in-text figure/table references to check.",
        )
    if not dangling:
        return _finding(
            "PY-XREF-FIGTAB", text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
            f"All {checked} in-text figure/table references match one of the "
            f"{n_caps} captions in the report.",
            confidence=0.8,
        )
    items = sorted(dangling.items(), key=lambda kv: (kv[0][0], [int(x) for x in re.findall(r"\d+", kv[0][1])]))
    shown = items[:15]
    detail = "; ".join(f"{k} {n} (p.{sorted(pg)[:4]})" for (k, n), pg in shown)
    more = f" (+{len(items) - len(shown)} more)" if len(items) > len(shown) else ""
    status = STATUS_NON_COMPLIANT if len(items) >= 5 else STATUS_NEEDS_REVIEW
    return _finding(
        "PY-XREF-FIGTAB", text, ITEM_ID, ITEM_TITLE, status,
        f"{len(items)} figure/table number(s) are referred to in the text but have no "
        "caption: either the reference is stale after a renumbering, or the caption "
        "was not recognised (regex-based; verify).",
        evidence=detail + more,
        pages=[pg for _kn, s in items for pg in s],
        confidence=0.65,
    )


# ---------------------------------------------------------------------------
# Check 2: numbering unique and sequential
# ---------------------------------------------------------------------------

def check_caption_numbering(pages: List[Page]) -> Finding:
    from .structural_checks import _finding

    text = "Figure and Table numbers are unique and run in sequence"
    skip = _list_pages(pages)
    caps = _captions(pages, skip)
    if len(caps) < MIN_CAPTIONS:
        return _finding(
            "PY-XREF-NUMBERING", text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            f"Only {len(caps)} figure/table caption(s) were recognised, too few to check numbering.",
        )

    duplicates: List[str] = []
    for (kind, num), occ in caps.items():
        real = [(pg, t) for pg, t in occ if not _CONTINUED_RE.search(t)]
        # A table that runs over a page repeats its caption; a *different* title
        # for the same number is a genuine clash.
        titles = {re.sub(r"\W+", " ", t.lower()).strip() for _pg, t in real if t}
        if len(titles) > 1:
            duplicates.append(f"{kind} {num} (p.{sorted({pg for pg, _t in real})})")

    gaps: List[str] = []
    for kind in ("Figure", "Table"):
        by_chapter: Dict[str, Set[int]] = defaultdict(set)
        for (k, num) in caps:
            if k != kind or "-" not in num:
                continue
            ch, _, idx = num.partition("-")
            if idx.isdigit():
                by_chapter[ch].add(int(idx))
        for ch in sorted(by_chapter, key=int):
            have = by_chapter[ch]
            missing = [i for i in range(1, max(have) + 1) if i not in have]
            # A long run of "missing" numbers means we didn't recognise the
            # captions, not that they're absent: report only small gaps.
            if missing and len(missing) <= 3 and len(have) >= 3:
                gaps.append(f"{kind} {ch}-{missing[0]}" + (f" (+{len(missing) - 1} more)" if len(missing) > 1 else ""))

    n = len(caps)
    if not duplicates and not gaps:
        return _finding(
            "PY-XREF-NUMBERING", text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
            f"{n} figure/table captions: each number is used once and each chapter's "
            "numbering runs without gaps.",
            confidence=0.7,
        )
    parts = []
    if duplicates:
        parts.append("the same number is used for different captions: " + "; ".join(duplicates[:8]))
    if gaps:
        parts.append("numbers missing from a sequence: " + "; ".join(gaps[:8]))
    return _finding(
        "PY-XREF-NUMBERING", text, ITEM_ID, ITEM_TITLE,
        STATUS_NON_COMPLIANT if duplicates else STATUS_NEEDS_REVIEW,
        "; ".join(parts).capitalize() + ". A gap can mean a deleted figure or a caption "
        "this check did not recognise (regex-based; verify).",
        evidence="; ".join(parts)[:400],
        confidence=0.55,
    )


# ---------------------------------------------------------------------------
# Check 3: section references resolve
# ---------------------------------------------------------------------------

_NUMBER_ONLY_HEADING_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,4})\s*$")


def _headings(pages: List[Page]) -> Set[str]:
    found: Set[str] = set()
    for p in pages:  # contents pages count: an entry there proves the heading exists
        lines = p.text.splitlines()
        for i, line in enumerate(lines):
            m = _HEADING_RE.match(line)
            if m:
                found.add(m.group(1))
                continue
            m = re.match(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,4})(?:\.0)?\s+\S.*\.{4,}", line)
            if m:  # contents line: "14.2   Resource Estimate ........ 14-4"
                found.add(m.group(1))
                continue
            m = _NUMBER_ONLY_HEADING_RE.match(line)
            if m:  # "27.0" on its own line, the title on the next
                nxt = next((l.strip() for l in lines[i + 1: i + 3] if l.strip()), "")
                if nxt and nxt[0].isupper() and len(nxt) <= 90 and not nxt.endswith("."):
                    found.add(m.group(1))
    out = set()
    for h in found:
        parts = h.split(".")
        for i in range(1, len(parts) + 1):
            out.add(".".join(parts[:i]))
        if h.endswith(".0"):
            out.add(h[:-2])
    return out


def check_section_references(pages: List[Page]) -> Finding:
    from .structural_checks import _finding

    text = "Every Section mentioned in the text exists as a heading"
    skip = _list_pages(pages)
    heads = _headings(pages)
    if len(heads) < 20:
        return _finding(
            "PY-XREF-SECTIONS", text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            f"Only {len(heads)} numbered heading(s) were recognised, too few to cross-check "
            "section references against.",
        )

    dangling: Dict[str, Set[int]] = defaultdict(set)
    checked = 0
    for p in pages:
        if p.number in skip:
            continue
        for m in _SECTION_REF_RE.finditer(p.text):
            if _SECTION_EXTERNAL_RE.match(p.text[m.end(): m.end() + 60]):
                continue  # "Section 1.5 of NI 43-101"
            if re.search(r"(?:NI|Form)\s*43-101[A-Z0-9]*\s*,?\s*$", p.text[max(0, m.start() - 25): m.start()]):
                continue
            num = m.group(1)
            if m.group(0).lower().startswith("item") and "." not in num:
                continue  # "Item 14" names a Form item, and is checked elsewhere
            checked += 1
            top = int(num.split(".")[0])
            if top == 0:
                continue
            if num not in heads and not (num.endswith(".0") and num[:-2] in heads) and top <= 27:
                dangling[num].add(p.number)

    if not checked:
        return _finding(
            "PY-XREF-SECTIONS", text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No in-text section references were found to check.",
        )
    if not dangling:
        return _finding(
            "PY-XREF-SECTIONS", text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
            f"All {checked} in-text section references point to a heading in the report.",
            confidence=0.75,
        )
    ordered = sorted(dangling.items(), key=lambda kv: [int(x) for x in kv[0].split(".")])
    shown = ordered[:15]
    detail = "; ".join(f"Section {n} (p.{sorted(pg)[:4]})" for n, pg in shown)
    more = f" (+{len(ordered) - len(shown)} more)" if len(ordered) > len(shown) else ""
    return _finding(
        "PY-XREF-SECTIONS", text, ITEM_ID, ITEM_TITLE,
        STATUS_NON_COMPLIANT if len(ordered) >= 5 else STATUS_NEEDS_REVIEW,
        f"{len(ordered)} section number(s) are referred to in the text but no heading "
        "with that number was found: the section may have been renumbered or removed "
        "(regex-based; verify).",
        evidence=detail + more,
        pages=[pg for _n, s in ordered for pg in s],
        confidence=0.6,
    )


def check_cross_references(pages: List[Page]) -> List[Finding]:
    return [
        check_figure_table_references(pages),
        check_caption_numbering(pages),
        check_section_references(pages),
    ]
