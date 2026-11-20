import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from google.genai._gaos.types.interactions.usage import Usage

from app.services.repair.usage import TOKEN_FIELDS

with patch("google.genai.Client"):
    from app.api.repair import _serialize_steps
    from app.services.repair import failed_runs, llm, runner
    from app.services.repair.prompt import Prompt
    from app.services.validation.evaluator import evaluate_repair


class TransientError(Exception):
    status_code = 503


class TestUsageRecording(unittest.TestCase):
    def setUp(self):
        self.create = Mock()
        self.enterContext(patch.object(llm, "client", SimpleNamespace(interactions=SimpleNamespace(create=self.create))))
        self.sleep = self.enterContext(patch.object(llm.time, "sleep"))
        self.enterContext(patch.object(runner.streamer, "log"))
        self.enterContext(patch.object(runner, "generate", llm.generate))
        self.prompt = Prompt("System", "User")
        self.html = '<div><img id="photo"></div>'
        self.violations = [{"id": "image-alt", "nodes": [{"target": ["#photo"]}]}]
        self.usage = {"total_input_tokens": 10, "total_output_tokens": 5, "total_thought_tokens": 2, "total_tokens": 19}

    def response(self, usage=None, status="completed", text='<div><img id="photo" alt="Photo"></div>'):
        return SimpleNamespace(status=status, usage=usage, output_text=text)

    def run_baseline(self):
        return runner.run_baseline(self.html, self.violations)

    def evaluate(self, run):
        return evaluate_repair(
            self.html, run.fixed_html, violations_before=self.violations, violations_after=[], repair_run=run,
        )

    def test_sdk_usage_preserves_extra_fields_and_provider_total(self):
        usage = Usage(**self.usage, total_cached_tokens=3, total_tool_use_tokens=2)
        self.create.return_value = self.response(usage)
        result = llm.generate(self.prompt)
        self.assertEqual(result.raw_usage, {**self.usage, "total_cached_tokens": 3, "total_tool_use_tokens": 2})
        self.assertEqual(result.total_tokens, 19)  # Components sum to 17; retain the provider value.
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.attempt_records[0].raw_usage, result.raw_usage)
        self.assertTrue(result.ok)

    def test_missing_usage_is_unknown(self):
        self.create.return_value = self.response()
        result = llm.generate(self.prompt)
        self.assertIsNone(result.raw_usage)
        for name in TOKEN_FIELDS:
            self.assertIsNone(getattr(result, name))
        self.assertTrue(result.ok)  # Usage availability does not determine reply acceptance.

    def test_reported_zero_is_preserved_and_not_replaced_with_component_sum(self):
        self.create.return_value = self.response({**self.usage, "total_tokens": 0, "total_thought_tokens": 0})
        result = llm.generate(self.prompt)
        self.assertEqual(result.total_tokens, 0)
        self.assertEqual(result.thought_tokens, 0)

    def test_missing_total_is_not_invented_from_components(self):
        usage = {k: v for k, v in self.usage.items() if k != "total_tokens"}
        self.create.return_value = self.response(usage)
        run = self.run_baseline()
        self.assertIsNone(run.total_tokens)
        self.assertEqual(run.prompt_tokens, 10)
        self.assertIsNone(self.evaluate(run).efficiency.total_tokens)

    def test_malformed_counts_remain_in_raw_usage_but_normalize_to_unknown(self):
        usage = dict(zip(self.usage, [True, -1, "2", 1.5]))
        self.create.return_value = self.response(usage)
        result = llm.generate(self.prompt)
        self.assertEqual(result.raw_usage, usage)
        for name in TOKEN_FIELDS:
            self.assertIsNone(getattr(result, name))

    def test_retry_success_keeps_attempts_and_reported_subtotal(self):
        self.create.side_effect = [TransientError("Try again"), self.response(self.usage)]
        run = self.run_baseline()
        self.assertEqual(run.steps[0].status, "applied")
        self.assertEqual(run.api_calls, 1)
        self.assertEqual(run.requests, 2)
        self.assertIsNone(run.total_tokens)
        summary = run.usage_summary()
        self.assertEqual(summary["reported_usage"]["total_tokens"], 19)
        self.assertFalse(summary["usage_complete"]["total_tokens"])
        self.assertIsNone(self.evaluate(run).efficiency.cost_usd)
        self.assertEqual(self.create.call_args_list[0], self.create.call_args_list[1])
        self.sleep.assert_called_once_with(1)

    def test_exhausted_attempts_are_saved_for_both_methods(self):
        for method in (runner.run_baseline, runner.run_sdg):
            with self.subTest(method=method.__name__):
                self.create.reset_mock()
                self.sleep.reset_mock()
                self.create.side_effect = TransientError("Unavailable")
                run = method(self.html, self.violations)
                self.assertEqual(run.steps[0].status, "llm_error")
                self.assertTrue(run.fallback_used)
                self.assertEqual(run.api_calls, 1)
                self.assertEqual(run.requests, 4)
                self.assertIsNone(run.total_tokens)
                self.assertEqual(len(run.steps[0].llm.attempt_records), 4)
                self.assertEqual(self.create.call_count, 4)
                self.assertEqual(self.sleep.call_args_list, [call(1), call(2), call(4)])
                for record in run.steps[0].llm.attempt_records:
                    self.assertIsNone(record.raw_usage)
                    self.assertIn("Unavailable", record.error)

    def test_nontransient_failure_has_one_attempt(self):
        self.create.side_effect = ValueError("Bad request")
        run = self.run_baseline()
        self.assertEqual(run.requests, 1)
        self.assertEqual(run.steps[0].status, "llm_error")
        self.sleep.assert_not_called()

    def test_explicit_error_usage_is_retained_and_summed_when_reported(self):
        error = TransientError("Retry with usage")
        error.body = {"usage": {key: 0 for key in self.usage}}
        self.create.side_effect = [error, self.response(self.usage)]
        run = self.run_baseline()
        self.assertEqual(run.requests, 2)
        self.assertEqual(run.total_tokens, 19)
        self.assertTrue(all(run.usage_summary()["usage_complete"].values()))
        self.assertEqual(run.steps[0].llm.attempt_records[0].raw_usage, error.body["usage"])

    def test_partial_error_usage_preserves_field_specific_coverage(self):
        error = TransientError("Partial usage")
        error.usage = {"total_input_tokens": 4}
        self.create.side_effect = [error, self.response(self.usage)]
        run = self.run_baseline()
        self.assertEqual(run.prompt_tokens, 14)
        self.assertIsNone(run.completion_tokens)
        self.assertEqual(run.usage_summary()["reported_usage"]["completion_tokens"], 5)

    def test_incomplete_and_unapplicable_replies_still_retain_usage(self):
        for status, text, expected in (("incomplete", "<html>", "llm_not_ok:incomplete"),
                                       ("completed", "not HTML", "not_html")):
            with self.subTest(status=status):
                self.create.return_value = self.response(self.usage, status, text)
                run = self.run_baseline()
                self.assertEqual(run.steps[0].status, expected)
                self.assertEqual(run.total_tokens, 19)
                self.assertEqual(self.evaluate(run).efficiency.total_tokens, 19)

    def test_elapsed_time_covers_generation_and_last_latency_is_separate(self):
        self.create.side_effect = [TransientError("Retry"), self.response(self.usage)]
        with patch.object(llm.time, "perf_counter", side_effect=[0, 1, 2, 4, 5, 6]):
            result = llm.generate(self.prompt)
        self.assertEqual(result.elapsed_s, 6)
        self.assertEqual(result.latency_s, 1)
        self.assertEqual([a.latency_s for a in result.attempt_records], [1, 1])

    def test_exception_outside_wrapper_does_not_invent_attempts_or_zero_usage(self):
        with patch.object(runner, "generate", side_effect=RuntimeError("Unexpected failure")):
            run = self.run_baseline()
        self.assertEqual(run.api_calls, 1)
        self.assertIsNone(run.requests)
        self.assertEqual(run.usage_summary()["known_requests"], 0)
        self.assertIsNone(run.total_tokens)

    def test_prompt_failure_does_not_count_a_generation(self):
        with patch.object(runner, "build_baseline_prompt", side_effect=RuntimeError("Prompt failed")):
            run = self.run_baseline()
        self.assertEqual(run.api_calls, 0)
        self.assertEqual(run.requests, 0)
        self.assertEqual(run.total_tokens, 0)
        self.create.assert_not_called()

    def test_zero_generations_and_local_skips_have_known_zero_usage(self):
        runs = [runner.run_baseline(self.html, []), runner.run_sdg(self.html, [])]
        runs.append(runner.RepairRun(self.html, [runner.Step("v1", "img", ["region"], "cascade_skipped")], 0))
        for run in runs:
            self.assertEqual(run.api_calls, 0)
            self.assertEqual(run.requests, 0)
            self.assertEqual(run.total_tokens, 0)
        self.create.assert_not_called()

    def test_api_and_saved_failure_records_keep_attempts_and_raw_usage(self):
        self.create.side_effect = [TransientError("Retry"), self.response(self.usage)]
        run = self.run_baseline()
        step = _serialize_steps(run)[0]
        self.assertTrue(step["generation_attempted"])
        self.assertEqual(step["llm"]["attempts"], 2)
        self.assertIsNone(step["llm"]["attempt_records"][0]["raw_usage"])
        self.assertEqual(step["llm"]["raw_usage"], self.usage)
        with tempfile.TemporaryDirectory() as directory, patch.object(failed_runs, "FAILED_RUNS_DIR", Path(directory)):
            record_id = failed_runs.save_failed_run(
                original_html=self.html, evaluation_original_html=self.html, use_sdg=False,
                violations_before=self.violations, run=run, error=RuntimeError("Scan failed"),
            )
            record = json.loads((Path(directory) / f"{record_id}.json").read_text())
        saved = record["repair_run"]["steps"][0]
        self.assertEqual(saved["llm"], step["llm"])
        self.assertTrue(saved["generation_attempted"])

    def test_evaluation_round_trip_preserves_unknowns_subtotals_and_provider_total(self):
        for responses in ([self.response(self.usage)], [TransientError("Retry"), self.response(self.usage)]):
            with self.subTest(attempts=len(responses)):
                self.create.side_effect = responses
                run = self.run_baseline()
                metrics = self.evaluate(run).efficiency.to_dict()
                report = evaluate_repair(self.html, run.fixed_html, violations_before=self.violations,
                                         violations_after=[], efficiency_data=metrics)
                self.assertEqual(report.efficiency.to_dict(), metrics)

    def test_standalone_evaluation_without_usage_does_not_claim_a_free_run(self):
        for data in (None, {}):
            with self.subTest(data=data):
                report = evaluate_repair(self.html, self.html, violations_before=[], violations_after=[], efficiency_data=data)
                self.assertIsNone(report.efficiency.api_calls)
                self.assertIsNone(report.efficiency.requests)
                self.assertIsNone(report.efficiency.total_tokens)
                self.assertIsNone(report.efficiency.cost_usd)


if __name__ == "__main__":
    unittest.main()
