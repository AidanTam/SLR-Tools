"""Deterministic check: an assumption that is stated more than once must have
the same value every time.

A technical report restates a handful of assumptions in many places (the Summary,
the resource and reserve sections, the economic analysis, the sensitivity
discussion): the gold price, the exchange rate, the discount rate, the mine
life. When a draft is edited, one copy gets updated and another doesn't, and
the report ends up using, say, US$2,200/oz in the cash flow and US$2,000/oz in
the Summary. This module finds every statement of each assumption and flags a
disagreement.

Some differences are legitimate, so the check is careful about them:

* a metal price used to constrain Mineral Resources is routinely higher than
  the one used for Mineral Reserves or the cash flow, so statements are grouped
  by what they are used for (resource / reserve / economic) and a difference
  *between* purposes is noted but is not a failure;
* sensitivity cases, historical estimates, spot prices, consensus forecasts and
  lists of several prices in one sentence are skipped;
* costs quoted per ounce (AISC, cash cost, royalties, refining charges) are not
  prices and are skipped.

A flag means "these values disagree where they should not", not "this is
wrong": a QP decides which one is right.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NEEDS_REVIEW,
    Finding,
    Page,
)

ITEM_ID = "consistency"
ITEM_TITLE = "Cross-Document Consistency (Automated)"

# Statements of an assumption needed before it is worth comparing.
MIN_MENTIONS = 2

# ---------------------------------------------------------------------------
# Context classification
# ---------------------------------------------------------------------------

# A mention near any of these is not "the" assumption: skip it.
_SKIP_WORDS = (
    "sensitiv", "scenario", "upside", "downside", "historical", "previous",
    "prior to", "formerly", "spot", "consensus", "forward curve", "year average",
    "average price", "trailing", "realized", "realised", "ytd", "analyst",
    "range of", "ranging", "varying", "varied", "increase of", "decrease of",
    "break-even", "breakeven", "break even",
)
# Money per unit that is a cost or a charge, not a price.
_COST_WORDS = (
    "cost", "aisc", "royalt", "charge", "refin", "smelt", "freight", "transport",
    "penalt", "margin", "revenue", "premium", "netback", "stream", "payable",
)
# What the assumption is used for, tested in this order.
_PURPOSES = (
    ("reserve", ("reserve",)),
    ("resource", ("resource", "pit shell", "reasonable prospects", "rpeee", "cut-off", "cutoff")),
    ("economic", ("economic", "npv", "cash flow", "cash-flow", "financial", "pea ", "feasibility",
                  "price deck", "base case", "irr", "payback", "after-tax", "pre-tax", "before-tax")),
)

_WINDOW = 150


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _window(text: str, start: int, end: int, radius: int = _WINDOW) -> str:
    return _norm(text[max(0, start - radius): end + radius])


def _purpose(window: str) -> str:
    low = window.lower()
    for name, words in _PURPOSES:
        if any(w in low for w in words):
            return name
    return "general"


# "at +80% NSR cut-off ... US$17.28/oz Ag": a stepped what-if, not the base case.
_SCENARIO_STEP_RE = re.compile(r"\bat\s+[+\-−]\s?\d{1,3}\s?%")


def _skipped(window: str) -> bool:
    low = window.lower()
    return any(w in low for w in _SKIP_WORDS) or _SCENARIO_STEP_RE.search(low) is not None


# ---------------------------------------------------------------------------
# Mentions and grouping
# ---------------------------------------------------------------------------

@dataclass
class Mention:
    key: str        # assumption group, e.g. "gold price (US$/oz)"
    value: float    # compared value
    shown: str      # value as the report writes it
    page: int
    purpose: str
    context: str


def _same(a: float, b: float, rel: float) -> bool:
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-12)


def _clusters(mentions: List[Mention], rel: float) -> List[List[Mention]]:
    """Group mentions whose values agree within `rel`."""
    out: List[List[Mention]] = []
    for m in sorted(mentions, key=lambda m: m.value):
        if out and _same(out[-1][0].value, m.value, rel):
            out[-1].append(m)
        else:
            out.append([m])
    return out


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

_NUMBER = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"

_METAL_NAMES = {
    "gold": "gold", "silver": "silver", "copper": "copper", "zinc": "zinc",
    "lead": "lead", "nickel": "nickel", "platinum": "platinum",
    "palladium": "palladium", "molybdenum": "molybdenum", "cobalt": "cobalt",
    "uranium": "uranium", "lithium": "lithium",
}
_METAL_SYMBOLS = {"Au": "gold", "Ag": "silver", "Cu": "copper", "Zn": "zinc",
                  "Ni": "nickel", "Pt": "platinum", "Pd": "palladium", "Mo": "molybdenum",
                  "Pb": "lead"}
_METAL_WORD_RE = re.compile(r"\b(" + "|".join(_METAL_NAMES) + r")\b", re.IGNORECASE)
_METAL_SYMBOL_RE = re.compile(r"\b(" + "|".join(_METAL_SYMBOLS) + r")\b")
_PER_OZ_METALS = {"gold", "silver", "platinum", "palladium"}
_PER_LB_METALS = {"copper", "zinc", "lead", "nickel", "molybdenum", "cobalt", "uranium"}

_UNIT_CANON = {"oz": "oz", "ounce": "oz", "lb": "lb", "pound": "lb", "t": "t",
               "tonne": "t", "kg": "kg", "st": "st"}
_PRICE_RE = re.compile(
    r"(US|C|CA|CAD|USD|A|AU)?\$\s?" + _NUMBER
    + r"\s?(?:/|\s+per\s+)\s?(oz|ounce|lb|pound|tonne|kg|st|t)\b(?![A-Za-z/])",
    re.IGNORECASE,
)
_PRICE_WORD_RE = re.compile(r"\b(price|prices|priced|pricing|assum\w*)\b", re.IGNORECASE)


def _currency(prefix: Optional[str]) -> str:
    p = (prefix or "").upper()
    return {"": "$", "US": "US$", "USD": "US$", "C": "C$", "CA": "C$", "CAD": "C$",
            "A": "A$", "AU": "A$"}.get(p, "$")


def _metal_in(text: str, lo: int, hi: int) -> Optional[Tuple[int, str]]:
    """(position, metal) of the last metal named in text[lo:hi], if any."""
    best = None
    for rx, table in ((_METAL_WORD_RE, _METAL_NAMES), (_METAL_SYMBOL_RE, _METAL_SYMBOLS)):
        for m in rx.finditer(text, lo, hi):
            name = table[m.group(1)] if rx is _METAL_SYMBOL_RE else table[m.group(1).lower()]
            if best is None or m.start() > best[0]:
                best = (m.start(), name)
    return best


def _nearest_metal(text: str, start: int, end: int) -> Optional[str]:
    """The metal this price belongs to: the one named just before it ("gold
    price of US$2,200/oz"), else one named right after ("US$2,200/oz gold")."""
    # "US$1.40/lb Zn, US$1.10/lb Pb": a metal written straight after the unit
    # belongs to that price, not to the previous one in the list.
    direct = _metal_in(text, end, min(len(text), end + 12))
    if direct and direct[0] - end <= 4:
        return direct[1]
    before = _metal_in(text, max(0, start - 60), start)
    if before:
        return before[1]
    after = _metal_in(text, end, min(len(text), end + 25))
    return after[1] if after else None


def _clause(text: str, start: int, end: int) -> str:
    """The sentence-ish span around a match, so a neighbouring sentence about
    costs doesn't disqualify a price."""
    lo = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start), start - 120, 0)
    hi_dot = text.find(". ", end)
    hi = min(hi_dot if hi_dot != -1 else len(text), end + 60)
    return _norm(text[lo:hi])


def _metal_prices(page: Page) -> Iterable[Mention]:
    text = page.text
    matches = list(_PRICE_RE.finditer(text))
    for m in matches:
        unit = _UNIT_CANON[m.group(3).lower()]
        metal = _nearest_metal(text, m.start(), m.end())
        if metal is None:
            continue
        if (unit == "oz" and metal not in _PER_OZ_METALS) or (
            unit == "lb" and metal not in _PER_LB_METALS
        ):
            continue
        if any(w in _clause(text, m.start(), m.end()).lower() for w in _COST_WORDS):
            continue
        window = _window(text, m.start(), m.end())
        # Needs to read as a price: "price"/"assumed" nearby, or the metal
        # named immediately before the figure ("gold at US$2,200/oz").
        immediate = text[max(0, m.start() - 25): m.start()]
        if not (_PRICE_WORD_RE.search(window) or _nearest_metal(immediate, len(immediate), len(immediate))):
            continue
        if _skipped(window):
            continue
        # Several prices of the same unit close together is a sensitivity list.
        neighbours = [o for o in matches
                      if _UNIT_CANON[o.group(3).lower()] == unit
                      and abs(o.start() - m.start()) <= _WINDOW]
        if len({o.group(2) for o in neighbours}) >= 3:
            continue
        cur = _currency(m.group(1))
        raw = m.group(2)
        value = float(raw.replace(",", ""))
        yield Mention(
            key=f"{metal} price ({cur}/{unit})",
            value=value,
            shown=f"{cur}{raw}/{unit}",
            page=page.number,
            purpose=_purpose(window),
            context=window,
        )


_FX_LABEL_RE = re.compile(
    r"\b(?:exchange\s+rate|fx\s+rate|foreign\s+exchange(?:\s+rate)?|currency\s+(?:exchange|conversion))",
    re.IGNORECASE,
)
_DECIMAL_RE = re.compile(r"(?<![\d.])(\d\.\d{2,4})(?!\d)")


def _exchange_rates(page: Page) -> Iterable[Mention]:
    text = page.text
    for m in _FX_LABEL_RE.finditer(text):
        window = _window(text, m.start(), m.end())
        if _skipped(window):
            continue
        tail = text[m.end(): m.end() + 90]
        for d in _DECIMAL_RE.finditer(tail):
            raw = d.group(1)
            value = float(raw)
            if value == 1.0 or not (0.3 <= value <= 3.0):
                continue
            # 0.75 US$/C$ and 1.33 C$/US$ are the same rate: compare as <1.
            canon = 1.0 / value if value > 1 else value
            yield Mention(
                key="exchange rate", value=canon, shown=raw, page=page.number,
                purpose="general", context=window,
            )
            break


_DISCOUNT_RES = (
    re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\s?%\s+(?:real\s+|nominal\s+|annual\s+|after-tax\s+)?discount\s+rate",
               re.IGNORECASE),
    re.compile(r"discount\s+rate\s*(?:of|at|was|is|=|:)?\s*(?:approximately\s+)?(\d{1,2}(?:\.\d+)?)\s?%",
               re.IGNORECASE),
)


def _discount_rates(page: Page) -> Iterable[Mention]:
    text = page.text
    found = []
    for rx in _DISCOUNT_RES:
        for m in rx.finditer(text):
            found.append(m)
    for m in found:
        window = _window(text, m.start(), m.end())
        if _skipped(window):
            continue
        # NPV is routinely tabulated at several rates in one passage.
        if len({o.group(1) for o in found if abs(o.start() - m.start()) <= 250}) >= 2:
            continue
        yield Mention(
            key="discount rate", value=float(m.group(1)), shown=f"{m.group(1)}%",
            page=page.number, purpose="general", context=window,
        )


_LOM_SKIP = ("open pit", "open-pit", "underground", "phase", "stage", "extension",
             "additional", "remaining", "initial", "year 1", "pre-production")
_LOM_RES = (
    re.compile(r"(?:mine\s+life|life[\s-]of[\s-]mine|LOM)(?:\s+(?:plan|period|of|is|was|=|:|\(|approximately|about|,)){0,4}\s*"
               r"(\d{1,2}(?:\.\d+)?)[\s-]?years?\b", re.IGNORECASE),
    re.compile(r"(\d{1,2}(?:\.\d+)?)[\s-]year\s+(?:mine\s+life|LOM\b|life[\s-]of[\s-]mine)", re.IGNORECASE),
)


def _mine_life(page: Page) -> Iterable[Mention]:
    text = page.text
    for rx in _LOM_RES:
        for m in rx.finditer(text):
            window = _window(text, m.start(), m.end())
            low = window.lower()
            if _skipped(window) or any(w in low for w in _LOM_SKIP):
                continue
            yield Mention(
                key="mine life", value=float(m.group(1)), shown=f"{m.group(1)} years",
                page=page.number, purpose="general", context=window,
            )


# key prefix -> how strictly a disagreement is treated
_EXTRACTORS = (_metal_prices, _exchange_rates, _discount_rates, _mine_life)
_REL_TOL = {"exchange rate": 0.005}
_DEFAULT_TOL = 1e-3

_CHECK_TEXT = {
    "exchange rate": "Exchange rate is the same wherever it is stated",
    "discount rate": "Discount rate is the same wherever it is stated",
    "mine life": "Mine life is the same wherever it is stated",
}


def _check_text(key: str) -> str:
    if key in _CHECK_TEXT:
        return _CHECK_TEXT[key]
    return f"{key[0].upper()}{key[1:]} assumption is the same wherever it is stated"


def _pages_text(pages: Iterable[int]) -> str:
    return ", ".join(str(p) for p in sorted(set(pages)))


# ---------------------------------------------------------------------------
# Judging one assumption
# ---------------------------------------------------------------------------

def _judge(key: str, mentions: List[Mention]) -> Optional[Finding]:
    from .structural_checks import _finding  # avoid import cycle

    rel = _REL_TOL.get(key, _DEFAULT_TOL)
    values = _clusters(mentions, rel)
    all_pages = [m.page for m in mentions]
    check_id = "PY-ASSUMP-" + re.sub(r"[^A-Z0-9]+", "-", key.upper()).strip("-")
    text = _check_text(key)

    def label(cluster: List[Mention]) -> str:
        m = max(cluster, key=lambda c: sum(1 for x in cluster if x.shown == c.shown))
        return m.shown

    if len(values) == 1:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
            f"{len(mentions)} statements of the {key}, all {label(values[0])} "
            f"(pages {_pages_text(all_pages)}).",
            pages=all_pages, confidence=0.8,
        )

    by_purpose: Dict[str, List[Mention]] = defaultdict(list)
    for m in mentions:
        by_purpose[m.purpose].append(m)

    conflicts: Set[str] = {p for p, ms in by_purpose.items() if len(_clusters(ms, rel)) > 1}
    labelled = [m for m in mentions if m.purpose != "general"]
    if labelled and "general" in by_purpose:
        # An unlabelled statement should agree with one of the labelled values.
        for m in by_purpose["general"]:
            if not any(_same(m.value, l.value, rel) for l in labelled):
                conflicts.add("general")
                break

    def describe(cluster: List[Mention]) -> str:
        purposes = sorted({m.purpose for m in cluster})
        return f"{label(cluster)} (p.{_pages_text(m.page for m in cluster)}; {'/'.join(purposes)})"

    summary = " vs ".join(describe(c) for c in values)
    # One quoted line per distinct value so the reviewer can see each use.
    evidence = " | ".join(f"p.{c[0].page}: {c[0].context[:140]}" for c in values[:4])

    if not conflicts:
        return _finding(
            check_id, text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
            f"The {key} takes different values, but each is tied to a different use: "
            f"{summary}. Confirm the difference is intended (a resource price is "
            "often higher than the reserve or economic price).",
            evidence=evidence, pages=all_pages, confidence=0.6,
        )

    strict = bool(conflicts & {"economic", "reserve"})
    return _finding(
        check_id, text, ITEM_ID, ITEM_TITLE,
        STATUS_NON_COMPLIANT if strict else STATUS_NEEDS_REVIEW,
        f"The {key} is stated with different values for the same use: {summary}. "
        "Check which is current and whether the others are leftovers from an earlier draft.",
        evidence=evidence, pages=all_pages, confidence=0.7 if strict else 0.55,
    )


def _merge_bare_dollar(grouped: Dict[str, List[Mention]]) -> None:
    """A price written with a bare "$" belongs with the report's one explicit
    currency for that metal and unit ("$2,100/oz" next to "US$2,100/oz"). With
    no explicit currency, or two, it stays on its own."""
    for key in [k for k in grouped if "($/" in k]:
        siblings = [k for k in grouped
                    if k != key and k.split("(")[0] == key.split("(")[0]
                    and k.endswith("$/" + key.split("/")[-1])]
        if len(siblings) == 1:
            grouped[siblings[0]].extend(grouped.pop(key))


# Items whose prices describe somebody else's or an earlier study: History
# (Item 6) and Adjacent Properties (Item 23).
_OTHER_STUDY_ITEMS = {"item_6", "item_23"}
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_PAST_YEAR_RE = re.compile(
    r"\b(?:in|for|during|from|of|as\s+of)\s+(19\d{2}|20\d{2})\b"
    r"|\b(19\d{2}|20\d{2})\s+(?:MRE|mre|estimate|resource\s+estimate|mineral\s+resource|PEA|study|report)\b",
    re.IGNORECASE,
)


def _report_year(pages: List[Page]) -> Optional[int]:
    """The year of the report itself: the latest year on the first pages."""
    years = [int(y) for p in pages[:3] for y in _YEAR_RE.findall(p.text)]
    plausible = [y for y in years if 1990 <= y <= 2100]
    return max(plausible) if plausible else None


def _about_an_earlier_year(context: str, report_year: Optional[int]) -> bool:
    """"In 2018, metal price assumptions were ..." in a report written in 2024
    is describing the 2018 study, not this one."""
    if report_year is None:
        return False
    for m in _PAST_YEAR_RE.finditer(context):
        year = int(m.group(1) or m.group(2))
        if year < report_year:
            return True
    return False


def check_assumption_consistency(
    pages: List[Page],
    list_pages: Optional[set] = None,
    page_items: Optional[Dict[int, Tuple[str, str]]] = None,
) -> List[Finding]:
    """One Finding per assumption that the report states at least twice."""
    if list_pages is None:
        from .structural_checks import _list_like_pages
        list_pages = _list_like_pages(pages)
    skip_pages = set(list_pages) | {
        n for n, (iid, _t) in (page_items or {}).items() if iid in _OTHER_STUDY_ITEMS
    }
    report_year = _report_year(pages)

    grouped: Dict[str, List[Mention]] = defaultdict(list)
    for p in pages:
        if p.number in skip_pages:
            continue
        for extract in _EXTRACTORS:
            for m in extract(p):
                if _about_an_earlier_year(m.context, report_year):
                    continue
                grouped[m.key].append(m)

    _merge_bare_dollar(grouped)

    findings = []
    for key in sorted(grouped):
        if len(grouped[key]) >= MIN_MENTIONS:
            f = _judge(key, grouped[key])
            if f is not None:
                findings.append(f)
    return findings
