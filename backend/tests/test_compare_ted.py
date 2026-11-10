import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.compare_ted import main


class TestCompareTed(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.original = Path(directory.name) / "original.html"
        self.repaired = Path(directory.name) / "repaired.html"
        subtree = '<div><p><span>Keep</span></p></div>'
        self.original.write_text('<html><body>' + subtree * 4 + '</body></html>', encoding="utf-8")
        self.repaired.write_text('<html><body>' + subtree * 3 + '</body></html>', encoding="utf-8")

    def test_default_measures_only_unpruned(self):
        output = io.StringIO()
        with (
            patch("scripts.compare_ted.calculate_legacy_pruned_structural_preservation") as legacy,
            redirect_stdout(output),
        ):
            main([str(self.original), str(self.repaired)])

        legacy.assert_not_called()
        results = json.loads(output.getvalue())
        self.assertEqual(set(results), {"unpruned"})
        self.assertEqual(results["unpruned"]["tree_edit_distance"], 3)
        self.assertFalse(results["unpruned"]["structure_preserved"])
        self.assertGreaterEqual(results["unpruned"]["elapsed_seconds"], 0)

    def test_flag_reports_both_metrics_separately(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main([str(self.original), str(self.repaired), "--compare-pruned"])

        results = json.loads(output.getvalue())
        self.assertEqual(set(results), {"unpruned", "legacy_pruned"})
        self.assertEqual(results["unpruned"]["tree_edit_distance"], 3)
        self.assertEqual(results["unpruned"]["structure_similarity"], 0.7857)
        self.assertFalse(results["unpruned"]["structure_preserved"])
        self.assertEqual(results["legacy_pruned"]["tree_edit_distance"], 1)
        self.assertEqual(results["legacy_pruned"]["structure_similarity"], 0.9286)
        self.assertTrue(results["legacy_pruned"]["structure_preserved"])
        for result in results.values():
            self.assertEqual(result["max_nodes"], 14)
            self.assertEqual(result["threshold"], 0.85)
            self.assertGreaterEqual(result["elapsed_seconds"], 0)

    def test_missing_input_reports_an_error(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit) as error:
            main([str(self.original.with_name("missing.html")), str(self.repaired)])

        self.assertEqual(error.exception.code, 2)
        self.assertIn("missing.html", output.getvalue())


if __name__ == "__main__":
    unittest.main()
