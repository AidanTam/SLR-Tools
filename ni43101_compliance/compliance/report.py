"""Render findings into a Word (.docx) compliance report."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import List

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from .models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    Finding,
)


def _group_sort_key(item_id: str, item_title: str):
    """Front matter first, then Items 1-27 in order, then certificates/
    consistency/anything else, then unmapped criteria last."""
    if item_id == "front_matter":
        return (0, 0, item_title)
    m = re.match(r"item_(\d{1,2})$", item_id or "")
    if m:
        return (1, int(m.group(1)), item_title)
    if not item_title or item_title == "General / Unmapped":
        return (3, 0, item_title)
    return (2, 0, item_title)

_STATUS_COLOR = {
    STATUS_COMPLIANT: RGBColor(0x1E, 0x7A, 0x34),      # green
    STATUS_PARTIAL: RGBColor(0xB8, 0x86, 0x00),        # amber
    STATUS_NON_COMPLIANT: RGBColor(0xC0, 0x28, 0x28),  # red
    STATUS_NOT_ADDRESSED: RGBColor(0x60, 0x60, 0x60),  # grey
    STATUS_NOT_APPLICABLE: RGBColor(0x3E, 0x6B, 0x4A),  # muted green: a pass, not a finding
}
_STATUS_ORDER = [
    STATUS_NON_COMPLIANT,
    STATUS_PARTIAL,
    STATUS_NOT_ADDRESSED,
    STATUS_NOT_APPLICABLE,
    STATUS_COMPLIANT,
]


def write_report(
    findings: List[Finding],
    report_name: str,
    checklist_name: str,
    model_name: str,
    out_path: str,
) -> None:
    doc = Document()

    doc.add_heading("NI 43-101 Compliance Review", level=0)
    meta = doc.add_paragraph()
    meta.add_run("Report reviewed: ").bold = True
    meta.add_run(report_name + "\n")
    meta.add_run("Checklist: ").bold = True
    meta.add_run(checklist_name + "\n")
    meta.add_run("Generated: ").bold = True
    meta.add_run(datetime.now().strftime("%Y-%m-%d %H:%M") + "\n")
    meta.add_run("Model (local): ").bold = True
    meta.add_run(model_name)

    _add_summary(doc, findings)
    _add_disclaimer(doc)

    doc.add_heading("Detailed Findings", level=1)
    # Group by NI 43-101 Item (front matter first, Items 1-27 in order,
    # certificates/consistency checks after, unmapped criteria last).
    grouped = {}
    titles = {}
    for f in findings:
        item_id = f.criterion.item_id or "unmapped"
        key = item_id
        grouped.setdefault(key, []).append(f)
        titles[key] = f.criterion.item_title or "General / Unmapped"

    for item_id in sorted(grouped, key=lambda k: _group_sort_key(k, titles[k])):
        item_title = titles[item_id]
        doc.add_heading(item_title, level=2)
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        hdr[0].paragraphs[0].add_run("Criterion").bold = True
        hdr[1].paragraphs[0].add_run("Status").bold = True
        hdr[2].paragraphs[0].add_run("Evidence & Rationale").bold = True

        for f in grouped[item_id]:
            row = table.add_row().cells
            row[0].text = f.criterion.text

            status_p = row[1].paragraphs[0]
            run = status_p.add_run(f.status)
            run.bold = True
            run.font.color.rgb = _STATUS_COLOR.get(f.status, RGBColor(0, 0, 0))
            method_label = "Automated check" if f.method == "python" else f"Model, conf. {f.confidence:.0%}" if f.confidence else "Model"
            tag = status_p.add_run(f"\n({method_label})")
            tag.font.size = Pt(8)
            tag.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

            cell = row[2]
            cell.text = ""
            if f.error:
                p = cell.paragraphs[0]
                r = p.add_run(f"ERROR: {f.error}")
                r.font.color.rgb = RGBColor(0xC0, 0x28, 0x28)
                continue
            if f.rationale:
                cell.paragraphs[0].add_run(f.rationale)
            if f.evidence:
                q = cell.add_paragraph()
                qr = q.add_run(f"“{f.evidence}”")
                qr.italic = True
                qr.font.size = Pt(9)
            if f.pages:
                pg = cell.add_paragraph()
                pr = pg.add_run("Pages: " + ", ".join(str(p) for p in f.pages))
                pr.font.size = Pt(8)
                pr.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

    doc.save(out_path)


def _add_summary(doc: Document, findings: List[Finding]) -> None:
    doc.add_heading("Summary", level=1)
    counts = Counter(f.status for f in findings)
    total = len(findings)

    table = doc.add_table(rows=1, cols=2)
    table.style = "Light List Accent 1"
    table.rows[0].cells[0].paragraphs[0].add_run("Status").bold = True
    table.rows[0].cells[1].paragraphs[0].add_run("Count").bold = True
    for status in _STATUS_ORDER:
        row = table.add_row().cells
        r = row[0].paragraphs[0].add_run(status)
        r.font.color.rgb = _STATUS_COLOR[status]
        pct = f" ({counts.get(status, 0) / total:.0%})" if total else ""
        row[1].paragraphs[0].add_run(f"{counts.get(status, 0)}{pct}")
    total_row = table.add_row().cells
    total_row[0].paragraphs[0].add_run("Total criteria").bold = True
    total_row[1].paragraphs[0].add_run(str(total)).bold = True

    methods = Counter(f.method for f in findings)
    if methods.get("python"):
        mp = doc.add_paragraph()
        mp.add_run(
            f"{methods.get('python', 0)} of {total} criteria were checked "
            "deterministically (no model call); "
            f"{methods.get('llm', 0)} were checked by the local model."
        ).italic = True


def _add_disclaimer(doc: Document) -> None:
    p = doc.add_paragraph()
    r = p.add_run(
        "This assessment was produced by an automated tool using a local language "
        "model against retrieved excerpts of the report. It is a drafting aid, not a "
        "Qualified Person's opinion. Every finding must be verified by a QP against "
        "the cited pages before reliance."
    )
    r.italic = True
    r.font.size = Pt(9)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
