"""Unit tests for compliance.structural_checks — no Ollama, no PDF needed.

Run with:  python -m unittest tests.test_structural_checks -v
"""

from __future__ import annotations

import unittest

from compliance.models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    Page,
)
from compliance.structural_checks import (
    _extract_item_numbers,
    check_adjacent_property_disclaimer,
    check_certificate_item_coverage,
    check_cost_table_present,
    check_effective_date_consistency,
    check_historical_estimate_disclaimer,
    check_recommendation_phases,
    check_references_list,
    check_table_of_contents,
    run_structural_checks,
)
from compliance.structure import detect_page_items

ITEM_26 = {1: ("item_26", "Recommendations")}


def pages(*texts: str) -> list:
    return [Page(number=i + 1, text=t) for i, t in enumerate(texts)]


class TestTableOfContents(unittest.TestCase):
    def test_missing(self):
        f = check_table_of_contents(pages("Cover page", "Some intro text"), {})
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)

    def test_present_with_leaders(self):
        toc_page = (
            "TABLE OF CONTENTS\n"
            "1.0 Summary....................1\n"
            "2.0 Introduction..............5\n"
            "3.0 Property Description......9\n"
        )
        f = check_table_of_contents(pages("Cover", toc_page), {})
        self.assertEqual(f.status, STATUS_COMPLIANT)
        self.assertEqual(f.pages, [2])

    def test_heading_without_leaders_is_partial(self):
        f = check_table_of_contents(pages("Cover", "TABLE OF CONTENTS\nSee attached."), {})
        self.assertEqual(f.status, STATUS_PARTIAL)


class TestReferencesList(unittest.TestCase):
    def test_no_heading(self):
        f = check_references_list(pages("Some report text with no references section."))
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)

    def test_all_citations_covered(self):
        body = "The deposit model follows (Smith, 2019) and (Jones and Lee, 2020)."
        refs = "References\nSmith, J. 2019. Deposit Models. Journal.\nJones, A. and Lee, B. 2020. Structural Geology.\n"
        f = check_references_list(pages(body, refs))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_missing_citation_flagged(self):
        body = "The deposit model follows (Smith, 2019) and (Nguyen, 2021)."
        refs = "References\nSmith, J. 2019. Deposit Models. Journal.\n"
        f = check_references_list(pages(body, refs))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("nguyen", f.evidence.lower())


class TestRecommendationPhases(unittest.TestCase):
    def test_no_phases_found(self):
        f = check_recommendation_phases(pages("Recommendations: continue work."), {})
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)

    def test_two_phases_compliant(self):
        text = "Phase 1 drilling is recommended, followed by Phase 2 metallurgical testing."
        f = check_recommendation_phases(pages(text), ITEM_26)
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_three_phases_noncompliant(self):
        text = "Phase 1, then Phase 2, then Phase 3 are all recommended."
        f = check_recommendation_phases(pages(text), ITEM_26)
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_no_phase_labels_in_recommendations_is_within_limit(self):
        f = check_recommendation_phases(pages("Continue infill drilling at a cost of $2M."), ITEM_26)
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_phases_outside_recommendations_are_ignored(self):
        # Greenstone regression: with Item 26 undetected, the old fallback
        # scanned all 394 pages and counted mine-construction "phases".
        body = pages("Phase 1, Phase 2, Phase 3 and Phase 4 of pit development.", "Drill more.")
        f = check_recommendation_phases(body, {2: ("item_26", "Recommendations")})
        self.assertEqual(f.status, STATUS_COMPLIANT)


class TestCautionaryLanguage(unittest.TestCase):
    def test_historical_estimate_with_caution(self):
        text = (
            "A historical mineral resource estimate was reported in 1998. The "
            "qualified person has not done sufficient work to classify the "
            "historical estimate as current mineral resources or mineral reserves."
        )
        f = check_historical_estimate_disclaimer(pages(text))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_historical_estimate_without_caution(self):
        text = "A historical mineral resource estimate of 2.1 Mt was reported in 1998."
        f = check_historical_estimate_disclaimer(pages(text))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_no_trigger_not_applicable(self):
        f = check_historical_estimate_disclaimer(pages("No historical work is discussed."))
        self.assertEqual(f.status, STATUS_NOT_APPLICABLE)

    def test_adjacent_property_with_caution(self):
        text = (
            "Data from an adjacent property was reviewed. The qualified person has "
            "been unable to verify the information and it is not necessarily "
            "indicative of the mineralization on the property."
        )
        f = check_adjacent_property_disclaimer(pages(text))
        self.assertEqual(f.status, STATUS_COMPLIANT)


class TestEffectiveDateConsistency(unittest.TestCase):
    def test_consistent_dates(self):
        p1 = "This report has an effective date of March 3, 2025."
        p2 = "Certificate: effective date of March 3, 2025."
        f = check_effective_date_consistency(pages(p1, p2))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_inconsistent_dates(self):
        p1 = "This report has an effective date of March 3, 2025."
        p2 = "Certificate: effective date of April 10, 2025."
        f = check_effective_date_consistency(pages(p1, p2))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_no_dates_found(self):
        f = check_effective_date_consistency(pages("No date statements here."))
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)


class TestCertificateCoverage(unittest.TestCase):
    def test_full_coverage(self):
        cert1 = "CERTIFICATE OF QUALIFIED PERSON\nI am responsible for Items 1 to 14 of this report."
        cert2 = "CERTIFICATE OF QUALIFIED PERSON\nI am responsible for Items 15 to 27 of this report."
        f = check_certificate_item_coverage(pages(cert1, cert2))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_gap_flagged(self):
        cert1 = "CERTIFICATE OF QUALIFIED PERSON\nI am responsible for Items 1 to 10 of this report."
        f = check_certificate_item_coverage(pages(cert1))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("11", f.evidence)

    def test_no_certificates(self):
        f = check_certificate_item_coverage(pages("No certificate here."))
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)


class TestCostTable(unittest.TestCase):
    def test_no_item_21_detected(self):
        f = check_cost_table_present(pages("Nothing relevant."), {}, None)
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)

    def test_non_pdf_report(self):
        page_items = {1: ("item_21", "Capital and Operating Costs")}
        f = check_cost_table_present(pages("Capital and operating costs summary."), page_items, "report.docx")
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)
        self.assertIn("PDF", f.rationale)


class TestOrchestrator(unittest.TestCase):
    def test_all_checks_run_and_tagged_python(self):
        findings = run_structural_checks(pages("Just some report text."), {}, report_path=None)
        self.assertEqual(len(findings), 9)
        self.assertTrue(all(f.method == "python" for f in findings))


# --------------------------------------------------------------------------
# Regressions from real published reports (Greenstone, Thunder Bay North,
# Ironwood). Each reproduces, in synthetic text, a layout that broke a check.
# --------------------------------------------------------------------------

TOC_PAGE = (
    "Table of Contents\n"
    "1.0 Summary ..................................... 1-1\n"
    "21.0 Capital and Operating Costs ................ 21-1\n"
    "23.0 Adjacent Properties ........................ 23-1\n"
)


class TestRealLayoutRegressions(unittest.TestCase):
    def test_heading_split_across_two_lines_is_detected(self):
        body = pages("Cover", "21.0 \nCapital and Operating Costs \nThis section is not applicable.")
        self.assertEqual(detect_page_items(body).get(2), ("item_21", "Capital and Operating Costs"))

    def test_section_page_dot_leaders_count_as_toc(self):
        f = check_table_of_contents(pages("Cover", TOC_PAGE), {})
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_toc_entry_and_heading_do_not_trigger_disclaimer(self):
        body = pages(TOC_PAGE, "23.0 \nAdjacent Properties \nThis section is not applicable.")
        self.assertEqual(check_adjacent_property_disclaimer(body).status, STATUS_NOT_APPLICABLE)

    def test_figure_caption_does_not_trigger_disclaimer(self):
        body = pages("Figure 23-1: Adjacent Properties to Greenstone Gold Mine Claims")
        self.assertEqual(check_adjacent_property_disclaimer(body).status, STATUS_NOT_APPLICABLE)

    def test_caution_far_down_the_same_paragraph_counts(self):
        filler = "It was based on drilling completed since 2007. " * 25
        text = (
            "Three historical Mineral Resource estimates were commissioned. " + filler +
            "The QPs have not done sufficient work to classify the historical estimates "
            "as current Mineral Resources."
        )
        self.assertEqual(check_historical_estimate_disclaimer(pages(text)).status, STATUS_COMPLIANT)

    def test_negated_mention_is_not_a_disclosure(self):
        body = pages("There are no historical mineral resource estimates for the Property.")
        self.assertEqual(check_historical_estimate_disclaimer(body).status, STATUS_NOT_APPLICABLE)

    def test_unrelated_no_earlier_in_sentence_does_not_suppress(self):
        body = pages("Although no drilling was done, a historical mineral resource estimate of 2 Mt exists.")
        self.assertEqual(check_historical_estimate_disclaimer(body).status, STATUS_NON_COMPLIANT)


class TestReferenceRegressions(unittest.TestCase):
    def _refs(self, body, entries):
        return check_references_list(pages(body, "27.0 \nReferences\n" + entries))

    def test_wrapped_journal_page_line_does_not_end_the_list(self):
        entries = (
            "Hollings, P. 2007. Geochemistry of the Nipigon Embayment. Canadian Journal,\n"
            "44: p1111-1110.\n"
            "MacDonald, J. 2018. First Technical Report on the Tamarack South Project.\n"
        )
        f = self._refs("As shown by (MacDonald 2018).", entries)
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_et_al_without_comma(self):
        entries = "Bleeker, W., Smith, J., Hamilton, M., et al. 2020. The Midcontinent Rift.\n"
        f = self._refs("Mineralized intrusions (Bleeker et al. 2020).", entries)
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_surname_must_be_a_whole_word_with_the_year(self):
        # Thunder Bay: "Good et al. 2015" is cited but only "Goodgame, 2010" is listed.
        entries = "Goodgame, V.R., 2010. Initial Lithogeochemistry Study.\n"
        f = self._refs("Quartz syenite (Good et al. 2015).", entries)
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("Good 2015", f.evidence)

    def test_acronym_resolved_through_the_reports_own_definition(self):
        body = (
            "Permits from the Ministry of Natural Resources and Forestry (MNRF) apply. "
            "Wetlands were evaluated (MNRF 2014)."
        )
        entries = "Ministry of Natural Resources. 2014. Ontario Wetland Evaluation System.\n"
        self.assertEqual(self._refs(body, entries).status, STATUS_COMPLIANT)

    def test_acronym_year_must_still_match(self):
        body = "Surveys by NorthWinds Environmental Services (NWES 2021; NWES 2022)."
        entries = (
            "NorthWinds Environmental Services. 2022. Comprehensive Fisheries Baseline Report.\n"
            "NorthWinds Environmental Services. 2003. Terrestrial Environment Baseline Report.\n"
        )
        f = self._refs(body, entries)
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("NWES 2021", f.evidence)
        self.assertNotIn("NWES 2022", f.evidence)

    def test_accents_are_folded(self):
        entries = "Toth, Z., Lafrance, B. 2014a. Stratigraphic setting.\n"
        f = self._refs("Recent studies (Tóth et al. 2014a).", entries)
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_non_author_parenthetical_is_ignored(self):
        entries = "Smith, J. 2019. Deposit Models.\n"
        f = self._refs("Operating (Since 2019) under (Smith 2019).", entries)
        self.assertEqual(f.status, STATUS_COMPLIANT)


class TestDateRegressions(unittest.TestCase):
    def test_body_dates_of_other_reports_are_ignored(self):
        title = "NI 43-101 Technical Report\nEffective Date: December 31, 2025"
        body = (
            "This Technical Report supersedes the previous technical report with an "
            "effective date of June 30, 2024. The resource estimate has an effective "
            "date of May 1, 2023."
        )
        cert = (
            "CERTIFICATE OF QUALIFIED PERSON\nI, A. QP, as an author of this report with an "
            "effective date of December 31st, 2025, certify that:"
        )
        f = check_effective_date_consistency(pages(title, "Cover 2", TOC_PAGE, body, cert))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_certificate_disagreeing_with_title_page_is_flagged(self):
        title = "Effective Date: October 9, 2025"
        cert = "CERTIFICATE OF QUALIFIED PERSON\nreport with an effective date of October 19, 2025"
        f = check_effective_date_consistency(pages(title, TOC_PAGE, cert))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)


class TestCertificateRegressions(unittest.TestCase):
    def test_decimal_subsections_collapse_to_their_item(self):
        self.assertEqual(_extract_item_numbers("19.1.1, 26.2, 1.3.1 to 1.3.7"), {1, 19, 26})

    def test_statement_with_dotted_section_numbers_is_read_to_the_end(self):
        cert = (
            "CERTIFICATE OF QUALIFIED PERSON\n"
            "6. I am responsible for the overall preparation of the Technical Report, as well "
            "as Sections 1.1.1.1, 1.3.1 to 1.3.7, 2 to 27, and related disclosure in Section 27.\n"
            "7. I am independent of the Issuer applying the test set out in Section 1.5 of NI 43-101.\n"
        )
        self.assertEqual(check_certificate_item_coverage(pages(cert)).status, STATUS_COMPLIANT)

    def test_section_reference_outside_a_responsibility_statement_claims_nothing(self):
        cert = (
            "CERTIFICATE OF QUALIFIED PERSON\n"
            "6. I am responsible for Sections 2 to 27 of the Technical Report.\n"
            "7. I am independent applying the test set out in Section 1.5 of NI 43-101.\n"
        )
        f = check_certificate_item_coverage(pages(cert))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("[1]", f.evidence)

    def test_single_qp_overall_preparation_claims_every_item(self):
        cert = (
            "CERTIFICATE OF QUALIFIED PERSON\n"
            "6. I am responsible for overall preparation of the Technical Report.\n"
        )
        self.assertEqual(check_certificate_item_coverage(pages(cert)).status, STATUS_COMPLIANT)

    def test_overall_preparation_adds_nothing_when_several_qps_sign(self):
        cert = (
            "CERTIFICATE OF QUALIFIED PERSON\n"
            "6. I am responsible for the overall preparation of the Technical Report.\n"
            "6. I am responsible for Sections 13 and 17 of the Technical Report.\n"
        )
        self.assertEqual(check_certificate_item_coverage(pages(cert)).status, STATUS_NON_COMPLIANT)

    def test_qp_table_rows_including_numbers_after_company_name(self):
        intro = (
            "Table 2-1: \nSummary of Qualified Persons \nQP \nCompany \nSections \n"
            "Alex Thompson, P.Geo Equinox \n4 to 11, 23, 26.2 \n"
            "Philippe Lebleu, P.Eng. Equinox \n1 to 3, 12.2, 15, 16, 19, 21, 22, 24, 25, 27 \n"
            "Kelly Boychuk, P.Eng \nEquinox \n14, 18, 20 \n"
            "Neil Lincoln, P.Eng. \nLincoln Metallurgical Inc. 12.3, 13, 17, 26.4 \n"
            "The QPs visited the Mine site on the following dates:"
        )
        self.assertEqual(check_certificate_item_coverage(pages(intro)).status, STATUS_COMPLIANT)

    def test_no_reserves_statement_exempts_item_15(self):
        cert = (
            "CERTIFICATE OF QUALIFIED PERSON\n"
            "6. I am responsible for Sections 1 to 14 and 16 to 27 of the Technical Report.\n"
        )
        s15 = "15.0 \nMineral Reserve Estimate \nNo Mineral Reserves have been estimated at the Project."
        body = pages(s15, cert)
        page_items = {1: ("item_15", "Mineral Reserve Estimates")}
        self.assertEqual(check_certificate_item_coverage(body, page_items).status, STATUS_COMPLIANT)

    def test_not_applicable_cost_section(self):
        body = pages("21.0 \nCapital and Operating Costs \nThis section is not applicable.")
        page_items = {1: ("item_21", "Capital and Operating Costs")}
        f = check_cost_table_present(body, page_items, "report.pdf")
        self.assertEqual(f.status, STATUS_NOT_APPLICABLE)


if __name__ == "__main__":
    unittest.main()
