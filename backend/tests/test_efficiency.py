import unittest
from types import SimpleNamespace

from app.services.repair.usage import summarize_usage
from app.services.validation.efficiency import calculate_efficiency, compute_cost


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


if __name__ == "__main__":
    unittest.main()
