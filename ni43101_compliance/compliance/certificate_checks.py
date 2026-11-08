"""Deterministic check: every QP certificate contains the statements NI 43-101
requires.

Part 8 of NI 43-101 (and the Certificate section of Form 43-101F1) requires each
qualified person's certificate to state, among other things, their
qualifications and registration, that they are a qualified person, whether and
when they visited the property, which sections they are responsible for, that
they are independent of the issuer, any prior involvement with the property,
that they have read the Instrument and the report complies with it, that the
report is not misleading, and the date.

This is boilerplate, so a wording check is reliable: each requirement is
looked for by its characteristic phrase in every certificate. A missing
statement is reported against the person's name. It cannot judge whether a
statement is *true* (is the QP really independent?), only that it is made.
Signatures that are images are invisible to text extraction, so a signature is
not required here.

`check_certificate_item_coverage` (in structural_checks) separately confirms the
certificates between them claim every Item 1-27.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_NEEDS_REVIEW,
    Finding,
    Page,
)

CHECK_ID = "PY-CERT-CONTENT"
CHECK_TEXT = "Each QP certificate contains the statements required by NI 43-101"
ITEM_ID = "certificates"
ITEM_TITLE = "Part 8 – Certificates and Consents of Qualified Persons"

MIN_CERT_CHARS = 800  # shorter than this is a stray match, not a certificate

# (name, required wording, whether its absence is a hard failure)
_ELEMENTS: List[Tuple[str, str, bool]] = [
    ("report title and effective date", r"effective\s+date\s+of\b|with\s+an\s+effective\s+date", True),
    ("qualified person statement", r"\bqualified\s+person\b", True),
    ("site visit (or that none was made)", r"\bvisit|\binspect", True),
    ("sections responsible for", r"responsible\s+for", True),
    ("independence from the issuer", r"independent\s+of\s+the\s+issuer|section\s+1\.5|independen", True),
    ("prior involvement with the property", r"prior\s+involvement|involvement\s+with\s+the\s+(?:property|project)|have\s+(?:not\s+)?had\s+(?:no\s+)?(?:any\s+)?(?:prior\s+)?involvement", True),
    ("read NI 43-101 and compliance of the report", r"read\s+(?:the\s+)?(?:national\s+instrument\s+|ni\s+)?43-?\s?101|prepared\s+in\s+compliance", True),
    ("report is not misleading", r"not\s+misleading", True),
    ("education", r"graduate|\bdegree\b|\bB\.?\s?Sc|\bM\.?\s?Sc|\bPh\.?\s?D|\bB\.?\s?A\.?\s?Sc|\bdiploma|\bB\.?\s?Eng", False),
    ("professional registration", r"registered|member\s+of|licen[sc]ed|\bP\.\s?(?:Eng|Geo|Geol)\b|\bP\.\s?G\.|\bFAusIMM\b|\bCPG\b|\bSME\b|\bMAusIMM\b|\bEur\s?Geol\b", False),
    ("years of experience", r"\d+\s+years|years\s+since|for\s+a\s+total\s+of", False),
]
_COMPILED = [(n, re.compile(rx, re.IGNORECASE), hard) for n, rx, hard in _ELEMENTS]

# "I, Pierre Landry, P.Geo., as an author of this report ... do hereby certify"
_START_RE = re.compile(
    r"\bI,\s+([A-Z][^,\n]{2,60}?),\s.{0,260}?(?:as\s+an?\s+author|do\s+hereby\s+certify|hereby\s+certify)",
    re.DOTALL,
)
_DATE_NEAR_END = re.compile(
    r"(?:dated|date|signed)[^.]{0,80}?(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?[A-Za-z]+,?\s+\d{4}|[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
    re.IGNORECASE,
)


def _certificates(region: List[Page]) -> List[Tuple[str, str, int]]:
    """(name, text, first page) for each certificate in the region."""
    text = ""
    starts: List[Tuple[int, int]] = []  # (offset, page)
    for p in region:
        starts.append((len(text), p.number))
        text += p.text + "\n"

    def page_at(off: int) -> int:
        page = region[0].number
        for o, n in starts:
            if o <= off:
                page = n
        return page

    matches = list(_START_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = text[m.start(): end]
        if len(seg) >= MIN_CERT_CHARS:
            out.append((re.sub(r"\s+", " ", m.group(1)).strip(), seg, page_at(m.start())))
    return out


def check_certificate_content(pages: List[Page]) -> Finding:
    from .structural_checks import _certificate_region, _finding

    region = _certificate_region(pages)
    certs = _certificates(region) if region else []
    if not certs:
        return _finding(
            CHECK_ID, CHECK_TEXT, ITEM_ID, ITEM_TITLE, STATUS_NOT_ADDRESSED,
            "No QP certificates (\"I, <name>, ... do hereby certify\") were found to check.",
        )

    hard_missing: Dict[str, List[str]] = {}
    soft_missing: Dict[str, List[str]] = {}
    for name, seg, _pg in certs:
        flat = re.sub(r"\s+", " ", seg)
        for label, rx, hard in _COMPILED:
            if not rx.search(flat):
                (hard_missing if hard else soft_missing).setdefault(name, []).append(label)
        if not _DATE_NEAR_END.search(flat[-900:]):
            hard_missing.setdefault(name, []).append("signature date")

    names = ", ".join(n for n, _s, _p in certs)
    pages_used = sorted({pg for _n, _s, pg in certs})
    if not hard_missing and not soft_missing:
        return _finding(
            CHECK_ID, CHECK_TEXT, ITEM_ID, ITEM_TITLE, STATUS_COMPLIANT,
            f"All {len(certs)} certificate(s) ({names}) contain each required statement: "
            "effective date, qualified person, site visit, responsibilities, independence, "
            "prior involvement, compliance with NI 43-101, not misleading, qualifications "
            "and signature date.",
            pages=pages_used, confidence=0.8,
        )
    parts = [f"{n}: {', '.join(m)}" for n, m in {**soft_missing, **hard_missing}.items()
             for m in [hard_missing.get(n, []) + [x for x in soft_missing.get(n, [])]]]
    detail = "; ".join(parts)
    return _finding(
        CHECK_ID, CHECK_TEXT, ITEM_ID, ITEM_TITLE,
        STATUS_NON_COMPLIANT if hard_missing else STATUS_NEEDS_REVIEW,
        f"Of {len(certs)} certificate(s) read, the following statements were not found: "
        f"{detail}. (Wording-based; a statement made in unusual words can be missed, so "
        "check the certificate itself.)",
        evidence=detail[:500], pages=pages_used, confidence=0.7,
    )
