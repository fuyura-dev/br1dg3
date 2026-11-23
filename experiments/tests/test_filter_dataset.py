"""Check filtering decisions and file handling with synthetic HTML and mocked scans."""

import contextlib
import csv
import io
import json
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

filtering = import_module("experiments.scripts.02_filter_dataset")


def scan_result(*selectors):
    from app.services.detection.detect import RELEVANT_RULES, ScanResult

    violations = [{"id": "image-alt", "nodes": [{"target": [selector]} for selector in selectors]}] if selectors else []
    return ScanResult(violations, {"selected_rule_ids": list(RELEVANT_RULES), "axe": {"violations": violations}})


class FilterDatasetTests(unittest.TestCase):
    def setUp(self):
        self.scan = self.enterContext(patch.object(filtering, "scan_with_report", return_value=scan_result("#image")))
        self.browser = self.enterContext(patch.object(filtering, "_get_driver"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "candidates"
        self.inputs.mkdir()
        self.output = self.root / "output"
        self.html = b'<img id="image" src="example.png">'

    def test_zero_edges_do_not_exclude_a_mapped_violation(self):
        row, evidence = filtering.check_html("image.html", self.html)
        self.assertEqual(row["status"], "passed")
        self.assertEqual(row["selected_violations"], 1)
        self.assertEqual(row["mapped_violations"], 1)
        self.assertEqual(row["unmapped_violations"], 0)
        self.assertEqual(row["original_sdg_edges"], 0)
        self.assertEqual(row["semantic_applicability"], "not_applicable")
        self.assertEqual(row["content_review"], "pending")
        self.assertEqual(evidence["scan"], self.scan.return_value.report)

    def test_rule_element_occurrences_are_not_distinct_elements(self):
        self.scan.return_value = scan_result("#image", "#other")
        self.scan.return_value.violations.append({"id": "presentation-role-conflict", "nodes": [{"target": ["#image"]}]})
        row, _ = filtering.check_html("two.html", self.html + b'<img id="other">')
        self.assertEqual(row["status"], "passed")
        self.assertEqual(row["selected_violations"], 3)
        self.assertEqual(row["distinct_rules"], 2)
        self.assertEqual(row["mapped_violations"], 3)

    def test_successful_zero_and_scan_failure_are_distinct(self):
        self.scan.return_value = scan_result()
        row, evidence = filtering.check_html("clean.html", self.html)
        self.assertEqual(row["status"], "not_passed")
        self.assertEqual(row["selected_violations"], 0)
        self.assertEqual(row["scan_status"], "success")
        self.assertIsNotNone(evidence["scan"])
        self.scan.side_effect = RuntimeError("synthetic timeout")
        row, evidence = filtering.check_html("error.html", self.html)
        self.assertEqual(row["status"], "needs_review")
        self.assertEqual(row["scan_status"], "error")
        self.assertIsNone(row["selected_violations"])
        self.assertIsNone(evidence["scan"])

    def test_partial_mapping_is_excluded_but_extraction_failure_is_unresolved(self):
        self.scan.return_value = scan_result("#image", "#missing")
        row, _ = filtering.check_html("partial.html", self.html)
        self.assertEqual(row["status"], "not_passed")
        self.assertEqual((row["mapped_violations"], row["unmapped_violations"]), (1, 1))
        with patch.object(filtering, "extract_sdg", side_effect=ValueError("synthetic graph failure")):
            row, evidence = filtering.check_html("graph-error.html", self.html)
        self.assertEqual(row["status"], "needs_review")
        self.assertEqual(row["sdg_status"], "error")
        self.assertIsNone(row["original_sdg_edges"])
        self.assertEqual(row["semantic_applicability"], "unknown")
        self.assertIsNotNone(evidence["scan"])

    def test_css_warnings_do_not_override_successful_scan_and_mapping(self):
        self.scan.return_value.report["stylesheet_warnings"] = [
            {"status": "unresolved_url", "href": "/theme.css"}
        ]
        row, evidence = filtering.check_html("missing-css.html", self.html)
        self.assertEqual(row["status"], "passed")
        self.assertEqual(row["stylesheet_warnings"], "unresolved_url: /theme.css")
        self.assertEqual(row["selected_violations"], 1)
        self.assertEqual(row["mapped_violations"], 1)
        self.assertEqual(evidence["scan"], self.scan.return_value.report)

        self.scan.return_value.violations = []
        row, _ = filtering.check_html("no-findings.html", self.html)
        self.assertEqual(row["status"], "not_passed")
        self.assertEqual(row["selected_violations"], 0)

    def test_empty_and_declared_encoding(self):
        row, _ = filtering.check_html("empty.html", b" \n")
        self.assertEqual(row["status"], "not_passed")
        self.scan.assert_not_called()
        data = b'<meta charset="windows-1252"><p>caf\xe9</p>' + self.html
        row, _ = filtering.check_html("encoded.html", data)
        self.assertEqual(row["status"], "passed")
        self.assertIn("caf\u00e9", self.scan.call_args.args[0])

    def test_copies_reports_and_non_overwrite(self):
        originals = {"a.html": self.html, "b.html": self.html + b"<!--clean-->", "c.html": self.html + b"<!--error-->"}
        for name, data in originals.items():
            (self.inputs / name).write_bytes(data)

        def scan(html):
            if "<!--error-->" in html:
                raise RuntimeError("synthetic timeout")
            return scan_result() if "<!--clean-->" in html else scan_result("#image")

        self.scan.side_effect = scan
        for name in ("passed", "not-passed"):
            (self.output / name).mkdir(parents=True)
        counts = filtering.filter_dataset(self.inputs, self.output)
        self.assertEqual(counts, {"passed": 1, "not_passed": 1, "needs_review": 1})
        self.browser.return_value.quit.assert_called_once()
        groups = {"a.html": "passed", "b.html": "not-passed", "c.html": "needs-review"}
        for name, data in originals.items():
            group = groups[name]
            self.assertEqual({p.name for p in (self.output / group).iterdir()}, {name})
            self.assertEqual((self.output / group / name).read_bytes(), data)
            self.assertEqual((self.inputs / name).read_bytes(), data)
        with (self.output / "results.csv").open(newline="") as f:
            rows = {row["filename"]: row for row in csv.DictReader(f)}
        self.assertEqual(rows["b.html"]["selected_violations"], "0")
        self.assertEqual(rows["c.html"]["selected_violations"], "")
        evidence = [json.loads(line) for line in (self.output / "scan-results.jsonl").read_text().splitlines()]
        self.assertEqual(len(evidence), 3)
        self.assertEqual(evidence[2]["result"]["status"], "needs_review")
        before = (self.output / "results.csv").read_bytes()
        with self.assertRaises(ValueError):
            filtering.filter_dataset(self.inputs, self.output)
        self.assertEqual((self.output / "results.csv").read_bytes(), before)

    def test_input_protection_and_missing_browser_leave_outputs_untouched(self):
        (self.inputs / "a.html").write_bytes(self.html)
        for output in (self.inputs, self.inputs / "nested", self.root):
            with self.subTest(output=output), self.assertRaises(ValueError):
                filtering.filter_dataset(self.inputs, output)
        self.browser.assert_not_called()
        self.browser.side_effect = RuntimeError("Browser unavailable")
        with self.assertRaises(RuntimeError):
            filtering.filter_dataset(self.inputs, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual((self.inputs / "a.html").read_bytes(), self.html)


if __name__ == "__main__":
    unittest.main()
