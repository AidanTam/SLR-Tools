"""Benchmark: run the deterministic checks on real, published NI 43-101 reports.

The PDFs aren't in the repo. Set NI43101_BENCHMARK_DIR to the folder holding
them (defaults to ~/Downloads); each test skips if its file is missing.

Expected results were verified by hand against the source text. Every check
is green except References on Greenstone and Thunder Bay North, where the
report cites a work that has no matching reference-list entry, and the Summary
figures check on Greenstone, whose Summary gives a 346 m crest elevation for
the Southwest Dam that appears nowhere in the body. Those stay red on purpose:
this test fails if a change hides them, as well as if a change reintroduces a
false failure.

Run with:  python -m unittest tests.test_benchmark_reports -v
"""

from __future__ import annotations

import os
import unittest

from compliance import ingest, structure, structural_checks
from compliance.models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
)

BENCH_DIR = os.environ.get(
    "NI43101_BENCHMARK_DIR", os.path.join(os.path.expanduser("~"), "Downloads")
)
GREEN = {STATUS_COMPLIANT, STATUS_NOT_APPLICABLE}

# file name -> citations genuinely missing from that report's reference list
REPORTS = {
    "greenstone": (
        "2026-03-Greenstone-Tech-Report.pdf",
        # No Equinox 2020 or McCormack entry at all; the only undated Toth
        # entry (Precambrian Research 371) has no year, so no 2024 entry.
        {"Equinox 2020", "McCormack 1984", "Tóth 2024"},
    ),
    "thunder_bay": (
        "20251121_slr_cleanair_thndrbayn_43-101_report_rev0-compressed.pdf",
        # No Bornhorst or Good entry (only "Goodgame, 2010"); NorthWinds is
        # listed for 2003 and 2022 only.
        {"Bornhorst 1994", "Good 2015", "NWES 2021"},
    ),
    "ironwood": ("SLR_20250529_Globex_Ironwood_NI43101_Rev0.pdf", set()),
}


class BenchmarkReports(unittest.TestCase):
    def _check(self, key: str) -> None:
        filename, missing_refs = REPORTS[key]
        path = os.path.join(BENCH_DIR, filename)
        if not os.path.exists(path):
            self.skipTest(f"{filename} not found in {BENCH_DIR}")
        pages = ingest.load_report(path)
        page_items = structure.detect_page_items(pages)
        findings = structural_checks.run_structural_checks(pages, page_items, report_path=path)
        for f in findings:
            if f.criterion.id == "PY-REFS" and missing_refs:
                self.assertEqual(f.status, STATUS_NON_COMPLIANT, f.rationale)
                for cite in missing_refs:
                    self.assertIn(cite, f.evidence)
                self.assertEqual(f.evidence.count("(cited p."), len(missing_refs), f.evidence)
            elif f.criterion.id == "PY-SUMMARY-NUMBERS" and key == "greenstone":
                self.assertEqual(f.status, STATUS_PARTIAL, f.rationale)
                self.assertIn("346 m", f.evidence)
                self.assertEqual(f.evidence.count("p."), 1, f.evidence)
            else:
                self.assertIn(f.status, GREEN, f"{f.criterion.id}: {f.rationale}")

    def test_greenstone(self):
        self._check("greenstone")

    def test_thunder_bay(self):
        self._check("thunder_bay")

    def test_ironwood(self):
        self._check("ironwood")


if __name__ == "__main__":
    unittest.main()
