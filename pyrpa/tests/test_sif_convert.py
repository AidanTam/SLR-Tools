"""Unit tests for pyrpa.sif_convert analyte column naming.

Run from the repo root with:  python -m unittest pyrpa.tests.test_sif_convert -v
"""

from __future__ import annotations

import os
import unittest

from pyrpa import sif_convert as s

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALS_CSV = os.path.join(REPO_ROOT, "VA26040082.csv")


def _fw(lead: str, cells: list, lead_width: int = 40, stride: int = 10) -> str:
    """One fixed-width line: left-aligned lead field, right-aligned cells."""
    return lead.ljust(lead_width) + "".join(c.rjust(stride) for c in cells)


class ColumnNameTests(unittest.TestCase):
    def test_joins_element_units_method(self):
        self.assertEqual(s.column_name("Ba", "ppm", "ME-MS81", 0), "Ba_ppm_ME-MS81")

    def test_skips_missing_parts(self):
        self.assertEqual(s.column_name("Au", "", "Au-AA23", 0), "Au_Au-AA23")
        self.assertEqual(s.column_name("", "", "", 4), "col_5")


class AlsDelimitedTests(unittest.TestCase):
    """ALS CSV certificates order the header rows method / element / units."""

    @unittest.skipUnless(os.path.exists(ALS_CSV), "example certificate not in repo")
    def test_example_certificate(self):
        with open(ALS_CSV, encoding="latin-1") as fh:
            p = s.parse_text(fh.read())
        self.assertEqual(p.lead_col_names, ["sample_id"])
        self.assertEqual(p.analytes[:2], ["Ba_ppm_ME-MS81", "Ce_ppm_ME-MS81"])
        self.assertIn("SiO2_%_ME-ICP06", p.analytes)
        self.assertIn("LOI_%_OA-GRA05", p.analytes)
        self.assertEqual(len(p.data_rows), 189)  # "# of SAMPLES : 189"
        self.assertEqual(p.analyte_headers["element"][0], "Ba")
        self.assertEqual(p.analyte_headers["units"][0], "ppm")
        self.assertEqual(p.analyte_headers["method"][0], "ME-MS81")

    def test_inline_als_layout(self):
        text = (
            "VA00000001 - Finalized\n"
            "# of SAMPLES : 2\n"
            ",ME-MS81,ME-MS81,ME-ICP06\n"
            "SAMPLE,Ba,Ce,SiO2\n"
            "DESCRIPTION,ppm,ppm,%\n"
            "AB-001,285,440,61.2\n"
            "AB-002,298,443,60.9\n"
        )
        p = s.parse_text(text)
        self.assertEqual(p.analytes, ["Ba_ppm_ME-MS81", "Ce_ppm_ME-MS81", "SiO2_%_ME-ICP06"])
        self.assertEqual(len(p.data_rows), 2)


class OtherLayoutTests(unittest.TestCase):
    def test_delimited_default_order_still_works(self):
        text = (
            "Au,Ag,Cu\n"
            "g/t,ppm,%\n"
            "Au-AA23,ME-ICP41,ME-ICP41\n"
            "0.005,0.2,0.01\n"
            "SampleID,Au,Ag,Cu\n"
        )
        # Header rows above need a lead column to line up with the data.
        text = "\n".join("," + ln if not ln.startswith("SampleID") else ln
                         for ln in text.splitlines())
        text += "\nAB-001,1.2,3.4,0.5\nAB-002,0.8,2.1,0.4\n"
        p = s.parse_text(text)
        self.assertEqual(p.lead_col_names, ["SampleID"])
        self.assertEqual(p.analytes, ["Au_g/t_Au-AA23", "Ag_ppm_ME-ICP41", "Cu_%_ME-ICP41"])
        self.assertEqual(p.analyte_headers["detection_limit"], ["0.005", "0.2", "0.01"])

    def test_single_label_row_keeps_plain_names(self):
        p = s.parse_text("SampleID,Au,Ag\nAB-001,1.2,3.4\nAB-002,0.8,2.1\n")
        self.assertEqual(p.analytes, ["Au", "Ag"])

    def test_fixed_width_als(self):
        lines = [
            _fw("VA00000002", []),
            _fw("CLIENT", ["X"]),
            _fw("", ["Au-AA23", "ME-MS81", "ME-MS81"]),
            _fw("", ["Au", "Ba", "Ba"]),
            _fw("UNITS", ["ppm", "ppm", "ppm"]),
            _fw("DETECTION", ["0.005", "0.5", "0.5"]),
            _fw("LABORATORY", ["VA", "VA", "VA"]),
            _fw("AB-001", ["1.2", "285", "286"]),
        ]
        p = s.parse_text("\n".join(lines))
        self.assertEqual(p.fmt, "fixed_width")
        # Repeated element/units/method still get unique names.
        self.assertEqual(p.analytes, ["Au_ppm_Au-AA23", "Ba_ppm_ME-MS81", "Ba_ppm_ME-MS81_2"])


if __name__ == "__main__":
    unittest.main()
