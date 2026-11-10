import unittest
from unittest.mock import call, patch

# Route tests do not need LLM credentials or a real client.
with patch("google.genai.Client"):
    from app.api import repair as repair_api
    from app.services.repair.runner import RepairRun, Step


class TestRepairCaching(unittest.TestCase):
    def setUp(self):
        self.html = (
            '<html><body><img src="'
            + self._testMethodName
            + '.png"></body></html>'
        )
        self.violations = [{"id": "image-alt", "nodes": [{"target": ["img"]}]}]
        self.detect = self.enterContext(patch.object(repair_api, "detect"))
        self.run_sdg = self.enterContext(patch.object(repair_api, "run_sdg"))
        self.run_baseline = self.enterContext(patch.object(repair_api, "run_baseline"))
        self.evaluate = self.enterContext(patch.object(repair_api, "evaluate_repair"))
        self.enterContext(patch.object(repair_api.streamer, "log"))
        self.enterContext(patch.dict(repair_api.cache, {}, clear=True))

    def _configure_runs(self, methods):
        runs = [
            RepairRun(
                fixed_html=self.html.replace("<img ", f'<img alt="Repair {index}" '),
                steps=[Step(str(index), "img", ["image-alt"], "applied")],
                unmapped=0,
            )
            for index in (1, 2)
        ]
        self.run_sdg.side_effect = [
            run for use_sdg, run in zip(methods, runs) if use_sdg
        ]
        self.run_baseline.side_effect = [
            run for use_sdg, run in zip(methods, runs) if not use_sdg
        ]
        self.detect.side_effect = [self.violations, [], self.violations, []]
        metrics = [{"run": 1}, {"run": 2}]
        self.evaluate.return_value.to_dict.side_effect = metrics
        return runs, metrics

    def _assert_independent_runs(self, methods, use_cache=True):
        runs, metrics = self._configure_runs(methods)
        responses = [
            repair_api.repair_html(
                repair_api.RepairRequest(
                    html=self.html, use_sdg=use_sdg, use_cache=use_cache
                )
            )
            for use_sdg in methods
        ]

        if use_cache:
            for use_sdg, original_response in zip(methods, responses):
                cached_response = repair_api.repair_html(
                    repair_api.RepairRequest(html=self.html, use_sdg=use_sdg)
                )
                self.assertTrue(cached_response.cache_hit)
                self.assertEqual(cached_response.fixed_html, original_response.fixed_html)
                self.assertEqual(cached_response.metrics, original_response.metrics)

        self.assertEqual(self.run_sdg.call_count, methods.count(True))
        self.assertEqual(self.run_baseline.call_count, methods.count(False))
        self.run_sdg.assert_has_calls(
            [call(self.html, self.violations)] * methods.count(True)
        )
        self.run_baseline.assert_has_calls(
            [call(self.html, self.violations)] * methods.count(False)
        )
        self.assertEqual(
            self.detect.call_args_list,
            [call(self.html), call(runs[0].fixed_html),
             call(self.html), call(runs[1].fixed_html)],
        )
        self.assertEqual(self.evaluate.call_count, 2)
        for index, response in enumerate(responses):
            self.assertEqual(response.fixed_html, runs[index].fixed_html)
            self.assertEqual(response.metrics, metrics[index])
            self.assertEqual(response.issues_before, 1)
            self.assertEqual(response.issues_after, 0)
            self.assertEqual(response.issues_fixed, 1)
            self.assertFalse(response.cache_hit)
            self.assertIs(
                self.evaluate.call_args_list[index].kwargs["repair_run"], runs[index]
            )

    def test_sdg_then_baseline_run_independently(self):
        self._assert_independent_runs((True, False))

    def test_baseline_then_sdg_run_independently(self):
        self._assert_independent_runs((False, True))

    def test_uncached_sdg_requests_return_fresh_results(self):
        self._assert_independent_runs((True, True), use_cache=False)

    def test_uncached_baseline_requests_return_fresh_results(self):
        self._assert_independent_runs((False, False), use_cache=False)

    def test_normal_requests_use_cache_by_default(self):
        runs, metrics = self._configure_runs((True, True))
        request = repair_api.RepairRequest(html=self.html)

        original = repair_api.repair_html(request)
        cached = repair_api.repair_html(request)

        self.assertTrue(request.use_cache)
        self.assertFalse(original.cache_hit)
        self.assertTrue(cached.cache_hit)
        self.assertIsNot(original, cached)
        self.assertEqual(cached.fixed_html, runs[0].fixed_html)
        self.assertEqual(cached.metrics, metrics[0])
        self.assertEqual(cached.steps, original.steps)
        self.assertEqual(self.detect.call_count, 2)
        self.run_sdg.assert_called_once_with(self.html, self.violations)
        self.run_baseline.assert_not_called()
        self.evaluate.assert_called_once()

    def test_different_html_does_not_reuse_cache(self):
        runs, _ = self._configure_runs((True, True))
        other_html = self.html.replace(".png", "-other.png")
        repair_api.repair_html(repair_api.RepairRequest(html=self.html))
        response = repair_api.repair_html(repair_api.RepairRequest(html=other_html))

        self.assertFalse(response.cache_hit)
        self.assertEqual(response.fixed_html, runs[1].fixed_html)
        self.assertEqual(
            self.run_sdg.call_args_list,
            [call(self.html, self.violations), call(other_html, self.violations)],
        )

    def test_bypass_neither_reads_nor_overwrites_existing_cache(self):
        runs, metrics = self._configure_runs((True, True))
        request = repair_api.RepairRequest(html=self.html)
        original = repair_api.repair_html(request)
        fresh = repair_api.repair_html(
            repair_api.RepairRequest(html=self.html, use_cache=False)
        )
        cached = repair_api.repair_html(request)

        self.assertFalse(fresh.cache_hit)
        self.assertEqual(fresh.fixed_html, runs[1].fixed_html)
        self.assertEqual(fresh.metrics, metrics[1])
        self.assertTrue(cached.cache_hit)
        self.assertEqual(cached.fixed_html, original.fixed_html)
        self.assertEqual(cached.metrics, original.metrics)
        self.assertEqual(self.run_sdg.call_count, 2)
        self.assertEqual(self.detect.call_count, 4)
        self.assertEqual(self.evaluate.call_count, 2)

    def test_bypass_does_not_populate_empty_cache(self):
        runs, _ = self._configure_runs((True, True))
        repair_api.repair_html(
            repair_api.RepairRequest(html=self.html, use_cache=False)
        )
        request = repair_api.RepairRequest(html=self.html)
        normal = repair_api.repair_html(request)
        cached = repair_api.repair_html(request)

        self.assertFalse(normal.cache_hit)
        self.assertEqual(normal.fixed_html, runs[1].fixed_html)
        self.assertTrue(cached.cache_hit)
        self.assertEqual(cached.fixed_html, normal.fixed_html)
        self.assertEqual(self.run_sdg.call_count, 2)

    def test_cache_expires_after_five_minutes(self):
        runs, _ = self._configure_runs((True, True))
        request = repair_api.RepairRequest(html=self.html)
        with patch.object(repair_api, "monotonic", return_value=100.0) as clock:
            original = repair_api.repair_html(request)
            clock.return_value = 399.0
            cached = repair_api.repair_html(request)
            clock.return_value = 400.0
            fresh = repair_api.repair_html(request)
            refreshed_cache = repair_api.repair_html(request)

        self.assertTrue(cached.cache_hit)
        self.assertEqual(cached.fixed_html, original.fixed_html)
        self.assertFalse(fresh.cache_hit)
        self.assertEqual(fresh.fixed_html, runs[1].fixed_html)
        self.assertTrue(refreshed_cache.cache_hit)
        self.assertEqual(refreshed_cache.fixed_html, fresh.fixed_html)
        self.assertEqual(self.run_sdg.call_count, 2)

    def test_no_violations_skips_repair_for_both_methods(self):
        self.detect.return_value = []
        for use_sdg in (True, False):
            with self.subTest(use_sdg=use_sdg):
                response = repair_api.repair_html(
                    repair_api.RepairRequest(html=self.html, use_sdg=use_sdg)
                )
                self.assertEqual(response.fixed_html, self.html)
                self.assertEqual(response.issues_before, 0)
                self.assertEqual(response.issues_after, 0)
                self.assertEqual(response.issues_fixed, 0)
                self.assertEqual(response.steps, [])
                self.assertFalse(response.cache_hit)
        self.assertEqual(self.detect.call_count, 2)
        self.run_sdg.assert_not_called()
        self.run_baseline.assert_not_called()
        self.evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
