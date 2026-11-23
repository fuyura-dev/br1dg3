"""Check the audit with small synthetic files."""

import contextlib
import csv
import io
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

audit = import_module("experiments.scripts.01_audit_dataset")
audit_dataset = audit.audit_dataset
inspect_content = audit.inspect_content


class AuditDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.originals, self.reference = self.root / "originals", self.root / "reference"
        self.originals.mkdir()
        self.reference.mkdir()
        self.csv = self.root / "ground_truth.csv"
        self.csv.write_text(
            "filename,source\na.html,scraped_sites\nb.html,scraped_sites\nc.html,scraped_sites\nfixed.html,scraped_sites_fixed\n"
        )
        for folder in [self.originals, self.reference]:
            for name in ["a.html", "b.html", "c.html"]:
                (folder / name).write_bytes(
                    b"<html><head><title>Example</title></head><body>Example text</body></html>"
                )
        self.output = self.root / "report"

    def run_audit(self, output=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return audit_dataset(self.originals, self.reference, self.csv, output or self.output)

    def test_inventory_duplicates_missing_extra_and_unchanged_inputs(self):
        (self.originals / "c.html").unlink()
        (self.originals / "extra.html").write_bytes(b"<p>Extra</p>")
        before = {p: p.read_bytes() for folder in [self.originals, self.reference] for p in folder.iterdir()}
        rows = {r["filename"]: r for r in self.run_audit()}
        self.assertEqual(set(rows), {"a.html", "b.html", "c.html", "extra.html"})
        self.assertTrue(rows["a.html"]["reference_match"])
        self.assertEqual(rows["a.html"]["duplicate_group"], rows["b.html"]["sha256"])
        self.assertIsNone(rows["c.html"]["size_bytes"])
        self.assertIsNone(rows["c.html"]["reference_match"])
        self.assertIn("unexpected_file", rows["extra.html"]["flags"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        with (self.output / "inventory.csv").open(newline="") as handle:
            exported = {r["filename"]: r for r in csv.DictReader(handle)}
        self.assertEqual(exported["c.html"]["size_bytes"], "")
        self.assertEqual([p.name for p in self.output.iterdir()], ["inventory.csv"])

    def test_mismatch_and_missing_reference_are_distinct(self):
        (self.originals / "a.html").write_bytes(b"<p>Changed</p>")
        (self.reference / "b.html").unlink()
        (self.originals / "directory").mkdir()
        rows = {r["filename"]: r for r in self.run_audit()}
        self.assertFalse(rows["a.html"]["reference_match"])
        self.assertIsNone(rows["b.html"]["reference_match"])
        self.assertIn("reference_read_error", rows["b.html"]["flags"])
        self.assertIsNone(rows["directory"]["sha256"])
        self.assertIn("file_read_error", rows["directory"]["flags"])

    def test_basic_content_checks(self):
        title, _, _, flags = inspect_content(
            b"<html><head><title>Access Denied</title></head><body>Blocked</body></html>"
        )
        self.assertEqual(title, "Access Denied")
        self.assertIn("possible_error_page", flags)
        html = (
            b"<html><head><title>Example</title><script>blocked</script></head><body><svg><title>Icon</title></svg>"
            + b"Ordinary content. " * 20
            + b"</body></html>"
        )
        title, _, _, flags = inspect_content(html)
        self.assertEqual(title, "Example")
        self.assertEqual(flags, [])
        self.assertIn("little_text", inspect_content(b"<html><body></body></html>")[3])

    def test_output_protection_and_filename_validation(self):
        self.run_audit()
        before = (self.output / "inventory.csv").read_bytes()
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertEqual(before, (self.output / "inventory.csv").read_bytes())
        with self.assertRaises(ValueError):
            self.run_audit(self.originals / "report")
        self.csv.write_text("filename,source\n../outside.html,scraped_sites\n")
        with self.assertRaises(ValueError):
            self.run_audit(self.root / "another-report")


if __name__ == "__main__":
    unittest.main()
