"""Deterministic, no-LLM checks for NI 43-101 requirements that don't need
semantic judgment: presence of a required document element, a countable rule
(e.g. "no more than two phases"), a mandated boilerplate disclaimer, or a
value that must literally match across two locations in the report.

Every check here is regex/structure based and runs against the same `Page`
objects the LLM pipeline uses. None of it calls Ollama, so this module works
even when no model is installed and runs in a fraction of a second.

These are heuristics over extracted text, not a legal determination — every
finding says so, and a "Not Addressed" here usually means "couldn't verify
automatically," not "missing." A QP should still check the cited pages.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Dict, List, Optional, Tuple

from .models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    Criterion,
    Finding,
    Page,
)
from .numeric_consistency import check_summary_numbers
from .structure import not_applicable_items

_NUM_ITEMS = 27  # Form 43-101F1 has 27 Items.


def _finding(
    check_id: str,
    text: str,
    item_id: str,
    item_title: str,
    status: str,
    rationale: str,
    evidence: str = "",
    pages: Optional[List[int]] = None,
    confidence: float = 1.0,
) -> Finding:
    return Finding(
        criterion=Criterion(id=check_id, text=text, item_id=item_id, item_title=item_title),
        status=status,
        confidence=confidence,
        rationale=rationale,
        evidence=evidence,
        pages=sorted(set(pages or [])),
        method="python",
    )


def _joined(pages: List[Page]) -> str:
    return "\n".join(p.text for p in pages)


# --------------------------------------------------------------------------
# 1. Table of Contents
# --------------------------------------------------------------------------

_TOC_HEADING_RE = re.compile(r"table\s+of\s+contents", re.IGNORECASE)
# Page refs come as "12", section-page "21-1" / "4-10", or front-matter
# roman numerals "iv" — all three are common in real reports.
_DOT_LEADER_RE = re.compile(
    r"\.{4,}\s*(?:\d{1,4}(?:\s*[-–]\s*\d{1,4})?|[ivxlcdm]{1,7})\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_CAPTION_LINE_RE = re.compile(r"^\s*(figure|table)\s+\d", re.IGNORECASE)


def _list_like_pages(pages: List[Page]) -> set:
    """Pages that read like a Table of Contents / List of Figures / List of
    Tables (several dot-leader lines) — a keyword match there is a caption or
    entry title, not substantive discussion, and should not trigger a check."""
    return {p.number for p in pages if len(_DOT_LEADER_RE.findall(p.text)) >= 2}


def _line_containing(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:] if end == -1 else text[start:end]


def check_table_of_contents(pages: List[Page], page_items: Dict[int, Tuple[str, str]]) -> Finding:
    front = [p for p in pages if p.number <= 15] or pages[:15]
    heading_page = None
    for p in front:
        if _TOC_HEADING_RE.search(p.text):
            heading_page = p.number
            break

    if heading_page is None:
        return _finding(
            "PY-TOC", "Table of Contents present", "front_matter",
            "Contents of the Technical Report", STATUS_NOT_ADDRESSED,
            "No \"Table of Contents\" heading found in the first 15 pages.",
        )

    window = [p for p in front if heading_page <= p.number <= heading_page + 2]
    leader_count = sum(len(_DOT_LEADER_RE.findall(p.text)) for p in window)
    if leader_count >= 3:
        return _finding(
            "PY-TOC", "Table of Contents present", "front_matter",
            "Contents of the Technical Report", STATUS_COMPLIANT,
            f"Heading found on page {heading_page} with {leader_count} dot-leader "
            "entries detected nearby.",
            pages=[heading_page],
        )
    return _finding(
        "PY-TOC", "Table of Contents present", "front_matter",
        "Contents of the Technical Report", STATUS_PARTIAL,
        f"Heading found on page {heading_page} but entries could not be confirmed "
        "automatically (no dot-leader lines detected) — verify manually.",
        pages=[heading_page],
        confidence=0.5,
    )


# --------------------------------------------------------------------------
# 2. Item 27 — References: every in-text citation appears in the list
# --------------------------------------------------------------------------

_REF_HEADING_RE = re.compile(r"^\s*(references|bibliography)\s*$", re.IGNORECASE | re.MULTILINE)
# End of the reference list: the next major section ("28.0", "Item 28"), the
# signature page, certificates, or an appendix. A line opening with a bare
# number is NOT enough — journal citations wrap to lines like "44: p1111-1110."
_REF_STOP_RE = re.compile(
    r"^\s*(?:item\s+\d{1,2}\b|\d{1,2}\.0\b)"
    r"|^\s*date\s+and\s+signature"
    r"|certificate\s+of\s+qualified\s+person"
    r"|consents?\s+of\s+qualified\s+person"
    # A bare "Appendix J" line or an all-caps "APPENDIX" heading; a mixed-case
    # line like "Appendix J – Photos.pdf" is a wrapped reference entry.
    r"|^\s*appendi(?:x|ces)(?:\s+[A-Z0-9]{1,3})?\s*$"
    r"|^\s*(?-i:APPENDIX|APPENDICES)\b",
    re.IGNORECASE | re.MULTILINE,
)
_REF_BLOCK_MAX_PAGES = 15  # safety cap if no stop heading is ever found
_PAREN_RE = re.compile(r"\(([^()]{3,250})\)")
# One citation inside a parenthetical: "Smith 2019", "Smith, 2019",
# "Smith and Jones, 2019", "Smith et al. 2019", "Smith et al., 2019a".
_CITATION_UNIT_RE = re.compile(
    r"^\s*(?:see\s+(?:also\s+)?|e\.g\.,?\s+|after\s+|modified\s+from\s+)?"
    r"([^\W\d_][\w'\-]+)"
    r"(?:\s+(?:and|&)\s+[^\W\d_][\w'\-]+|,?\s+et\s+al\.?)?"
    r",?\s*((?:19|20)\d{2})[a-z]?\s*$"
)
# Capitalized words that open a parenthetical with a year but aren't authors,
# e.g. "(Since 2019)", "(June 2021)", "(Phase 2 2024)".
_NOT_AUTHORS = {
    "since", "from", "in", "between", "circa", "ca", "approximately", "approx",
    "after", "before", "until", "during", "as", "of", "by", "to", "up",
    "through", "and", "or", "the", "est", "estimated", "updated", "effective",
    "dated", "report", "year", "years", "fiscal", "fy", "mid", "early", "late",
    "end", "start", "phase", "figure", "table", "section", "item", "appendix",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar",
    "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "spring", "summer", "fall", "autumn", "winter", "q1", "q2", "q3", "q4",
}
_YEAR_WINDOW = 200  # chars after a name within which its year must appear (one entry)
_ACRONYM_RE = re.compile(r"^[A-Z][A-Z&]{1,7}$")
_EXPANSION_WORD = r"(?:[A-Z][\w&'\-]*|of|and|for|the|&)"
_EXPANSION_STOPWORDS = {"of", "and", "for", "the", "&"}


def _fold(text: str) -> str:
    """Accent- and case-insensitive form, so "Tóth" (precomposed or
    decomposed) matches "Toth" the way a reader would treat them."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _running_lines(pages: List[Page]) -> set:
    """Header/footer lines repeated on many pages ("Equinox Gold Corp. |
    Greenstone Property", "March 30, 2026"). Left in the reference text they
    could falsely satisfy a citation, e.g. "(Equinox 2026)"."""
    counts: Dict[str, int] = {}
    for p in pages:
        lines = [" ".join(l.split()) for l in p.text.splitlines() if l.strip()]
        for line in set(lines[:6] + lines[-4:]):
            counts[line] = counts.get(line, 0) + 1
    threshold = max(5, int(len(pages) * 0.3))
    return {line for line, c in counts.items() if c >= threshold}


def _iter_citations(text: str):
    """Yield (surname, year) for each parenthetical author-year citation,
    including each unit of multi-citations like "(Smith 2019; Jones 2020)"."""
    text = unicodedata.normalize("NFC", text)
    for pm in _PAREN_RE.finditer(text):
        for unit in re.split(r";", pm.group(1)):
            m = _CITATION_UNIT_RE.match(" ".join(unit.split()))
            if not m:
                continue
            surname, year = m.group(1), m.group(2)
            if not surname[0].isupper() or surname.lower() in _NOT_AUTHORS:
                continue
            yield surname, year


def _acronym_expansions(acronym: str, full_text: str) -> List[List[str]]:
    """Significant words of each expansion the report itself gives for an
    acronym: "Ministry of Natural Resources and Forestry (MNRF)", a
    parenthetical like "NorthWinds Environmental Services (NWES 2021; ...",
    or an abbreviations-list row "MNRF  Ministry of Natural Resources ..."."""
    a = re.escape(acronym)
    phrase = rf"{_EXPANSION_WORD}(?:\s+{_EXPANSION_WORD}){{0,9}}"
    patterns = [
        rf"\b({phrase})\s*\(\s*{a}\b",
        rf"(?:^|\n)\s*{a}\s+({phrase})",
    ]
    expansions = []
    for pat in patterns:
        for m in re.finditer(pat, full_text):
            words = [w for w in m.group(1).split() if w.lower() not in _EXPANSION_STOPWORDS]
            if words and not (len(words) == 1 and words[0] == acronym):
                expansions.append(words)
    return expansions


def _name_then_year(words: List[str], year: str, folded_ref: str) -> bool:
    name = r"\b[\s\S]{0,25}?\b".join(re.escape(_fold(w)) for w in words)
    return re.search(rf"\b{name}\b[\s\S]{{0,{_YEAR_WINDOW}}}?\b{year}", folded_ref) is not None


def _reference_listed(surname: str, year: str, folded_ref: str, full_text: str) -> bool:
    """The name must appear as a whole word with the cited year shortly
    after it — so "Good et al. 2015" doesn't match "Goodgame, V.R., 2010".
    An acronym citation ("MNRF 2014") that isn't itself in the list is
    resolved through the report's own definition of it."""
    if _name_then_year([surname], year, folded_ref):
        return True
    if not _ACRONYM_RE.match(surname):
        return False
    for words in _acronym_expansions(surname, full_text):
        # Any run of up to 3 consecutive significant words, so "Ontario
        # Ministry of Natural Resources and Forestry" still finds the entry
        # "Ministry of Natural Resources. 2014."
        k = min(3, len(words))
        for i in range(len(words) - k + 1):
            if _name_then_year(words[i: i + k], year, folded_ref):
                return True
    return False


def check_references_list(pages: List[Page]) -> Finding:
    list_pages = _list_like_pages(pages)
    ref_page = None
    ref_start_offset = None
    for p in pages:
        if p.number in list_pages:
            continue
        m = _REF_HEADING_RE.search(p.text)
        if m:
            ref_page = p.number
            ref_start_offset = m.end()
            break

    if ref_page is None:
        return _finding(
            "PY-REFS", "Item 27: References list present", "item_27", "References",
            STATUS_NOT_ADDRESSED,
            "No \"References\" or \"Bibliography\" heading was found.",
        )

    candidate_pages = [p for p in pages if ref_page <= p.number <= ref_page + _REF_BLOCK_MAX_PAGES]
    ref_text_parts = []
    ref_block_end = ref_page
    for p in candidate_pages:
        text = p.text[ref_start_offset:] if p.number == ref_page else p.text
        stop = _REF_STOP_RE.search(text)
        ref_block_end = p.number
        if stop:
            ref_text_parts.append(text[: stop.start()])
            break
        ref_text_parts.append(text)
    running = _running_lines(pages)
    ref_text = "\n".join(
        line for line in "\n".join(ref_text_parts).splitlines()
        if " ".join(line.split()) not in running
    )
    folded_ref = _fold(ref_text)

    body_pages = [
        p for p in pages
        if (p.number < ref_page or p.number > ref_block_end) and p.number not in list_pages
    ]

    citations: Dict[Tuple[str, str], set] = {}  # (surname, year) -> pages cited on
    for p in body_pages:
        for surname, year in _iter_citations(p.text):
            citations.setdefault((surname, year), set()).add(p.number)

    if not citations:
        entry_count = len([l for l in ref_text.splitlines() if re.search(r"(19|20)\d{2}", l)])
        return _finding(
            "PY-REFS", "Item 27: References list present", "item_27", "References",
            STATUS_COMPLIANT if entry_count else STATUS_PARTIAL,
            f"Reference list found at page {ref_page} (~{entry_count} dated entries). "
            "No parenthetical (Author, Year) in-text citations were detected in the "
            "body to cross-check against it.",
            pages=[ref_page],
            confidence=0.6,
        )

    full_text = unicodedata.normalize("NFC", _joined(pages))
    missing = {
        key: pgs for key, pgs in citations.items()
        if not _reference_listed(key[0], key[1], folded_ref, full_text)
    }
    if missing:
        detail = "; ".join(
            f"{s} {y} (cited p.{sorted(pgs)})" for (s, y), pgs in sorted(missing.items())
        )
        missing_pages = sorted({pg for pgs in missing.values() for pg in pgs})
        return _finding(
            "PY-REFS", "Item 27: References list present", "item_27", "References",
            STATUS_NON_COMPLIANT,
            f"{len(missing)} in-text citation(s) have no matching entry (surname + "
            f"year) in the reference list at pages {ref_page}-{ref_block_end}: "
            f"{detail}. (Regex-based matching — verify before relying on this.)",
            evidence=detail,
            pages=missing_pages + [ref_page],
            confidence=0.7,
        )

    return _finding(
        "PY-REFS", "Item 27: References list present", "item_27", "References",
        STATUS_COMPLIANT,
        f"All {len(citations)} distinct in-text citation(s) have a matching entry "
        f"(surname + year) in the reference list at pages {ref_page}-{ref_block_end}.",
        pages=[ref_page],
    )


# --------------------------------------------------------------------------
# 3. Item 26 — Recommendations must not exceed two phases
# --------------------------------------------------------------------------

_PHASE_RE = re.compile(r"\bphase\s+([1-4]|i{1,3}v?|iv|one|two|three|four)\b", re.IGNORECASE)
_PHASE_NORMALIZE = {
    "1": 1, "2": 2, "3": 3, "4": 4,
    "i": 1, "ii": 2, "iii": 3, "iv": 4,
    "one": 1, "two": 2, "three": 3, "four": 4,
}


def check_recommendation_phases(pages: List[Page], page_items: Dict[int, Tuple[str, str]]) -> Finding:
    item_26_pages = sorted(n for n, (iid, _t) in page_items.items() if iid == "item_26")
    if not item_26_pages:
        # Scanning the whole report instead would count every "Phase N" in
        # unrelated contexts (mine construction phases, historical programs).
        return _finding(
            "PY-PHASES", "Item 26: recommendations apply to no more than two phases",
            "item_26", "Recommendations", STATUS_NOT_ADDRESSED,
            "The Recommendations section (Item 26) was not detected, so the phase "
            "count could not be scoped to it; verify manually.",
        )
    scope = [p for p in pages if p.number in item_26_pages]

    found = {}
    for p in scope:
        for m in _PHASE_RE.finditer(p.text):
            token = m.group(1).lower()
            num = _PHASE_NORMALIZE.get(token)
            if num is not None:
                found.setdefault(num, set()).add(p.number)

    if not found:
        return _finding(
            "PY-PHASES", "Item 26: recommendations apply to no more than two phases",
            "item_26", "Recommendations", STATUS_COMPLIANT,
            f"No \"Phase N\" labels in the Recommendations section (p.{item_26_pages[0]}"
            f"-{item_26_pages[-1]}), so it does not exceed the two-phase limit.",
            pages=item_26_pages[:1],
        )

    all_pages = sorted({pg for pgs in found.values() for pg in pgs})
    if len(found) > 2:
        return _finding(
            "PY-PHASES", "Item 26: recommendations apply to no more than two phases",
            "item_26", "Recommendations", STATUS_NON_COMPLIANT,
            f"{len(found)} distinct phases detected ({sorted(found)}), but Item 26 "
            "limits recommendations to no more than two phases.",
            evidence=f"Phases found: {sorted(found)}",
            pages=all_pages,
        )
    return _finding(
        "PY-PHASES", "Item 26: recommendations apply to no more than two phases",
        "item_26", "Recommendations", STATUS_COMPLIANT,
        f"{len(found)} distinct phase(s) detected ({sorted(found)}), within the two-phase limit.",
        pages=all_pages,
    )


# --------------------------------------------------------------------------
# 4 & 5. Mandated cautionary boilerplate near specific disclosures
# --------------------------------------------------------------------------

_SECTION_NUM_PREFIX_RE = re.compile(r"^\s*\d{1,2}(?:\.\d+)*\s*")
# Negation directly governing the trigger phrase: "no historical ...",
# "not aware of any known historical ...". Must end right where the trigger
# starts, so an unrelated "no" earlier in the sentence doesn't suppress it.
_NEGATION_RE = re.compile(
    r"\b(?:no|not\s+aware\s+of\s+any|not\s+any|there\s+(?:are|were)\s+no)"
    r"\s+(?:known\s+|previous\s+|other\s+|reported\s+)?$",
    re.IGNORECASE,
)


def _is_heading_line(line: str) -> bool:
    """A short Title Case line with no sentence punctuation, e.g. "Adjacent
    Properties" or "6.3 Historical Resource Estimates" — a section heading
    naming the topic, not a disclosure that needs a disclaimer."""
    body = _SECTION_NUM_PREFIX_RE.sub("", line).strip()
    if not body or len(body) > 70 or body.endswith((".", ",", ";", ":")):
        return False
    words = re.findall(r"[A-Za-z][\w'\-]*", body)
    if not words or len(words) > 8:
        return False
    return all(w[0].isupper() for w in words if len(w) > 3)


def _is_negated(text: str, pos: int) -> bool:
    """"There are no historical estimates ..." states the disclosure is absent."""
    preceding = " ".join(text[max(0, pos - 60):pos].split())
    return _NEGATION_RE.search(preceding + " ") is not None


def _check_cautionary_language(
    pages: List[Page],
    trigger_re: "re.Pattern",
    caution_phrases: List[str],
    check_id: str,
    text: str,
    item_id: str,
    item_title: str,
) -> Finding:
    hits = []  # (page_number, has_caution)
    list_pages = _list_like_pages(pages)
    for idx, p in enumerate(pages):
        if p.number in list_pages:
            continue  # Table of Contents / List of Figures / List of Tables
        # The disclaimer usually closes the same paragraph or subsection, which
        # can run well past the triggering sentence or wrap onto the next page.
        next_text = pages[idx + 1].text if idx + 1 < len(pages) else ""
        scope = " ".join((p.text + " " + next_text).split()).lower()
        for m in trigger_re.finditer(p.text):
            line = _line_containing(p.text, m.start())
            if _CAPTION_LINE_RE.match(line):
                continue  # "Figure 23-1: Adjacent Properties to ..." — a caption
            if _is_heading_line(line):
                continue  # "23.0 Adjacent Properties" — a heading
            if _is_negated(p.text, m.start()):
                continue
            has_caution = any(phrase in scope for phrase in caution_phrases)
            hits.append((p.number, has_caution))

    if not hits:
        return _finding(
            check_id, text, item_id, item_title, STATUS_NOT_APPLICABLE,
            "No disclosure that triggers this requirement was found in the report "
            "body (Table of Contents entries, figure captions and section headings "
            "are ignored), so the disclaimer is not required.",
        )

    covered_pages = sorted({pg for pg, ok in hits if ok})
    uncovered_pages = sorted({pg for pg, ok in hits if not ok} - set(covered_pages))
    if covered_pages:
        return _finding(
            check_id, text, item_id, item_title, STATUS_COMPLIANT,
            f"Found {len(hits)} triggering mention(s); required cautionary language "
            f"was detected nearby on page(s) {covered_pages}.",
            pages=covered_pages,
            confidence=0.7,
        )
    return _finding(
        check_id, text, item_id, item_title, STATUS_NON_COMPLIANT,
        f"Found {len(hits)} triggering mention(s) on page(s) {uncovered_pages} with no "
        "mandated cautionary language detected nearby (regex/keyword match — verify "
        "manually before relying on this).",
        pages=uncovered_pages,
        confidence=0.6,
    )


def check_historical_estimate_disclaimer(pages: List[Page]) -> Finding:
    return _check_cautionary_language(
        pages,
        re.compile(r"historical\s+(?:mineral\s+)?(?:resource|reserve)s?\s+estimate", re.IGNORECASE),
        [
            "not done sufficient work to classify",
            "not treating the historical estimate",
            "not treating any historical estimate",
            "not treating these historical estimate",
            "should not be relied upon",
            "not current mineral resources",
            "not be considered current",
            "not be relied upon",
        ],
        "PY-HIST-CAUTION",
        "Item 6(c): historical estimate cautionary language (s.2.4)",
        "item_6", "History",
    )


def check_adjacent_property_disclaimer(pages: List[Page]) -> Finding:
    return _check_cautionary_language(
        pages,
        re.compile(r"adjacent\s+propert(?:y|ies)", re.IGNORECASE),
        [
            "unable to verify the information",
            "not necessarily indicative",
            "not indicative of the mineralization",
        ],
        "PY-ADJ-CAUTION",
        "Item 23(c): adjacent property verification disclaimer",
        "item_23", "Adjacent Properties",
    )


# --------------------------------------------------------------------------
# 6. Effective date consistency across the whole document
# --------------------------------------------------------------------------

_DATE_PATTERN = (
    r"[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"                 # October 9th, 2025
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?[A-Za-z]+,?\s+\d{4}"  # 9 October 2025
    r"|\d{4}-\d{2}-\d{2}"                                               # 2025-10-09
    r"|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"                               # 09/10/2025
)
_EFFECTIVE_DATE_RE = re.compile(
    r"effective\s+date\s*(?:of\s+(?:this|the)\s+technical\s+report)?\s*"
    r"(?:is|:|of|as\s+(?:of|at)|[-–—])?\s*(" + _DATE_PATTERN + r")",
    re.IGNORECASE,
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date(raw: str) -> Optional[date]:
    raw = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", raw.strip().rstrip(".,"), flags=re.IGNORECASE)
    raw = re.sub(r"\bday\s+of\s+", "", raw, flags=re.IGNORECASE)
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                return None
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", raw)
    if m:
        month = _MONTHS.get(m.group(2).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", raw)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, a, b)
        except ValueError:
            try:
                return date(y, b, a)
            except ValueError:
                return None
    return None


_SUPERSEDED_CONTEXT_RE = re.compile(
    r"supersed|previous\s+(?:technical\s+report|report)|prior\s+(?:technical\s+report|report)"
    r"|prior\s+involvement|co-?authored?|previously\s+filed|earlier\s+report",
    re.IGNORECASE,
)
_SUPERSEDED_LOOKBACK = 220  # chars before the match to check for another report's context

_CERT_HEADING_RE = re.compile(r"certificate\s+of\s+qualified\s+person", re.IGNORECASE)
_CONSENT_HEADING_RE = re.compile(r"consents?\s+of\s+qualified\s+person", re.IGNORECASE)
_SIGNATURE_PAGE_RE = re.compile(r"date\s+and\s+signature|signature\s+page", re.IGNORECASE)
_APPENDIX_HEADING_RE = re.compile(
    r"^\s*(?:\d{1,2}\.0\s*)?appendi(?:x|ces)\b", re.IGNORECASE | re.MULTILINE
)
_CERT_REGION_MAX_PAGES = 30


def _certificate_region(pages: List[Page]) -> List[Page]:
    """Pages from the first Certificate of Qualified Person to the end of the
    certificates (an appendix, or the end of the report). Certificates after
    the first often carry no repeated heading, so a per-heading block would
    miss them. Table of Contents entries naming the section don't count."""
    list_pages = _list_like_pages(pages)
    for idx, p in enumerate(pages):
        if p.number in list_pages or not _CERT_HEADING_RE.search(p.text):
            continue
        region = [p]
        for q in pages[idx + 1: idx + _CERT_REGION_MAX_PAGES]:
            head = "\n".join(q.text.splitlines()[:15])
            if _APPENDIX_HEADING_RE.search(head):
                break
            region.append(q)
        return region
    return []


def _statutory_date_pages(pages: List[Page]) -> List[Page]:
    """Where Form 43-101F1 and Part 8 require the report's own effective date:
    the title page(s), the date and signature page, and each QP certificate
    and consent. Body text is excluded on purpose — it legitimately cites
    other reports' effective dates, and a Mineral Resource estimate can carry
    its own effective date distinct from the report's."""
    list_pages = _list_like_pages(pages)
    first_list = min(list_pages) if list_pages else None
    front = [p for p in pages[:4] if first_list is None or p.number < first_list] or pages[:2]
    signature = [
        p for p in pages
        if p.number not in list_pages and _SIGNATURE_PAGE_RE.search(p.text)
        and p not in front
    ]
    consents = [
        p for p in pages
        if p.number not in list_pages and _CONSENT_HEADING_RE.search(p.text)
    ]
    selected = {p.number: p for p in front + signature + _certificate_region(pages) + consents}
    return [selected[n] for n in sorted(selected)]


def check_effective_date_consistency(pages: List[Page]) -> Finding:
    found: Dict[date, set] = {}
    raw_by_date: Dict[date, str] = {}
    unparsed_pages = []
    for p in _statutory_date_pages(pages):
        for m in _EFFECTIVE_DATE_RE.finditer(p.text):
            context = p.text[max(0, m.start() - _SUPERSEDED_LOOKBACK): m.start()]
            if _SUPERSEDED_CONTEXT_RE.search(context):
                continue  # citing a different, superseded report's effective date
            raw = m.group(1)
            parsed = _parse_date(raw)
            if parsed is None:
                unparsed_pages.append(p.number)
                continue
            found.setdefault(parsed, set()).add(p.number)
            raw_by_date[parsed] = raw

    check_text = "Effective date matches on the title page, signature page and QP certificates"
    if not found:
        return _finding(
            "PY-DATE-CONSISTENCY", check_text,
            "consistency", "Cross-Document Consistency (Automated)", STATUS_NOT_ADDRESSED,
            "No \"effective date\" statements were found on the title page, date and "
            "signature page, or QP certificates.",
        )

    if len(found) == 1:
        (only_date,) = found.keys()
        return _finding(
            "PY-DATE-CONSISTENCY", check_text,
            "consistency", "Cross-Document Consistency (Automated)", STATUS_COMPLIANT,
            f"All {sum(len(v) for v in found.values())} \"effective date\" statement(s) "
            f"on the title, signature and certificate pages agree: {raw_by_date[only_date]}.",
            pages=sorted(found[only_date]),
        )

    detail = "; ".join(f"{raw_by_date[d]} (p.{sorted(pgs)})" for d, pgs in found.items())
    return _finding(
        "PY-DATE-CONSISTENCY", check_text,
        "consistency", "Cross-Document Consistency (Automated)", STATUS_NON_COMPLIANT,
        f"{len(found)} different effective dates appear across the title page, "
        f"signature page and QP certificates: {detail}. The report's effective date "
        "must be the same in each of these places.",
        evidence=detail,
        pages=sorted({pg for pgs in found.values() for pg in pgs}),
        confidence=0.75,
    )


# --------------------------------------------------------------------------
# 7. Certificate (e): every Item 1-27 is claimed by at least one QP
# --------------------------------------------------------------------------

_RESPONSIBLE_START_RE = re.compile(r"responsible\s+for\b", re.IGNORECASE)
# A statement ends at a period followed by a newline, or by whitespace and a
# capital letter. Periods inside section numbers ("1.1.2.1", and even the
# typo'd "1.3.10. 1.3.12") don't end it.
_SENTENCE_END_RE = re.compile(r"\.\s*\n|\.\s+(?=[A-Z])")
_SECTION_WORD_RE = re.compile(r"\b(?:sections?|items?)\b", re.IGNORECASE)
_WHOLE_REPORT_RE = re.compile(
    r"\b(?:overall|entire|whole|all\s+(?:sections|items|parts)\s+of)\b[^.]*\breport\b",
    re.IGNORECASE,
)
# Real reports carry the QP -> section mapping in an Introduction table as
# often as in the certificates ("Table 2-1: Summary of Qualified Persons",
# "Qualified Persons and Responsibilities").
_QP_TABLE_HEADING_RE = re.compile(
    r"summary\s+of\s+qualified\s+persons"
    r"|qualified\s+persons?\s+and\s+(?:their\s+)?responsibilit"
    r"|responsibilit\w*\s+of\s+(?:the\s+)?qualified\s+persons"
    r"|qp\s+responsibilit",
    re.IGNORECASE,
)
_DESIGNATION_RE = re.compile(
    r"\bP\.\s?(?:Eng|Geo|Geol|Ag)\b|\bP\.\s?G\.|\bPh\.?\s?D\b|\bF?AusIMM\b|\bCPG\b"
    r"|\bSME[-\s]RM\b|\bRM[-\s]SME\b|\bEur\s?Geol\b|\bF?IMMM\b|\bPr\.?\s?Sci\.?\s?Nat\b",
    re.IGNORECASE,
)
_ROW_MAX_LINES = 6
_ROW_STOP_RE = re.compile(r"^\s*\d{1,2}\.\d+\s*$|^\s*(?:table|figure)\s+\d", re.IGNORECASE)
_PAGE_LABEL_RE = re.compile(r"^\s*\d{1,2}\s*[-–]\s*\d{1,3}\s*$")
_RANGE_RE = re.compile(r"\b(\d{1,2})\s*(?:to|through|[-–—])\s*(\d{1,2})\b")
_NUM_RE = re.compile(r"\b(\d{1,2})\b")
# Whole dotted sub-item, so "19.1.1" collapses to 19 (not "19" plus a stray "1").
_DECIMAL_SUBITEM_RE = re.compile(r"\b(\d{1,2})(?:\.\d+)+\b")


def _extract_item_numbers(span: str) -> set:
    """Pull Item/Section numbers out of a text span: ranges ('4 to 11'),
    singles, and decimal sub-items ('26.2' means Item 26 — collapsed first so
    it isn't also read as standalone Item 2), clipped to 1-27."""
    span = _DECIMAL_SUBITEM_RE.sub(r"\1", span)
    nums = set()
    for rm in _RANGE_RE.finditer(span):
        a, b = int(rm.group(1)), int(rm.group(2))
        if 1 <= a <= _NUM_ITEMS and 1 <= b <= _NUM_ITEMS and a <= b:
            nums.update(range(a, b + 1))
    remainder = _RANGE_RE.sub(" ", span)
    for nm in _NUM_RE.finditer(remainder):
        n = int(nm.group(1))
        if 1 <= n <= _NUM_ITEMS:
            nums.add(n)
    return nums


def _responsibility_statements(text: str) -> List[str]:
    """Each "responsible for ..." statement, up to its real sentence end."""
    statements = []
    for m in _RESPONSIBLE_START_RE.finditer(text):
        tail = text[m.end(): m.end() + 500]
        end = _SENTENCE_END_RE.search(tail)
        statements.append(tail[: end.start()] if end else tail)
    return statements


def _certificate_coverage(region: List[Page]) -> Tuple[Dict[int, set], int]:
    """Items claimed in certificate "I am responsible for ..." statements.

    A statement only counts numbers if it names Sections/Items, so "Section
    1.5 of NI 43-101" elsewhere in a certificate can't claim Item 1. The one
    exception is a single-QP report: "responsible for the overall preparation
    of the Technical Report" with no sections listed claims all of it. With
    several QPs that phrase means coordination, so it adds nothing there."""
    statements = []  # (page, item numbers, claims whole report)
    for p in region:
        for stmt in _responsibility_statements(p.text):
            nums = _extract_item_numbers(stmt) if _SECTION_WORD_RE.search(stmt) else set()
            whole = not nums and _WHOLE_REPORT_RE.search(stmt) is not None
            if nums or whole:
                statements.append((p.number, nums, whole))

    covered: Dict[int, set] = {}
    if len(statements) == 1 and statements[0][2]:
        pno = statements[0][0]
        return {n: {pno} for n in range(1, _NUM_ITEMS + 1)}, 1
    for pno, nums, _whole in statements:
        for n in nums:
            covered.setdefault(n, set()).add(pno)
    return covered, len(statements)


def _qp_table_coverage(pages: List[Page]) -> Tuple[Dict[int, set], List[int]]:
    """Items claimed in a QP responsibilities table. Each row starts at a line
    carrying a professional designation (P.Eng., P.Geo., ...) and runs until
    the next row, a new heading, or a few lines — so numbers in prose before
    or after the table are never read as responsibilities."""
    list_pages = _list_like_pages(pages)
    for idx, p in enumerate(pages):
        if p.number in list_pages:
            continue
        hm = _QP_TABLE_HEADING_RE.search(p.text)
        if not hm:
            continue
        segments = [(p.number, p.text[hm.end():].splitlines())]
        if idx + 1 < len(pages):
            nxt = pages[idx + 1].text.splitlines()
            # Only a true continuation: rows resume near the top of the page.
            if any(_DESIGNATION_RE.search(l) for l in nxt[:12]):
                segments.append((pages[idx + 1].number, nxt))
        covered: Dict[int, set] = {}
        for pno, lines in segments:
            starts = [i for i, l in enumerate(lines) if _DESIGNATION_RE.search(l)]
            for k, i in enumerate(starts):
                end = starts[k + 1] if k + 1 < len(starts) else len(lines)
                row = []
                for line in lines[i: min(end, i + _ROW_MAX_LINES)]:
                    if row and _ROW_STOP_RE.match(line):
                        break
                    if not _PAGE_LABEL_RE.match(line):
                        row.append(line)
                for n in _extract_item_numbers(" ".join(row)):
                    covered.setdefault(n, set()).add(pno)
        return covered, [p.number]
    return {}, []


def check_certificate_item_coverage(
    pages: List[Page], page_items: Optional[Dict[int, Tuple[str, str]]] = None
) -> Finding:
    check_text = "Certificate (e): all Items are claimed by a QP"
    item_title = "Part 8 – Certificates and Consents of Qualified Persons"
    region = _certificate_region(pages)
    covered, statements = _certificate_coverage(region)
    table_covered, table_pages = _qp_table_coverage(pages)
    for n, pgs in table_covered.items():
        covered.setdefault(n, set()).update(pgs)

    if not region and not table_pages:
        return _finding(
            "PY-CERT-COVERAGE", check_text, "certificates", item_title, STATUS_NOT_ADDRESSED,
            "No \"Certificate of Qualified Person\" section or QP responsibilities "
            "table was found.",
        )

    not_applicable = not_applicable_items(pages, page_items or {})
    missing = sorted(
        n for n in range(1, _NUM_ITEMS + 1) if n not in covered and n not in not_applicable
    )
    all_pages = sorted(
        {pg for pgs in covered.values() for pg in pgs}
        | ({region[0].number} if region else set())
        | set(table_pages)
    )
    sources = []
    if region:
        sources.append(
            f"certificates (p.{region[0].number}-{region[-1].number}, "
            f"{statements} responsibility statement(s))"
        )
    if table_pages:
        sources.append(f"the QP responsibilities table (p.{table_pages[0]})")
    source_note = " and ".join(sources)
    na_note = (
        f" Item(s) {sorted(not_applicable)} are stated as not applicable in the "
        "report and need no QP."
        if not_applicable else ""
    )
    if missing:
        return _finding(
            "PY-CERT-COVERAGE", check_text, "certificates", item_title, STATUS_NON_COMPLIANT,
            f"Read {source_note}, but Item(s) {missing} are not claimed as any QP's "
            f"responsibility.{na_note} (Regex-based parsing — verify manually.)",
            evidence=f"Uncovered Items: {missing}",
            pages=all_pages,
            confidence=0.6,
        )
    return _finding(
        "PY-CERT-COVERAGE", check_text, "certificates", item_title, STATUS_COMPLIANT,
        f"Read {source_note}; every Item is claimed by at least one qualified "
        f"person.{na_note}",
        pages=all_pages,
        confidence=0.8,
    )


# --------------------------------------------------------------------------
# 8. Item 21: capital/operating costs in tabular form (PDF only)
# --------------------------------------------------------------------------

def check_cost_table_present(
    pages: List[Page], page_items: Dict[int, Tuple[str, str]], pdf_path: Optional[str]
) -> Finding:
    item_21_pages = sorted(n for n, (iid, _t) in page_items.items() if iid == "item_21")
    if not item_21_pages:
        return _finding(
            "PY-COST-TABLE", "Item 21: costs set out in tabular form", "item_21",
            "Capital and Operating Costs", STATUS_NOT_ADDRESSED,
            "Item 21 section was not detected in the report; cannot verify table presence.",
        )
    na_page = not_applicable_items(pages, page_items).get(21)
    if na_page is not None:
        # Items 15-22 apply to advanced properties; an exploration-stage
        # report states Item 21 is not applicable rather than tabling costs.
        return _finding(
            "PY-COST-TABLE", "Item 21: costs set out in tabular form", "item_21",
            "Capital and Operating Costs", STATUS_NOT_APPLICABLE,
            f"The report states Item 21 is not applicable (p.{na_page}), so no cost "
            "table is required. Confirm that fits the property's stage.",
            pages=[na_page],
        )
    if not pdf_path or not pdf_path.lower().endswith(".pdf"):
        return _finding(
            "PY-COST-TABLE", "Item 21: costs set out in tabular form", "item_21",
            "Capital and Operating Costs", STATUS_NOT_ADDRESSED,
            "Automated table detection only supports PDF reports; verify manually.",
            pages=item_21_pages,
        )

    try:
        import fitz
    except ImportError:
        return _finding(
            "PY-COST-TABLE", "Item 21: costs set out in tabular form", "item_21",
            "Capital and Operating Costs", STATUS_NOT_ADDRESSED,
            "PyMuPDF is not installed; cannot run table detection.",
            pages=item_21_pages,
        )

    found_pages = []
    try:
        with fitz.open(pdf_path) as doc:
            for pno in item_21_pages:
                if pno - 1 >= len(doc):
                    continue
                page = doc[pno - 1]
                tf = page.find_tables()
                for tbl in tf.tables:
                    if tbl.row_count >= 2 and tbl.col_count >= 2:
                        found_pages.append(pno)
                        break
    except Exception as exc:
        return _finding(
            "PY-COST-TABLE", "Item 21: costs set out in tabular form", "item_21",
            "Capital and Operating Costs", STATUS_NOT_ADDRESSED,
            f"Table detection failed ({exc}); verify manually.",
            pages=item_21_pages,
        )

    if found_pages:
        return _finding(
            "PY-COST-TABLE", "Item 21: costs set out in tabular form", "item_21",
            "Capital and Operating Costs", STATUS_COMPLIANT,
            f"A table with ≥2 rows/columns was detected on page(s) {found_pages}.",
            pages=found_pages,
        )
    return _finding(
        "PY-COST-TABLE", "Item 21: costs set out in tabular form", "item_21",
        "Capital and Operating Costs", STATUS_NON_COMPLIANT,
        f"Item 21 narrative was detected on page(s) {item_21_pages} but no tabular "
        "structure was found there; the Instrument requires major cost components "
        "in tabular form.",
        pages=item_21_pages,
    )


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

def run_structural_checks(
    pages: List[Page],
    page_items: Dict[int, Tuple[str, str]],
    report_path: Optional[str] = None,
) -> List[Finding]:
    """Run every deterministic check and return one Finding per check.

    Never raises: a check that errors becomes a Not Addressed finding with
    the error recorded, so one bad regex can't take down the whole run.
    """
    checks = [
        lambda: check_table_of_contents(pages, page_items),
        lambda: check_references_list(pages),
        lambda: check_recommendation_phases(pages, page_items),
        lambda: check_historical_estimate_disclaimer(pages),
        lambda: check_adjacent_property_disclaimer(pages),
        lambda: check_effective_date_consistency(pages),
        lambda: check_certificate_item_coverage(pages, page_items),
        lambda: check_cost_table_present(pages, page_items, report_path),
        lambda: check_summary_numbers(pages, page_items),
    ]
    findings = []
    for i, run in enumerate(checks, start=1):
        try:
            findings.append(run())
        except Exception as exc:  # pragma: no cover - defensive
            findings.append(
                _finding(
                    f"PY-ERR-{i}", f"Structural check #{i} failed to run", "",
                    "General / Unmapped", STATUS_NOT_ADDRESSED,
                    "", evidence=str(exc),
                )
            )
    return findings
