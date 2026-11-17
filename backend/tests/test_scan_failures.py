import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from app.api import evaluate as evaluate_api
from app.api import scan as scan_api
from app.services.detection import detect as detection
from app.services.validation import evaluator
from fastapi import HTTPException

# The repair route imports the LLM client; tests never generate real repairs.
with patch("google.genai.Client"):
    from app.api import repair as repair_api
    from app.services.repair.runner import RepairRun


class TestScanFailureHandling(unittest.TestCase):
    def setUp(self):
        self.html = '<html><body><img src="test.png"></body></html>'
        self.violations = [{"id": "image-alt", "nodes": [{"target": ["img"]}]}]
        self.error_result = {"error": "Axe crashed", "violations": []}
        self.driver = Mock()
        self.get_driver = self.enterContext(
            patch.object(detection, "_get_driver", return_value=self.driver)
        )
        self.enterContext(patch.object(evaluator.streamer, "log"))
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.dict(repair_api.cache, {}, clear=True))
        self.run_sdg = self.enterContext(patch.object(repair_api, "run_sdg"))
        self.run_baseline = self.enterContext(patch.object(repair_api, "run_baseline"))

    def _evaluate(self, **kwargs):
        return evaluate_api.evaluate_document_repair(
            evaluate_api.EvaluateRequest(
                html_original=self.html,
                html_repaired=self.html,
                **kwargs,
            )
        )

    def _assert_no_credit(self, response, expected_before):
        result = response.effectiveness
        self.assertTrue(result["scan_failed"])
        self.assertEqual(result["violations_before"], expected_before)
        self.assertEqual(result["violations_after"], expected_before)
        self.assertEqual(result["violations_reduced"], 0)
        self.assertEqual(result["reduction_rate"], 0)
        self.assertFalse(result["compliance_improved"])
        self.assertFalse(result["fully_fixed"])

    def test_evaluate_failed_initial_scan_is_503(self):
        self.driver.execute_async_script.return_value = self.error_result

        with self.assertRaises(HTTPException) as caught:
            self._evaluate()

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("Pre-repair", caught.exception.detail)
        self.assertIn("Axe crashed", caught.exception.detail)
        self.driver.execute_async_script.assert_called_once()
        self.driver.quit.assert_called_once()

    def test_evaluate_unavailable_browser_is_503(self):
        self.get_driver.side_effect = RuntimeError("Chrome unavailable")

        with self.assertRaises(HTTPException) as caught:
            self._evaluate(violations_after=[])

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("Chrome unavailable", caught.exception.detail)

    def test_evaluate_missing_initial_scan_with_detection_disabled_is_422(self):
        with self.assertRaises(HTTPException) as caught:
            self._evaluate(violations_after=[], run_detection_if_missing=False)

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("violations_before", caught.exception.detail)
        self.get_driver.assert_not_called()

    def test_evaluate_successful_empty_scans_remain_valid(self):
        self.driver.execute_async_script.return_value = {"violations": []}

        response = self._evaluate()

        self.assertEqual(response.effectiveness["violations_before"], 0)
        self.assertEqual(response.effectiveness["violations_after"], 0)
        self.assertFalse(response.effectiveness["scan_failed"])
        self.assertTrue(response.effectiveness["fully_fixed"])
        self.assertEqual(self.driver.quit.call_count, 2)

    def test_evaluate_failed_final_scan_gives_no_credit(self):
        self.driver.execute_async_script.side_effect = [
            {"violations": self.violations}, self.error_result,
        ]

        response = self._evaluate()

        self._assert_no_credit(response, expected_before=1)
        self.assertEqual(response.structure["structure_similarity"], 1)
        self.assertIn("preservation_rate", response.semantic)
        self.assertEqual(self.driver.quit.call_count, 2)

    def test_evaluate_failed_final_scan_is_not_fully_fixed_with_zero_before(self):
        self.driver.execute_async_script.return_value = self.error_result

        response = self._evaluate(violations_before=[])

        self._assert_no_credit(response, expected_before=0)

    def test_evaluate_missing_final_scan_with_detection_disabled_gives_no_credit(self):
        response = self._evaluate(
            violations_before=self.violations, run_detection_if_missing=False,
        )

        self._assert_no_credit(response, expected_before=1)
        self.get_driver.assert_not_called()

    def test_evaluate_precomputed_successful_results_skip_detection(self):
        response = self._evaluate(
            violations_before=self.violations,
            violations_after=[],
            run_detection_if_missing=False,
        )

        self.assertEqual(response.effectiveness["violations_reduced"], 1)
        self.assertTrue(response.effectiveness["fully_fixed"])
        self.assertFalse(response.effectiveness["scan_failed"])
        self.get_driver.assert_not_called()

    def test_scan_route_failure_is_503(self):
        self.driver.execute_async_script.return_value = self.error_result

        with self.assertRaises(HTTPException) as caught:
            scan_api.scan_html(scan_api.ScanRequest(html=self.html))

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("Axe crashed", caught.exception.detail)

    def test_scan_route_genuine_empty_result_is_successful(self):
        self.driver.execute_async_script.return_value = {"violations": []}

        response = scan_api.scan_html(scan_api.ScanRequest(html=self.html))

        self.assertEqual(response.total_issues, 0)
        self.assertEqual(response.issues, [])

    def test_repair_initial_scan_failure_skips_generation_and_cache(self):
        self.driver.execute_async_script.return_value = self.error_result
        for use_sdg in (True, False):
            with self.subTest(use_sdg=use_sdg):
                with self.assertRaises(HTTPException) as caught:
                    repair_api.repair_html(
                        repair_api.RepairRequest(html=self.html, use_sdg=use_sdg)
                    )
                self.assertEqual(caught.exception.status_code, 503)
                self.assertIn("Axe crashed", caught.exception.detail)

        self.run_sdg.assert_not_called()
        self.run_baseline.assert_not_called()
        self.assertEqual(repair_api.cache, {})

    def test_repair_final_scan_failure_does_not_return_or_cache_success(self):
        run = RepairRun(fixed_html=self.html, steps=[], unmapped=0)
        self.run_sdg.return_value = run
        self.run_baseline.return_value = run
        with patch.object(repair_api, "evaluate_repair") as evaluate:
            for use_sdg in (True, False):
                with self.subTest(use_sdg=use_sdg):
                    self.driver.execute_async_script.side_effect = [
                        {"violations": self.violations}, self.error_result,
                    ]
                    with self.assertRaises(HTTPException) as caught:
                        repair_api.repair_html(
                            repair_api.RepairRequest(html=self.html, use_sdg=use_sdg)
                        )
                    self.assertEqual(caught.exception.status_code, 503)
                    self.assertIn("Post-repair", caught.exception.detail)
                    self.assertIn("Axe crashed", caught.exception.detail)
            evaluate.assert_not_called()

        self.run_sdg.assert_called_once()
        self.run_baseline.assert_called_once()
        self.assertEqual(repair_api.cache, {})


if __name__ == "__main__":
    unittest.main()
