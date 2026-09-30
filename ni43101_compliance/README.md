# NI 43-101 Compliance Checker (offline)

Checks an NI 43-101 technical report (at any stage of completion) against a
company compliance checklist and produces a Word document listing every
criterion as **Compliant / Partial / Non-Compliant / Not Addressed**, with a
quoted piece of evidence and the page number for each verdict.

Everything runs **locally** — the report and checklist never leave the machine.

## How it solves the "documents are hundreds of pages" problem

It never sends the whole report to the model. Instead:

1. **Ingest** the report into pages (true page numbers from the PDF).
2. **Structure** — detect the 27 standard NI 43-101 Items and tag each page.
3. **Index** — split into chunks, embed them locally, cache the embeddings.
4. **Check** — for each checklist criterion, retrieve only the handful of most
   relevant, page-cited excerpts and ask the model to judge *just that slice*.
5. **Report** — aggregate into a Word doc grouped by NI 43-101 Item.

Each model call sees a few thousand tokens, not the whole document, so it stays
within a small local model's context window, is faster and cheaper, and every
verdict is auditable against a cited page.

## One-time setup

1. **Install Ollama** (Windows): download from https://ollama.com/download and
   run the installer. It runs a local server at `http://localhost:11434`.

2. **Pull the models** (in a terminal):
   ```bash
   ollama pull qwen2.5:7b-instruct
   ollama pull nomic-embed-text
   ```

3. **Install Python dependencies**:
   ```bash
   python -m pip install -r requirements.txt
   ```

Recommended for your GTX 1060 6GB: `qwen2.5:7b-instruct` (Q4) fits in VRAM. If
generation is too slow, switch `chat_model` in `config.yaml` to
`qwen2.5:3b-instruct`.

## Usage

```bash
python run_compliance.py --report path\to\report.pdf --checklist path\to\checklist.docx
```

Options:

- `-o, --output`      output `.docx` path (default: `<report>_compliance.docx`)
- `--config`          config file (default: `config.yaml`)
- `--no-cache`        re-embed the report instead of using cached embeddings
- `--python-only`     run only the deterministic checks below and skip the LLM
                      entirely — no Ollama needed, finishes in under a second,
                      and `--checklist` isn't required
- `--no-structural`   skip the deterministic checks and run the LLM pass only

Re-running with a **different checklist** against the **same report** reuses the
cached embeddings, so only the checking step runs.

## Deterministic (no-LLM) checks

About a third of Form 43-101F1's checkable items don't need a language model —
they're presence checks, counting rules, mandated boilerplate, or a fact that
must match somewhere else in the report. `compliance/structural_checks.py` runs
these with plain regex/structure parsing and tags each finding `(Automated
check)` in the report, distinct from the model-judged ones:

- Table of Contents present (dot-leader detection)
- Item 27: every in-text `(Author, Year)` citation appears in the References list
- Item 26: recommendations don't exceed the two-phase limit
- Item 6(c): historical estimate cautionary language (s.2.4) is present
- Item 23(c): adjacent-property verification disclaimer is present
- Effective date is identical everywhere it's stated (title page, certificates, consents)
- Certificate (e): the union of all QPs' claimed Items covers 1–27 with no gaps
- Item 21: capital/operating costs appear in an actual table (PDF only, via `PyMuPDF.find_tables()`)
- Summary (Item 1) figures agree with the full sections: every quantity with a unit
  (`77 Mt`, `27,000 t/d`, `1.08 g/t`, `US$1.2 billion`, `14 years`) and every stand-alone
  table number in the Summary must have a matching value somewhere in the body, allowing
  for rounding and unit scaling (`27,000 t/d` = `27 kt/d`, `9.9 Mt` = `9.86 Mt`). Unmatched
  figures are listed with their page. Derived numbers can have no verbatim counterpart, so
  treat a flag as "check this". A figure counts as matched if the value appears anywhere in
  the body, so a common value ("5 years") is weak evidence and a changed one can slip through

These run first, unconditionally, before the LLM pass — so every criterion
they cover never costs a model call. Run `python -m unittest tests.test_structural_checks -v`
to see them exercised against synthetic report text with no PDF, no
checklist, and no Ollama required.

## Configuration

See `config.yaml` — model names, chunk size, how many excerpts to retrieve per
criterion, and whether to use the LLM to extract criteria from the checklist.

## Layout

```
run_compliance.py        CLI orchestrator
config.yaml              settings
compliance/
  ingest.py              PDF/DOCX -> pages
  structure.py           NI 43-101 Item detection + criterion->Item mapping
  structural_checks.py   deterministic, no-LLM checks (see above)
  numeric_consistency.py Summary-vs-body figure check (no LLM)
  checklist.py           checklist -> atomic criteria (LLM-assisted)
  index.py               chunk + embed + retrieve (with disk cache)
  checker.py             per-criterion verdict engine (LLM)
  report.py              Word output
  llm.py                 local Ollama client
  models.py              data structures
tests/
  test_structural_checks.py   unit tests for the deterministic checks
  fixtures/                   synthetic sample report + its generated report
```

## Limitations

- Verdicts are a **drafting aid**, not a Qualified Person's opinion. A QP must
  verify every finding against the cited pages.
- Scanned/image-only PDFs need OCR first (not included).
- Item detection is best-effort; it only *boosts* retrieval, so imperfect
  detection degrades gracefully rather than breaking results.
