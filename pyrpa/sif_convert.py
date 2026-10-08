"""
sif_convert.py  -  Parse geological assay-lab certificate SIF files into tidy
tabular data.

Handles two shapes of the Standard Interchange Format that labs send for
import into Micromine / Geobank:

  * FIXED-WIDTH (e.g. ALS): a metadata block, then a stack of header rows
    (method / element / units / detection / upper limit / tolerance /
    digestion / temperature / time / laboratory), then space-padded,
    right-aligned data columns. Files are usually latin-1 encoded.

  * DELIMITED: comma/tab/semicolon separated, with a small multi-row header
    block above the data.

The module is pure standard library and works entirely in memory (no file
reads/writes), so it is safe to import on Streamlit Cloud. It exposes
parse_text() plus helpers returning CSV strings and DataFrames.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------

# Row labels (left field) of the fixed-width header block. Presence of these
# is also how we recognise a fixed-width ALS-style file.
FIXED_HEADER_LABELS = {
    "UNITS": "units",
    "DETECTION": "detection_limit",
    "UPPERLIMIT": "upper_limit",
    "TOLERANCE": "tolerance",
    "DIGESTION": "digestion",
    "TEMPERATURE": "temperature",
    "TIME": "time",
    "LABORATORY": "laboratory",
}

# Delimited-format header row labels, top to bottom. Only a fallback: rows are
# first classified by content (see _classify_header_row), because labs disagree
# on the order (ALS CSVs run method / element / units).
DELIM_HEADER_LABELS = ["element", "units", "method", "detection_limit"]

UNIT_TOKENS = {
    "%", "pct", "ppm", "ppb", "ppt", "g/t", "gpt", "oz/t", "opt", "mg/kg",
    "ug/g", "µg/g", "ug/kg", "µg/kg", "mg/l", "ug/l", "kg", "g", "mg",
}

# Lab method codes: ME-MS81, Au-AA23, OA-GRA05, TOT-ICP06, ...
METHOD_CODE_RE = re.compile(r"^[A-Za-z]{2,}-[A-Za-z0-9]+$")

SAMPLE_ID_PATTERNS = [
    r"^[A-Za-z]{1,6}[-_ ]?\d{2,}$",
    r"^\d{3,}$",
    r"^[A-Za-z0-9]{2,}[-_/][A-Za-z0-9-]+$",
]

SAMPLE_HEADER_WORDS = {
    "sample", "sampleid", "sample_id", "sampleno", "sample no", "sample number",
    "sampid", "hole", "holeid", "hole_id", "dhid", "bhid", "id", "labid",
    "lab_id", "sample id",
}

NON_NUMERIC_RESULT_TOKENS = {"", "-", "na", "n/a", "nd", "n.d.", "ins", "insuf"}


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class ParsedSif:
    fmt: str = "delimited"                    # "fixed_width" | "delimited"
    delimiter: str = ""                       # only meaningful for delimited
    certificate: str = ""
    metadata: dict = field(default_factory=dict)
    analyte_headers: dict = field(default_factory=dict)   # label -> [per-col str]
    n_lead_cols: int = 1
    lead_col_names: list = field(default_factory=list)
    analytes: list = field(default_factory=list)          # unique display names
    data_rows: list = field(default_factory=list)         # aligned lead+analyte
    source_file: str = ""                     # set by the caller; written to every output row


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def _is_number(cell: str) -> bool:
    cc = (cell or "").strip().lstrip("<>").replace(",", "")
    if cc == "":
        return False
    try:
        float(cc)
        return True
    except ValueError:
        return False


def numeric_fraction(cells: list) -> float:
    vals = [c for c in cells if (c or "").strip() != ""]
    if not vals:
        return 0.0
    return sum(1 for c in vals if _is_number(c)) / len(vals)


def looks_like_sample_id(cell: str) -> bool:
    c = (cell or "").strip()
    if not c:
        return False
    return any(re.match(pat, c, re.IGNORECASE) for pat in SAMPLE_ID_PATTERNS)


def _dedupe(names: list) -> list:
    out, seen = [], {}
    for k, raw in enumerate(names):
        name = (raw or "").strip() or f"col_{k+1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name] + 1}"
        else:
            seen[name] = 0
        out.append(name)
    return out


def column_name(element: str, units: str, method: str, j: int) -> str:
    """Analyte column name as element_units_method, e.g. Ba_ppm_ME-MS81.

    Missing parts are skipped; a column with none of them becomes col_<n>.
    """
    parts = [(s or "").strip() for s in (element, units, method)]
    return "_".join(s for s in parts if s) or f"col_{j+1}"


def _column_names(analyte_headers: dict, n_cols: int) -> list:
    def at(label, j):
        seq = analyte_headers.get(label, [])
        return seq[j] if j < len(seq) else ""
    return _dedupe([column_name(at("element", j), at("units", j), at("method", j), j)
                    for j in range(n_cols)])


def _classify_header_row(cells: list) -> str | None:
    """Guess which header row this is from its analyte cells, or None."""
    vals = [c.strip() for c in cells if (c or "").strip()]
    if not vals:
        return None
    def share(pred):
        return sum(1 for v in vals if pred(v)) / len(vals)
    if share(lambda v: v.lower() in UNIT_TOKENS) >= 0.8:
        return "units"
    if share(lambda v: METHOD_CODE_RE.match(v) is not None) >= 0.8:
        return "method"
    if share(_is_number) >= 0.8:
        return "detection_limit"
    return "element"


def result_flag(raw: str) -> str:
    low = (raw or "").strip().lower()
    if raw.startswith("<"):
        return "below_detection"
    if raw.startswith(">"):
        return "above_range"
    if low in NON_NUMERIC_RESULT_TOKENS:
        return "not_reported"
    return ""


# --------------------------------------------------------------------------
# Fixed-width (ALS-style) parsing
# --------------------------------------------------------------------------

def _is_fixed_width(lines: list) -> bool:
    leads = {ln[:40].strip().upper() for ln in lines[:60]}
    hits = sum(1 for lbl in ("DETECTION", "UNITS", "LABORATORY") if lbl in leads)
    return hits >= 2


def _detect_geometry(detection_line: str) -> tuple:
    """Return (lead_width, stride) from a fully-populated, right-aligned row.

    Columns are right-aligned, so each token's END position is its field's
    right edge. The label token sits far to the left; the analyte fields march
    in a constant stride."""
    ends = [m.end() for m in re.finditer(r"\S+", detection_line)]
    if len(ends) < 3:
        return 30, 20
    diffs = [ends[i + 1] - ends[i] for i in range(1, len(ends) - 1)]
    stride = Counter(diffs).most_common(1)[0][0] if diffs else 20
    stride = max(stride, 2)
    first_analyte_end = ends[1]
    lead_width = max(first_analyte_end - stride, 1)
    return lead_width, stride


def parse_fixed_width(lines: list) -> ParsedSif:
    # Locate the header block: the first row whose left field is blank but whose
    # body carries content is the METHOD row; the next is the ELEMENT row.
    def lead(ln, w):
        return ln[:w].strip()

    # Provisional geometry from the DETECTION row (fully populated).
    det_idx = next((i for i, ln in enumerate(lines)
                    if ln[:40].strip().upper() == "DETECTION"), None)
    if det_idx is None:
        raise ValueError("Fixed-width SIF: no DETECTION row found.")
    lead_width, stride = _detect_geometry(lines[det_idx])

    maxlen = max((len(ln) for ln in lines), default=lead_width)
    n_cols = max(round((maxlen - lead_width) / stride), 1)

    def cells(ln):
        return [ln[lead_width + stride * j: lead_width + stride * (j + 1)].strip()
                for j in range(n_cols)]

    # Header block start = first row with blank left field and non-blank body.
    block_start = None
    for i, ln in enumerate(lines):
        if lead(ln, lead_width) == "" and ln.strip() != "":
            block_start = i
            break
    if block_start is None:
        raise ValueError("Fixed-width SIF: could not find the header block.")

    # Metadata: labelled key/value lines above the header block.
    certificate = lines[0][:lead_width].strip() if lines else ""
    metadata = {}
    for ln in lines[:block_start]:
        key = ln[:lead_width].strip()
        val = ln[lead_width:].strip()
        if key:
            metadata[key] = val

    # Walk the header block: two blank-lead rows (method, element) then the
    # labelled rows, until the first data row (a non-blank, non-label lead).
    analyte_headers = {}
    blank_rows_seen = 0
    i = block_start
    while i < len(lines):
        lbl = lead(lines[i], lead_width)
        up = lbl.upper()
        if lbl == "":
            role = "method" if blank_rows_seen == 0 else "element"
            blank_rows_seen += 1
            analyte_headers[role] = cells(lines[i])
            i += 1
        elif up in FIXED_HEADER_LABELS:
            analyte_headers[FIXED_HEADER_LABELS[up]] = cells(lines[i])
            i += 1
        else:
            break  # first data row
    data_start = i

    display = _column_names(analyte_headers, n_cols)

    lead_names = ["certificate", "sample_id"]
    data_rows = []
    for ln in lines[data_start:]:
        sid = lead(ln, lead_width)
        if not sid or sid.upper() in FIXED_HEADER_LABELS:
            continue
        data_rows.append([certificate, sid] + cells(ln))

    return ParsedSif(
        fmt="fixed_width",
        certificate=certificate,
        metadata=metadata,
        analyte_headers=analyte_headers,
        n_lead_cols=2,
        lead_col_names=lead_names,
        analytes=display,
        data_rows=data_rows,
    )


# --------------------------------------------------------------------------
# Delimited parsing (fallback for comma/tab certificates)
# --------------------------------------------------------------------------

def sniff_delimiter(sample_text: str) -> str:
    candidates = [",", "\t", ";", "|"]
    lines = [ln for ln in sample_text.splitlines() if ln.strip()]
    best, best_score = ",", -1.0
    for d in candidates:
        counts = [ln.count(d) for ln in lines]
        counts = [c for c in counts if c > 0]
        if not counts:
            continue
        mode = max(set(counts), key=counts.count)
        consistency = counts.count(mode) / len(counts)
        score = mode * consistency
        if score > best_score:
            best, best_score = d, score
    return best


def _find_first_data_row(rows: list) -> int:
    for i, row in enumerate(rows):
        if not row:
            continue
        first, rest = row[0], row[1:]
        if looks_like_sample_id(first) and numeric_fraction(rest) >= 0.5 and len(rest) >= 2:
            return i
        if len(rest) >= 3 and numeric_fraction(rest) >= 0.8 and (first or "").strip() != "":
            return i
    return -1


def parse_delimited(text: str, forced_delim: str | None = None) -> ParsedSif:
    delimiter = forced_delim or sniff_delimiter(text[:8192])
    rows = [[(c or "").strip() for c in r]
            for r in csv.reader(io.StringIO(text), delimiter=delimiter)]
    if not rows:
        raise ValueError("File is empty or unreadable.")

    data_start = _find_first_data_row(rows)
    if data_start < 0:
        raise ValueError("Could not locate a data row; try forcing the delimiter.")

    first_data = rows[data_start]
    n_lead = 0
    for cell in first_data:
        if _is_number(cell):
            break
        n_lead += 1
        if n_lead >= 4:
            break
    n_lead = max(1, n_lead)
    n_analytes = len(first_data) - n_lead

    header_block = []
    i = data_start - 1
    while i >= 0 and rows[i] and any(c for c in rows[i]):
        if len(rows[i]) < max(2, n_lead + 1):
            break
        header_block.insert(0, rows[i])
        if len(header_block) >= len(DELIM_HEADER_LABELS) + 1:
            break
        i -= 1

    def col(row, idx):
        return row[idx].strip() if idx < len(row) else ""

    lead_names = ["sample_id"] + [f"lead_{k}" for k in range(1, n_lead)]
    label_row = None
    if header_block and header_block[-1][0].strip().lower() in SAMPLE_HEADER_WORDS:
        label_row = header_block.pop()
        lead_names = [(c.strip() or f"lead_{k}") for k, c in enumerate(label_row[:n_lead])]

    # Label each row by its content; rows that can't be told apart, or whose
    # role is already taken, get the remaining labels in the default order.
    block_cells = [[col(hrow, n_lead + j) for j in range(n_analytes)] for hrow in header_block]
    roles = [_classify_header_row(cells) for cells in block_cells]
    taken = set()
    for k, role in enumerate(roles):
        if role in taken:
            roles[k] = None
        elif role:
            taken.add(role)
    spare = iter(l for l in DELIM_HEADER_LABELS if l not in taken)
    analyte_headers = {}
    for off, cells in enumerate(block_cells):
        label = roles[off] or next(spare, f"header_{off}")
        analyte_headers[label] = cells

    if not any(analyte_headers.get("element", [])):
        if label_row is not None:
            analyte_headers["element"] = [col(label_row, n_lead + j) for j in range(n_analytes)]
        elif not any(analyte_headers.get(k) for k in ("units", "method")):
            analyte_headers["element"] = [f"analyte_{j+1}" for j in range(n_analytes)]
    analytes = _column_names(analyte_headers, n_analytes)

    data_rows = []
    for row in rows[data_start:]:
        if not row or not any(c for c in row):
            continue
        if not (looks_like_sample_id(row[0]) or numeric_fraction(row[n_lead:]) >= 0.5):
            continue
        data_rows.append([col(row, k) for k in range(n_lead + n_analytes)])

    return ParsedSif(
        fmt="delimited",
        delimiter=delimiter,
        analyte_headers=analyte_headers,
        n_lead_cols=n_lead,
        lead_col_names=lead_names,
        analytes=analytes,
        data_rows=data_rows,
    )


def parse_text(text: str, forced_delim: str | None = None) -> ParsedSif:
    """Parse a SIF certificate, auto-selecting fixed-width vs delimited."""
    lines = text.splitlines()
    if not lines:
        raise ValueError("File is empty or unreadable.")
    if forced_delim is None and _is_fixed_width(lines):
        return parse_fixed_width(lines)
    return parse_delimited(text, forced_delim)


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def to_wide_csv(p: ParsedSif) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_file"] + list(p.lead_col_names) + list(p.analytes))
    for row in p.data_rows:
        w.writerow([p.source_file] + list(row))
    return buf.getvalue()


def to_long_csv(p: ParsedSif) -> str:
    elements = p.analyte_headers.get("element", list(p.analytes))
    methods = p.analyte_headers.get("method", [])
    units = p.analyte_headers.get("units", [])
    dls = p.analyte_headers.get("detection_limit", [])

    def at(seq, j):
        return seq[j] if j < len(seq) else ""

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_file"] + list(p.lead_col_names)
               + ["col_index", "element", "method", "value", "units", "detection_limit", "flag"])
    for row in p.data_rows:
        lead = row[: p.n_lead_cols]
        for j in range(len(p.analytes)):
            raw = row[p.n_lead_cols + j] if (p.n_lead_cols + j) < len(row) else ""
            w.writerow([p.source_file] + lead + [j, at(elements, j), at(methods, j), raw,
                               at(units, j), at(dls, j), result_flag(raw)])
    return buf.getvalue()


def to_wide_df(p: ParsedSif):
    import pandas as pd
    cols = ["source_file"] + list(p.lead_col_names) + list(p.analytes)
    return pd.DataFrame([[p.source_file] + list(r) for r in p.data_rows], columns=cols)


def analyte_table_df(p: ParsedSif):
    import pandas as pd
    n = len(p.analytes)
    data = {"column": list(p.analytes)}
    for label in ("element", "method", "units", "detection_limit"):
        seq = p.analyte_headers.get(label, [])
        if any(seq):
            data[label] = [seq[j] if j < len(seq) else "" for j in range(n)]
    return pd.DataFrame(data)


def metadata_df(p: ParsedSif):
    import pandas as pd
    if not p.metadata:
        return pd.DataFrame(columns=["field", "value"])
    return pd.DataFrame(list(p.metadata.items()), columns=["field", "value"])


def diagnostic(p: ParsedSif) -> dict:
    names = {",": "comma", "\t": "tab", ";": "semicolon", "|": "pipe"}
    return {
        "format": p.fmt,
        "certificate": p.certificate,
        "delimiter": names.get(p.delimiter, p.delimiter) if p.fmt == "delimited" else "fixed width",
        "analyte_count": len(p.analytes),
        "sample_count": len(p.data_rows),
        "header_rows": list(p.analyte_headers.keys()),
    }
