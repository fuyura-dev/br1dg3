"""Verify token selection and file preservation with synthetic HTML and mocked HTTP."""

import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

filtering = import_module("experiments.scripts.02_5_filter_token_budget")


class TokenBudgetTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(redirect_stdout(io.StringIO()))
        self.dataset = self.root / "eligibility"
        (self.dataset / "passed").mkdir(parents=True)
        self.output = self.root / "token-budget"
        self.html = (b'<!DOCTYPE html><html><head><meta charset="windows-1252">'
                     b'<style>p {color:red}</style><link rel="stylesheet" href="theme.css">'
                     b'</head><body><p style="color:blue">caf\xe9</p>'
                     b'<script>console.log("test")</script></body></html>')
        self.inputs()

    def inputs(self, count=1):
        self.rows = []
        for i in range(count):
            name = f"example_{i}.html"
            (self.dataset / "passed" / name).write_bytes(self.html)
            self.rows.append({"filename": name, "sha256": hashlib.sha256(self.html).hexdigest(),
                              "status": "passed", "reason": "Mapped violations found.",
                              "original_sdg_edges": "0", "selected_violations": "2",
                              "scan_status": "success", "semantic_applicability": "not_applicable"})
        self.write_report()

    def write_report(self):
        with (self.dataset / "results.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.rows[0])
            writer.writeheader()
            writer.writerows(self.rows)

    def client(self, handler):
        return self.enterContext(httpx.Client(transport=httpx.MockTransport(handler)))

    def test_boundary_groups_copies_and_error_preservation(self):
        self.inputs(4)
        replies = iter([(200, {"totalTokens": 59_999}), (200, {"totalTokens": 60_000}),
                        (200, {"totalTokens": 60_001}), (429, {"error": "synthetic limit"})])
        calls = []

        def respond(request):
            calls.append(request)
            status, body = next(replies)
            return httpx.Response(status, json=body)

        counts = filtering.filter_dataset(self.dataset, self.output, self.client(respond), "test-model")
        self.assertEqual(counts, {"passed": 2, "not_passed": 1, "needs_review": 1})
        self.assertEqual(len(calls), 4)
        with (self.output / "results.csv").open() as stream:
            results = list(csv.DictReader(stream))
        groups = ["passed", "passed", "not-passed", "needs-review"]
        for original, row, group in zip(self.rows, results, groups, strict=True):
            with self.subTest(group=group, filename=row["filename"]):
                self.assertEqual((self.output / group / row["filename"]).read_bytes(), self.html)
                self.assertEqual((self.dataset / "passed" / row["filename"]).read_bytes(), self.html)
                for key in ("sha256", "original_sdg_edges", "scan_status", "selected_violations", "semantic_applicability"):
                    self.assertEqual(row[key], original[key])
                self.assertEqual((row["count_model"], row["token_limit"], row["exclusion_operator"]),
                                 ("test-model", "60000", ">"))
        self.assertEqual([row["prepared_tokens"] for row in results], ["59999", "60000", "60001", ""])
        self.assertIn("429", results[-1]["error"])
        self.assertEqual(results[-1]["status"], "needs_review")
        with (self.dataset / "results.csv").open() as stream:
            self.assertEqual(list(csv.DictReader(stream)), self.rows)

    def test_exact_once_preprocessed_html_sent_to_official_endpoint(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"totalTokens": 100})

        decoded = filtering.UnicodeDammit(self.html, is_html=True).unicode_markup
        expected = filtering.preprocess(decoded)
        with patch.object(filtering, "preprocess", wraps=filtering.preprocess) as prepare:
            row = filtering.check_html(self.rows[0], self.html, self.client(respond), "test-model")
        prepare.assert_called_once_with(decoded)
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(str(request.url), "https://generativelanguage.googleapis.com/v1beta/models/test-model:countTokens")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.content), {"contents": [{"role": "user", "parts": [{"text": expected}]}]})
        self.assertNotIn("<script", expected)
        self.assertNotIn("<style", expected)
        self.assertIn('href="theme.css"', expected)
        self.assertIn('style="color:blue"', expected)
        self.assertIn("caf\u00e9", expected)
        self.assertEqual(row["prepared_sha256"], hashlib.sha256(expected.encode()).hexdigest())

    def test_missing_or_invalid_counts_never_become_zero(self):
        for value in (None, -1, True, "60000", 1.5):
            with self.subTest(value=value):
                body = {} if value is None else {"totalTokens": value}
                client = self.client(lambda request, body=body: httpx.Response(200, json=body))
                row = filtering.check_html(self.rows[0], self.html, client, "test-model")
                self.assertEqual(row["status"], "needs_review")
                self.assertIsNone(row["prepared_tokens"])
                self.assertIn("Token counting failed", row["reason"])

    def test_timeout_is_review_not_exclusion(self):
        def timeout(request):
            raise httpx.ReadTimeout("Synthetic timeout", request=request)

        row = filtering.check_html(self.rows[0], self.html, self.client(timeout), "test-model")
        self.assertEqual(row["status"], "needs_review")
        self.assertIsNone(row["prepared_tokens"])
        self.assertIn("ReadTimeout", row["error"])

    def test_decoding_errors_make_no_counter_request(self):
        for markup, replacement in ((None, False), ("replacement text", True)):
            decoded = SimpleNamespace(original_encoding=None, unicode_markup=markup,
                                      contains_replacement_characters=replacement)
            with self.subTest(markup=markup), patch.object(filtering, "UnicodeDammit", return_value=decoded), patch.object(filtering, "count_tokens") as count:
                row = filtering.check_html(self.rows[0], b"undecodable", None, "test-model")
            count.assert_not_called()
            self.assertEqual(row["status"], "needs_review")
            self.assertIsNone(row["prepared_tokens"])
            self.assertEqual(row["prepared_sha256"], "")

    def test_changed_source_stops_before_counting(self):
        (self.dataset / "passed/example_0.html").write_bytes(b"changed")
        with patch.object(filtering, "count_tokens") as count, self.assertRaisesRegex(ValueError, "differs from"):
            filtering.filter_dataset(self.dataset, self.output, None, "test-model")
        count.assert_not_called()

    def test_folder_mismatch_and_duplicate_rows_are_rejected(self):
        self.rows.append(dict(self.rows[0]))
        self.write_report()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            filtering.filter_dataset(self.dataset, self.output, None, "test-model")
        self.assertFalse(self.output.exists())
        self.rows.pop()
        self.write_report()
        (self.dataset / "passed/extra.html").write_bytes(self.html)
        with self.assertRaisesRegex(ValueError, "does not match"):
            filtering.filter_dataset(self.dataset, self.output, None, "test-model")
        self.assertFalse(self.output.exists())

    def test_existing_and_overlapping_outputs_are_untouched(self):
        self.output.mkdir()
        sentinel = self.output / "results.csv"
        sentinel.write_text("existing results")
        for output in (self.output, self.dataset, self.dataset / "nested", self.root):
            with self.subTest(output=output), self.assertRaises(ValueError):
                filtering.filter_dataset(self.dataset, output, None, "test-model")
        self.assertEqual(sentinel.read_text(), "existing results")
        self.assertEqual((self.dataset / "passed/example_0.html").read_bytes(), self.html)


if __name__ == "__main__":
    unittest.main()
