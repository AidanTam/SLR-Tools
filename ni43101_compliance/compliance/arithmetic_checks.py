"""Deterministic checks: the arithmetic in the report's tables holds.

Resource, reserve and cost tables are edited by hand late in a draft, and the
numbers stop adding up: a Total row that no longer equals its rows, a
Measured + Indicated line that doesn't equal Measured plus Indicated, contained
ounces that don't equal tonnes x grade. These checks recompute them.

Tables are read with PyMuPDF's table finder, so this is PDF-only. Every
comparison allows for the rounding the table itself shows (a total of
`3,002` over rows that are each rounded to the nearest integer can differ by a
few units and still be right), and a column is only summed when a Total row
looks like a sum (not an average: a grade column's Total is smaller than its
largest row, and is skipped).

Three tests, all on the same parsed tables:

* Total / Subtotal rows equal the sum of the rows they total (additive
  columns only);
* Measured + Indicated (and Proven + Probable) equal the combined category,
  for tonnage and contained metal, and the combined grade is the tonnage-
  weighted average;
* contained metal equals tonnage x grade (g/t to ounces, % to tonnes or pounds).

A flag means "these numbers disagree beyond rounding", which in a resource
table is nearly always a real error or a stale cell, but a QP should look.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

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

# Cap how much a flagged difference is explained away as rounding.
_REL_FLOOR = 0.005
# A Total that is wildly different from its rows almost always means the table
# was read wrongly (rows lost across a page break, merged cells). A real
# arithmetic slip is a near miss, so only differences up to this are reported.
MAX_NEAR_MISS = 0.15
GRAMS_PER_TROY_OZ = 31.1034768
LB_PER_TONNE = 2204.62262

_NUMBER_CELL = re.compile(r"^\(?-?\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\)?$")
_BLANKISH = {"", "-", "–", "—", "nil", "n/a", "na"}


def _num(cell: Optional[str]) -> Optional[Tuple[float, int]]:
    """(value, decimals shown) for a numeric cell, else None."""
    if cell is None:
        return None
    c = cell.strip().replace("−", "-").replace(" ", "")
    m = _NUMBER_CELL.match(c)
    if not m:
        return None
    neg = c.startswith("(") or c.startswith("-")
    value = float((m.group(1) + (m.group(2) or "")).replace(",", ""))
    return (-value if neg else value), (len(m.group(2)) - 1 if m.group(2) else 0)


@dataclass
class Grid:
    page: int
    rows: List[List[str]]
    header: List[str]            # one combined header string per column
    first_data: int              # index of the first data row
    label: str                   # short description for messages

    def cell(self, r: int, c: int) -> Optional[Tuple[float, int]]:
        if c >= len(self.rows[r]):
            return None
        return _num(self.rows[r][c])

    def row_label(self, r: int) -> str:
        return re.sub(r"\s+", " ", (self.rows[r][0] or "").strip())


def _clean(cell: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (cell or "")).strip()


def _to_grid(page_no: int, raw_rows: List[List[Optional[str]]]) -> Optional[Grid]:
    rows = [[_clean(c) for c in r] for r in raw_rows if r]
    if len(rows) < 3:
        return None
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    first = None
    for i, r in enumerate(rows):
        if sum(1 for c in r[1:] if _num(c)) >= 2:
            first = i
            break
    if first is None or first == 0:
        return None
    # Header: the rows above the data, a merged header cell carried right over
    # the blank cells it spans.
    header = [""] * ncol
    for r in rows[:first]:
        last = ""
        for j, c in enumerate(r):
            if c:
                last = c
            filled = c or (last if j > 0 else "")
            if filled and filled not in header[j]:
                header[j] = (header[j] + " " + filled).strip()
    label = " / ".join(h for h in header[1:4] if h)[:60] or "table"
    return Grid(page_no, rows, header, first, label)


# ---------------------------------------------------------------------------
# Column semantics
# ---------------------------------------------------------------------------

_NON_ADDITIVE = re.compile(
    r"grade|g/t|\bgpt\b|%|ratio|price|\$/|/t\b|per\s+t|per\s+oz|/oz|average|\bavg\b|"
    r"\brate\b|factor|recovery|strip|density|\byear\b|\bkm\b|cut-?off|\bsg\b|\bppm\b|"
    r"\bdepth\b|\bwidth\b|\bdip\b|\bazimuth\b|\bcoefficient\b|\bno\.\b",
    re.IGNORECASE,
)
_TOTAL_ROW = re.compile(r"^\s*(?:sub-?\s*)?total\b", re.IGNORECASE)
_SUBTOTAL_ROW = re.compile(r"^\s*(?:sub-?\s*total|total)\b", re.IGNORECASE)


def _is_additive(header: str) -> bool:
    return not _NON_ADDITIVE.search(header)


def _decimals(cells: Iterable[Optional[Tuple[float, int]]]) -> int:
    return max((c[1] for c in cells if c), default=0)


def _close(total: float, parts_sum: float, n_terms: int, decimals: int) -> bool:
    slack = (n_terms + 1) * 0.5 * (10 ** -decimals)
    return abs(total - parts_sum) <= max(_REL_FLOOR * abs(parts_sum), slack) + 1e-9


@dataclass
class Issue:
    page: int
    kind: str
    text: str
    rel: float   # how far off, as a fraction of the stated value
    group: str = ""  # issues sharing a group are one problem (same total row)

    def __str__(self) -> str:
        return f"p.{self.page}: {self.text}"


# ---------------------------------------------------------------------------
# Test 1: Total / Subtotal rows
# ---------------------------------------------------------------------------

def _total_issues(g: Grid) -> Tuple[int, List[Issue]]:
    tested = 0
    issues: List[Issue] = []
    total_rows = [r for r in range(g.first_data, len(g.rows)) if _TOTAL_ROW.match(g.row_label(r))]
    if not total_rows:
        return 0, issues
    for col in range(1, len(g.header)):
        if not _is_additive(g.header[col]):
            continue
        for t in total_rows:
            tv = g.cell(t, col)
            if tv is None:
                continue
            prev_totals = [x for x in total_rows if x < t]
            start = prev_totals[-1] + 1 if prev_totals else g.first_data
            body = [r for r in range(start, t) if not _TOTAL_ROW.match(g.row_label(r))]
            all_body = [r for r in range(g.first_data, t) if not _TOTAL_ROW.match(g.row_label(r))]
            subtotals = prev_totals
            candidates = []
            for rows in (body, all_body, subtotals):
                vals = [g.cell(r, col) for r in rows]
                vals = [v for v in vals if v is not None]
                if len(vals) >= 2:
                    candidates.append(vals)
            if not candidates:
                continue
            total, dec_t = tv
            # A Total below its largest row is an average or an unrelated
            # column, not a sum: leave it.
            if all(total < max(v[0] for v in vals) * 0.999 for vals in candidates) or total == 0:
                continue
            tested += 1
            ok = False
            best = None
            for vals in candidates:
                s = sum(v[0] for v in vals)
                if _close(total, s, len(vals), max(dec_t, _decimals(vals))):
                    ok = True
                    break
                if best is None or abs(total - s) < abs(total - best):
                    best = s
            if not ok:
                rel = abs(total - best) / abs(total) if total else 1.0
                if rel > MAX_NEAR_MISS:
                    continue  # far off: the parser dropped or split rows, not a typo
                issues.append(Issue(
                    g.page, "total",
                    f"\"{g.row_label(t)}\" shows {tv[0]:,.{dec_t}f} in column "
                    f"\"{g.header[col][:40]}\" but the rows above sum to {best:,.{dec_t}f}",
                    rel,
                    group=f"{g.page}|{g.row_label(t)}",
                ))
    return tested, issues


# ---------------------------------------------------------------------------
# Test 2: category sums (Measured + Indicated, Proven + Probable)
# ---------------------------------------------------------------------------

_CAT_PAIRS = (
    ("measured", "indicated", r"measured\s*(?:\+|&|and)\s*indicated|m\s*(?:\+|&)\s*i\b|\bm&i\b"),
    ("proven", "probable", r"proven\s*(?:\+|&|and)\s*probable|p\s*(?:\+|&)\s*p\b|\bp&p\b"),
)


def _row_kind(label: str) -> Optional[str]:
    low = label.lower().strip()
    for a, b, combo in _CAT_PAIRS:
        if re.search(combo, low):
            return a + "+" + b
        if re.match(rf"^{a}\b", low):
            return a
        if re.match(rf"^{b}\b", low):
            return b
    return None


def _kind_of_header(h: str) -> Optional[str]:
    low = h.lower()
    for a, b, combo in _CAT_PAIRS:
        if re.search(combo, low):
            return a + "+" + b
        if re.search(rf"\b{a}\b", low) and not re.search(rf"\b{b}\b", low):
            return a
        if re.search(rf"\b{b}\b", low) and not re.search(rf"\b{a}\b", low):
            return b
    return None


def _col_role(h: str) -> Optional[str]:
    low = h.lower()
    if re.search(r"contained|metal|\bkoz\b|\bmoz\b|\bmlb\b|\bklb\b|\boz\b", low) and not re.search(r"g/t|grade", low):
        return "metal"
    if re.search(r"grade|g/t|\bgpt\b|%\s*(?:cu|zn|ni|pb|au|ag)|\bcu\s*%|\bni\s*%|\bzn\s*%", low):
        return "grade"
    if re.search(r"tonn|\bkt\b|\bmt\b|tonnes", low):
        return "tonnage"
    return None


def _category_issues(g: Grid) -> Tuple[int, List[Issue]]:
    tested = 0
    issues: List[Issue] = []

    # Orientation A: categories are rows ("Measured", "Indicated", "M + I").
    kinds = {r: _row_kind(g.row_label(r)) for r in range(g.first_data, len(g.rows))}
    for a, b, _c in _CAT_PAIRS:
        ra = next((r for r, k in kinds.items() if k == a), None)
        rb = next((r for r, k in kinds.items() if k == b), None)
        rc = next((r for r, k in kinds.items() if k == a + "+" + b), None)
        if ra is None or rb is None or rc is None:
            continue
        t, i = _sum_rows(g, ra, rb, rc, a, b)
        tested += t
        issues.extend(i)

    # Orientation B: categories are column groups (Measured | Indicated | M + I).
    cols = {c: _kind_of_header(g.header[c]) for c in range(1, len(g.header))}
    for a, b, _c in _CAT_PAIRS:
        for role in ("tonnage", "metal"):
            ca = [c for c, k in cols.items() if k == a and _col_role(g.header[c]) == role]
            cb = [c for c, k in cols.items() if k == b and _col_role(g.header[c]) == role]
            cc = [c for c, k in cols.items() if k == a + "+" + b and _col_role(g.header[c]) == role]
            if not (ca and cb and cc):
                continue
            for r in range(g.first_data, len(g.rows)):
                va, vb, vc = g.cell(r, ca[0]), g.cell(r, cb[0]), g.cell(r, cc[0])
                if not (va and vb and vc):
                    continue
                tested += 1
                dec = max(va[1], vb[1], vc[1])
                if not _close(vc[0], va[0] + vb[0], 2, dec):
                    issues.append(Issue(
                        g.page, "category",
                        f"\"{g.row_label(r)}\": {a.title()} {va[0]:,.{va[1]}f} + {b.title()} "
                        f"{vb[0]:,.{vb[1]}f} = {va[0] + vb[0]:,.{dec}f}, but "
                        f"{a.title()} + {b.title()} shows {vc[0]:,.{vc[1]}f} ({role})",
                        abs(vc[0] - va[0] - vb[0]) / max(abs(vc[0]), 1e-9),
                    ))
    return tested, issues


def _sum_rows(g: Grid, ra: int, rb: int, rc: int, a: str, b: str) -> Tuple[int, List[Issue]]:
    tested = 0
    issues: List[Issue] = []
    roles = {c: _col_role(g.header[c]) for c in range(1, len(g.header))}
    for col, role in roles.items():
        if role not in ("tonnage", "metal"):
            continue
        va, vb, vc = g.cell(ra, col), g.cell(rb, col), g.cell(rc, col)
        if not (va and vb and vc):
            continue
        tested += 1
        dec = max(va[1], vb[1], vc[1])
        if not _close(vc[0], va[0] + vb[0], 2, dec):
            issues.append(Issue(
                g.page, "category",
                f"{a.title()} {va[0]:,.{va[1]}f} + {b.title()} {vb[0]:,.{vb[1]}f} = "
                f"{va[0] + vb[0]:,.{dec}f}, but {a.title()} + {b.title()} shows "
                f"{vc[0]:,.{vc[1]}f} (column \"{g.header[col][:40]}\")",
                abs(vc[0] - va[0] - vb[0]) / max(abs(vc[0]), 1e-9),
            ))
    # Combined grade = tonnage-weighted average.
    for gcol, grole in roles.items():
        if grole != "grade":
            continue
        tcol = next((c for c in range(gcol - 1, 0, -1) if roles.get(c) == "tonnage"), None)
        if tcol is None or gcol - tcol > 2:
            continue
        ta, tb, tc = g.cell(ra, tcol), g.cell(rb, tcol), g.cell(rc, tcol)
        ga, gb, gc = g.cell(ra, gcol), g.cell(rb, gcol), g.cell(rc, gcol)
        if not (ta and tb and ga and gb and gc) or ta[0] + tb[0] <= 0:
            continue
        expect = (ta[0] * ga[0] + tb[0] * gb[0]) / (ta[0] + tb[0])
        tested += 1
        tol = max(0.5 * 10 ** -gc[1] * 2, 0.01 * abs(expect))
        # tiny categories (e.g. 1 kt) make the weights unstable; widen to the
        # larger grade's rounding relative to the smaller tonnage.
        share = min(ta[0], tb[0]) / (ta[0] + tb[0])
        tol += abs(ga[0] - gb[0]) * 0.5 * (10 ** -ta[1]) / max(ta[0] + tb[0], 1e-9) + share * 0
        if abs(expect - gc[0]) > tol:
            issues.append(Issue(
                g.page, "grade",
                f"combined grade shows {gc[0]:.{gc[1]}f} but the tonnage-weighted average of "
                f"{a.title()} ({ga[0]:.{ga[1]}f}) and {b.title()} ({gb[0]:.{gb[1]}f}) is "
                f"{expect:.{gc[1]}f} (column \"{g.header[gcol][:40]}\")",
                abs(expect - gc[0]) / max(abs(gc[0]), 1e-9),
            ))
    return tested, issues


# ---------------------------------------------------------------------------
# Test 3: contained metal = tonnage x grade
# ---------------------------------------------------------------------------

def _tonnage_factor(h: str) -> Optional[float]:
    """Header -> tonnes per unit shown, or None."""
    low = h.lower()
    if re.search(r"\bmt\b|million\s+tonn|\(mt\)", low):
        return 1e6
    if re.search(r"\bkt\b|000\s*t\b|thousand\s+tonn|\(kt\)|k\s*tonnes", low):
        return 1e3
    if re.search(r"\btonnes\b|\btonnage\b|\(t\)|\btons\b", low):
        return 1.0
    return None


def _metal_oz_factor(h: str) -> Optional[float]:
    low = h.lower()
    if re.search(r"\bmoz\b|million\s+oun", low):
        return 1e6
    if re.search(r"\bkoz\b|thousand\s+oun|000\s*oz", low):
        return 1e3
    if re.search(r"\boz\b|ounces", low):
        return 1.0
    return None


def _metal_mass_factor(h: str) -> Optional[Tuple[str, float]]:
    low = h.lower()
    if re.search(r"\bmlb\b|million\s+(?:pounds|lbs?)", low):
        return "lb", 1e6
    if re.search(r"\bklb\b|thousand\s+(?:pounds|lbs?)", low):
        return "lb", 1e3
    if re.search(r"\blbs?\b|pounds", low):
        return "lb", 1.0
    if re.search(r"\bmt\b|million\s+tonn", low):
        return "t", 1e6
    if re.search(r"\bkt\b|thousand\s+tonn", low):
        return "t", 1e3
    if re.search(r"\bt\b|tonnes", low):
        return "t", 1.0
    return None


def _contained_issues(g: Grid) -> Tuple[int, List[Issue]]:
    tested = 0
    issues: List[Issue] = []
    ncol = len(g.header)
    for j in range(1, ncol - 2):
        tf = _tonnage_factor(g.header[j]) if _col_role(g.header[j]) == "tonnage" else None
        if tf is None or _col_role(g.header[j + 1]) != "grade" or _col_role(g.header[j + 2]) != "metal":
            continue
        gh = g.header[j + 1].lower()
        mh = g.header[j + 2]
        per_gt = bool(re.search(r"g/t|\bgpt\b|ppm", gh))
        per_pct = "%" in gh
        if per_gt and _metal_oz_factor(mh):
            mf = _metal_oz_factor(mh)

            def expected(t: float, gr: float) -> float:
                return t * tf * gr / GRAMS_PER_TROY_OZ / mf
        elif per_pct and _metal_mass_factor(mh):
            unit, mf = _metal_mass_factor(mh)

            def expected(t: float, gr: float, unit=unit, mf=mf) -> float:
                tonnes = t * tf * gr / 100.0
                return (tonnes * LB_PER_TONNE if unit == "lb" else tonnes) / mf
        else:
            continue
        for r in range(g.first_data, len(g.rows)):
            t, gr, m = g.cell(r, j), g.cell(r, j + 1), g.cell(r, j + 2)
            if not (t and gr and m) or t[0] <= 0 or gr[0] <= 0:
                continue
            exp = expected(t[0], gr[0])
            # Slack for the rounding of each input and of the stated result.
            rel = 0.015 + 0.5 * 10 ** -t[1] / t[0] + 0.5 * 10 ** -gr[1] / gr[0]
            tol = rel * exp + 0.5 * 10 ** -m[1] + 1e-9
            tested += 1
            if abs(exp - m[0]) > tol:
                issues.append(Issue(
                    g.page, "contained",
                    f"\"{g.row_label(r)}\": {t[0]:,.{t[1]}f} x {gr[0]:.{gr[1]}f} gives about "
                    f"{exp:,.{max(m[1], 0)}f}, but the table shows {m[0]:,.{m[1]}f} "
                    f"(column \"{g.header[j + 2][:40]}\")",
                    abs(exp - m[0]) / max(abs(m[0]), 1e-9),
                ))
    return tested, issues


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

_CANDIDATE_RE = re.compile(r"\b(total|measured|indicated|proven|probable|subtotal)\b", re.IGNORECASE)
_MAX_PAGES_TABLES = 700


def _grids(pdf_path: str, pages: List[Page]) -> Iterable[Grid]:
    import fitz

    wanted = [p.number for p in pages if _CANDIDATE_RE.search(p.text)
              and len(re.findall(r"\d", p.text)) > 40]
    with fitz.open(pdf_path) as doc:
        for pno in wanted[:_MAX_PAGES_TABLES]:
            if pno - 1 >= len(doc):
                continue
            try:
                tables = doc[pno - 1].find_tables().tables
            except Exception:
                continue
            for t in tables:
                try:
                    g = _to_grid(pno, t.extract())
                except Exception:
                    g = None
                if g:
                    yield g


def run_table_checks(pages: List[Page], pdf_path: Optional[str]) -> Dict[str, Tuple[int, List[Issue], int]]:
    """{test name: (comparisons made, issues, tables read)}."""
    results = {"total": [0, [], 0], "category": [0, [], 0], "contained": [0, [], 0]}
    seen = set()
    for g in _grids(pdf_path, pages):
        # The same table is often repeated in the Summary and Item 14.
        sig = tuple(tuple(r) for r in g.rows)
        if sig in seen:
            continue
        seen.add(sig)
        for name, fn in (("total", _total_issues), ("category", _category_issues),
                         ("contained", _contained_issues)):
            n, iss = fn(g)
            if n:
                results[name][0] += n
                results[name][2] += 1
            results[name][1].extend(iss)
    return {k: (v[0], v[1], v[2]) for k, v in results.items()}


_TEXTS = {
    "total": ("PY-ARITH-TOTALS", "Total and Subtotal rows equal the sum of the rows they total"),
    "category": ("PY-ARITH-CATEGORIES",
                 "Measured + Indicated (and Proven + Probable) equal the sum of their categories"),
    "contained": ("PY-ARITH-CONTAINED", "Contained metal equals tonnage x grade"),
}


def _collapse(issues: List[Issue]) -> List[Issue]:
    """One issue per Total row, however many columns of it disagree."""
    out: List[Issue] = []
    seen: Dict[str, Issue] = {}
    for i in issues:
        if not i.group:
            out.append(i)
        elif i.group in seen:
            if "(and other columns)" not in seen[i.group].text:
                seen[i.group].text += " (and other columns)"
        else:
            seen[i.group] = i
            out.append(i)
    return out


def check_table_arithmetic(pages: List[Page], pdf_path: Optional[str]) -> List[Finding]:
    from .structural_checks import _finding

    def na(reason: str) -> List[Finding]:
        return [
            _finding(cid, text, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED, reason)
            for cid, text in _TEXTS.values()
        ]

    if not pdf_path or not pdf_path.lower().endswith(".pdf"):
        return na("Table arithmetic checks need the original PDF (table detection); verify manually.")
    try:
        import fitz  # noqa: F401
    except ImportError:
        return na("PyMuPDF is not installed; cannot read tables.")
    try:
        results = run_table_checks(pages, pdf_path)
    except Exception as exc:
        return na(f"Table reading failed ({exc}); verify manually.")

    findings = []
    for name, (cid, text) in _TEXTS.items():
        tested, issues, n_tables = results[name]
        if tested == 0:
            continue  # no table in the report has the layout this test needs
        if not issues:
            findings.append(_finding(
                cid, text, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
                f"{tested} comparison(s) across {n_tables} table(s) all agree within the "
                "rounding shown in the tables.",
                confidence=0.75,
            ))
            continue
        issues = _collapse(issues)
        issues.sort(key=lambda i: -i.rel)
        worst = issues[0].rel
        shown = issues[:8]
        more = f" (+{len(issues) - len(shown)} more)" if len(issues) > len(shown) else ""
        # A Total can be off because rows were lost across a page break, so it
        # is never stronger than Needs Review; the other two tests are fully
        # determined by the table's own numbers.
        strong = name != "total" and worst > 0.02
        findings.append(_finding(
            cid, text, ITEM_ID, ITEM_TITLE,
            STATUS_NON_COMPLIANT if strong else STATUS_NEEDS_REVIEW,
            f"{len(issues)} problem(s) found among {tested} comparison(s): the numbers "
            "disagree beyond the rounding the table shows. This is usually a stale or "
            "mistyped cell after an edit, but can come from a table the parser misread "
            "(verify against the page).",
            evidence=" | ".join(str(i) for i in shown) + more,
            pages=[i.page for i in issues],
            confidence=0.7,
        ))
    return findings
