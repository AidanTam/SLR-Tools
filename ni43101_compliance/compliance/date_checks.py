"""Deterministic checks: the dates in the report are in a possible order.

`check_effective_date_consistency` already confirms the effective date is the
same everywhere it is stated. These checks add the ordering rules that follow
from what the dates mean:

* the effective date cannot be after the report date;
* a QP cannot sign (date a certificate) before the effective date;
* a site visit cannot be after the effective date;
* the reference list cannot cite work published after the effective date.

The report date is read from the running header or footer that repeats it on
most pages (the most common date there), falling back to the title page.
Dates come from the same parser the effective-date check uses.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Dict, List, Optional, Tuple

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

_MONTH = (r"(?:January|February|March|April|May|June|July|August|September|October|"
          r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?")
# "October 27, 2025", "27 October 2025", "27th day of October, 2025"
_DATE_RE = re.compile(
    rf"\b({_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?{_MONTH},?\s+\d{{4}})\b",
    re.IGNORECASE,
)
# "March 3 to 5, 2025", "March 3, 4 and 5, 2025": the last day is what matters.
_RANGE_RE = re.compile(
    rf"\b({_MONTH})\s+(\d{{1,2}})(?:\s*(?:,|and|&|to|through|[-–])\s*\d{{1,2}})+,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_RANGE_LAST = re.compile(r"(\d{1,2})(?!.*\d{1,2}\s*,?\s+\d{4})")


def _parse(raw: str) -> Optional[date]:
    from .structural_checks import _parse_date
    return _parse_date(raw)


def _dates_in(text: str) -> List[Tuple[date, int]]:
    """Every parseable date in the text with its offset."""
    out: List[Tuple[date, int]] = []
    for m in _RANGE_RE.finditer(text):
        nums = re.findall(r"\d{1,2}", m.group(0).split(m.group(3))[0])
        if nums:
            d = _parse(f"{m.group(1)} {nums[-1]}, {m.group(3)}")
            if d:
                out.append((d, m.start()))
    for m in _DATE_RE.finditer(text):
        d = _parse(m.group(1))
        if d:
            out.append((d, m.start()))
    return out


def _fmt(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


# ---------------------------------------------------------------------------
# Reading the key dates
# ---------------------------------------------------------------------------

def _effective_date(pages: List[Page]) -> Optional[date]:
    from .structural_checks import (
        _EFFECTIVE_DATE_RE, _SUPERSEDED_CONTEXT_RE, _parse_date, _statutory_date_pages,
    )

    votes: Counter = Counter()
    for p in _statutory_date_pages(pages):
        for m in _EFFECTIVE_DATE_RE.finditer(p.text):
            ctx = p.text[max(0, m.start() - 220): m.start()]
            if _SUPERSEDED_CONTEXT_RE.search(ctx):
                continue
            d = _parse_date(m.group(1))
            if d:
                votes[d] += 1
    return votes.most_common(1)[0][0] if votes else None


def _running_lines(page: Page) -> List[str]:
    lines = [l.strip() for l in page.text.splitlines() if l.strip()]
    return lines[:4] + lines[-3:]


def _report_date(pages: List[Page], effective: Optional[date]) -> Tuple[Optional[date], str]:
    """Most common date in running headers/footers; else a date on the title page."""
    votes: Counter = Counter()
    for p in pages:
        seen = set()
        for line in _running_lines(p):
            for d, _ in _dates_in(line):
                seen.add(d)
        votes.update(seen)
    if votes:
        d, n = votes.most_common(1)[0]
        if n >= max(5, int(len(pages) * 0.2)):
            return d, "page headers/footers"
    for p in pages[:3]:
        for m in re.finditer(r"(?:report\s+date|date\s+of\s+(?:this\s+)?report|dated|date)\s*[:\-]?\s*", p.text, re.I):
            for d, _ in _dates_in(p.text[m.end(): m.end() + 40]):
                return d, f"title page (p.{p.number})"
    # An undeclared date alone on the cover that isn't the effective date.
    for p in pages[:2]:
        for line in p.text.splitlines():
            if re.search(r"effective", line, re.I):
                continue
            ds = _dates_in(line)
            if len(ds) == 1 and len(line.strip()) < 40 and ds[0][0] != effective:
                return ds[0][0], f"title page (p.{p.number})"
    return None, ""


# ---------------------------------------------------------------------------
# Check 1: report date and signature dates vs the effective date
# ---------------------------------------------------------------------------

_SIGN_CONTEXT = re.compile(r"dated|signed|date\s*:|this\s+\d", re.IGNORECASE)


def _signature_dates(pages: List[Page]) -> List[Tuple[date, int]]:
    """Dates a QP signed on. In a certificate that is the closing "Dated this
    2nd day of May, 2025" line, so only the tail of each certificate is read:
    earlier text (a QP's experience, "this report, dated April 2014...") names
    other documents' dates."""
    from .certificate_checks import _certificates
    from .structural_checks import _certificate_region, _CONSENT_HEADING_RE, _list_like_pages

    skip = _list_like_pages(pages)
    region = _certificate_region(pages)
    in_region = {p.number for p in region}
    out: List[Tuple[date, int]] = []
    for _name, seg, first_page in _certificates(region):
        tail = seg[-600:]
        for d, off in _dates_in(tail):
            ctx = tail[max(0, off - 60): off + 10]
            if _SIGN_CONTEXT.search(ctx) and not re.search(r"effective|visited|inspect|site", ctx, re.I):
                out.append((d, first_page))
    for p in pages:
        if p.number in skip or p.number in in_region or not _CONSENT_HEADING_RE.search(p.text):
            continue
        for d, off in _dates_in(p.text):
            ctx = p.text[max(0, off - 60): off + 10]
            if _SIGN_CONTEXT.search(ctx) and not re.search(r"effective|visited|inspect|site", ctx, re.I):
                out.append((d, p.number))
    return out


def check_date_order(pages: List[Page]) -> Finding:
    from .structural_checks import _finding

    check_id = "PY-DATE-ORDER"
    text = "Report date is on or after the effective date, and QPs sign on or after it"
    effective = _effective_date(pages)
    if effective is None:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No effective date was found on the title, signature or certificate pages.",
        )
    report, source = _report_date(pages, effective)
    signatures = _signature_dates(pages)

    problems: List[str] = []
    pg: List[int] = []
    if report is not None and report < effective:
        problems.append(
            f"the report date ({_fmt(report)}, from {source}) is before the effective "
            f"date ({_fmt(effective)})"
        )
    early = [(d, n) for d, n in signatures if d < effective]
    if early:
        shown = "; ".join(f"{_fmt(d)} (p.{n})" for d, n in early[:4])
        problems.append(f"signature date(s) before the effective date {_fmt(effective)}: {shown}")
        pg += [n for _d, n in early]

    if problems:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NON_COMPLIANT,
            "Date order is impossible: " + "; ".join(problems) + ".",
            evidence="; ".join(problems), pages=pg, confidence=0.75,
        )
    parts = [f"effective date {_fmt(effective)}"]
    if report is not None:
        parts.append(f"report date {_fmt(report)} ({source})")
    if signatures:
        parts.append(f"{len(signatures)} signature date(s), all on or after the effective date")
    else:
        parts.append("no signature dates were found to compare")
    return _finding(
        check_id, text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
        "Dates are in a possible order: " + "; ".join(parts) + ".",
        confidence=0.75 if report is not None else 0.55,
    )


# ---------------------------------------------------------------------------
# Check 2: site visit not after the effective date
# ---------------------------------------------------------------------------

_VISIT_RE = re.compile(
    r"(?:visited|visit(?:ed)?\s+(?:to\s+)?the\s+(?:property|site|project|mine)|site\s+visit|"
    r"personal\s+inspection|inspected)[^.\n]{0,160}",
    re.IGNORECASE,
)
_NO_VISIT_RE = re.compile(r"\bnot\s+(?:visited|inspected)|have\s+not\s+visited|no\s+site\s+visit", re.IGNORECASE)


def check_site_visit_dates(pages: List[Page]) -> Finding:
    from .structural_checks import _finding, _list_like_pages

    check_id = "PY-DATE-SITEVISIT"
    text = "Site visit dates are on or before the effective date"
    effective = _effective_date(pages)
    if effective is None:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No effective date was found, so site visit dates could not be compared with it.",
        )
    skip = _list_like_pages(pages)
    visits: Dict[date, set] = {}
    for p in pages:
        if p.number in skip:
            continue
        flat = re.sub(r"\s+", " ", p.text)
        for m in _VISIT_RE.finditer(flat):
            if _NO_VISIT_RE.search(m.group(0)):
                continue
            for d, _ in _dates_in(m.group(0)):
                visits.setdefault(d, set()).add(p.number)
    if not visits:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No dated site visits were found to compare with the effective date.",
        )
    late = {d: pgs for d, pgs in visits.items() if d > effective}
    if late:
        detail = "; ".join(f"{_fmt(d)} (p.{sorted(pgs)[:4]})" for d, pgs in sorted(late.items()))
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NEEDS_REVIEW,
            f"Site visit date(s) fall after the effective date ({_fmt(effective)}): {detail}. "
            "The date may belong to a different event, or the effective date may be stale.",
            evidence=detail, pages=[n for pgs in late.values() for n in pgs], confidence=0.6,
        )
    return _finding(
        check_id, text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
        f"{len(visits)} site visit date(s) found, all on or before the effective date "
        f"({_fmt(effective)}).",
        pages=[n for pgs in visits.values() for n in pgs], confidence=0.7,
    )


# ---------------------------------------------------------------------------
# Check 3: no reference dated after the effective date
# ---------------------------------------------------------------------------

def check_reference_years(pages: List[Page]) -> Finding:
    from .structural_checks import (
        _REF_BLOCK_MAX_PAGES, _REF_HEADING_RE, _REF_STOP_RE, _finding, _list_like_pages,
    )

    check_id = "PY-DATE-REFYEARS"
    text = "No reference is dated after the effective date"
    effective = _effective_date(pages)
    if effective is None:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No effective date was found, so reference years could not be compared with it.",
        )
    skip = _list_like_pages(pages)
    ref_page = next((p for p in pages if p.number not in skip and _REF_HEADING_RE.search(p.text)), None)
    if ref_page is None:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No References section was found.",
        )
    lines: List[Tuple[int, str]] = []
    for p in pages:
        if not (ref_page.number <= p.number <= ref_page.number + _REF_BLOCK_MAX_PAGES):
            continue
        body = p.text
        if p.number == ref_page.number:
            body = body[_REF_HEADING_RE.search(body).end():]
        stop = _REF_STOP_RE.search(body)
        lines += [(p.number, l) for l in (body[: stop.start()] if stop else body).splitlines()]
        if stop:
            break

    # An entry begins with its author and carries the publication year; a
    # retrieval date ("accessed 2026") or an in-press year is not one.
    later: Dict[int, set] = {}
    entries = 0
    for pno, line in lines:
        if not re.match(r"^\s*[A-Z][\w'’.\-&]+", line):
            continue
        scrub = re.sub(r"(?:accessed|retrieved|viewed|downloaded|updated|cited|dated|issued)[^.;)\]]{0,40}", "", line, flags=re.I)
        m = re.search(r"[\s(,.]((?:19|20)\d{2})[a-z]?[\s).,]", scrub)
        if not m:
            continue
        entries += 1
        year = int(m.group(1))
        if year > effective.year:
            later.setdefault(year, set()).add(pno)
    if not entries:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No dated reference entries were recognised.",
        )
    if later:
        detail = "; ".join(f"{y} (p.{sorted(p)[:4]})" for y, p in sorted(later.items()))
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_NEEDS_REVIEW,
            f"Reference year(s) later than the effective date ({_fmt(effective)}): {detail}. "
            "Work published after the effective date cannot have informed the report as of "
            "that date (regex-based; verify the entries).",
            evidence=detail, pages=[n for p in later.values() for n in p], confidence=0.6,
        )
    return _finding(
        check_id, text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
        f"{entries} dated reference entries; none is later than the effective date year "
        f"({effective.year}).",
        confidence=0.7,
    )


def check_dates(pages: List[Page]) -> List[Finding]:
    return [check_date_order(pages), check_site_visit_dates(pages), check_reference_years(pages)]
