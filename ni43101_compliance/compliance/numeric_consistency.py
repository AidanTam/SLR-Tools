"""Deterministic check: numbers stated in the Summary (Item 1) must be
supported by the full sections of the report.

Item 1 restates figures that are developed in Items 4-26 (resource tonnage and
grade, capital cost, mine life, plant throughput...). If a Summary figure has
no counterpart anywhere in the body, either the Summary is stale or the body
was edited without updating it. This is the most common late-draft
inconsistency in a technical report, and it is purely mechanical to look for.

Two kinds of figure are pulled from the Summary:

* quantities with a unit ("77 Mt", "27,000 t/d", "US$1.2 billion", "1.08 g/t")
  are compared after converting to a base unit, so "27,000 t/d" in the Summary
  agrees with "27 kt/d" in the body;
* stand-alone numbers in table cells (PDF text extraction puts one cell per
  line), compared as bare values, also allowing a x1000 / x1,000,000 change of
  scale between a Summary table (Mt) and its source table (kt).

A figure counts as supported when some body figure agrees with it to the
precision either one is written at, so a Summary rounded to "9.9 Mt" agrees
with "9.86 Mt" in the body. Only figures with no counterpart are reported.

Like every check in this package it is a heuristic over extracted text: an
unmatched figure means "could not find this elsewhere", not "wrong", and
derived numbers (a sum, a rounding to a different unit) can legitimately have
no verbatim counterpart. A QP should check the cited lines.
"""

from __future__ import annotations

import bisect
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from .models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_PARTIAL,
    Criterion,
    Finding,
    Page,
)

CHECK_ID = "PY-SUMMARY-NUMBERS"
CHECK_TEXT = "Figures stated in the Summary agree with the full sections of the report"
ITEM_ID = "consistency"
ITEM_TITLE = "Cross-Document Consistency (Automated)"

# Below this many checkable Summary figures the result says nothing useful.
MIN_FIGURES = 5
# Fraction of unsupported figures above which the check is Non-Compliant
# rather than Partial. Derived figures legitimately lack a counterpart, so a
# few misses are only "review these".
NON_COMPLIANT_FRACTION = 0.30

# ---------------------------------------------------------------------------
# Number and unit parsing
# ---------------------------------------------------------------------------

_NUMBER = r"(?<![\w.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"

# unit text (lower-case) -> (family, factor to the family's base unit)
_UNITS: Dict[str, Tuple[str, float]] = {
    "kt/d": ("t_per_day", 1e3), "t/d": ("t_per_day", 1.0), "tpd": ("t_per_day", 1.0),
    "ktpd": ("t_per_day", 1e3),
    "mt/a": ("t_per_year", 1e6), "mtpa": ("t_per_year", 1e6), "mt/y": ("t_per_year", 1e6),
    "mt/yr": ("t_per_year", 1e6), "kt/a": ("t_per_year", 1e3), "ktpa": ("t_per_year", 1e3),
    "t/a": ("t_per_year", 1.0), "tpa": ("t_per_year", 1.0),
    "tonnes per day": ("t_per_day", 1.0), "tonne per day": ("t_per_day", 1.0),
    "t per day": ("t_per_day", 1.0), "kt per day": ("t_per_day", 1e3),
    "tonnes per year": ("t_per_year", 1.0), "tonnes per annum": ("t_per_year", 1.0),
    "t per year": ("t_per_year", 1.0), "kt per year": ("t_per_year", 1e3),
    "mt per year": ("t_per_year", 1e6), "mt per annum": ("t_per_year", 1e6),
    "mt": ("mass", 1e6), "kt": ("mass", 1e3), "t": ("mass", 1.0),
    "tonnes": ("mass", 1.0), "tonne": ("mass", 1.0), "tons": ("mass", 1.0),
    "moz": ("oz", 1e6), "koz": ("oz", 1e3), "oz": ("oz", 1.0),
    "mlb": ("lb", 1e6), "klb": ("lb", 1e3), "lb": ("lb", 1.0), "lbs": ("lb", 1.0),
    "g/t": ("grade", 1.0), "gpt": ("grade", 1.0), "ppm": ("grade", 1.0),
    "%": ("pct", 1.0),
    "km": ("length", 1e3), "m": ("length", 1.0), "metres": ("length", 1.0),
    "meters": ("length", 1.0),
    "ha": ("area", 1.0), "hectares": ("area", 1.0),
    "years": ("years", 1.0), "year": ("years", 1.0), "yrs": ("years", 1.0),
    "months": ("months", 1.0),
}
# Multi-word units ("tonnes per day") may wrap across a line; a hyphen joins a
# number to its unit in compound adjectives ("a 14-year mine life").
_UNIT_ALT = "|".join(
    re.escape(u).replace(r"\ ", r"\s+") for u in sorted(_UNITS, key=len, reverse=True)
)
_QUANTITY_RE = re.compile(
    _NUMBER + r"[ \t-]?(" + _UNIT_ALT + r")(?![A-Za-z/])", re.IGNORECASE
)
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-five": 25, "thirty": 30, "forty": 40,
    "fifty": 50,
}
# Spelled-out durations ("an additional five years") are quoted in prose as
# often as digits; only time units are read this way, because for anything
# else a spelled number is usually a count of things, not a measurement.
_WORD_DURATION_RE = re.compile(
    r"\b(" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")[\s-]+(?:(?:consecutive|continuous|operating|full|calendar)[\s-]+)?(years?|months?)\b",
    re.IGNORECASE,
)

_SCALE_WORDS = {
    "billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "m": 1e6, "mm": 1e6,
    "thousand": 1e3, "k": 1e3,
}
# "$", "US$", "C$", "CAD$" ... then a number, optional scale word, optional "/unit".
_MONEY_RE = re.compile(
    r"(?:US|C|CA|CAD|USD|A|AU)?\$\s?" + _NUMBER
    + r"(?:\s{0,3}(billion|million|thousand|bn|mm|m|b|k)(?![A-Za-z]))?"
    + r"(?:\s?/\s?(oz|t|tonne|lb|st|kt|g|ton))?",
    re.IGNORECASE,
)
_BARE_LINE_RE = re.compile(r"^\s*(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s+(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?))*\s*$")
_NUM_TOKEN_RE = re.compile(_NUMBER)
_SCALES = (1.0, 1e3, 1e-3, 1e6, 1e-6)


def _parse(token: str) -> Tuple[float, int]:
    """Numeric value and number of decimals as written."""
    clean = token.replace(",", "")
    decimals = len(clean.split(".")[1]) if "." in clean else 0
    return float(clean), decimals


def _is_year_like(token: str) -> bool:
    return "," not in token and "." not in token and len(token) == 4 and 1900 <= int(token) <= 2100


def _sig_digits(token: str) -> int:
    return len(token.replace(",", "").replace(".", "").lstrip("0"))


class Figure:
    """One number found in the report, in base units where it has a unit."""
    __slots__ = ("family", "value", "step", "text", "page", "raw_value", "raw_step", "sig")

    def __init__(self, family: str, value: float, step: float, text: str, page: int,
                 raw: Optional[Tuple[float, float, int]] = None):
        self.family, self.value, self.step, self.text, self.page = family, value, step, text, page
        # The number as written (before unit conversion) and its significant digits.
        self.raw_value, self.raw_step, self.sig = raw if raw else (value, step, 0)


def _line_of(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return (text[start:] if end == -1 else text[start:end]).strip()


def _quantities(page: Page) -> Iterable[Figure]:
    """Unit-bearing quantities on a page (prose, and table cells that carry the unit)."""
    text = page.text
    for m in _QUANTITY_RE.finditer(text):
        family, factor = _UNITS[re.sub(r"\s+", " ", m.group(2).lower())]
        value, decimals = _parse(m.group(1))
        yield Figure(family, value * factor, (10.0 ** -decimals) * factor,
                     _context(text, m.start(), m.end()), page.number,
                     raw=(value, 10.0 ** -decimals, _sig_digits(m.group(1))))
    for m in _WORD_DURATION_RE.finditer(text):
        family = "years" if m.group(2).lower().startswith("year") else "months"
        yield Figure(family, float(_WORD_NUMBERS[m.group(1).lower()]), 1.0,
                     _context(text, m.start(), m.end()), page.number)
    for m in _MONEY_RE.finditer(text):
        value, decimals = _parse(m.group(1))
        factor = _SCALE_WORDS.get((m.group(2) or "").lower(), 1.0)
        per = (m.group(3) or "").lower()
        family = f"usd_per_{per}" if per else "usd"
        yield Figure(family, value * factor, (10.0 ** -decimals) * factor,
                     _context(text, m.start(), m.end()), page.number,
                     raw=(value, 10.0 ** -decimals, _sig_digits(m.group(1))))


def _context(text: str, start: int, end: int, radius: int = 60) -> str:
    snippet = text[max(0, start - radius): end + radius]
    return re.sub(r"\s+", " ", snippet).strip()


def _bare_numbers(page: Page, only_table_lines: bool) -> Iterable[Figure]:
    """Plain numbers. In the Summary only lines that are nothing but numbers
    (table cells) are used; in the body every number is a possible source."""
    text = page.text
    if only_table_lines:
        pos = 0
        for line in text.splitlines(keepends=True):
            if _BARE_LINE_RE.match(line):
                for m in _NUM_TOKEN_RE.finditer(line):
                    tok = m.group(1)
                    if _is_year_like(tok) or (_sig_digits(tok) < 3 and "." not in tok):
                        continue
                    value, decimals = _parse(tok)
                    yield Figure("bare", value, 10.0 ** -decimals, _row_context(text, pos), page.number)
            pos += len(line)
    else:
        for m in _NUM_TOKEN_RE.finditer(text):
            value, decimals = _parse(m.group(1))
            yield Figure("bare", value, 10.0 ** -decimals, "", page.number)


def _row_context(text: str, pos: int) -> str:
    """The few lines around a table cell, to say which row it belongs to."""
    lines = text[:pos].splitlines()[-4:] + text[pos:].splitlines()[:2]
    return re.sub(r"\s+", " ", " ".join(l.strip() for l in lines if l.strip()))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

class _Pool:
    """Body figures by family, sorted by value for windowed lookup."""

    def __init__(self, figures: Iterable[Figure]):
        by_family: Dict[str, List[Figure]] = defaultdict(list)
        for f in figures:
            by_family[f.family].append(f)
        self._values: Dict[str, List[float]] = {}
        self._figs: Dict[str, List[Figure]] = {}
        for fam, figs in by_family.items():
            figs.sort(key=lambda f: f.value)
            self._figs[fam] = figs
            self._values[fam] = [f.value for f in figs]

    def supported(self, fig: Figure, scales: Tuple[float, ...] = (1.0,)) -> Optional[Figure]:
        vals = self._values.get(fig.family)
        if not vals:
            return None
        for k in scales:
            target = fig.value * k
            window = max(0.10 * abs(target), 0.5 * fig.step * k) + 1e-12
            lo = bisect.bisect_left(vals, target - window)
            hi = bisect.bisect_right(vals, target + window)
            for cand in self._figs[fig.family][lo:hi]:
                tol = 0.5 * max(fig.step * k, cand.step) + 1e-9 * max(1.0, abs(target))
                if abs(cand.value - target) <= tol:
                    return cand
        return None


# A figure this long is distinctive enough that a bare table cell carrying the
# same digits (the unit sits in the column header, not beside the number) is
# good evidence; shorter ones ("1.08", "14") coincide with unrelated numbers.
MIN_SIG_FOR_TABLE_CELL = 4


def _in_table_cell(fig: Figure, bare_pool: "_Pool") -> bool:
    if fig.family == "bare" or fig.sig < MIN_SIG_FOR_TABLE_CELL:
        return False
    as_written = Figure("bare", fig.raw_value, fig.raw_step, "", fig.page)
    return bare_pool.supported(as_written) is not None


def _summary_and_body(
    pages: List[Page], page_items: Dict[int, Tuple[str, str]], list_pages: set
) -> Tuple[List[Page], List[Page]]:
    summary = [p for p in pages if page_items.get(p.number, ("",))[0] == "item_1"
               and p.number not in list_pages]
    summary_nums = {p.number for p in summary}
    body = [p for p in pages if p.number not in summary_nums and p.number not in list_pages]
    return summary, body


def check_summary_numbers(
    pages: List[Page], page_items: Dict[int, Tuple[str, str]], list_pages: Optional[set] = None
) -> Finding:
    from .structural_checks import _finding, _list_like_pages  # avoid import cycle

    if list_pages is None:
        list_pages = _list_like_pages(pages)
    summary, body = _summary_and_body(pages, page_items, list_pages)
    if not summary:
        return _finding(
            CHECK_ID, CHECK_TEXT, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No Summary (Item 1) pages were detected, so its figures could not be "
            "compared with the rest of the report.",
        )

    body_quantities = [f for p in body for f in _quantities(p)]
    body_pool = _Pool(body_quantities)
    bare_pool = _Pool(f for p in body for f in _bare_numbers(p, only_table_lines=False))

    checked = 0
    missing: List[Figure] = []
    seen = set()
    for p in summary:
        figures = [(f, body_pool, (1.0,)) for f in _quantities(p)]
        figures += [(f, bare_pool, _SCALES) for f in _bare_numbers(p, only_table_lines=True)]
        for fig, pool, scales in figures:
            key = (fig.family, round(fig.value, 6))
            if key in seen:
                continue  # the same figure restated within the Summary counts once
            seen.add(key)
            checked += 1
            if pool.supported(fig, scales) is None and not _in_table_cell(fig, bare_pool):
                missing.append(fig)

    span = f"{summary[0].number}-{summary[-1].number}"
    if checked < MIN_FIGURES:
        return _finding(
            CHECK_ID, CHECK_TEXT, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            f"Only {checked} checkable figure(s) were found in the Summary (pages {span}); "
            "too few to compare with the rest of the report.",
            pages=[p.number for p in summary],
        )

    if not missing:
        return _finding(
            CHECK_ID, CHECK_TEXT, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
            f"All {checked} distinct figures checked in the Summary (pages {span}) "
            "have a matching value in the full sections of the report.",
            pages=[p.number for p in summary],
            confidence=0.8,
        )

    fraction = len(missing) / checked
    status = STATUS_NON_COMPLIANT if fraction > NON_COMPLIANT_FRACTION else STATUS_PARTIAL
    shown = missing[:12]
    lines = [f"p.{f.page}: {f.text}" for f in shown]
    more = f" (+{len(missing) - len(shown)} more)" if len(missing) > len(shown) else ""
    return _finding(
        CHECK_ID, CHECK_TEXT, ITEM_ID, ITEM_TITLE, status,
        f"{len(missing)} of {checked} distinct figures in the Summary (pages {span}) have no "
        "matching value anywhere in the full sections. Each may be a stale Summary figure, "
        "or a derived number (a total, or a change of unit) that has no verbatim counterpart: "
        "check the cited lines.",
        evidence=" | ".join(lines) + more,
        pages=[f.page for f in missing],
        confidence=0.6,
    )
