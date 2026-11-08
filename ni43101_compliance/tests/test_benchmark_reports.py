"""Benchmark: run the deterministic checks on real, published NI 43-101 reports.

The PDFs aren't in the repo. Set NI43101_BENCHMARK_DIR to the folder holding
them (defaults to ~/Downloads); each test skips if its file is missing.

Expected results were verified by hand against the source text. Every check
is green except the ones listed per report in EXPECTED_NOT_GREEN, and each of
those stays red on purpose: this test fails if a change hides it, as well as if
a change reintroduces a false failure. Highlights, all confirmed in the PDFs:
Greenstone and Thunder Bay North cite works missing from their reference lists;
Greenstone's Summary gives a 346 m dam crest that appears nowhere in the body,
its waste-storage table totals 916 where the rows sum to 892, and one QP
certificate omits the prior-involvement statement; Thunder Bay North's capital
cost table shows a 246.3 sub-total over rows that sum to 239.3, and its G&A
lines sum to 69.0 against a 64.5 total.

PY-ARITH-TOTALS is the one noisy check (a table that continues from the
previous page loses rows, so its Total looks wrong). It may be Needs Review on any
report and is not pinned unless it was confirmed.

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
    STATUS_NEEDS_REVIEW,
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
    "fireweed": (
        "SLR_20241017_Fireweed_Macpass_NI43-101_rev1.pdf",
        # Cited as (Goodfellow 1991) on p.59; the list has 1992, 1993 and 2007.
        {"Goodfellow 1991"},
    ),
}

# check id -> status that is expected and verified (all others must be green).
EXPECTED_NOT_GREEN = {
    "greenstone": {
        "PY-SUMMARY-NUMBERS": STATUS_NEEDS_REVIEW,
        "PY-DATE-REFYEARS": STATUS_NEEDS_REVIEW,      # "CEDC. 2026." website entry
        "PY-ARITH-TOTALS": STATUS_NEEDS_REVIEW,       # storage capacity 916 vs 892
        "PY-CERT-CONTENT": STATUS_NON_COMPLIANT,  # no prior-involvement statement
    },
    "thunder_bay": {
        "PY-ARITH-TOTALS": STATUS_NEEDS_REVIEW,       # 246.3 vs 239.3, G&A 64.5 vs 69.0
    },
    "ironwood": {},
    "fireweed": {
        # p.103 says "see Section 11.3.4 below"; the headings stop at 11.3.3.
        "PY-XREF-SECTIONS": STATUS_NEEDS_REVIEW,
        # Inferred silver 4.05 + 5.875 + 0.80 = 10.725 against a total of 10.00.
        "PY-ARITH-TOTALS": STATUS_NEEDS_REVIEW,
    },
}
# Checks that may be Needs Review on a given report without being pinned:
# the totals check is noisy everywhere; Fireweed's Summary gives germanium and
# gallium figures that are not yet hand-checked.
NOISY = {"*": {"PY-ARITH-TOTALS"}, "fireweed": {"PY-SUMMARY-NUMBERS"}}


class BenchmarkReports(unittest.TestCase):
    def _check(self, key: str) -> None:
        filename, missing_refs = REPORTS[key]
        path = os.path.join(BENCH_DIR, filename)
        if not os.path.exists(path):
            self.skipTest(f"{filename} not found in {BENCH_DIR}")
        pages = ingest.load_report(path)
        page_items = structure.detect_page_items(pages)
        findings = structural_checks.run_structural_checks(pages, page_items, report_path=path)
        expected = EXPECTED_NOT_GREEN[key]
        seen = {f.criterion.id: f for f in findings}
        for f in findings:
            cid = f.criterion.id
            if cid == "PY-REFS" and missing_refs:
                self.assertEqual(f.status, STATUS_NON_COMPLIANT, f.rationale)
                for cite in missing_refs:
                    self.assertIn(cite, f.evidence)
                self.assertEqual(f.evidence.count("(cited p."), len(missing_refs), f.evidence)
            elif cid == "PY-SUMMARY-NUMBERS" and key == "greenstone":
                self.assertEqual(f.status, STATUS_NEEDS_REVIEW, f.rationale)
                self.assertIn("346 m", f.evidence)
                self.assertEqual(f.evidence.count("p."), 1, f.evidence)
            elif cid in expected:
                self.assertEqual(f.status, expected[cid], f"{cid}: {f.rationale}")
            elif cid in NOISY["*"] | NOISY.get(key, set()):
                self.assertIn(f.status, GREEN | {STATUS_NEEDS_REVIEW}, f"{cid}: {f.rationale}")
            else:
                self.assertIn(f.status, GREEN, f"{cid}: {f.rationale}")
        for cid in expected:
            self.assertIn(cid, seen, f"{cid} did not run")

    def test_greenstone(self):
        self._check("greenstone")

    def test_thunder_bay(self):
        self._check("thunder_bay")

    def test_ironwood(self):
        self._check("ironwood")

    def test_fireweed(self):
        # Regression: its certificates quote an earlier report's 2014 dates
        # (not this report's effective/signature dates), its QP table says
        # "all sections exclusive of 13 and 14.6", and the 2018 estimate's zinc
        # price and exchange rate are quoted for comparison. None of those is a
        # finding, so only the two pinned above should be red.
        self._check("fireweed")


if __name__ == "__main__":
    unittest.main()
