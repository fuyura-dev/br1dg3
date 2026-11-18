import json
import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from app.services.repair import failed_runs

with patch("google.genai.Client"):
    from app.services.repair.llm import LLMResult
    from app.services.repair.runner import RepairRun, Step


class TestFailedRunRecords(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.records_dir = Path(directory.name) / "failed_runs"
        self.enterContext(patch.object(failed_runs, "FAILED_RUNS_DIR", self.records_dir))
        self.original = '<html><body><script>keep()</script><img src="café.png"></body></html>'
        self.prepared = '<html><body><!--__BR1DG3_STASH_0__--><img src="café.png"></body></html>'
        self.violations = [{"id": "image-alt", "nodes": [{"target": ["img"]}]}]
        self.run = RepairRun(
            fixed_html='<html><body><img src="café.png" alt="Café"></body></html>',
            steps=[
                Step(
                    token="first", tag="img", rules=["image-alt"], status="applied",
                    original_node_id="n1", node_id="n2",
                    warnings=["Example warning"], related_relationships=["parent_child"],
                    llm=LLMResult(
                        text='\n<img src="café.png" alt="Café">\n',
                        ok=True, status="completed", model="test-model",
                        prompt_tokens=12, completion_tokens=7, thought_tokens=2,
                        total_tokens=21, latency_s=0.1, attempts=2,
                    ),
                ),
                Step(
                    token="second", tag="button", rules=["button-name"],
                    status="llm_error", error="Request failed", llm=None,
                ),
            ],
            unmapped=1,
        )

    def _save(self, use_sdg=True):
        return failed_runs.save_failed_run(
            original_html=self.original,
            evaluation_original_html=self.prepared,
            use_sdg=use_sdg,
            violations_before=self.violations,
            run=self.run,
            error=RuntimeError("Final scan failed"),
        )

    def test_saved_record_preserves_artifacts_replies_and_available_usage(self):
        original_run = asdict(self.run)

        record_id = self._save()
        record = json.loads((self.records_dir / f"{record_id}.json").read_text(encoding="utf-8"))

        self.assertEqual(UUID(record_id).hex, record_id)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["record_id"], record_id)
        self.assertEqual(datetime.fromisoformat(record["recorded_at"]).utcoffset(), timedelta(0))
        self.assertEqual(record["method"], "sdg")
        self.assertEqual(record["failure_stage"], "post_repair_scan")
        self.assertEqual(record["original_html"], self.original)
        self.assertEqual(record["evaluation_original_html"], self.prepared)
        self.assertEqual(record["violations_before"], self.violations)
        self.assertIsNone(record["violations_after"])
        self.assertEqual(record["scan_error"], {"type": "RuntimeError", "message": "Final scan failed"})
        self.assertEqual(record["repair_run"], original_run)
        self.assertEqual(record["repair_run"]["steps"][0]["llm"]["text"], self.run.steps[0].llm.text)
        self.assertIsNone(record["repair_run"]["steps"][1]["llm"])
        self.assertEqual(asdict(self.run), original_run)
        self.assertEqual(list(self.records_dir.iterdir()), [self.records_dir / f"{record_id}.json"])

    def test_repeated_failures_create_separate_records_without_overwriting(self):
        first_id = self._save(use_sdg=True)
        first_path = self.records_dir / f"{first_id}.json"
        first_content = first_path.read_bytes()

        second_id = self._save(use_sdg=False)
        second_record = json.loads((self.records_dir / f"{second_id}.json").read_text(encoding="utf-8"))

        self.assertNotEqual(first_id, second_id)
        self.assertEqual(first_path.read_bytes(), first_content)
        self.assertEqual(second_record["method"], "zero_shot")
        self.assertEqual(len(list(self.records_dir.glob("*.json"))), 2)

    def test_final_scan_failure_retains_generation_fallback_metadata(self):
        self.run = RepairRun(
            fixed_html=self.prepared,
            steps=[Step("baseline", None, ["image-alt"], "llm_error", error="Unavailable")],
            unmapped=0,
        )
        record_id = self._save(use_sdg=False)
        record = json.loads((self.records_dir / f"{record_id}.json").read_text(encoding="utf-8"))
        saved = record["repair_run"]
        self.assertEqual(saved["fixed_html"], self.prepared)
        self.assertIsNone(saved["candidate_html"])
        self.assertTrue(saved["fallback_used"])
        self.assertEqual(saved["generation_status"], "no_candidate")
        self.assertEqual(saved["steps"][0]["error"], "Unavailable")

    def test_write_failure_removes_partial_record(self):
        with (
            patch.object(failed_runs.os, "fsync", side_effect=OSError("Disk full")),
            self.assertRaisesRegex(OSError, "Disk full"),
        ):
            self._save()

        self.assertEqual(list(self.records_dir.iterdir()), [])

    def test_publish_failure_preserves_previous_records_and_removes_temp_file(self):
        first_id = self._save()
        first_path = self.records_dir / f"{first_id}.json"
        first_content = first_path.read_bytes()

        with (
            patch.object(Path, "replace", side_effect=OSError("Cannot publish record")),
            self.assertRaisesRegex(OSError, "Cannot publish record"),
        ):
            self._save()

        self.assertEqual(first_path.read_bytes(), first_content)
        self.assertEqual(list(self.records_dir.iterdir()), [first_path])

    def test_directory_creation_failure_does_not_overwrite_existing_file(self):
        self.records_dir.write_text("Existing file", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            self._save()

        self.assertEqual(self.records_dir.read_text(encoding="utf-8"), "Existing file")


if __name__ == "__main__":
    unittest.main()
