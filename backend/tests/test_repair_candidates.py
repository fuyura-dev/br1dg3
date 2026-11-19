import unittest
from dataclasses import asdict
from unittest.mock import patch

from app.api import evaluate as evaluate_api
from app.services.detection.detect import ScanResult
from app.services.validation.evaluator import MissingInitialScanError, evaluate_repair
from tests.repair_fixtures import sdg_reply

with patch("google.genai.Client"):
    from app.api import repair as repair_api
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


class TestRepairCandidates(unittest.TestCase):
    def setUp(self):
        self.html = (
            '<!DOCTYPE html>\n<html><body><label id="label" for="field">Name</label>'
            '<input id="field"><img id="photo" src="photo.png">'
            '<button id="submit"></button></body></html>'
        )
        self.violations = [self._violation("image-alt", "#photo")]
        self.enterContext(patch.object(runner.streamer, "log"))
        self.generate = self.enterContext(patch.object(runner, "generate"))
        self.enterContext(patch.dict(repair_api.cache, {}, clear=True))

    def _violation(self, rule, selector):
        return {
            "id": rule, "impact": "critical", "description": "Test issue",
            "help": "Test help", "helpUrl": "https://example.test/rule",
            "nodes": [{"target": [selector], "html": "<img>"}],
        }

    def _reply(self, text, ok=True, status="completed"):
        return LLMResult(
            text=text, ok=ok, status=status, model="test-model",
            prompt_tokens=10, completion_tokens=5, thought_tokens=2,
            total_tokens=17, latency_s=0.1, attempts=1,
        )

    def _evaluate(self, run, **kwargs):
        return evaluate_repair(
            html_original=self.html, html_repaired=run.fixed_html,
            violations_before=self.violations, violations_after=[],
            repair_run=run, run_detection_if_missing=False, **kwargs,
        )

    def _scan_results(self):
        return [ScanResult(v, {"axe": {"violations": v}}) for v in (self.violations, [])]

    def _assert_no_credit(self, report):
        self.assertEqual(report.evaluation["score_basis"], "no_candidate_failure_policy")
        self.assertTrue(report.evaluation["fallback_used"])
        self.assertTrue(report.effectiveness.no_candidate)
        self.assertFalse(report.effectiveness.scan_failed)
        self.assertEqual(report.effectiveness.reduction_rate, 0)
        self.assertEqual(report.effectiveness.violations_after, report.effectiveness.violations_before)
        self.assertFalse(report.effectiveness.compliance_improved)
        self.assertFalse(report.effectiveness.fully_fixed)
        self.assertEqual(report.safety.score, 0)
        self.assertEqual(report.safety.reason, "no_candidate")
        self.assertEqual(report.structure.structure_similarity, 0)
        self.assertFalse(report.structure.structure_preserved)
        self.assertIsNone(report.structure.tree_edit_distance)
        self.assertIsNone(report.structure.repaired_nodes)
        self.assertIsNone(report.structure.max_nodes)
        self.assertFalse(report.structure.unparseable)
        self.assertTrue(report.semantic.has_dependencies)
        self.assertEqual(report.semantic.dependencies_valid, 0)
        self.assertEqual(report.semantic.preservation_rate, 0)
        self.assertIsNone(report.semantic.broken_count)
        self.assertEqual(report.semantic.broken_examples, [])

    def test_baseline_rejected_replies_keep_raw_output_without_fallback_credit(self):
        cases = [
            (self._reply("\nnot HTML\n"), "not_html"),
            (self._reply("   "), "empty_reply"),
            (self._reply("", ok=False, status="empty"), "llm_not_ok:empty"),
            (self._reply("<html><body>", ok=False, status="incomplete"), "llm_not_ok:incomplete"),
        ]
        for reply, status in cases:
            with self.subTest(status=status):
                self.generate.return_value = reply
                run = runner.run_baseline(self.html, self.violations)
                self.assertEqual(run.fixed_html, runner.preprocess(self.html))
                self.assertIsNone(run.candidate_html)
                self.assertTrue(run.fallback_used)
                self.assertEqual(run.generation_status, "no_candidate")
                self.assertEqual(run.steps[0].status, status)
                self.assertEqual(run.steps[0].llm.text, reply.text)
                self.assertIsNone(run.steps[0].candidate_html)
                report = self._evaluate(run)
                self._assert_no_credit(report)
                self.assertEqual(report.efficiency.total_tokens, 17)
                self.assertEqual(report.efficiency.api_calls, 1)
                self.assertGreater(report.efficiency.cost_usd, 0)

    def test_baseline_exception_has_failure_status_and_no_candidate(self):
        self.generate.side_effect = RuntimeError("Model unavailable")
        run = runner.run_baseline(self.html, self.violations)
        self.assertEqual(run.steps[0].status, "llm_error")
        self.assertIn("Model unavailable", run.steps[0].error)
        self.assertIsNone(run.steps[0].llm)
        self._assert_no_credit(self._evaluate(run))

    def test_baseline_accepted_identical_output_is_evaluated(self):
        self.generate.return_value = self._reply(f"\n```html\n{self.html}\n```\n")
        run = runner.run_baseline(self.html, self.violations)
        self.assertEqual(run.candidate_html, self.html)
        self.assertEqual(run.steps[0].candidate_html, self.html)
        self.assertEqual(run.generation_status, "accepted")
        self.assertFalse(run.fallback_used)
        report = self._evaluate(run)
        self.assertEqual(report.evaluation["artifact"], "candidate")
        self.assertEqual(report.safety.score, 1)
        self.assertEqual(report.structure.structure_similarity, 1)
        self.assertEqual(report.semantic.preservation_rate, 100)

    def test_sdg_all_failed_steps_have_no_candidate(self):
        self.generate.side_effect = [self._reply("not HTML"), RuntimeError("Unavailable")]
        violations = self.violations + [self._violation("button-name", "#submit")]
        run = runner.run_sdg(self.html, violations)
        self.assertEqual(run.failed_steps, 2)
        self.assertTrue(run.fallback_used)
        self.assertIsNone(run.candidate_html)
        self._assert_no_credit(self._evaluate(run))
        self.assertEqual(self.generate.call_count, 2)

    def test_accepted_baseline_with_parse_errors_keeps_its_output(self):
        reply = self.html + "</span>"
        self.generate.return_value = self._reply(reply)
        run = runner.run_baseline(self.html, self.violations)
        report = self._evaluate(run)
        self.assertEqual(run.fixed_html, reply)
        self.assertEqual(run.candidate_html, reply)
        self.assertEqual(run.generation_status, "accepted")
        self.assertFalse(run.fallback_used)
        self.assertEqual(report.safety.score, 0)
        self.assertEqual(report.safety.reason, "parse_errors")
        self.assertEqual(report.structure.structure_similarity, 1)
        self.assertEqual(self.generate.call_count, 1)

    def test_evaluate_api_returns_parse_error_details(self):
        response = evaluate_api.evaluate_document_repair(evaluate_api.EvaluateRequest(
            html_original=self.html, html_repaired=self.html + "</span>",
            violations_before=self.violations, violations_after=[], run_detection_if_missing=False,
        ))
        safety = response.model_dump()["safety"]
        self.assertEqual(safety["score"], 0)
        self.assertEqual(safety["parser"], "html5lib")
        self.assertEqual(safety["parser_version"], "1.1")
        self.assertEqual(safety["parse_mode"], "document")
        self.assertEqual(safety["error_count"], 2)
        self.assertIn("unexpected-end-tag", [error["code"] for error in safety["errors"]])

    def test_sdg_empty_and_incomplete_replies_do_not_create_candidates(self):
        for reply in (self._reply(" "), self._reply("<img", ok=False, status="incomplete")):
            with self.subTest(reply=reply):
                self.generate.return_value = reply
                run = runner.run_sdg(self.html, self.violations)
                self.assertIsNone(run.candidate_html)
                self.assertTrue(run.fallback_used)
                self._assert_no_credit(self._evaluate(run))

    def test_sdg_partial_candidate_survives_a_later_failed_step(self):
        def generate(prompt):
            if self.generate.call_count == 1:
                return self._reply(sdg_reply('<img id="photo" src="photo.png" alt="Photo">'))
            return self._reply("not HTML")

        self.generate.side_effect = generate
        violations = self.violations + [self._violation("button-name", "#submit")]
        # Freeze only the order; exercise actual context extraction and patching.
        with patch.object(runner, "order_violations_by_dependency", side_effect=lambda graph, units: units):
            run = runner.run_sdg(self.html, violations)
        self.assertEqual(run.generation_status, "partial")
        self.assertEqual(run.failed_steps, 1)
        self.assertFalse(run.fallback_used)
        self.assertIn('alt="Photo"', run.candidate_html)
        self.assertNotIn("data-br1dg3", run.candidate_html)
        self.assertEqual(run.candidate_html, run.fixed_html)
        self.assertIsNotNone(run.steps[0].candidate_html)
        self.assertIsNone(run.steps[1].candidate_html)
        report = self._evaluate(run)
        self.assertEqual(report.evaluation["score_basis"], "artifact_measurement")
        self.assertEqual(report.safety.score, 1)
        self.assertGreater(report.structure.structure_similarity, 0)
        self.assertEqual(report.efficiency.api_calls, 2)

    def test_sdg_accepted_unchanged_patch_still_produces_candidate(self):
        self.generate.return_value = self._reply(sdg_reply('<img id="photo" src="photo.png">'))
        run = runner.run_sdg(self.html, self.violations)
        self.assertEqual(run.generation_status, "accepted")
        self.assertFalse(run.fallback_used)
        self.assertEqual(self._evaluate(run).structure.structure_similarity, 1)

    def test_sdg_unmapped_targets_are_not_generated_candidates(self):
        run = runner.run_sdg(self.html, [self._violation("image-alt", "#missing")])
        self.generate.assert_not_called()
        self.assertEqual(run.unmapped, 1)
        self.assertEqual(run.generation_status, "no_candidate")
        self._assert_no_credit(self._evaluate(run))

    def test_sdg_candidate_with_unmapped_targets_is_partial(self):
        self.generate.return_value = self._reply(sdg_reply('<img id="photo" src="photo.png" alt="Photo">'))
        run = runner.run_sdg(
            self.html, self.violations + [self._violation("button-name", "#missing")],
        )
        self.assertEqual(run.generation_status, "partial")
        self.assertEqual(run.unmapped, 1)
        self.assertFalse(run.fallback_used)
        self.assertIsNotNone(run.candidate_html)

    def test_sdg_all_skipped_targets_are_not_generated_candidates(self):
        html = '<main><p id="text">Text</p></main>'
        # Historical all-skip records still do not establish a generated candidate.
        # New runs require an earlier accepted patch before inferring any skip.
        run = runner.RepairRun(html, [runner.Step("v1", "p", ["region"], "cascade_resolved")], 0)
        self.generate.assert_not_called()
        self.assertEqual(run.steps[0].status, "cascade_resolved")
        self.assertEqual(run.failed_steps, 0)
        self.assertEqual(run.generation_status, "no_candidate")
        self.assertTrue(run.fallback_used)

    def test_no_violations_requires_no_generation_and_is_not_a_failure(self):
        for method in (runner.run_baseline, runner.run_sdg):
            with self.subTest(method=method.__name__):
                run = method(self.html, [])
                self.assertEqual(run.generation_status, "not_needed")
                self.assertFalse(run.fallback_used)
                self.assertIsNone(run.candidate_html)
        self.generate.assert_not_called()

    def test_saved_run_data_distinguishes_fallback_and_candidate(self):
        self.generate.return_value = self._reply("not HTML")
        run = runner.run_baseline(self.html, self.violations)
        saved = asdict(run)
        self.assertTrue(saved["fallback_used"])
        self.assertEqual(saved["generation_status"], "no_candidate")
        self.assertIsNone(saved["candidate_html"])
        self.assertEqual(saved["steps"][0]["llm"]["text"], "not HTML")

    def test_evaluate_api_accepts_explicit_fallback_status_for_saved_runs(self):
        with patch("app.services.validation.evaluator.scan_with_report") as detect:
            response = evaluate_api.evaluate_document_repair(evaluate_api.EvaluateRequest(
                html_original=self.html, html_repaired=self.html,
                violations_before=self.violations, fallback_used=True,
                efficiency_data={"api_calls": 1, "prompt_tokens": 10, "completion_tokens": 5},
            ))
        detect.assert_not_called()
        self.assertEqual(response.evaluation["score_basis"], "no_candidate_failure_policy")
        self.assertEqual(response.structure["structure_similarity"], 0)
        self.assertFalse(response.effectiveness["scan_failed"])
        self.assertEqual(response.efficiency["total_tokens"], 15)

    def test_explicit_fallback_cannot_be_fully_fixed_even_with_zero_original_issues(self):
        report = evaluate_repair(
            self.html, self.html, [], [], fallback_used=True, run_detection_if_missing=False,
        )
        self.assertFalse(report.effectiveness.fully_fixed)
        self.assertEqual(report.effectiveness.reduction_rate, 0)

    def test_no_dependencies_remains_not_applicable_on_failure(self):
        plain = "<div>Text</div>"
        report = evaluate_repair(
            plain, plain, self.violations, [], fallback_used=True, run_detection_if_missing=False,
        )
        self.assertFalse(report.semantic.has_dependencies)
        self.assertIsNone(report.semantic.preservation_rate)
        self.assertEqual(report.semantic.dependencies_before, 0)

    def test_evaluate_fallback_still_requires_a_successful_initial_scan(self):
        with self.assertRaisesRegex(MissingInitialScanError, "violations_before"):
            evaluate_repair(
                self.html, self.html, fallback_used=True, run_detection_if_missing=False,
            )

    def test_plain_evaluation_does_not_guess_failure_from_identical_html(self):
        report = evaluate_repair(
            self.html, self.html, self.violations, self.violations, run_detection_if_missing=False,
        )
        self.assertEqual(report.evaluation["artifact"], "supplied_html")
        self.assertEqual(report.structure.structure_similarity, 1)
        self.assertEqual(report.safety.score, 1)
        self.assertFalse(report.effectiveness.no_candidate)

    def test_repair_api_returns_fallback_status_and_preserves_it_in_cache(self):
        raw_reply = "\nnot HTML\n"
        for use_sdg in (True, False):
            with self.subTest(use_sdg=use_sdg):
                self.generate.return_value = self._reply(raw_reply)
                self.generate.reset_mock()
                with patch.object(repair_api, "scan_with_report", side_effect=self._scan_results()) as detect:
                    request = repair_api.RepairRequest(html=self.html, use_sdg=use_sdg)
                    response = repair_api.repair_html(request)
                    cached = repair_api.repair_html(request)
                self.assertEqual(detect.call_count, 2)
                self.generate.assert_called_once()
                self.assertTrue(response.generation["fallback_used"])
                self.assertIsNone(response.candidate_html)
                self.assertEqual(response.steps[0]["raw_reply"], raw_reply)
                self.assertIsNone(response.steps[0]["candidate_html"])
                self.assertIn("fallback HTML returned", response.summary)
                self.assertEqual(response.metrics["safety"]["score"], 0)
                self.assertEqual(response.metrics["structure"]["structure_similarity"], 0)
                self.assertTrue(cached.cache_hit)
                self.assertEqual(cached.generation, response.generation)
                self.assertEqual(cached.metrics, response.metrics)

    def test_candidate_and_restored_user_output_are_both_available(self):
        html = self.html.replace("<body>", "<body><script>keep()</script>")
        self.generate.return_value = self._reply(
            self.html.replace('<img id="photo"', '<img alt="Photo" id="photo"')
        )
        with patch.object(repair_api, "scan_with_report", side_effect=self._scan_results()):
            response = repair_api.repair_html(repair_api.RepairRequest(
                html=html, use_sdg=False, use_cache=False,
            ))
        self.assertEqual(response.generation["status"], "accepted")
        self.assertIn("<script>keep()</script>", response.fixed_html)
        self.assertNotIn("<script>", response.candidate_html)
        self.assertEqual(response.metrics["evaluation"]["artifact"], "candidate")


if __name__ == "__main__":
    unittest.main()
