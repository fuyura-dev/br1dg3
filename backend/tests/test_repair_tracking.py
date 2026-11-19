import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from app.services.repair.patch import MARKER, apply_reply, outer_html
from tests.repair_fixtures import sdg_reply, target_from_prompt

with patch("google.genai.Client"):
    from app.api.repair import _serialize_steps
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


class TestPatchTracking(unittest.TestCase):
    def _apply(self, original, reply):
        soup = BeautifulSoup(original, "html.parser")
        target = soup.find(attrs={MARKER: "v1"})
        before = outer_html(soup)
        result = apply_reply(target, reply, "v1")
        if not result.applied:
            self.assertEqual(result.status, "tracking_rejected")
            self.assertEqual(outer_html(soup), before)
            self.assertIsNotNone(target.parent)
        return soup, result

    def test_preserved_markers_allow_idless_children_and_reordering(self):
        soup, result = self._apply(
            '<div data-br1dg3="v1"><img data-br1dg3="v2"><button data-br1dg3="v3">Save</button></div>',
            '<main data-br1dg3="v1"><button data-br1dg3="v3">Save</button><img data-br1dg3="v2"></main>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.find(attrs={MARKER: "v2"}).name, "img")
        self.assertEqual(soup.find(attrs={MARKER: "v3"}).name, "button")

    def test_recovers_target_and_descendants_by_id_inside_new_wrappers(self):
        soup, result = self._apply(
            '<div id="parent" data-br1dg3="v1"><img id="photo" data-br1dg3="v2"></div>',
            '<main><section id="parent"><figure><img id="photo"></figure></section></main>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.find(id="parent")[MARKER], "v1")
        self.assertEqual(soup.find(id="photo")[MARKER], "v2")
        self.assertIn("marker_recovered:v1", result.warnings)
        self.assertIn("marker_recovered:v2", result.warnings)

    def test_recovery_covers_multiple_replacement_roots(self):
        soup, result = self._apply(
            '<div id="parent" data-br1dg3="v1"><img id="photo" data-br1dg3="v2"></div>',
            '<div id="parent"></div><img id="photo">',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.img[MARKER], "v2")
        self.assertEqual(soup.img.parent, soup)

    def test_sole_idless_same_tag_target_can_retain_its_slot(self):
        soup, result = self._apply('<img data-br1dg3="v1">', '<img alt="Photo">')
        self.assertTrue(result.applied)
        self.assertEqual(soup.img[MARKER], "v1")

    def test_missing_child_requires_an_unchanged_unique_id(self):
        cases = [
            ('<img data-br1dg3="v2">', '<img>'),
            ('<img id="photo" data-br1dg3="v2">', '<img id="changed">'),
            ('<img id="photo" data-br1dg3="v2">', ''),
            ('<img id="photo" data-br1dg3="v2">', '<img id="photo"><img id="photo">'),
            ('<img id="photo" data-br1dg3="v2"><span id="photo"></span>', '<img id="photo">'),
        ]
        for original_child, reply_child in cases:
            with self.subTest(original=original_child, reply=reply_child):
                _, result = self._apply(
                    f'<div data-br1dg3="v1">{original_child}</div>',
                    f'<div data-br1dg3="v1" role="region">{reply_child}</div>',
                )
                self.assertFalse(result.applied)
                self.assertIn("marker_lost:v2", result.warnings)

    def test_duplicate_id_outside_target_prevents_recovery(self):
        _, result = self._apply(
            '<div data-br1dg3="v1"><img id="photo" data-br1dg3="v2"></div><aside id="photo"></aside>',
            '<div data-br1dg3="v1"><img id="photo"></div>',
        )
        self.assertFalse(result.applied)
        self.assertIn("marker_lost:v2", result.warnings)

    def test_rejects_duplicate_foreign_and_swapped_markers(self):
        original = (
            '<div id="parent" data-br1dg3="v1">'
            '<img id="photo" data-br1dg3="v2"><button id="save" data-br1dg3="v3">Save</button></div>'
        )
        cases = [
            ('<img id="photo" data-br1dg3="v2"><button id="save" data-br1dg3="v2">Save</button>', 'marker_duplicate:v2'),
            ('<img id="photo" data-br1dg3="v2"><button id="save" data-br1dg3="foreign">Save</button>', 'marker_unexpected:foreign'),
            ('<img id="photo" data-br1dg3="v3"><button id="save" data-br1dg3="v2">Save</button>', 'marker_identity_changed:v2'),
            ('<img id="changed" data-br1dg3="v2"><button id="save" data-br1dg3="v3">Save</button>', 'marker_identity_changed:v2'),
            ('<img id="photo" data-br1dg3="v2"><button id="save" data-br1dg3="v3">Save</button><span data-br1dg3="v1"></span>', 'marker_duplicate:v1'),
        ]
        for children, warning in cases:
            with self.subTest(warning=warning, children=children):
                _, result = self._apply(original, f'<div id="parent" data-br1dg3="v1">{children}</div>')
                self.assertFalse(result.applied)
                self.assertIn(warning, result.warnings)

    def test_outside_target_markers_cannot_be_imported(self):
        _, result = self._apply(
            '<div data-br1dg3="v1"><img id="photo" data-br1dg3="v2"></div><button data-br1dg3="v3"></button>',
            '<div data-br1dg3="v1"><img id="photo" data-br1dg3="v2"><button data-br1dg3="v3"></button></div>',
        )
        self.assertFalse(result.applied)
        self.assertIn("marker_unexpected:v3", result.warnings)

    def test_duplicate_original_markers_cannot_reach_an_ambiguous_lookup(self):
        _, result = self._apply(
            '<div data-br1dg3="v1"><img data-br1dg3="v2"></div><button data-br1dg3="v2"></button>',
            '<div data-br1dg3="v1"><img data-br1dg3="v2"></div>',
        )
        self.assertFalse(result.applied)
        self.assertIn("marker_duplicate:v2", result.warnings)

    def test_ambiguous_target_is_not_assigned_to_first_element(self):
        _, result = self._apply('<div data-br1dg3="v1">Text</div>', '<div>Text</div><div>More</div>')
        self.assertFalse(result.applied)
        self.assertIn("marker_lost:v1", result.warnings)

    def test_one_failed_recovery_does_not_publish_other_candidate_changes(self):
        _, result = self._apply(
            '<div data-br1dg3="v1"><img id="photo" data-br1dg3="v2"><button data-br1dg3="v3">Save</button></div>',
            '<main data-br1dg3="v1"><img id="photo"><button>Save</button></main>',
        )
        self.assertFalse(result.applied)
        self.assertIn("marker_lost:v3", result.warnings)
        self.assertNotIn("marker_recovered:v2", result.warnings)

    def test_body_placeholder_expansion_keeps_descendant_markers(self):
        soup, result = self._apply(
            '<html><head><title>Page</title></head><body data-br1dg3="v1">'
            '<section id="content"><img data-br1dg3="v2"></section></body></html>',
            '<body><main><section id="content">…</section></main></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.body[MARKER], "v1")
        self.assertEqual(soup.body.main.img[MARKER], "v2")
        self.assertEqual(soup.title.string, "Page")

    def test_html_placeholder_expansion_keeps_all_tracked_descendants(self):
        soup, result = self._apply(
            '<!DOCTYPE html><html data-br1dg3="v1"><head><title>Page</title></head>'
            '<body data-br1dg3="v2"><section id="content"><img data-br1dg3="v3"></section></body></html>',
            '<html lang="en"><head>…</head><body><main><section id="content">…</section></main></body></html>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.html[MARKER], "v1")
        self.assertEqual(soup.body[MARKER], "v2")
        self.assertEqual(soup.main.img[MARKER], "v3")
        self.assertEqual(soup.html["lang"], "en")
        self.assertTrue(outer_html(soup).startswith("<!DOCTYPE html>"))

    def test_root_patch_rolls_back_after_assembled_identity_check_fails(self):
        for root in ("html", "body"):
            with self.subTest(root=root):
                original_body = '<section id="content" data-br1dg3="v2"><img></section>'
                changed_body = '<main><section id="changed">…</section></main>'
                if root == "html":
                    original_body = f'<head><title>Page</title></head><body>{original_body}</body>'
                    changed_body = f'<head>…</head><body>{changed_body}</body>'
                _, result = self._apply(
                    f'<{root} data-br1dg3="v1">{original_body}</{root}>',
                    f'<{root} lang="en">{changed_body}</{root}>',
                )
                self.assertFalse(result.applied)
                self.assertIn("marker_identity_changed:v2", result.warnings)

    def test_duplicate_markers_are_rejected_even_in_collapsed_root_replies(self):
        _, result = self._apply(
            '<body data-br1dg3="v1"><section id="content"><img data-br1dg3="v2"></section></body>',
            '<body><section id="content" data-br1dg3="v2">…</section><aside data-br1dg3="v2">…</aside></body>',
        )
        self.assertFalse(result.applied)
        self.assertIn("marker_duplicate:v2", result.warnings)


class TestTrackingInRepairRun(unittest.TestCase):
    def _run(self, *, child_id, lose_marker=True, extra_marker=False):
        html = f'<div id="parent"><img{child_id}></div>'
        violations = [
            {"id": "region", "nodes": [{"target": ["#parent"]}]},
            {"id": "image-alt", "nodes": [{"target": ["img"]}]},
        ]
        if extra_marker:
            violations = violations[:1]
        prompts = []

        def generate(prompt):
            prompts.append(prompt.user)
            target = target_from_prompt(prompt)
            if target.name == "div":
                target["role"] = "region"
                target["aria-label"] = "Gallery"
                if lose_marker:
                    target.img.attrs.pop(MARKER, None)
                if extra_marker:
                    target.img[MARKER] = "foreign"
            else:
                target["alt"] = "Photo"
            return LLMResult(
                text=sdg_reply(str(target)), ok=True, status="completed", model="controlled-test",
                prompt_tokens=10, completion_tokens=5, thought_tokens=0,
                total_tokens=15, latency_s=0.1, attempts=1,
            )

        with patch.object(runner, "generate", side_effect=generate), patch.object(runner.streamer, "log"):
            run = runner.run_sdg(html, violations)
        return run, prompts

    def test_recovered_child_reaches_its_prompt_with_updated_parent_context(self):
        run, prompts = self._run(child_id=' id="photo"')
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])
        self.assertIn("marker_recovered:v2", run.steps[0].warnings)
        self.assertIn('aria-label="Gallery"', prompts[1])
        self.assertIn("--landmark_context-->", prompts[1])
        self.assertIn('alt="Photo"', run.fixed_html)
        self.assertNotIn(MARKER, run.fixed_html)
        self.assertEqual(run.generation_status, "accepted")

    def test_uncertain_parent_is_rejected_and_child_still_runs_on_previous_html(self):
        run, prompts = self._run(child_id="")
        self.assertEqual([s.status for s in run.steps], ["tracking_rejected", "applied"])
        self.assertIn("marker_lost:v2", run.steps[0].warnings)
        self.assertNotIn('aria-label="Gallery"', prompts[1])
        self.assertNotIn('role="region"', run.fixed_html)
        self.assertIn('alt="Photo"', run.fixed_html)
        self.assertEqual(run.generation_status, "partial")
        self.assertEqual(run.failed_steps, 1)
        self.assertEqual(run.total_tokens, 30)
        self.assertEqual(run.api_calls, 2)
        serialized = _serialize_steps(run)[0]
        self.assertEqual(serialized["status"], "tracking_rejected")
        self.assertEqual(serialized["raw_reply"], run.steps[0].llm.text)
        self.assertIsNone(serialized["candidate_html"])
        self.assertIn("marker_lost:v2", serialized["warnings"])

    def test_tracking_rejection_alone_is_no_candidate_and_keeps_usage(self):
        run, prompts = self._run(child_id="", extra_marker=True)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(run.steps[0].status, "tracking_rejected")
        self.assertEqual(run.generation_status, "no_candidate")
        self.assertTrue(run.fallback_used)
        self.assertIsNone(run.candidate_html)
        self.assertEqual(run.failed_steps, 1)
        self.assertEqual(run.total_tokens, 15)
        self.assertEqual(run.fixed_html, '<div id="parent"><img></div>')


if __name__ == "__main__":
    unittest.main()
