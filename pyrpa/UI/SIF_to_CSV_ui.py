"""SIF Certificate to CSV — drop assay-lab SIF certificates in, get CSV out.

Wraps pyrpa.sif_convert. Runs fully in memory (no disk writes), so it works
on Streamlit Cloud. Supports batch upload: multiple certificates are merged
into one combined wide CSV and one combined long CSV (row-stacked when the
columns match, union with a warning when they differ), with an optional
per-file .zip. Widget keys are namespaced so nothing collides.
"""

import csv
import importlib
import io
import os
import zipfile

import pandas as pd
import streamlit as st

from pyrpa import sif_convert

# Streamlit Cloud keeps the Python process alive across redeploys and only
# re-runs the entry script, so an imported module can stay pinned to an older
# cached copy even after a git deploy. This UI file is re-executed from disk on
# every run (via runpy), so reloading here guarantees the latest parser.
sif_convert = importlib.reload(sif_convert)


# ── Offline "Run locally" bundle ─────────────────────────────────────────────
# A hosted web page cannot open a terminal on the viewer's machine (browser
# sandbox). The next best thing: hand them a small, dependency-free bundle they
# can double-click. It reuses the SAME parser that runs here (read from disk at
# request time) so the offline result always matches the online one.

INBOX_DIRNAME = "move SIF files here"
INBOX_PLACEHOLDER = "put your SIF files in this folder.txt"

_CLI_WRAPPER = r'''#!/usr/bin/env python3
# Local runner for the SLR Tools "SIF Certificate to CSV" converter.
# Bundled by the app's "Run locally" button. Standard library only.
#
# Easiest: move your certificates into the "move SIF files here" folder and
# double-click "Run SIF to CSV.bat" (or run: python sif_to_csv.py).
# Naming files explicitly still works:
#   python sif_to_csv.py FILE.sif [more.sif ...] [--outdir csv_out]
import argparse, csv, datetime, glob, io, os
import sif_convert

INBOX = "move SIF files here"
PLACEHOLDER = "put your sif files in this folder.txt"
HERE = os.path.dirname(os.path.abspath(__file__))


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def _stack(csvs):
    out, header = [], None
    for s in csvs:
        lines = s.splitlines()
        if not lines:
            continue
        if header is None:
            header = lines[0]
            out.append(header)
        out.extend(lines[1:])
    return "\n".join(out) + "\n"


def _merge_wide(parsed):
    """Combined wide CSV. Row-stack when every file shares one column set;
    otherwise use the union of columns (blank where a file lacks one) —
    the same behaviour as the online tool."""
    headers = [tuple(r.lead_col_names + r.analytes) for _, r in parsed]
    if len(set(headers)) == 1:
        return _stack([sif_convert.to_wide_csv(r) for _, r in parsed]), True
    union = []
    for h in headers:
        for c in h:
            if c not in union:
                union.append(c)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_file"] + union)
    for (_, r), h in zip(parsed, headers):
        idx = {c: k for k, c in enumerate(h)}
        for row in r.data_rows:
            w.writerow([r.source_file] + [row[idx[c]] if c in idx and idx[c] < len(row) else "" for c in union])
    return buf.getvalue(), False


def _report(parsed, failed, same_cols, outdir):
    """The same stats the online tool shows: per-file format / certificate /
    analyte columns / rows, plus the combined-output metrics."""
    total_rows = sum(len(r.data_rows) for _, r in parsed)
    lines = [
        "SIF Certificate to CSV - conversion report",
        "Run: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
        "Files converted      : %d" % len(parsed),
        "Files failed         : %d" % len(failed),
        "Total rows (incl. QC): %d" % total_rows,
    ]
    if len(parsed) > 1:
        lines.append("Columns              : " + ("consistent" if same_cols else "union (differ)"))
    lines.append("")
    for name, r in parsed:
        d = sif_convert.diagnostic(r)
        fmt = "fixed width" if d["format"] == "fixed_width" else d["delimiter"] + "-delimited"
        lines += [
            name,
            "  Format          : " + fmt,
            "  Certificate     : " + (d["certificate"] or "-"),
            "  Analyte columns : %d" % d["analyte_count"],
            "  Rows (incl. QC) : %d" % d["sample_count"],
            "",
        ]
    if failed:
        lines.append("Failed files (excluded from the merge):")
        for name, msg in failed:
            lines.append("  %s: %s" % (name, msg))
        lines += ["  Tip: retry with --delimiter comma / tab / semicolon / pipe.", ""]
    lines.append("Output folder: " + os.path.abspath(outdir))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Convert assay-lab SIF certificates to CSV.")
    ap.add_argument("files", nargs="*",
                    help='Optional files (wildcards ok). Default: everything in "%s".' % INBOX)
    ap.add_argument("--outdir", default="csv_out")
    ap.add_argument("--delimiter", default=None, help="Force a delimiter ('tab' for tab).")
    args = ap.parse_args()
    forced = "\t" if args.delimiter == "tab" else args.delimiter

    if args.files:
        paths = []
        for pattern in args.files:
            hits = glob.glob(pattern)
            paths.extend(hits if hits else [pattern])
    else:
        inbox = os.path.join(HERE, INBOX)
        os.makedirs(inbox, exist_ok=True)
        paths = sorted(
            p for p in glob.glob(os.path.join(inbox, "*"))
            if os.path.isfile(p) and os.path.basename(p).lower() != PLACEHOLDER
        )
        if not paths:
            print('Nothing to convert. Move your .sif certificates into the')
            print('"%s" folder and run this again.' % INBOX)
            return

    outdir = args.outdir if os.path.isabs(args.outdir) else os.path.join(HERE, args.outdir)
    os.makedirs(outdir, exist_ok=True)

    parsed, failed = [], []
    for p in paths:
        name = os.path.basename(p)
        if not os.path.isfile(p):
            print("[skip] not a file:", p)
            continue
        try:
            result = sif_convert.parse_text(read_text(p), forced)
            result.source_file = name
        except Exception as exc:
            failed.append((name, str(exc)))
            print("[FAIL]", name, "->", exc)
            continue
        parsed.append((name, result))
        base = os.path.splitext(name)[0]
        with open(os.path.join(outdir, base + "_wide.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(sif_convert.to_wide_csv(result))
        with open(os.path.join(outdir, base + "_long.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(sif_convert.to_long_csv(result))
        print("[ok]", name, "->", base + "_wide.csv /", base + "_long.csv")

    same_cols = True
    if len(parsed) > 1:
        wide_combined, same_cols = _merge_wide(parsed)
        with open(os.path.join(outdir, "combined_wide.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(wide_combined)
        with open(os.path.join(outdir, "combined_long.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(_stack([sif_convert.to_long_csv(r) for _, r in parsed]))
        print("[ok] merged %d files -> combined_wide.csv / combined_long.csv" % len(parsed))

    if parsed or failed:
        report = _report(parsed, failed, same_cols, outdir)
        with open(os.path.join(outdir, "report.txt"), "w", encoding="utf-8") as fh:
            fh.write(report)
        print()
        print(report)


if __name__ == "__main__":
    main()
'''

_BAT_LAUNCHER = r'''@echo off
cd /d "%~dp0"
title SIF Certificate to CSV
echo(
echo    SIF Certificate to CSV  (local runner)
echo(
where python >nul 2>nul || (
  echo    Python 3.9+ was not found on PATH.
  echo    Install it from https://www.python.org/downloads/ and tick
  echo    "Add python.exe to PATH", then run this again.
  echo(
  pause
  exit /b 1
)
if "%~1"=="" (
  echo    Converting everything in the "move SIF files here" folder...
  echo(
  python sif_to_csv.py
) else (
  python sif_to_csv.py %*
)
echo(
echo    Done. CSVs and report.txt are in the csv_out folder.
pause
'''

_LOCAL_README = r'''SIF Certificate to CSV - local runner
=====================================

Offline copy of the SLR Tools "SIF Certificate to CSV" converter. It runs
entirely on your machine; nothing is uploaded anywhere.

Requirements: Python 3.9+ (https://www.python.org/downloads/).
No other install needed (standard library only). No limit on file count.

Windows (easiest):
  1. Unzip this folder somewhere.
  2. Move your .sif certificates into the "move SIF files here" folder.
  3. Double-click "Run SIF to CSV.bat".
  4. CSVs land in a "csv_out" folder, along with report.txt - the same
     stats the online tool shows (per-file format, certificate, analyte
     columns, rows, and the combined-merge summary).
  (If SmartScreen warns about the .bat, choose "More info" then "Run anyway".
   Dragging .sif files onto the .bat still works too.)

Command line (any OS):
  python sif_to_csv.py                  (converts the "move SIF files here" folder)
  python sif_to_csv.py FILE.sif [more.sif ...] --outdir csv_out

Per file: <name>_wide.csv and <name>_long.csv
Several files: combined_wide.csv and combined_long.csv (merged automatically)
Always: report.txt with the conversion summary
'''


def _local_bundle_bytes() -> bytes:
    """Zip the current parser + a tiny CLI + a Windows launcher for offline use."""
    with open(sif_convert.__file__, "r", encoding="utf-8") as fh:
        core_src = fh.read()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sif_convert.py", core_src)
        zf.writestr("sif_to_csv.py", _CLI_WRAPPER)
        zf.writestr("Run SIF to CSV.bat", _BAT_LAUNCHER)
        zf.writestr("README.txt", _LOCAL_README)
        zf.writestr(
            f"{INBOX_DIRNAME}/{INBOX_PLACEHOLDER}",
            'Move your .sif certificates into this folder, then double-click\n'
            '"Run SIF to CSV.bat" one level up. This note file is ignored.\n',
        )
    return buf.getvalue()


st.title("CSV Files Compilation")
st.markdown(
    "Convert assay-lab **SIF certificates** (the Standard Interchange Format "
    "files from ALS, SGS, Bureau Veritas, Intertek, etc.) into clean CSV. "
    "Drop one or more files below — multiple files are merged into one combined CSV."
)

DELIM_CHOICES = {
    "Auto-detect": None,
    "Comma ( , )": ",",
    "Tab": "\t",
    "Semicolon ( ; )": ";",
    "Pipe ( | )": "|",
}

with st.sidebar:
    st.markdown("## Options")
    delim_label = st.selectbox(
        "Delimiter",
        list(DELIM_CHOICES.keys()),
        index=0,
        help="Leave on Auto-detect unless the columns come out wrong.",
        key="sif_delim",
    )
    forced_delim = DELIM_CHOICES[delim_label]
    make_zip = st.checkbox(
        "Also offer per-file .zip",
        value=False,
        help="Build a zip of each file's own wide + long CSVs, in addition to the merged output.",
        key="sif_zip",
    )

    with st.expander("🖥️ Run locally (offline)"):
        st.caption(
            "A web page can't open a terminal on your PC, so this gives you a small "
            "offline bundle instead. It runs on your machine and nothing is uploaded. "
            "Good for big batches or confidential data. Needs Python 3.9+ (no internet "
            "or install)."
        )
        st.download_button(
            "⬇️ Download local runner (.zip)",
            data=_local_bundle_bytes(),
            file_name="SIF-to-CSV-local.zip",
            mime="application/zip",
            use_container_width=True,
            key="run_local_zip",
        )
        st.markdown(
            "**How to use**\n"
            "1. Unzip the downloaded file into a folder.\n"
            "2. Move your `.sif` certificates into the **move SIF files here** folder "
            "(any number of files).\n"
            "3. Double-click **Run SIF to CSV.bat**.\n"
            "4. Your CSVs land in a new **csv_out** folder — per-file wide/long CSVs, "
            "combined CSVs when you convert several, and a **report.txt** with the same "
            "stats this page shows."
        )
        st.markdown(
            "**Prefer typing?** Open the unzipped folder, click the address bar, "
            "type `cmd`, press Enter, then run:"
        )
        st.code("python sif_to_csv.py", language="bash")
        st.caption(
            "First run only: if Windows SmartScreen warns, choose *More info* then "
            "*Run anyway*. If Python isn't found, install it from python.org and tick "
            '"Add python.exe to PATH".'
        )

uploaded = st.file_uploader(
    "SIF certificate file(s)",
    type=["sif", "csv", "txt"],
    accept_multiple_files=True,
    key="sif_upload",
    help="These stay on the server only for this session and are never stored.",
)

if not uploaded:
    st.info("Upload one or more .sif certificate files to begin.")
    st.stop()

# ── Batch size guard ─────────────────────────────────────────────────────────
# Every session on Streamlit Cloud shares one container with a fixed memory
# budget, so an oversized batch doesn't just fail for the person uploading — it
# takes the whole app down for everyone until it is rebooted. Converting costs
# roughly 15x the uploaded bytes at peak (the long-format CSV dominates, at
# rows x analytes), so refuse batches that would put the container at risk and
# hand the user the offline runner, which has no limit.
MAX_FILES = 60
MAX_TOTAL_BYTES = 40 * 1024 * 1024

total_bytes = sum(up.size for up in uploaded)
if len(uploaded) > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
    st.error(
        f"This batch is too large to convert online: **{len(uploaded)} files, "
        f"{total_bytes / 1024 / 1024:.0f} MB** (limit: {MAX_FILES} files and "
        f"{MAX_TOTAL_BYTES // 1024 // 1024} MB per batch).\n\n"
        "The hosted app shares one server with everyone else using these tools, "
        "so a batch this big would run it out of memory. Use the offline runner "
        "below instead — it has no limit, runs on your own machine, and produces "
        "identical output."
    )
    st.download_button(
        "⬇️ Download local runner (.zip)",
        data=_local_bundle_bytes(),
        file_name="SIF-to-CSV-local.zip",
        mime="application/zip",
        key="run_local_zip_toobig",
        help="Unzip, move your .sif files into the folder it makes, double-click the .bat.",
    )
    st.caption(
        "Converting a smaller batch here still works — try splitting it up if you "
        "would rather stay in the browser."
    )
    st.stop()


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _stack_csv(csv_strings) -> str:
    """Concatenate CSV strings that share an identical header: keep the first
    header, drop the rest, append all data rows.

    Takes any iterable so callers can pass a generator: each file's CSV is then
    freed as soon as its rows are copied, instead of every file's CSV being held
    at once alongside the combined result."""
    out, header = [], None
    for s in csv_strings:
        lines = s.splitlines()
        if not lines:
            continue
        if header is None:
            header = lines[0]
            out.append(header)
        out.extend(lines[1:])
    return "\n".join(out) + "\n"


# ── Parse every uploaded file ────────────────────────────────────────────────
results, errors = [], []
for up in uploaded:
    try:
        parsed_file = sif_convert.parse_text(_decode(up.getvalue()), forced_delim)
        parsed_file.source_file = up.name
        results.append((up.name, parsed_file))
    except Exception as exc:  # noqa: BLE001 — report per file, keep going
        errors.append((up.name, str(exc)))

if errors:
    st.warning(f"Could not parse {len(errors)} file(s) — they are excluded from the merge:")
    for name, msg in errors:
        st.write(f"- **{name}**: {msg}")
    st.caption(
        "Tip: try forcing the delimiter in the sidebar. If it still fails, the header "
        "layout may be unusual — share a redacted sample (structure only, fake values). "
        "You can also use **Run locally (offline)** in the sidebar to convert on your own machine."
    )

if not results:
    st.stop()

multi = len(results) > 1

# ── Combined output (batch) ──────────────────────────────────────────────────
if multi:
    st.subheader("Combined output")

    schemas = {tuple(p.lead_col_names + p.analytes) for _, p in results}
    same_cols = len(schemas) == 1

    long_combined = _stack_csv(sif_convert.to_long_csv(p) for _, p in results)
    if same_cols:
        wide_combined = _stack_csv(sif_convert.to_wide_csv(p) for _, p in results)
    else:
        # Union of columns, written row by row. Building a DataFrame per file and
        # concatenating them costs several full copies of the batch at peak; this
        # holds only the output, and matches what the offline runner does.
        union = []
        for _, p in results:  # file order, so the column order is reproducible
            for col in list(p.lead_col_names) + list(p.analytes):
                if col not in union:
                    union.append(col)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["source_file"] + union)
        for _, p in results:
            pos = {col: i for i, col in enumerate(list(p.lead_col_names) + list(p.analytes))}
            for row in p.data_rows:
                writer.writerow(
                    [p.source_file]
                    + [row[pos[c]] if c in pos and pos[c] < len(row) else "" for c in union]
                )
        wide_combined = buf.getvalue()

    total_rows = sum(len(p.data_rows) for _, p in results)
    c1, c2, c3 = st.columns(3)
    c1.metric("Files merged", len(results))
    c2.metric("Total rows", total_rows)
    c3.metric("Columns", "consistent" if same_cols else "union (differ)")

    if same_cols:
        st.caption("All files share the same columns — merged by stacking rows.")
    else:
        st.warning(
            "Files have different column sets. The combined **wide** CSV uses the union of "
            "columns (blank where a file lacks one); the combined **long** CSV is unaffected. "
            "Each row carries its `certificate`, so you can always tell files apart."
        )

    st.markdown("**Combined preview** (first 20 rows of the wide table):")
    preview = pd.read_csv(io.StringIO(wide_combined), nrows=20, dtype=str, keep_default_na=False)
    st.dataframe(preview, use_container_width=True, hide_index=True)

    d1, d2 = st.columns(2)
    d1.download_button(
        "⬇️ Combined wide CSV",
        data=wide_combined,
        file_name="combined_wide.csv",
        mime="text/csv",
        use_container_width=True,
        key="cmb_wide",
        help="All samples from all files, one row per sample, one column per analyte.",
    )
    d2.download_button(
        "⬇️ Combined long CSV",
        data=long_combined,
        file_name="combined_long.csv",
        mime="text/csv",
        use_container_width=True,
        key="cmb_long",
        help="All measurements from all files, one row per (sample, analyte).",
    )

    if make_zip:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, p in results:
                stem = name.rsplit(".", 1)[0]
                zf.writestr(f"{stem}_wide.csv", sif_convert.to_wide_csv(p))
                zf.writestr(f"{stem}_long.csv", sif_convert.to_long_csv(p))
        st.download_button(
            "⬇️ Each file separately (.zip)",
            data=buf.getvalue(),
            file_name="sif_csv_export.zip",
            mime="application/zip",
            use_container_width=True,
            key="cmb_zip",
        )

    st.divider()
    st.caption("Per-file details below (for spot-checking each certificate).")

# ── Per-file detail ──────────────────────────────────────────────────────────
for idx, (name, parsed) in enumerate(results):
    with st.expander(name, expanded=(not multi)):
        diag = sif_convert.diagnostic(parsed)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Format", "fixed width" if diag["format"] == "fixed_width" else diag["delimiter"])
        c2.metric("Certificate", diag["certificate"] or "—")
        c3.metric("Analyte columns", diag["analyte_count"])
        c4.metric("Rows (incl. QC)", diag["sample_count"])

        if not multi:
            # Full detail for a single upload; kept light in batch mode.
            if parsed.metadata:
                with st.popover("Certificate details"):
                    st.dataframe(sif_convert.metadata_df(parsed), use_container_width=True, hide_index=True)

            st.markdown("**Detected columns** — check element / method / units line up before trusting the output:")
            st.dataframe(sif_convert.analyte_table_df(parsed), use_container_width=True, hide_index=True)

            st.markdown("**Data preview** (first 20 rows):")
            st.dataframe(sif_convert.to_wide_df(parsed).head(20), use_container_width=True, hide_index=True)

            stem = name.rsplit(".", 1)[0]
            d1, d2 = st.columns(2)
            d1.download_button(
                "⬇️ Download wide CSV",
                data=sif_convert.to_wide_csv(parsed),
                file_name=f"{stem}_wide.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"sif_wide_{idx}",
                help="One row per sample, one column per analyte.",
            )
            d2.download_button(
                "⬇️ Download long CSV",
                data=sif_convert.to_long_csv(parsed),
                file_name=f"{stem}_long.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"sif_long_{idx}",
                help="Tidy: one row per (sample, analyte) with units, method, detection limit, flag.",
            )
        else:
            meta = parsed.metadata or {}
            bits = [f"**{k}:** {meta[k]}" for k in ("CLIENT", "PROJECT", "DATE COMPLETED") if k in meta]
            if bits:
                st.caption(" · ".join(bits))
