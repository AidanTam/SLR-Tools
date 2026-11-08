"""Unit tests for compliance.assumption_consistency — no Ollama, no PDF needed.

Run with:  python -m unittest tests.test_assumption_consistency -v
"""

from __future__ import annotations

import unittest

from compliance.assumption_consistency import check_assumption_consistency
from compliance.models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NEEDS_REVIEW,
    Page,
)


def run(*texts: str):
    pages = [Page(number=i + 1, text=t) for i, t in enumerate(texts)]
    return {f.criterion.id: f for f in check_assumption_consistency(pages, list_pages=set())}


class TestMetalPrice(unittest.TestCase):
    GOLD = "PY-ASSUMP-GOLD-PRICE-US-OZ"

    def test_same_price_everywhere_is_compliant(self):
        f = run(
            "The economic analysis uses a gold price of US$2,200/oz.",
            "Cash flow is based on a long-term gold price of US$2,200/oz.",
        )[self.GOLD]
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_two_prices_for_the_economic_analysis_is_non_compliant(self):
        f = run(
            "The economic analysis uses a gold price of US$2,200/oz.",
            "The NPV cash flow assumes a gold price of US$2,000/oz.",
        )[self.GOLD]
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("2,200", f.rationale)
        self.assertIn("2,000", f.rationale)

    def test_unlabelled_conflict_is_partial(self):
        f = run(
            "Metal prices: gold price of US$2,200/oz.",
            "A gold price of US$2,000/oz was used.",
        )[self.GOLD]
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)

    def test_resource_vs_reserve_price_is_a_note_not_a_failure(self):
        f = run(
            "Mineral Resources are constrained by a pit shell at a gold price of US$2,500/oz.",
            "Mineral Reserves are based on a gold price of US$2,000/oz.",
        )[self.GOLD]
        self.assertEqual(f.status, STATUS_COMPLIANT)
        self.assertIn("different use", f.rationale)

    def test_sensitivity_and_spot_prices_are_ignored(self):
        f = run(
            "The base case uses a gold price of US$2,200/oz.",
            "In the sensitivity analysis a gold price of US$2,600/oz was tested.",
            "The spot gold price of US$3,100/oz on the effective date was not used.",
            "The cash flow uses a gold price of US$2,200/oz.",
        )[self.GOLD]
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_price_list_in_one_sentence_is_ignored(self):
        findings = run(
            "Gold price of US$1,800/oz, US$2,000/oz, US$2,200/oz and US$2,400/oz were run.",
            "Economic analysis gold price of US$2,200/oz.",
        )
        # Only one real statement remains, below the minimum to compare.
        self.assertNotIn(self.GOLD, findings)

    def test_costs_per_ounce_are_not_prices(self):
        findings = run(
            "The gold price is US$2,200/oz. AISC is US$1,150/oz gold.",
            "Cash cost of US$900/oz gold. Economic analysis gold price US$2,200/oz.",
        )
        self.assertEqual(findings[self.GOLD].status, STATUS_COMPLIANT)

    def test_different_metals_are_separate(self):
        findings = run(
            "Economic analysis: gold price of US$2,200/oz and silver price of US$26/oz.",
            "Cash flow: gold price of US$2,200/oz and silver price of US$30/oz.",
        )
        self.assertEqual(findings[self.GOLD].status, STATUS_COMPLIANT)
        self.assertEqual(findings["PY-ASSUMP-SILVER-PRICE-US-OZ"].status, STATUS_NON_COMPLIANT)

    def test_copper_price_per_pound(self):
        findings = run(
            "The financial model assumes a copper price of US$4.00/lb.",
            "Cash flow uses a copper price of US$3.75/lb.",
        )
        self.assertEqual(findings["PY-ASSUMP-COPPER-PRICE-US-LB"].status, STATUS_NON_COMPLIANT)

    def test_bare_dollar_joins_the_explicit_currency(self):
        findings = run(
            "The economic analysis uses a gold price of $2,200/oz.",
            "Cash flow uses a gold price of US$2,000/oz.",
        )
        self.assertEqual(list(findings), [self.GOLD])
        self.assertEqual(findings[self.GOLD].status, STATUS_NON_COMPLIANT)

    def test_prices_quoted_for_an_earlier_study_are_ignored(self):
        findings = run(
            "NI 43-101 Technical Report. October 17, 2024.",
            "The economic analysis uses a gold price of US$2,200/oz.",
            "In 2018, metal price assumptions were a gold price of US$1,300/oz.",
            "The cash flow uses a gold price of US$2,200/oz.",
        )
        self.assertEqual(findings[self.GOLD].status, STATUS_COMPLIANT)

    def test_history_and_adjacent_property_pages_are_skipped(self):
        pages_ = [
            Page(number=1, text="Report 2024."),
            Page(number=2, text="Economic analysis gold price of US$2,200/oz."),
            Page(number=3, text="The historical estimate used a gold price of US$1,000/oz."),
            Page(number=4, text="Cash flow gold price of US$2,200/oz."),
        ]
        items = {3: ("item_6", "History")}
        f = {x.criterion.id: x for x in check_assumption_consistency(pages_, list_pages=set(), page_items=items)}
        self.assertEqual(f[self.GOLD].status, STATUS_COMPLIANT)

    def test_single_statement_makes_no_finding(self):
        self.assertEqual(run("Economic analysis gold price of US$2,200/oz."), {})


class TestExchangeRate(unittest.TestCase):
    FX = "PY-ASSUMP-EXCHANGE-RATE"

    def test_reciprocal_rates_agree(self):
        f = run(
            "An exchange rate of US$0.75 = C$1.00 was assumed.",
            "The exchange rate was C$1.33 per US$1.00.",
        )[self.FX]
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_different_rates_are_flagged(self):
        f = run(
            "An exchange rate of 0.75 US$/C$ was assumed.",
            "The foreign exchange rate used was 0.72 US$/C$.",
        )[self.FX]
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)


class TestDiscountRate(unittest.TestCase):
    DR = "PY-ASSUMP-DISCOUNT-RATE"

    def test_conflicting_discount_rates_are_flagged(self):
        f = run(
            "The NPV was calculated at a 5% discount rate.",
            "Results use a discount rate of 8%.",
        )[self.DR]
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)

    def test_several_rates_in_one_passage_are_ignored(self):
        findings = run(
            "NPV is shown at a 5% discount rate, a 8% discount rate and a 10% discount rate.",
            "The base case uses a 5% discount rate.",
        )
        self.assertNotIn(self.DR, findings)


class TestMineLife(unittest.TestCase):
    ML = "PY-ASSUMP-MINE-LIFE"

    def test_conflicting_mine_life_is_flagged(self):
        f = run(
            "The project has a 14 year mine life.",
            "Life of mine of 12 years is supported by the reserve.",
        )[self.ML]
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)

    def test_matching_mine_life_is_compliant(self):
        f = run(
            "The project has a 14 year mine life.",
            "The LOM plan covers a mine life of 14 years.",
        )[self.ML]
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_open_pit_vs_underground_life_is_not_compared(self):
        findings = run(
            "The open pit mine life is 6 years.",
            "The underground mine life is 9 years.",
        )
        self.assertNotIn(self.ML, findings)


if __name__ == "__main__":
    unittest.main()
