import json
import unittest
from unittest.mock import Mock, patch

with patch("google.genai.Client"):
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


class TestRepairProgress(unittest.TestCase):
    def setUp(self):
        self.html = '<div><img id="photo" src="photo.png"></div>'
        self.violations = [{"id": "image-alt", "nodes": [{"target": ["#photo"], "html": '<img id="photo">'}]}]
        self.enterContext(patch.object(runner.streamer, "log"))
        self.generate = self.enterContext(patch.object(runner, "generate", side_effect=self.reply))

    def reply(self, prompt):
        html = '<img id="photo" src="photo.png" alt="Photo">'
        text = json.dumps({"scope": "target", "html": html}) if prompt.edit_scope else f'<div>{html}</div>'
        return LLMResult(text, True, "completed", "test-model", 10, 5, 0, 15, 0.1, 1)

    def test_optional_progress_keeps_repair_outputs_identical(self):
        for method in (runner.run_baseline, runner.run_sdg):
            with self.subTest(method=method.__name__):
                ordinary = method(self.html, self.violations)
                observed = []
                recorded = method(self.html, self.violations, on_progress=lambda step, html, items=observed: items.append((step, html)))
                self.assertEqual(recorded.fixed_html, ordinary.fixed_html)
                self.assertEqual(recorded.generation_summary(), ordinary.generation_summary())
                self.assertEqual(len(observed), len(recorded.steps))
                self.assertIs(observed[0][0], recorded.steps[0])
                self.assertEqual(observed[-1][1], recorded.candidate_html)
                self.assertNotIn("data-br1dg3", observed[-1][1])

    def test_rejected_reply_is_recorded_without_another_generation(self):
        self.generate.side_effect = None
        self.generate.return_value = LLMResult("not HTML", True, "completed", "test-model", 10, 5, 0, 15, 0.1, 1)
        callback = Mock()
        run = runner.run_baseline(self.html, self.violations, on_progress=callback)
        self.assertEqual(run.generation_status, "no_candidate")
        callback.assert_called_once_with(run.steps[0], run.fixed_html)
        self.generate.assert_called_once()

    def test_progress_storage_error_propagates(self):
        for method in (runner.run_baseline, runner.run_sdg):
            with self.subTest(method=method.__name__), self.assertRaisesRegex(RuntimeError, "Cannot save"):
                method(self.html, self.violations, on_progress=Mock(side_effect=RuntimeError("Cannot save")))


if __name__ == "__main__":
    unittest.main()
