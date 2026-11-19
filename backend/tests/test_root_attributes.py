import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from app.services.repair.context import ContextExtractor
from app.services.repair.patch import MARKER, apply_reply, outer_html
from app.services.repair.prompt import build_sdg_prompt
from app.services.sdg.builder import SDGBuilder
from tests.repair_fixtures import sdg_reply, target_from_prompt

with patch("google.genai.Client"):
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


class TestRootAttributes(unittest.TestCase):
    def _apply(self, original, reply):
        soup = BeautifulSoup(original, "html.parser")
        target = soup.find(attrs={MARKER: "v1"})
        before = outer_html(soup)
        result = apply_reply(target, reply, "v1")
        if not result.applied:
            self.assertEqual(outer_html(soup), before)
        return soup, result

    def test_body_removes_omitted_shown_attributes_and_keeps_hidden_attributes(self):
        soup, result = self._apply(
            '<body id="page" data-br1dg3="v1" class="page dark" style="color: black" '
            'data-theme="dark" aria-hidden="true" role="none" tabindex="-1" hidden inert>'
            '<section id="content"><img data-br1dg3="v2"></section></body>',
            '<body id="page"><section id="content">…</section></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.body.attrs, {
            "id": "page", MARKER: "v1", "class": ["page", "dark"],
            "style": "color: black", "data-theme": "dark",
        })
        self.assertEqual(soup.img[MARKER], "v2")

    def test_html_and_explicit_body_are_reconciled_independently(self):
        soup, result = self._apply(
            '<!DOCTYPE html><html id="page" data-br1dg3="v1" lang="en" aria-hidden="true" class="layout">'
            '<head data-info="keep"><title>Page</title></head>'
            '<body id="content" data-br1dg3="v2" role="none" style="color: black" data-theme="dark">'
            '<img data-br1dg3="v3"></body></html>',
            '<html id="page" lang="fr"><head>…</head><body id="content">…</body></html>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.html.attrs, {"id": "page", MARKER: "v1", "lang": "fr", "class": ["layout"]})
        self.assertEqual(soup.body.attrs, {
            "id": "content", MARKER: "v2", "style": "color: black", "data-theme": "dark",
        })
        self.assertEqual(soup.img[MARKER], "v3")
        self.assertEqual(soup.head["data-info"], "keep")
        self.assertEqual(soup.title.string, "Page")
        self.assertTrue(outer_html(soup).startswith("<!DOCTYPE html>"))

    def test_new_attributes_still_apply(self):
        for root in ("html", "body"):
            with self.subTest(root=root):
                soup, result = self._apply(
                    f'<{root} data-br1dg3="v1"><p>Keep</p></{root}>',
                    f'<{root} lang="en" role="main" aria-label="Page" hidden '
                    f'class="new" style="color: blue" data-theme="light">…</{root}>',
                )
                self.assertTrue(result.applied)
                actual = soup.find(root)
                self.assertEqual(actual.attrs, {
                    MARKER: "v1", "lang": "en", "role": "main", "aria-label": "Page", "hidden": "",
                    "class": ["new"], "style": "color: blue", "data-theme": "light",
                })

    def test_existing_attributes_still_update_including_explicit_hidden_attributes(self):
        for root in ("html", "body"):
            with self.subTest(root=root):
                soup, result = self._apply(
                    f'<{root} data-br1dg3="v1" lang="en" aria-hidden="true" '
                    f'class="old" style="color: black" data-theme="dark"><p>Keep</p></{root}>',
                    f'<{root} lang="fr" aria-hidden="false" class="new" '
                    f'style="color: blue" data-theme="light">…</{root}>',
                )
                self.assertTrue(result.applied)
                self.assertEqual(soup.find(root).attrs, {
                    MARKER: "v1", "lang": "fr", "aria-hidden": "false", "class": ["new"],
                    "style": "color: blue", "data-theme": "light",
                })

    def test_body_only_reply_keeps_html_attributes(self):
        soup, result = self._apply(
            '<html data-br1dg3="v1" lang="en" aria-hidden="true"><head><title>Page</title></head>'
            '<body aria-hidden="true" class="page"><p>Keep</p></body></html>',
            '<body>…</body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.html["lang"], "en")
        self.assertEqual(soup.html["aria-hidden"], "true")
        self.assertNotIn("aria-hidden", soup.body.attrs)
        self.assertEqual(soup.body["class"], ["page"])
        self.assertEqual(soup.p.string, "Keep")

    def test_html_reply_without_body_keeps_body_attributes(self):
        soup, result = self._apply(
            '<html data-br1dg3="v1" aria-hidden="true"><head><title>Page</title></head>'
            '<body id="content" data-br1dg3="v2" aria-hidden="true"><img></body></html>',
            '<html lang="en"><head>…</head></html>',
        )
        self.assertTrue(result.applied)
        self.assertNotIn("aria-hidden", soup.html.attrs)
        self.assertEqual(soup.body.attrs, {"id": "content", MARKER: "v2", "aria-hidden": "true"})
        self.assertIsNotNone(soup.img)

    def test_wrapper_only_reply_keeps_root_attributes(self):
        for root in ("html", "body"):
            with self.subTest(root=root):
                original = BeautifulSoup(
                    '<html lang="en"><head><title>Page</title></head><body aria-hidden="true" class="page">'
                    '<section id="content"><img data-br1dg3="v2"></section></body></html>', "html.parser",
                )
                original.find(root)[MARKER] = "v1"
                expected_html_attrs = dict(original.html.attrs)
                expected_body_attrs = dict(original.body.attrs)
                soup, result = self._apply(str(original), '<main><section id="content">…</section></main>')
                self.assertTrue(result.applied)
                self.assertEqual(soup.html.attrs, expected_html_attrs)
                self.assertEqual(soup.body.attrs, expected_body_attrs)
                self.assertEqual(soup.body.main.img[MARKER], "v2")

    def test_collapsed_body_can_remove_attribute_without_replacing_content(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1" aria-hidden="true">Before<!--keep--><p>Text</p>After</body>',
            '<body>…</body>',
        )
        self.assertTrue(result.applied)
        self.assertNotIn("aria-hidden", soup.body.attrs)
        self.assertEqual(soup.body.decode_contents(), 'Before<!--keep--><p>Text</p>After')

    def test_omitted_tracked_root_id_rejects_all_candidate_changes(self):
        for root in ("html", "body"):
            with self.subTest(root=root):
                _, result = self._apply(
                    f'<{root} id="page" data-br1dg3="v1" aria-hidden="true"><p>Keep</p></{root}>',
                    f'<{root} lang="en">…</{root}>',
                )
                self.assertFalse(result.applied)
                self.assertEqual(result.status, "tracking_rejected")
                self.assertIn("marker_identity_changed:v1", result.warnings)

    def test_omitted_tracked_body_id_rolls_back_html_and_body_changes(self):
        soup, result = self._apply(
            '<html data-br1dg3="v1" aria-hidden="true"><head><title>Page</title></head>'
            '<body id="content" data-br1dg3="v2" aria-hidden="true"><img></body></html>',
            '<html lang="en"><head>…</head><body>…</body></html>',
        )
        self.assertFalse(result.applied)
        self.assertIn("marker_identity_changed:v2", result.warnings)
        self.assertEqual(soup.html["aria-hidden"], "true")
        self.assertEqual(soup.body["aria-hidden"], "true")

    def test_ordinary_target_still_uses_full_replacement_attributes(self):
        soup, result = self._apply(
            '<div id="panel" data-br1dg3="v1" class="old" style="color: black" data-theme="dark" aria-hidden="true">Text</div>',
            '<div id="panel" data-br1dg3="v1">Text</div>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.div.attrs, {"id": "panel", MARKER: "v1"})

    def test_real_root_prompt_round_trip_preserves_hidden_attributes(self):
        for root in ("html", "body"):
            with self.subTest(root=root):
                original = BeautifulSoup(
                    '<html><head><title>Page</title></head><body><section id="content"><img></section></body></html>',
                    "html.parser",
                )
                target = original.find(root)
                target.attrs = {
                    "id": "page", MARKER: "v1", "aria-hidden": "true", "lang": "en",
                    "class": ["layout"], "style": "color: black", "data-theme": "dark",
                }
                expected = {key: value for key, value in target.attrs.items() if key != "aria-hidden"}
                builder = SDGBuilder(str(original), [{"id": "aria-hidden-focus", "nodes": [{"target": ["#page"]}]}])
                node_id = builder.element_to_id[builder.soup.find(id="page")]
                context = ContextExtractor.from_builder(builder).extract(node_id)
                prompt = build_sdg_prompt(context, builder.element_to_id)
                markup = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
                reply = BeautifulSoup(markup, "html.parser").find(root)
                self.assertEqual(reply.attrs, {"id": "page", "aria-hidden": "true", "lang": "en"})
                del reply["aria-hidden"]
                soup, result = self._apply(str(original), str(reply))
                self.assertTrue(result.applied)
                self.assertEqual(soup.find(root).attrs, expected)
                self.assertIn("omitting a shown attribute from that tag removes it", prompt.user)


class TestRootAttributesInRepairRun(unittest.TestCase):
    def test_unhidden_body_updates_child_prompt_and_retains_unshown_attributes(self):
        html = (
            '<html><head><title>Page</title></head>'
            '<body id="page" aria-hidden="true" class="layout" style="color: black" data-theme="dark">'
            '<button id="child"></button></body></html>'
        )
        violations = [
            {"id": "aria-hidden-focus", "nodes": [{"target": ["#page"]}]},
            {"id": "button-name", "nodes": [{"target": ["#child"]}]},
        ]
        prompts = []

        def generate(prompt):
            prompts.append(prompt.user)
            target = target_from_prompt(prompt)
            if target.name == "body":
                del target["aria-hidden"]
            else:
                target.string = "Save"
            return LLMResult(
                text=sdg_reply(str(target)), ok=True, status="completed", model="controlled-test",
                prompt_tokens=10, completion_tokens=5, thought_tokens=0,
                total_tokens=15, latency_s=0.1, attempts=1,
            )

        with patch.object(runner, "generate", side_effect=generate), patch.object(runner.streamer, "log"):
            run = runner.run_sdg(html, violations)
        self.assertEqual([step.status for step in run.steps], ["applied", "applied"])
        self.assertEqual(run.generation_status, "accepted")
        self.assertEqual(len(prompts), 2)
        self.assertIn('aria-hidden="true"', prompts[0])
        self.assertNotIn("aria-hidden", prompts[1])
        self.assertNotIn("--hidden_context-->", prompts[1])
        output = BeautifulSoup(run.fixed_html, "html.parser")
        self.assertEqual(output.body.attrs, {
            "id": "page", "class": ["layout"], "style": "color: black", "data-theme": "dark",
        })
        self.assertEqual(output.button.string, "Save")
        self.assertNotIn(MARKER, run.fixed_html)


if __name__ == "__main__":
    unittest.main()
