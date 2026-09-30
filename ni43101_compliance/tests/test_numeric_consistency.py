"""Unit tests for compliance.numeric_consistency — no Ollama, no PDF needed.

Run with:  python -m unittest tests.test_numeric_consistency -v
"""

from __future__ import annotations

import unittest

from compliance.models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_PARTIAL,
    Page,
)
from compliance.numeric_consistency import check_summary_numbers

# Page 1 is the Summary; everything after it is the body.
SUMMARY_ITEMS = {1: ("item_1", "Summary")}

SUMMARY = (
    "1.1 Executive Summary\n"
    "The LOM plan removes 77 Mt of material at 27,000 t/d over a 14 year mine life.\n"
    "Average head grade is 1.08 g/t Au and the initial capital cost is US$1.2 billion.\n"
    "Plant throughput reaches 9.86 Mt/a.\n"
)


def pages(*texts: str) -> list:
    return [Page(number=i + 1, text=t) for i, t in enumerate(texts)]


def run(summary: str, *body: str):
    return check_summary_numbers(pages(summary, *body), SUMMARY_ITEMS)


class TestSummaryNumbers(unittest.TestCase):
    def test_all_figures_repeated_in_body(self):
        f = run(
            SUMMARY,
            "The plan moves 77 Mt. The plant runs at 27,000 t/d for a 14 year life.",
            "Head grade 1.08 g/t Au. Capital cost of US$1.2 billion. Plant rate 9.86 Mt/a.",
        )
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_unit_scaling_and_rounding_are_accepted(self):
        f = run(
            SUMMARY,
            "Material movement is capped at 77 Mt. The mill nameplate is 27 kt/d.",
            "The mine life is a 14-year period. Grade is 1.08 g/t Au. "
            "Capital of $1,200 million. Throughput is 9.9 Mt/a.",
        )
        self.assertEqual(f.status, STATUS_COMPLIANT, f.evidence)

    def test_line_wrapped_units_and_scale_words(self):
        f = run(
            SUMMARY,
            "Material movement is capped at 77 Mt. Ore is processed at 27,000 tonnes\n"
            "per day. Mine life is 14 years.",
            "Grade is 1.08 g/t Au. Capital cost is US$1.2\nbillion. Rate 9.86 Mt per year.",
        )
        self.assertEqual(f.status, STATUS_COMPLIANT, f.evidence)

    def test_figure_missing_from_body_is_flagged(self):
        f = run(
            SUMMARY,
            "The plan moves 77 Mt. The plant runs at 27,000 t/d for a 14 year life.",
            "Head grade 3.10 g/t Au. Capital cost of US$1.2 billion. Plant rate 9.86 Mt/a.",
        )
        self.assertIn(f.status, (STATUS_PARTIAL, STATUS_NON_COMPLIANT))
        self.assertIn("1.08 g/t", f.evidence)

    def test_grade_is_not_matched_by_a_different_unit(self):
        # 1.08 as a percentage in the body is not the 1.08 g/t stated in the Summary.
        f = run(
            SUMMARY,
            "The plan moves 77 Mt. The plant runs at 27,000 t/d for a 14 year life.",
            "Recovery is 1.08 %. Capital cost of US$1.2 billion. Plant rate 9.86 Mt/a.",
        )
        self.assertIn("1.08 g/t", f.evidence)

    def test_many_missing_figures_is_non_compliant(self):
        f = run(SUMMARY, "Nothing numeric here.", "Nor here.")
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_spelled_out_duration_is_compared(self):
        summary = SUMMARY + "Stockpiles are processed for an additional five years.\n"
        f = run(
            summary,
            "The plan moves 77 Mt. The plant runs at 27,000 t/d for a 14 year life.",
            "Head grade 1.08 g/t Au. Capital cost of US$1.2 billion. Plant rate 9.86 Mt/a. "
            "Stockpile reclaim takes 4.25 years.",
        )
        self.assertIn("five years", f.evidence)

    def test_table_cells_compared_across_a_change_of_scale(self):
        summary = SUMMARY + "Table 1-1\nMeasured\nTonnes (kt)\n1,234\n2.45\n5,678\n"
        body = (
            "The plan moves 77 Mt. The plant runs at 27,000 t/d for a 14 year life. "
            "Grade 1.08 g/t Au. Capital cost of US$1.2 billion. Rate 9.86 Mt/a.",
            "Table 14-1\nMeasured\nTonnes (Mt)\n1.234\n2.45\n5.678\n",
        )
        f = run(summary, *body)
        self.assertEqual(f.status, STATUS_COMPLIANT, f.evidence)

    def test_table_cell_that_disagrees_is_flagged(self):
        summary = SUMMARY + "Table 1-1\nMeasured\nTonnes (kt)\n1,234\n2.45\n5,678\n"
        body = (
            "The plan moves 77 Mt. The plant runs at 27,000 t/d for a 14 year life. "
            "Grade 1.08 g/t Au. Capital cost of US$1.2 billion. Rate 9.86 Mt/a.",
            "Table 14-1\nMeasured\nTonnes (Mt)\n1.234\n2.45\n5.876\n",
        )
        f = run(summary, *body)
        self.assertIn(f.status, (STATUS_PARTIAL, STATUS_NON_COMPLIANT))
        self.assertIn("5,678", f.evidence)

    def test_years_and_page_labels_in_tables_are_ignored(self):
        summary = SUMMARY + "Table 1-2\n2024\n2025\n1-20\n"
        f = run(
            summary,
            "The plan moves 77 Mt. The plant runs at 27,000 t/d for a 14 year life. "
            "Grade 1.08 g/t Au. Capital cost of US$1.2 billion. Rate 9.86 Mt/a.",
        )
        self.assertEqual(f.status, STATUS_COMPLIANT, f.evidence)

    def test_too_few_figures_is_not_addressed(self):
        f = run("1.1 Summary\nThe project is a gold mine in Ontario, 77 Mt.\n", "Body text.")
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)

    def test_no_summary_detected(self):
        f = check_summary_numbers(pages("Body only, 77 Mt."), {})
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)

    def test_figures_repeated_within_the_summary_count_once(self):
        summary = "Summary\n" + "The plan moves 77 Mt. " * 10
        f = run(summary, "Body.")
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)  # one distinct figure, not ten


if __name__ == "__main__":
    unittest.main()
