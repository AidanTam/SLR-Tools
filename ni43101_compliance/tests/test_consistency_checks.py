"""Unit tests for the cross-reference, arithmetic, date and certificate checks.

All synthetic: no PDF, no Ollama. Run with:
    python -m unittest tests.test_consistency_checks -v
"""

from __future__ import annotations

import unittest

from compliance.arithmetic_checks import (
    _category_issues,
    _contained_issues,
    _to_grid,
    _total_issues,
)
from compliance.certificate_checks import check_certificate_content
from compliance.crossref_checks import (
    check_caption_numbering,
    check_figure_table_references,
    check_section_references,
)
from compliance.date_checks import check_date_order, check_reference_years, check_site_visit_dates
from compliance.models import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_ADDRESSED,
    STATUS_NEEDS_REVIEW,
    Page,
)


def pages(*texts: str) -> list:
    return [Page(number=i + 1, text=t) for i, t in enumerate(texts)]


# ---------------------------------------------------------------------------
# Cross-references
# ---------------------------------------------------------------------------

def _captioned(n: int = 6, skip: int = 0) -> str:
    return "\n".join(
        f"Figure 4-{i}: Location map {i}" for i in range(1, n + 1) if i != skip
    )


class TestFigureTableReferences(unittest.TestCase):
    def test_every_reference_has_a_caption(self):
        f = check_figure_table_references(pages(
            _captioned(6),
            "The claims are shown in Figure 4-2 and Figure 4-5.",
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_reference_to_a_missing_caption_is_flagged(self):
        f = check_figure_table_references(pages(
            _captioned(6, skip=3),
            "The claims are shown in Figure 4-3 and Figure 4-5.",
        ))
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)
        self.assertIn("Figure 4-3", f.evidence)

    def test_wrapped_sentence_is_not_mistaken_for_a_caption(self):
        # "Table 4-9. A regular block ..." starts a line but is a sentence.
        f = check_figure_table_references(pages(
            _captioned(6),
            "described in\nTable 4-9. A regular block size of 5 m by 5 m was used and\n"
            "cross-checks were run.",
        ))
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)
        self.assertIn("Table 4-9", f.evidence)

    def test_references_to_other_documents_are_ignored(self):
        f = check_figure_table_references(pages(
            _captioned(6),
            "See Figure 4-2. Table 7-1 of Smith (2019) lists the assays, "
            "and Figure 9-4 in NI 43-101 shows nothing.",
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_label_only_caption_line_counts(self):
        f = check_figure_table_references(pages(
            _captioned(5) + "\nFigure 4-6 \nLocation of claims\n",
            "See Figure 4-6.",
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_too_few_captions_is_not_addressed(self):
        f = check_figure_table_references(pages("Figure 1-1: Map\nSee Figure 1-2."))
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)


class TestCaptionNumbering(unittest.TestCase):
    def test_clean_sequence(self):
        self.assertEqual(check_caption_numbering(pages(_captioned(6))).status, STATUS_COMPLIANT)

    def test_gap_in_sequence(self):
        f = check_caption_numbering(pages(_captioned(6, skip=3)))
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)
        self.assertIn("4-3", f.rationale)

    def test_same_number_two_titles_is_non_compliant(self):
        f = check_caption_numbering(pages(
            _captioned(6) + "\nFigure 4-2: A different map\n"
        ))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_continued_table_is_not_a_duplicate(self):
        f = check_caption_numbering(pages(
            _captioned(6),
            "Figure 4-2: Location map 2 (continued)\n",
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)


def _headings(n_sections: int = 22) -> str:
    return "\n".join(f"{i}.0 Heading number {i}\n{i}.1 Sub heading {i}" for i in range(1, n_sections + 1))


class TestSectionReferences(unittest.TestCase):
    def test_existing_section_is_fine(self):
        f = check_section_references(pages(_headings(), "Described in Section 14.1."))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_missing_section_is_flagged(self):
        f = check_section_references(pages(_headings(), "Described in Section 14.7."))
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)
        self.assertIn("14.7", f.evidence)

    def test_section_of_another_document_is_ignored(self):
        f = check_section_references(pages(
            _headings(), "Independence is defined in Section 1.5 of NI 43-101. See Section 3.1."
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_number_on_its_own_line_is_a_heading(self):
        text = _headings() + "\n27.0\nReferences\n"
        f = check_section_references(pages(text, "See Section 27.0."))
        self.assertEqual(f.status, STATUS_COMPLIANT)


# ---------------------------------------------------------------------------
# Table arithmetic
# ---------------------------------------------------------------------------

def grid(*rows):
    return _to_grid(1, [list(r) for r in rows])


class TestTotals(unittest.TestCase):
    HEAD = ["Cost Item", "Initial ($M)", "Sustaining ($M)", "Total ($M)"]

    def test_total_that_adds_up(self):
        g = grid(self.HEAD, ["A", "10.0", "5.0", "15.0"], ["B", "20.0", "1.0", "21.0"],
                 ["Total", "30.0", "6.0", "36.0"])
        tested, issues = _total_issues(g)
        self.assertGreater(tested, 0)
        self.assertEqual(issues, [])

    def test_stale_total_is_found(self):
        # The sub-total shows 246.3 over rows that sum to 239.3.
        g = grid(self.HEAD, ["A", "10.0", "5.0", "29.0"], ["B", "20.0", "1.0", "65.0"],
                 ["C", "3.0", "2.0", "145.3"], ["Sub-Total", "33.0", "8.0", "246.3"])
        _tested, issues = _total_issues(g)
        self.assertEqual(len(issues), 1)
        self.assertIn("246.3", issues[0].text)

    def test_rounding_is_tolerated(self):
        g = grid(["Item", "Cost", "Share"], ["A", "3.3", "1.1"], ["B", "3.3", "1.1"], ["C", "3.3", "1.1"],
                 ["Total", "10.0", "3.3"])
        self.assertEqual(_total_issues(g)[1], [])

    def test_average_column_is_not_summed(self):
        g = grid(["Zone", "Tonnes (kt)", "Mean value"], ["A", "100", "7.0"], ["B", "300", "9.0"],
                 ["Total", "400", "8.5"])
        self.assertEqual(_total_issues(g)[1], [])

    def test_total_far_from_rows_is_treated_as_a_misread_table(self):
        g = grid(["Item", "Cost", "Share"], ["A", "10", "1"], ["B", "20", "2"], ["Total", "900", "3"])
        self.assertEqual(_total_issues(g)[1], [])

    def test_subtotals_roll_up_to_a_grand_total(self):
        g = grid(["Area", "Tonnes (kt)", "Holes"], ["P1", "100", "5"], ["P2", "50", "4"],
                 ["Subtotal Open Pit", "150", "9"], ["U1", "70", "3"], ["U2", "30", "2"],
                 ["Subtotal Underground", "100", "5"], ["Total In Situ", "250", "14"])
        self.assertEqual(_total_issues(g)[1], [])


class TestCategories(unittest.TestCase):
    HEAD = [["Category", "Tonnage (kt)", "Grade (g/t)", "Contained Au (koz)"]]

    def test_m_plus_i_adds_up(self):
        g = grid(*self.HEAD, ["Measured", "1,000", "2.00", "64"], ["Indicated", "3,000", "1.00", "96"],
                 ["M + I", "4,000", "1.25", "161"])
        tested, issues = _category_issues(g)
        self.assertGreater(tested, 0)
        self.assertEqual(issues, [])

    def test_wrong_m_plus_i_tonnage(self):
        g = grid(*self.HEAD, ["Measured", "1,000", "2.00", "64"], ["Indicated", "3,000", "1.00", "96"],
                 ["M + I", "4,500", "1.25", "161"])
        _tested, issues = _category_issues(g)
        self.assertTrue(any("4,500" in i.text for i in issues))

    def test_wrong_weighted_grade(self):
        g = grid(*self.HEAD, ["Measured", "1,000", "2.00", "64"], ["Indicated", "3,000", "1.00", "96"],
                 ["M + I", "4,000", "1.80", "161"])
        _tested, issues = _category_issues(g)
        self.assertTrue(any(i.kind == "grade" for i in issues))

    def test_category_columns_layout(self):
        g = grid(
            ["", "Measured Tonnage (kt)", "Indicated Tonnage (kt)", "Measured + Indicated Tonnage (kt)"],
            ["Deposit A", "100", "200", "300"],
            ["Deposit B", "10", "20", "99"],
        )
        _tested, issues = _category_issues(g)
        self.assertEqual(len(issues), 1)
        self.assertIn("Deposit B", issues[0].text)


class TestContainedMetal(unittest.TestCase):
    HEAD = [["Zone", "Tonnage (kt)", "Grade (g/t)", "Contained Au (koz)"]]

    def test_consistent_row(self):
        # 1,000 kt x 2.00 g/t = 64.3 koz
        g = grid(*self.HEAD, ["A", "1,000", "2.00", "64"], ["B", "2,000", "1.50", "96"],
                 ["C", "500", "3.00", "48"])
        tested, issues = _contained_issues(g)
        self.assertEqual(tested, 3)
        self.assertEqual(issues, [])

    def test_wrong_contained_ounces(self):
        g = grid(*self.HEAD, ["A", "1,000", "2.00", "84"], ["B", "2,000", "1.50", "96"],
                 ["C", "500", "3.00", "48"])
        _tested, issues = _contained_issues(g)
        self.assertEqual(len(issues), 1)
        self.assertIn("\"A\"", issues[0].text)

    def test_percent_grade_to_pounds(self):
        # 10,000 kt x 0.50 % Cu = 50 kt = 110.2 Mlb
        g = grid(["Zone", "Tonnage (kt)", "Cu Grade (%)", "Contained Cu (Mlb)"],
                 ["A", "10,000", "0.50", "110"], ["B", "2,000", "1.00", "44"],
                 ["C", "1,000", "2.00", "44"])
        tested, issues = _contained_issues(g)
        self.assertEqual(tested, 3)
        self.assertEqual(issues, [])


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def _front(effective: str, header_date: str) -> str:
    return f"Acme Corp. | Project NI 43-101 Technical Report {header_date}\nEffective Date: {effective}\n"


def _report(effective: str, header_date: str, body: str = "", n: int = 8) -> list:
    out = [_front(effective, header_date) + "Title page\n"]
    for _ in range(n):
        out.append(f"Acme Corp. | Project NI 43-101 Technical Report {header_date}\nSome body text.\n{body}\n")
    return pages(*out)


class TestDateOrder(unittest.TestCase):
    def test_normal_order(self):
        f = check_date_order(_report("March 31, 2025", "May 20, 2025"))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_report_dated_before_effective_date(self):
        f = check_date_order(_report("June 30, 2025", "May 20, 2025"))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_signature_before_effective_date(self):
        cert = _certificate("Jane Doe").replace("2nd day of May, 2025", "2nd day of January, 2025")
        rep = _report("March 31, 2025", "May 20, 2025", n=6)
        rep.append(Page(number=len(rep) + 1, text="Certificate of Qualified Person\n" + cert))
        f = check_date_order(rep)
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_date_of_an_earlier_report_in_a_certificate_is_not_a_signature(self):
        # A QP's experience bullet: "This report, dated April 23, 2014, ..."
        cert = _certificate("Jane Doe").replace(
            "1. I am a Principal",
            "This report, dated April 23, 2014, with an effective date of March 3, 2014, was "
            "completed under the supervision of Someone Else. 1. I am a Principal",
        )
        rep = _report("March 31, 2025", "May 20, 2025", n=6)
        rep.append(Page(number=len(rep) + 1, text="Certificate of Qualified Person\n" + cert))
        self.assertEqual(check_date_order(rep).status, STATUS_COMPLIANT)

    def test_no_effective_date(self):
        f = check_date_order(pages("Nothing here."))
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)


class TestSiteVisit(unittest.TestCase):
    def test_visit_before_effective_date(self):
        f = check_site_visit_dates(_report(
            "March 31, 2025", "May 20, 2025",
            body="I visited the Property on February 3 and 4, 2025.",
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_visit_after_effective_date(self):
        f = check_site_visit_dates(_report(
            "March 31, 2025", "May 20, 2025",
            body="I visited the Property on April 22, 2025.",
        ))
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)
        self.assertIn("April 22, 2025", f.evidence)

    def test_no_visit_is_not_compared(self):
        f = check_site_visit_dates(_report(
            "March 31, 2025", "May 20, 2025", body="I did not visit the Property in 2026."
        ))
        self.assertEqual(f.status, STATUS_NOT_ADDRESSED)


class TestReferenceYears(unittest.TestCase):
    def _with_refs(self, *refs: str) -> list:
        rep = _report("March 31, 2025", "May 20, 2025", n=5)
        rep.append(Page(number=len(rep) + 1, text="References\n" + "\n".join(refs) + "\n"))
        return rep

    def test_all_references_on_or_before_effective_year(self):
        f = check_reference_years(self._with_refs(
            "Smith, J. 2019. A paper. Journal 3.", "Jones, A. 2025. Another. Report.",
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_reference_after_effective_year(self):
        f = check_reference_years(self._with_refs(
            "Smith, J. 2019. A paper. Journal 3.", "Jones, A. 2026. Newer. Report.",
        ))
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)
        self.assertIn("2026", f.evidence)

    def test_access_date_is_not_a_publication_year(self):
        f = check_reference_years(self._with_refs(
            "Smith, J. 2019. A paper. Accessed March 3, 2026. www.example.com",
            "Jones, A. 2020. Another. Report.",
        ))
        self.assertEqual(f.status, STATUS_COMPLIANT)


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

class TestAllSectionsExclusiveOf(unittest.TestCase):
    def test_exclusive_of_claims_everything_else(self):
        from compliance.structural_checks import _extract_item_numbers

        claimed = _extract_item_numbers(
            "overall preparation and all sections exclusive of 13 and 14.6, and related "
            "subsections in 1, 25, and 26 of the Technical Report"
        )
        self.assertNotIn(13, claimed)          # carved out entirely
        self.assertIn(14, claimed)             # only 14.6 is carved out
        self.assertIn(1, claimed)              # "related subsections in 1" is not an exclusion
        self.assertIn(26, claimed)
        self.assertEqual(len(claimed), 26)

    def test_plain_list_is_unchanged(self):
        from compliance.structural_checks import _extract_item_numbers

        self.assertEqual(_extract_item_numbers("Sections 4 to 6 and 12"), {4, 5, 6, 12})



def _certificate(name: str = "Jane Doe", drop: str = "") -> str:
    parts = {
        "head": f"I, {name}, P.Geo., as an author of this report entitled NI 43-101 Technical Report "
                "for the Project with an effective date of March 31, 2025 prepared for Acme Corp., "
                "do hereby certify that: ",
        "employer": "1. I am a Principal Geologist with Consulting Ltd, of Toronto, ON. ",
        "education": "2. I am a graduate of the University of Toronto in 2006 with a Bachelor of Science degree. ",
        "registration": "3. I am registered as a Professional Geologist in Ontario. I have worked as a geologist for a total of 11 years. ",
        "qp": "4. I have read the definition of qualified person set out in NI 43-101 and fulfil the requirements. ",
        "visit": "5. I visited the Project on October 24 and 25, 2024. ",
        "responsible": "6. I am responsible for sections 4 to 12 of the Technical Report. ",
        "independence": "7. I am independent of the Issuer applying the test set out in Section 1.5 of NI 43-101. ",
        "prior": "8. I have had no prior involvement with the property that is the subject of the Technical Report. ",
        "read": "9. I have read NI 43-101, and the Technical Report has been prepared in compliance with it. ",
        "misleading": "10. To the best of my knowledge, the Technical Report contains all scientific and technical "
                      "information required to make the Technical Report not misleading. ",
        "signed": "Dated this 2nd day of May, 2025 (Signed and Sealed) " + name + " ",
    }
    parts.pop(drop, None)
    return "".join(parts.values()) + " " * 0


def _cert_pages(*certs: str) -> list:
    text = "Certificate of Qualified Person\n" + "\n".join(certs)
    return pages("front matter", text)


class TestCertificateContent(unittest.TestCase):
    def test_complete_certificates(self):
        f = check_certificate_content(_cert_pages(_certificate("Jane Doe"), _certificate("Sam Roe")))
        self.assertEqual(f.status, STATUS_COMPLIANT)
        self.assertIn("2 certificate", f.rationale)

    def test_missing_prior_involvement_names_the_qp(self):
        f = check_certificate_content(_cert_pages(
            _certificate("Jane Doe"), _certificate("Sam Roe", drop="prior"),
        ))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("Sam Roe", f.evidence)
        self.assertIn("prior involvement", f.evidence)
        self.assertNotIn("Jane Doe", f.evidence)

    def test_missing_independence_is_hard(self):
        f = check_certificate_content(_cert_pages(_certificate("Jane Doe", drop="independence")))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)

    def test_missing_only_experience_is_partial(self):
        cert = _certificate("Jane Doe").replace("I have worked as a geologist for a total of 11 years. ", "")
        cert = cert.replace("in 2006", "")
        f = check_certificate_content(_cert_pages(cert))
        self.assertEqual(f.status, STATUS_NEEDS_REVIEW)

    def test_statement_that_no_visit_was_made_counts(self):
        cert = _certificate("Jane Doe").replace("I visited the Project on October 24 and 25, 2024.",
                                                "I did not visit the Project.")
        f = check_certificate_content(_cert_pages(cert))
        self.assertEqual(f.status, STATUS_COMPLIANT)

    def test_missing_date(self):
        f = check_certificate_content(_cert_pages(_certificate("Jane Doe", drop="signed")))
        self.assertEqual(f.status, STATUS_NON_COMPLIANT)
        self.assertIn("signature date", f.evidence)

    def test_no_certificates(self):
        self.assertEqual(check_certificate_content(pages("Just text.")).status, STATUS_NOT_ADDRESSED)


if __name__ == "__main__":
    unittest.main()
