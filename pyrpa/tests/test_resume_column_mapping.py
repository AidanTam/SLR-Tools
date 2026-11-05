"""Unit tests for resuming a saved session without losing the column mapping.

Run from the repo root with:  python -m unittest pyrpa.tests.test_resume_column_mapping -v
"""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock

import pandas as pd

from pyrpa.UI import common

COLUMNS = ["Project", "Batch", "Analyte", "Reading", "Mystery"]
FIELD_MAP = {"lab_col": "lab", "elem_col": "element", "val_col": "value", "unit_col": "unit"}


def _upload(state: dict, file_id: str = "file-1") -> io.BytesIO:
    """A saved-progress upload, written the way the tools' save buttons do it."""
    uploaded = io.BytesIO(json.dumps(state).encode())
    uploaded.file_id = file_id
    return uploaded


class ResumeTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(common.st, "session_state", {})
        self.state = patcher.start()
        self.addCleanup(patcher.stop)
        self.df = pd.DataFrame(columns=COLUMNS)

    def _saved_session(self) -> dict:
        """Map a file, override some picks by hand, and return what gets saved."""
        common.sync_column_mapping(self.df, "blanks", FIELD_MAP)
        self.state.update(lab_col="Project", val_col="Mystery", unit_col="None")
        saved = json.loads(json.dumps(self.state))
        self.state.clear()
        return saved


class SavedMappingTests(ResumeTestCase):
    def test_resume_keeps_manual_mapping(self):
        saved = self._saved_session()
        self.assertTrue(common.load_saved_state(_upload(saved), "blanks"))
        common.sync_column_mapping(self.df, "blanks", FIELD_MAP)
        self.assertEqual(self.state["lab_col"], "Project")
        self.assertEqual(self.state["val_col"], "Mystery")
        self.assertEqual(self.state["elem_col"], "Analyte")
        self.assertEqual(self.state["unit_col"], "None")

    def test_saved_column_missing_from_new_file_is_auto_mapped(self):
        saved = self._saved_session()
        renamed = pd.DataFrame(columns=["Project", "Batch", "Analyte", "Reading"])
        common.load_saved_state(_upload(saved), "blanks")
        common.sync_column_mapping(renamed, "blanks", FIELD_MAP)
        self.assertEqual(self.state["lab_col"], "Project")
        self.assertEqual(self.state["val_col"], "Reading")

    def test_mapping_survives_when_data_is_uploaded_on_a_later_run(self):
        saved = self._saved_session()
        common.load_saved_state(_upload(saved), "blanks")
        # Runs with no data file stop before reaching sync_column_mapping.
        common.load_saved_state(_upload(saved), "blanks")
        common.sync_column_mapping(self.df, "blanks", FIELD_MAP)
        self.assertEqual(self.state["val_col"], "Mystery")

    def test_changed_file_after_resume_gets_fresh_guesses(self):
        saved = self._saved_session()
        common.load_saved_state(_upload(saved), "blanks")
        common.sync_column_mapping(self.df, "blanks", FIELD_MAP)
        common.sync_column_mapping(pd.DataFrame(columns=["Lab", "Element", "Value"]), "blanks", FIELD_MAP)
        self.assertEqual(self.state["lab_col"], "Lab")
        self.assertEqual(self.state["val_col"], "Value")

    def test_rerun_of_same_file_keeps_override_made_after_resume(self):
        saved = self._saved_session()
        common.load_saved_state(_upload(saved), "blanks")
        common.sync_column_mapping(self.df, "blanks", FIELD_MAP)
        self.state["val_col"] = "Reading"
        common.sync_column_mapping(self.df, "blanks", FIELD_MAP)
        self.assertEqual(self.state["val_col"], "Reading")

    def test_fresh_session_still_auto_maps(self):
        common.sync_column_mapping(self.df, "blanks", FIELD_MAP)
        self.assertEqual(self.state["elem_col"], "Analyte")
        self.assertEqual(self.state["val_col"], "Reading")


class LoadSavedStateTests(ResumeTestCase):
    def test_no_file_is_a_no_op(self):
        self.assertFalse(common.load_saved_state(None, "blanks"))
        self.assertEqual(self.state, {})

    def test_same_upload_applies_only_once(self):
        upload = _upload({"lab_col": "Project"})
        self.assertTrue(common.load_saved_state(upload, "blanks"))
        self.state["lab_col"] = "Batch"
        self.assertFalse(common.load_saved_state(upload, "blanks"))
        self.assertEqual(self.state["lab_col"], "Batch")

    def test_new_upload_applies_again(self):
        common.load_saved_state(_upload({"lab_col": "Project"}, "file-1"), "blanks")
        self.assertTrue(common.load_saved_state(_upload({"lab_col": "Batch"}, "file-2"), "blanks"))
        self.assertEqual(self.state["lab_col"], "Batch")

    def test_app_shell_and_button_keys_are_not_restored(self):
        common.load_saved_state(_upload({
            "lab_col": "Project",
            "authenticated": True,
            "active_tool": "CRMs_ui.py",
            "active_section": "QA/QC",
            "blanks_wide_reshape_btn": False,
            "blanks_wide_skip_btn": False,
        }), "blanks")
        self.assertEqual(self.state["lab_col"], "Project")
        for key in ("authenticated", "active_tool", "active_section",
                    "blanks_wide_reshape_btn", "blanks_wide_skip_btn"):
            self.assertNotIn(key, self.state)

    def test_sets_cfg_loaded_even_if_the_file_saved_it_false(self):
        # Duplicates reads this flag to skip its Run button after a load.
        common.load_saved_state(_upload({"cfg_loaded": False}), "dups")
        self.assertTrue(self.state["cfg_loaded"])

    def test_transform_is_applied(self):
        common.load_saved_state(_upload({"a": 1}), "crms", transform=lambda s: {"a": s["a"] + 1})
        self.assertEqual(self.state["a"], 2)


if __name__ == "__main__":
    unittest.main()
