#!/usr/bin/env python
"""NI 43-101 compliance checker — command-line entry point.

Usage:
    python run_compliance.py --report REPORT.pdf --checklist CHECKLIST.docx
    python run_compliance.py -r REPORT.pdf -c CHECKLIST.docx -o result.docx

Everything runs locally against an Ollama server. No data leaves the machine.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import yaml
from tqdm import tqdm

from compliance.checker import check_criterion
from compliance.checklist import extract_criteria, load_checklist_text
from compliance.index import build_index, report_cache_key
from compliance.ingest import load_report
from compliance.llm import OllamaClient
from compliance.report import write_report
from compliance.structural_checks import run_structural_checks
from compliance.structure import detect_page_items


def parse_args():
    ap = argparse.ArgumentParser(description="Offline NI 43-101 compliance checker.")
    ap.add_argument("-r", "--report", required=True, help="Report file (PDF or DOCX).")
    ap.add_argument(
        "-c", "--checklist", default=None,
        help="Checklist file (PDF or DOCX). Required unless --python-only.",
    )
    ap.add_argument("-o", "--output", default=None, help="Output .docx path.")
    ap.add_argument("--config", default="config.yaml", help="Config file path.")
    ap.add_argument("--no-cache", action="store_true", help="Ignore cached report embeddings.")
    ap.add_argument(
        "--python-only", action="store_true",
        help="Run only the deterministic, no-LLM structural checks (no Ollama needed, "
        "seconds instead of minutes). Skips the checklist entirely.",
    )
    ap.add_argument(
        "--no-structural", action="store_true",
        help="Skip the deterministic structural checks and run the LLM pass only.",
    )
    return ap.parse_args()


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        print(f"Config not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def preflight(llm: OllamaClient, cfg: dict) -> None:
    reachable, models = llm.health()
    if not reachable:
        print(
            f"ERROR: Ollama is not reachable at {llm.host}.\n"
            f"  Start it (launch the Ollama app, or run `ollama serve`) and try again.",
            file=sys.stderr,
        )
        sys.exit(1)

    def installed(name: str) -> bool:
        base = name.split(":")[0]
        return any(m == name or m.split(":")[0] == base for m in models)

    missing = [m for m in (llm.chat_model, llm.embed_model) if not installed(m)]
    if missing:
        print("ERROR: required Ollama models are not installed:", file=sys.stderr)
        for m in missing:
            print(f"    ollama pull {m}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    o = cfg["ollama"]
    r = cfg["retrieval"]

    if not args.python_only and not args.checklist:
        print("ERROR: --checklist is required unless --python-only is set.", file=sys.stderr)
        sys.exit(1)

    paths = [args.report] + ([args.checklist] if args.checklist else [])
    for path in paths:
        if not os.path.exists(path):
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)

    output = args.output or (
        os.path.splitext(os.path.basename(args.report))[0] + "_compliance.docx"
    )

    t0 = time.time()

    # 1. Ingest + structure the report.
    print(f"Reading report: {args.report}")
    pages = load_report(args.report)
    page_items = detect_page_items(pages)
    detected = len({v[0] for v in page_items.values()})
    print(f"  {len(pages)} pages; detected {detected}/27 standard Items.")

    findings = []

    # 2. Deterministic structural checks — no LLM, runs in under a second.
    if not args.no_structural:
        print("Running structural checks (no LLM)...")
        structural = run_structural_checks(pages, page_items, report_path=args.report)
        findings.extend(structural)
        print(f"  {len(structural)} structural checks done.")

    if args.python_only:
        write_report(
            findings,
            report_name=os.path.basename(args.report),
            checklist_name="(python-only structural checks; no checklist used)",
            model_name="none (deterministic checks only)",
            out_path=output,
        )
        _print_summary(findings, time.time() - t0, output)
        return

    llm = OllamaClient(
        host=o["host"],
        chat_model=o["chat_model"],
        embed_model=o["embed_model"],
        temperature=o.get("temperature", 0),
        timeout=o.get("request_timeout", 600),
    )
    preflight(llm, cfg)

    # 3. Build (or load cached) retrieval index.
    cache_dir = cfg.get("cache", {}).get("dir", "output/.cache")
    use_cache = cfg.get("cache", {}).get("enabled", True) and not args.no_cache
    cache_key = (
        report_cache_key(args.report, o["embed_model"], r["chunk_size"], r["chunk_overlap"])
        if use_cache
        else None
    )
    index = build_index(
        pages,
        page_items,
        llm,
        chunk_size=r["chunk_size"],
        overlap=r["chunk_overlap"],
        cache_key=cache_key,
        cache_dir=cache_dir if use_cache else None,
    )
    print(f"  Indexed {len(index.chunks)} chunks.")

    # 4. Parse the checklist into atomic criteria.
    print(f"Reading checklist: {args.checklist}")
    raw = load_checklist_text(args.checklist)
    criteria = extract_criteria(
        raw, llm, use_llm=cfg.get("checklist", {}).get("use_llm_extraction", True)
    )
    if not criteria:
        print("ERROR: no criteria could be extracted from the checklist.", file=sys.stderr)
        sys.exit(1)
    print(f"  Extracted {len(criteria)} criteria.")

    # 5. Check every criterion against the report.
    for crit in tqdm(criteria, desc="Checking criteria", unit="crit"):
        findings.append(
            check_criterion(
                crit,
                index,
                llm,
                top_k=r["top_k"],
                item_boost=r["item_boost"],
                max_context_chars=r["max_context_chars"],
            )
        )

    # 6. Write the Word report.
    write_report(
        findings,
        report_name=os.path.basename(args.report),
        checklist_name=os.path.basename(args.checklist),
        model_name=o["chat_model"],
        out_path=output,
    )

    _print_summary(findings, time.time() - t0, output)


def _print_summary(findings, elapsed: float, output: str) -> None:
    from collections import Counter

    counts = Counter(f.status for f in findings)
    methods = Counter(f.method for f in findings)
    print("\nDone in %.0fs. Summary:" % elapsed)
    for status, n in counts.most_common():
        print(f"  {status:>14}: {n}")
    print(
        f"\n  ({methods.get('python', 0)} checked deterministically, "
        f"{methods.get('llm', 0)} checked by the model)"
    )
    print(f"\nReport written to: {output}")


if __name__ == "__main__":
    main()
