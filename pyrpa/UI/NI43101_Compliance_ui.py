"""NI 43-101 Compliance Check — deterministic (no-LLM) structural checks
against Form 43-101F1, run instantly in the browser.

About a third of the checklist is presence/structural/cross-reference work —
Table of Contents, reference-list completeness, the two-phase recommendation
limit, mandated cautionary boilerplate, effective-date consistency across the
document, certificate Item-coverage, cost-table presence — that a regex/
structure pass can decide with no model call. This page runs only those
checks, entirely in memory, so it works on Streamlit Cloud with no GPU/Ollama
available.

The other ~70% of the checklist is narrative sufficiency ("does this section
adequately describe X"), which genuinely needs an LLM reading the full report.
That full pass runs locally against Ollama and is deliberately not exposed
here: Streamlit Cloud has no local model to call, and NI 43-101 technical
reports are frequently pre-disclosure/market-sensitive, so the complete
checker is offered as an offline download instead of a cloud upload.
"""

import importlib
import io
import os
import sys
import tempfile
import zipfile

import streamlit as st

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_here, "..", ".."))
_ni_root = os.path.join(_repo_root, "ni43101_compliance")
if _ni_root not in sys.path:
    sys.path.insert(0, _ni_root)

from compliance import models as _ni_models
from compliance import ingest, structure, structural_checks
from compliance import report as ni_report

# Streamlit's local file watcher doesn't reliably pick up edits to modules
# imported via a sys.path insert like this one, and Streamlit Cloud keeps the
# process alive across redeploys and only re-runs this entry script — either
# way, an already-imported module can stay pinned to a stale cached copy even
# after the file on disk changes. This UI file is re-executed from disk on
# every run (via runpy), so reloading here guarantees the latest checks run.
# Same pattern as SIF_to_CSV_ui.py, and for the same reason.
importlib.reload(_ni_models)
importlib.reload(ingest)
importlib.reload(structure)
importlib.reload(structural_checks)
importlib.reload(ni_report)

from compliance.models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
)

MAX_MB = 60
_STATUS_ICON = {
    STATUS_COMPLIANT: "✅",
    STATUS_NOT_APPLICABLE: "☑️",
    STATUS_PARTIAL: "⚠️",
    STATUS_NON_COMPLIANT: "❌",
    STATUS_NOT_ADDRESSED: "ℹ️",
}
_STATUS_ORDER = {
    STATUS_NON_COMPLIANT: 0,
    STATUS_PARTIAL: 1,
    STATUS_NOT_ADDRESSED: 2,
    STATUS_NOT_APPLICABLE: 3,
    STATUS_COMPLIANT: 4,
}


@st.cache_data(show_spinner=False)
def _local_bundle_bytes() -> bytes:
    """Zip the full standalone checker (including the LLM pass) plus the SLR
    checklist already in this repo, so the offline download is one self-
    contained folder a user can unzip and run against their own Ollama."""
    exclude_dirs = {"__pycache__", "output", ".cache", "tests"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(_ni_root):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if f.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(root, f)
                arc = os.path.relpath(full, _ni_root).replace(os.sep, "/")
                zf.write(full, arc)
        checklist_path = os.path.join(
            _repo_root, "SLR NI 43-101 Compliance Checklist for QAQC.docx"
        )
        if os.path.exists(checklist_path):
            zf.write(checklist_path, "SLR NI 43-101 Compliance Checklist for QAQC.docx")
    return buf.getvalue()


st.title("NI 43-101 Compliance Check")
st.markdown(
    "Runs the **deterministic** checks from Form 43-101F1 against an uploaded "
    "technical report — presence checks, counting rules, mandated "
    "boilerplate, and cross-document consistency (effective date, QP Item "
    "coverage, and more). No AI model is involved; results appear in seconds."
)

with st.expander("ℹ️ What this does — and doesn't — check"):
    st.markdown(
        "Roughly a **third** of Form 43-101F1's requirements can be verified "
        "mechanically, with no judgment call:\n\n"
        "- Table of Contents present\n"
        "- Item 27: every in-text citation appears in the References list\n"
        "- Item 26: recommendations don't exceed the two-phase limit\n"
        "- Item 6(c) / 23(c): mandated cautionary language near historical-"
        "estimate and adjacent-property disclosures\n"
        "- Effective date matches everywhere it's stated (title page, "
        "signature page, each certificate/consent)\n"
        "- Certificate (e): every QP's claimed Items union to cover 1–27\n"
        "- Item 21: capital/operating costs sit in an actual table (PDF only)\n"
        "- Summary figures (tonnes, grades, costs, mine life) agree with the "
        "full sections of the report\n\n"
        "The remaining ~70% — *does this section adequately describe X* — "
        "needs real language understanding and does not run here. See "
        "**Run the full check locally** below for that pass."
    )

with st.expander("\U0001f5a5️ Run the full check locally (with AI, offline)"):
    st.caption(
        "The complete pass — including the narrative-sufficiency checks "
        "that need language understanding — runs against a local model via "
        "Ollama, entirely on your machine. Recommended for pre-disclosure or "
        "otherwise confidential reports: nothing leaves your computer."
    )
    st.download_button(
        "⬇️ Download local compliance checker (.zip)",
        data=_local_bundle_bytes(),
        file_name="ni43101-compliance-local.zip",
        mime="application/zip",
        use_container_width=True,
        key="ni_local_zip",
    )
    st.markdown(
        "1. Unzip, then follow the included README: install "
        "[Ollama](https://ollama.com/download), pull `qwen2.5:7b-instruct` "
        "and `nomic-embed-text`, then `pip install -r requirements.txt`.\n"
        "2. Full pass: `python run_compliance.py --report your_report.pdf "
        '--checklist "SLR NI 43-101 Compliance Checklist for QAQC.docx"`\n'
        "3. Just the checks on this page, from the command line: add "
        "`--python-only` (no Ollama needed either way for that mode)."
    )

uploaded = st.file_uploader(
    "Technical report (PDF or DOCX)",
    type=["pdf", "docx"],
    help="Held in memory for this session only; nothing is written to the server.",
    key="ni_report_upload",
)

if not uploaded:
    st.info("Upload a report to run the deterministic checks.")
    st.stop()

if uploaded.size > MAX_MB * 1024 * 1024:
    st.error(
        f"This file is {uploaded.size / 1024 / 1024:.0f} MB, over the "
        f"{MAX_MB} MB limit for the hosted checker (this app shares one "
        "server with everyone using these tools). Use the local download "
        "above instead — no size limit, and it also runs the full "
        "AI-assisted pass."
    )
    st.stop()

suffix = os.path.splitext(uploaded.name)[1].lower() or ".pdf"
tmp_path = None
try:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    with st.spinner("Reading report..."):
        pages = ingest.load_report(tmp_path)
        page_items = structure.detect_page_items(pages)

    with st.spinner("Running structural checks..."):
        findings = structural_checks.run_structural_checks(
            pages, page_items, report_path=tmp_path
        )
finally:
    if tmp_path and os.path.exists(tmp_path):
        os.unlink(tmp_path)

detected = len({v[0] for v in page_items.values()})
c1, c2, c3 = st.columns(3)
c1.metric("Pages", len(pages))
c2.metric("Items detected", f"{detected}/27")
c3.metric("Checks run", len(findings))

st.divider()

for f in sorted(findings, key=lambda f: _STATUS_ORDER.get(f.status, 9)):
    icon = _STATUS_ICON.get(f.status, "•")
    label = f"{icon} {f.criterion.item_title} — {f.criterion.text}"
    expanded = f.status in (STATUS_NON_COMPLIANT, STATUS_PARTIAL)
    with st.expander(label, expanded=expanded):
        st.write(f"**Status:** {f.status}")
        if f.rationale:
            st.write(f.rationale)
        if f.evidence:
            st.caption(f"Evidence: {f.evidence}")
        if f.pages:
            st.caption("Pages: " + ", ".join(str(p) for p in f.pages))

st.divider()

doc_buf = io.BytesIO()
ni_report.write_report(
    findings,
    report_name=uploaded.name,
    checklist_name="Form 43-101F1 (deterministic checks only — see "
    "'Run the full check locally' above for the complete AI-assisted pass)",
    model_name="none (deterministic checks only)",
    out_path=doc_buf,
)

st.download_button(
    "⬇️ Download findings (.docx)",
    data=doc_buf.getvalue(),
    file_name=os.path.splitext(uploaded.name)[0] + "_compliance_structural.docx",
    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    use_container_width=True,
    key="ni_download_report",
)
