import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock, patch

from app.api import evaluate as evaluate_api
from app.api import scan as scan_api
from app.services.detection import detect as detection
from app.services.detection.preprocess import preprocess
from app.services.repair import failed_runs
from fastapi import HTTPException

with patch("google.genai.Client"):
    from app.api import repair as repair_api
    from app.services.repair.runner import RepairRun, Step


class TestScanReports(unittest.TestCase):
    def setUp(self):
        self.html = '<!DOCTYPE html><html><body><img src="photo.png"></body></html>'
        self.selected = {"id": "image-alt", "nodes": [{"target": ["img"], "html": '<img src="photo.png">'}]}
        self.excluded = {"id": "color-contrast", "nodes": [{"target": ["p"]}]}
        self.review = {"id": "label", "nodes": [{"target": ["input"]}]}
        self.driver = Mock()
        self.enterContext(patch.object(detection, "_get_driver", return_value=self.driver))
        self.enterContext(patch.object(detection, "_wait_for_stylesheets", return_value=[]))
        self.enterContext(patch.object(repair_api.streamer, "log"))
        self.enterContext(patch.dict(repair_api.cache, {}, clear=True))
        self.enterContext(redirect_stdout(io.StringIO()))
        self.run = RepairRun(
            fixed_html=self.html.replace("<img ", '<img alt="Photo" '),
            steps=[Step("image", "img", ["image-alt"], "applied")], unmapped=0,
        )
        self.run_sdg = self.enterContext(patch.object(repair_api, "run_sdg", return_value=self.run))
        self.run_baseline = self.enterContext(patch.object(repair_api, "run_baseline", return_value=self.run))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.records_dir = Path(directory.name) / "failed_runs"
        self.enterContext(patch.object(failed_runs, "FAILED_RUNS_DIR", self.records_dir))

    def _report(self, violations):
        return deepcopy({
            "violations": violations,
            "passes": [{"id": "html-has-lang", "nodes": [{"target": ["html"]}]}],
            "incomplete": [self.review],
            "inapplicable": [{"id": "video-caption", "nodes": []}],
            "testEngine": {"name": "axe-core", "version": "4.10.3"},
            "testEnvironment": {"userAgent": "test-browser", "windowWidth": 1200, "windowHeight": 800},
            "timestamp": "2026-11-18T02:00:00.000Z",
            "url": "data:text/html,",
        })

    def _evaluate(self, **kwargs):
        return evaluate_api.evaluate_document_repair(evaluate_api.EvaluateRequest(
            html_original=self.html, html_repaired=self.run.fixed_html, **kwargs,
        ))

    def test_scan_retains_raw_report_and_keeps_repair_inputs_independent(self):
        raw = self._report([self.selected, self.excluded])
        self.driver.execute_async_script.return_value = raw
        html = self.html.replace("</body>", "<script>keep()</script><style>p{color:red}</style></body>")
        result = detection.scan_with_report(html)
        self.assertEqual(result.violations, [self.selected])
        self.assertEqual(result.report["axe"], raw)
        self.assertEqual(result.report["selected_rule_ids"], list(detection.RELEVANT_RULES))
        self.assertEqual(result.report["removed_elements"], ["script", "style"])
        self.assertEqual(result.report["prepared_html_sha256"], sha256(preprocess(html).encode()).hexdigest())
        result.violations[0]["nodes"][0]["target"] = ["changed-by-caller"]
        self.assertEqual(raw["violations"][0]["nodes"][0]["target"], ["img"])
        self.driver.execute_async_script.assert_called_once()
        self.driver.quit.assert_called_once()

    def test_legacy_detect_still_returns_only_selected_violations(self):
        self.driver.execute_async_script.return_value = self._report([self.selected, self.excluded])
        self.assertEqual(detection.detect(self.html), [self.selected])
        self.driver.execute_async_script.assert_called_once()

    def test_scan_api_keeps_selected_issue_count_and_full_report(self):
        raw = self._report([self.selected, self.excluded])
        self.driver.execute_async_script.return_value = raw
        response = scan_api.scan_html(scan_api.ScanRequest(html=self.html))
        self.assertEqual(response.total_issues, 1)
        self.assertEqual([issue.id for issue in response.issues], ["image-alt"])
        self.assertEqual(response.model_dump()["scan_report"]["axe"], raw)
        self.driver.execute_async_script.assert_called_once()

    def test_both_repair_methods_keep_scoped_inputs_metrics_and_cached_reports(self):
        for use_sdg in (True, False):
            with self.subTest(use_sdg=use_sdg):
                self.driver.reset_mock()
                before = self._report([self.selected, self.excluded])
                after = self._report([self.excluded])
                self.driver.execute_async_script.side_effect = [before, after]
                request = repair_api.RepairRequest(html=self.html, use_sdg=use_sdg)
                response = repair_api.repair_html(request)
                cached = repair_api.repair_html(request)
                method = self.run_sdg if use_sdg else self.run_baseline
                method.assert_called_once_with(self.html, [self.selected])
                self.assertEqual(response.issues_before, 1)
                self.assertEqual(response.issues_after, 0)
                self.assertEqual(response.metrics["effectiveness"]["violations_reduced"], 1)
                self.assertTrue(response.metrics["effectiveness"]["fully_fixed"])
                self.assertEqual(response.scan_reports["before"]["axe"], before)
                self.assertEqual(response.scan_reports["after"]["axe"], after)
                self.assertEqual(cached.scan_reports, response.scan_reports)
                self.assertTrue(cached.cache_hit)
                self.assertNotIn("scan_reports", response.metrics)
                response.scan_reports["before"]["axe"]["violations"].clear()
                cached.scan_reports["after"]["axe"]["incomplete"].clear()
                fresh_copy = repair_api.repair_html(request)
                self.assertEqual(len(fresh_copy.scan_reports["before"]["axe"]["violations"]), 2)
                self.assertEqual(fresh_copy.scan_reports["after"]["axe"]["incomplete"], [self.review])
                self.assertEqual(self.driver.execute_async_script.call_count, 2)
                self.assertEqual(self.driver.quit.call_count, 2)
        self.assertFalse(self.records_dir.exists())

    def test_no_selected_violations_retains_report_without_repair_or_final_scan(self):
        raw = self._report([self.excluded])
        self.driver.execute_async_script.return_value = raw
        response = repair_api.repair_html(repair_api.RepairRequest(html=self.html))
        self.assertEqual(response.issues_before, 0)
        self.assertEqual(response.summary, "No confirmed selected-rule violations detected.")
        self.assertEqual(response.scan_reports["before"]["axe"], raw)
        self.assertIsNone(response.scan_reports["after"])
        self.assertIsNone(response.metrics)
        self.assertEqual(response.fixed_html, self.html)
        self.run_sdg.assert_not_called()
        self.run_baseline.assert_not_called()
        self.driver.execute_async_script.assert_called_once()

    def test_evaluate_automatic_scans_preserve_all_outcomes_without_counting_them(self):
        before = self._report([self.selected, self.excluded])
        after = self._report([self.excluded])
        self.driver.execute_async_script.side_effect = [before, after]
        response = self._evaluate()
        self.assertEqual(response.effectiveness["violations_before"], 1)
        self.assertEqual(response.effectiveness["violations_after"], 0)
        self.assertTrue(response.effectiveness["fully_fixed"])
        self.assertEqual(response.scan_reports["before"]["axe"], before)
        self.assertEqual(response.scan_reports["after"]["axe"], after)
        self.assertEqual(self.driver.execute_async_script.call_count, 2)

    def test_saved_violation_lists_do_not_invent_reports_or_trigger_scans(self):
        response = self._evaluate(
            violations_before=[self.selected], violations_after=[], run_detection_if_missing=False,
        )
        self.assertEqual(response.scan_reports, {"before": None, "after": None})
        self.assertEqual(response.effectiveness["violations_reduced"], 1)
        self.driver.execute_async_script.assert_not_called()

    def test_mixed_saved_and_automatic_scan_retains_only_actual_report(self):
        raw = self._report([self.selected, self.excluded])
        self.driver.execute_async_script.return_value = raw
        response = self._evaluate(violations_after=[])
        self.assertEqual(response.scan_reports["before"]["axe"], raw)
        self.assertIsNone(response.scan_reports["after"])
        self.driver.execute_async_script.assert_called_once()

    def test_evaluation_final_failure_keeps_initial_evidence_and_no_credit(self):
        before = self._report([self.selected, self.excluded])
        self.driver.execute_async_script.side_effect = [before, {"error": "Axe failed"}]
        response = self._evaluate()
        self.assertTrue(response.effectiveness["scan_failed"])
        self.assertFalse(response.effectiveness["fully_fixed"])
        self.assertEqual(response.scan_reports["before"]["axe"], before)
        self.assertIsNone(response.scan_reports["after"])

    def test_repair_final_failure_saves_complete_initial_report(self):
        before = self._report([self.selected, self.excluded])
        self.driver.execute_async_script.side_effect = [before, {"error": "Axe failed"}]
        with self.assertRaises(HTTPException) as caught:
            repair_api.repair_html(repair_api.RepairRequest(html=self.html))
        self.assertEqual(caught.exception.status_code, 503)
        record = json.loads(next(self.records_dir.glob("*.json")).read_text())
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["scan_reports"]["before"]["axe"], before)
        self.assertIsNone(record["scan_reports"]["after"])
        self.assertEqual(record["violations_before"], [self.selected])
        self.assertIn("Axe failed", record["scan_error"]["message"])
        self.assertEqual(self.driver.execute_async_script.call_count, 2)
        self.assertEqual(repair_api.cache, {})


if __name__ == "__main__":
    unittest.main()
