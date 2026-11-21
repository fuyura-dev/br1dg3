import unittest
from types import SimpleNamespace

from app.services.repair.usage import (
    TOKEN_FIELDS,
    summarize_completed_usage,
    summarize_usage,
)
from app.services.validation.efficiency import (
    calculate_efficiency,
    calculate_efficiency_from_run,
    compute_cost,
)


class TestEfficiencyAccounting(unittest.TestCase):
    def test_legacy_display_prices_and_formula_remain_unchanged(self):
        self.assertEqual(compute_cost(1_000_000, 1_000_000, 1_000_000), 0.675)

    def test_unknown_components_do_not_produce_a_false_free_estimate(self):
        self.assertIsNone(compute_cost(100, 20, None))
        self.assertEqual(compute_cost(0, 0, 0), 0)

    def test_manual_complete_components_can_still_be_summed(self):
        result = calculate_efficiency(1, 10, 5, 2)
        self.assertEqual(result.total_tokens, 17)
        self.assertEqual(result.total_tokens_source, "supplied_components")
        self.assertIsNone(result.requests)

    def test_supplied_total_is_not_overwritten(self):
        result = calculate_efficiency(1, 10, 5, 2, total_tokens=19)
        self.assertEqual(result.total_tokens, 19)
        self.assertEqual(result.total_tokens_source, "supplied_total")

    def test_explicit_unknown_total_stays_unknown(self):
        result = calculate_efficiency(1, 10, 5, 2, total_tokens=None)
        self.assertIsNone(result.total_tokens)
        self.assertFalse(result.usage_complete["total_tokens"])

    def test_missing_manual_component_is_not_zero(self):
        result = calculate_efficiency(1, 10, 5, None)
        self.assertIsNone(result.total_tokens)
        self.assertIsNone(result.cost_usd)
        self.assertEqual(result.reported_usage["completion_tokens"], 5)

    def test_legacy_retry_record_retains_response_but_prior_attempts_are_unknown(self):
        result = SimpleNamespace(prompt_tokens=10, completion_tokens=5, thought_tokens=2, total_tokens=17, attempts=2)
        summary = summarize_usage([SimpleNamespace(llm=result)])
        self.assertEqual(summary["requests"], 2)
        self.assertEqual(summary["reported_usage"]["total_tokens"], 17)
        self.assertIsNone(summary["total_tokens"])

    def test_legacy_applied_step_without_usage_does_not_claim_zero_generations(self):
        summary = summarize_usage([SimpleNamespace(status="applied", llm=None)])
        self.assertEqual(summary["api_calls"], 1)
        self.assertIsNone(summary["requests"])
        self.assertIsNone(summary["total_tokens"])

    def test_mixed_recorded_and_unknown_request_counts_keep_known_subtotal(self):
        result = SimpleNamespace(prompt_tokens=10, completion_tokens=5, thought_tokens=2, total_tokens=17, attempts=1)
        summary = summarize_usage([SimpleNamespace(llm=result), SimpleNamespace(status="llm_error", llm=None)])
        self.assertEqual(summary["api_calls"], 2)
        self.assertIsNone(summary["requests"])
        self.assertEqual(summary["known_requests"], 1)
        self.assertIsNone(summary["total_tokens"])
        self.assertEqual(summary["reported_usage"]["total_tokens"], 17)


class TestCompletedResponseUsage(unittest.TestCase):
    def setUp(self):
        self.usage = {"total_input_tokens": 10, "total_output_tokens": 5, "total_thought_tokens": 2, "total_tokens": 19}

    def step(self, *records, attempts=None, status="applied"):
        return SimpleNamespace(
            status=status, generation_attempted=True,
            llm=SimpleNamespace(attempts=len(records) if attempts is None else attempts,
                                attempt_records=[SimpleNamespace(status=s, raw_usage=u) for s, u in records]),
        )

    def test_completed_usage_excludes_error_usage_without_changing_existing_summary(self):
        for error_usage in (None, self.usage):
            with self.subTest(error_usage=error_usage):
                steps = [self.step(("request_error", error_usage), ("completed", self.usage))]
                before = summarize_usage(steps)
                summary = summarize_completed_usage(steps)
                self.assertEqual(summary["completed_response_count"], 1)
                usage = summary["completed_response_usage"]
                self.assertEqual(usage["total_tokens"], 19)  # Provider total, not the component sum of 17.
                self.assertEqual(usage["prompt_tokens"], 10)
                self.assertTrue(all(usage["usage_complete"].values()))
                self.assertEqual(summarize_usage(steps), before)

    def test_multiple_completed_responses_are_summed_even_when_patches_fail(self):
        steps = [self.step(("completed", self.usage), status=status)
                 for status in ("applied", "not_html", "empty_reply", "tracking_rejected")]
        summary = summarize_completed_usage(steps)
        self.assertEqual(summary["completed_response_count"], 4)
        self.assertEqual(summary["completed_response_usage"]["total_tokens"], 76)
        self.assertEqual(summary["completed_response_usage"]["completion_tokens"], 20)

    def test_missing_completed_usage_is_unknown_per_field(self):
        steps = [self.step(("completed", self.usage)), self.step(("completed", {"total_input_tokens": 4}))]
        summary = summarize_completed_usage(steps)
        self.assertEqual(summary["completed_response_count"], 2)
        usage = summary["completed_response_usage"]
        self.assertEqual(usage["prompt_tokens"], 14)
        self.assertTrue(usage["usage_complete"]["prompt_tokens"])
        self.assertIsNone(usage["total_tokens"])
        self.assertEqual(usage["reported_usage"]["total_tokens"], 19)
        self.assertFalse(usage["usage_complete"]["total_tokens"])

    def test_missing_provider_total_is_not_rebuilt_from_components(self):
        raw = {key: value for key, value in self.usage.items() if key != "total_tokens"}
        usage = summarize_completed_usage([self.step(("completed", raw))])["completed_response_usage"]
        self.assertIsNone(usage["total_tokens"])
        self.assertEqual(usage["thought_tokens"], 2)

    def test_malformed_usage_and_reported_zero_remain_distinct(self):
        raw = {"total_input_tokens": True, "total_output_tokens": -1, "total_thought_tokens": "2", "total_tokens": 0}
        usage = summarize_completed_usage([self.step(("completed", raw))])["completed_response_usage"]
        self.assertEqual(usage["total_tokens"], 0)
        self.assertTrue(usage["usage_complete"]["total_tokens"])
        for field in ("prompt_tokens", "completion_tokens", "thought_tokens"):
            self.assertIsNone(usage[field])
            self.assertFalse(usage["usage_complete"][field])

    def test_no_completed_responses_has_zero_usage_in_this_scope(self):
        cases = [[], [SimpleNamespace(status="cascade_skipped", llm=None)]]
        cases.extend([self.step((status, self.usage))] for status in (
            "request_error", "incomplete", "failed", "cancelled", "budget_exceeded",
            "in_progress", "requires_action", "queued",
        ))
        for steps in cases:
            with self.subTest(steps=steps):
                summary = summarize_completed_usage(steps)
                self.assertEqual(summary["completed_response_count"], 0)
                usage = summary["completed_response_usage"]
                self.assertEqual(usage["basis"], "completed_responses")
                for name in TOKEN_FIELDS:
                    self.assertEqual(usage[name], 0)
                    self.assertTrue(usage["usage_complete"][name])

    def test_unknown_completion_status_keeps_only_known_subtotals(self):
        for status in (None, "unknown", "unrecognized_status"):
            with self.subTest(status=status):
                steps = [self.step(("completed", self.usage)), self.step((status, self.usage))]
                summary = summarize_completed_usage(steps)
                self.assertIsNone(summary["completed_response_count"])
                usage = summary["completed_response_usage"]
                self.assertEqual(usage["known_completed_responses"], 1)
                self.assertFalse(usage["count_complete"])
                self.assertIsNone(usage["total_tokens"])
                self.assertEqual(usage["reported_usage"]["total_tokens"], 19)

    def test_missing_attempt_record_does_not_establish_complete_count(self):
        summary = summarize_completed_usage([self.step(("completed", self.usage), attempts=2)])
        self.assertIsNone(summary["completed_response_count"])
        usage = summary["completed_response_usage"]
        self.assertEqual(usage["known_completed_responses"], 1)
        self.assertIsNone(usage["prompt_tokens"])
        self.assertEqual(usage["reported_usage"]["prompt_tokens"], 10)

    def test_legacy_final_response_requires_single_attempt_for_complete_count(self):
        for attempts in (1, 2, None):
            with self.subTest(attempts=attempts):
                result = SimpleNamespace(status="completed", attempts=attempts, prompt_tokens=10,
                                         completion_tokens=5, thought_tokens=2, total_tokens=19)
                summary = summarize_completed_usage([SimpleNamespace(llm=result)])
                self.assertEqual(summary["completed_response_count"], 1 if attempts == 1 else None)
                usage = summary["completed_response_usage"]
                self.assertEqual(usage["total_tokens"], 19 if attempts == 1 else None)
                self.assertEqual(usage["known_completed_responses"], 1)

    def test_missing_result_cannot_be_inferred_from_patch_status(self):
        summary = summarize_completed_usage([SimpleNamespace(status="applied", llm=None)])
        self.assertIsNone(summary["completed_response_count"])
        self.assertIsNone(summary["completed_response_usage"]["total_tokens"])

    def test_manual_totals_without_response_evidence_leave_new_summary_unavailable(self):
        for report in (calculate_efficiency_from_run(None), calculate_efficiency(1, 10, 5, 2),
                       calculate_efficiency(0, 0, 0, 0)):
            with self.subTest(report=report):
                self.assertIsNone(report.completed_response_count)
                self.assertIsNone(report.completed_response_usage)


if __name__ == "__main__":
    unittest.main()
