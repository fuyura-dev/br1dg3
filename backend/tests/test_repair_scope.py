import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from app.services.detection.preprocess import (
    preprocess,
    stash_non_essential,
    unstash_non_essential,
)
from app.services.repair import failed_runs
from app.services.repair.context import ContextExtractor
from app.services.repair.patch import MARKER, outer_html, strip_markers
from app.services.repair.prompt import build_baseline_prompt, build_sdg_prompt
from app.services.repair.scope import (
    BLOCK_CHAR_LIMIT,
    BLOCK_ELEMENT_LIMIT,
    TARGET_CHAR_LIMIT,
    TARGET_ELEMENT_LIMIT,
    ScopedReply,
    apply_scoped_reply,
    parse_scoped_reply,
    select_scope,
)
from app.services.sdg.builder import SDGBuilder
from tests.repair_fixtures import sdg_reply, target_from_prompt

with patch("google.genai.Client"):
    from app.api.repair import _serialize_steps
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


def prompt_for(html, rule="label", selector="#target"):
    builder = SDGBuilder(html, [{"id": rule, "nodes": [{"target": [selector]}]}])
    target = builder.soup.select_one(selector)
    target[MARKER] = "v1"
    ctx = ContextExtractor.from_builder(builder).extract(builder.element_to_id[target])
    return builder, build_sdg_prompt(ctx, builder.element_to_id)


class TestScopeSelectionAndPrompt(unittest.TestCase):
    def test_only_immediate_parent_is_offered_and_target_markup_is_complete(self):
        _, prompt = prompt_for('<section><div><span>Nearby</span><input id="target"></div><p>Outside</p></section>')
        scope = prompt.edit_scope
        self.assertEqual(scope.block.name, "div")
        self.assertEqual(scope.allowed, ["target", "block"])
        self.assertNotIn("Outside", scope.block_markup)
        target_section = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
        self.assertIn('id="target"', target_section)
        self.assertEqual(prompt.user.count('id="target"'), 2)  # Complete in both [T] and [B].
        self.assertEqual(target_from_prompt(prompt)["id"], "target")
        self.assertIn('"scope" and "html"', prompt.system)
        self.assertIn("existing siblings", prompt.user)

    def test_non_empty_target_keeps_attributes_and_children_when_block_offered(self):
        _, prompt = prompt_for(
            '<div><nav id="target" class="menu" aria-label="Nav"><a href="/home"><span>Home</span></a></nav></div>',
            rule="landmark-unique",
        )
        self.assertEqual(prompt.edit_scope.allowed, ["target", "block"])
        target_section = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
        self.assertIn('class="menu"', target_section)
        self.assertIn('<a href="/home"><span>Home</span></a>', target_section)

    def test_editable_and_external_graph_context_are_distinguished(self):
        _, prompt = prompt_for(
            '<section><div id="field"><span id="near">Near</span><input id="target" aria-describedby="external"></div>'
            '<p id="external">External description</p></section>',
        )
        readonly = prompt.user.split("## Related elements (read-only)\n", 1)[1].split("\n\n##", 1)[0]
        editable = prompt.user.split("## Related elements inside the editable scope\n", 1)[1].split("\n\n##", 1)[0]
        self.assertIn('id="external"', readonly)
        self.assertNotIn('id="field"', readonly)
        self.assertIn('id="field"', editable)
        self.assertIn("--aria_describedby-->", prompt.user)

    def test_document_shells_and_fragment_parent_do_not_offer_block_mode(self):
        for html in (
            '<input id="target">', '<html><body><input id="target"></body></html>',
            '<html><head><title id="target">Title</title></head><body></body></html>',
        ):
            with self.subTest(html=html):
                _, prompt = prompt_for(html)
                self.assertEqual(prompt.edit_scope.allowed, ["target"])
                self.assertIn("Only scope=target is allowed", prompt.user)

    def test_oversized_parent_falls_back_to_complete_target(self):
        for oversized in ('x' * BLOCK_CHAR_LIMIT, '<i></i>' * BLOCK_ELEMENT_LIMIT):
            with self.subTest(kind=oversized[:1]):
                _, prompt = prompt_for(f'<div><input id="target">{oversized}</div>')
                self.assertEqual(prompt.edit_scope.reason, "parent_too_large")
                self.assertEqual(prompt.edit_scope.allowed, ["target"])
                self.assertNotIn("## Editable block", prompt.user)
                self.assertIn('id="target"', prompt.edit_scope.target_markup)

    def test_parent_limits_include_root_and_tracking_and_report_selected_budget(self):
        base = '<div><input id="target" data-br1dg3="v1"></div>'
        for contents, extra in (
            ('x' * (BLOCK_CHAR_LIMIT - len(base)), 'x'),
            ('<i></i>' * (BLOCK_ELEMENT_LIMIT - 2), '<i></i>'),
        ):
            with self.subTest(kind=extra):
                html = base.replace('</div>', contents + '</div>')
                builder, prompt = prompt_for(html)
                self.assertEqual(prompt.edit_scope.reason, "immediate_parent")
                metadata = prompt.edit_scope.record(builder.element_to_id)
                self.assertEqual(metadata["character_limit"], 3_000)
                self.assertEqual(metadata["element_limit"], 30)
                self.assertIsNone(metadata["reply_character_limit"])
                self.assertIsNone(metadata["reply_element_limit"])

                builder, fallback = prompt_for(html.replace('</div>', extra + '</div>'))
                self.assertEqual(fallback.edit_scope.reason, "parent_too_large")
                metadata = fallback.edit_scope.record(builder.element_to_id)
                self.assertEqual(metadata["character_limit"], TARGET_CHAR_LIMIT)
                self.assertEqual(metadata["element_limit"], TARGET_ELEMENT_LIMIT)
                self.assertEqual(metadata["parent_character_limit"], 3_000)
                self.assertEqual(metadata["parent_element_limit"], 30)

    def test_target_larger_than_parent_budget_remains_available_in_full(self):
        for contents in ('x' * BLOCK_CHAR_LIMIT, '<i></i>' * BLOCK_ELEMENT_LIMIT):
            with self.subTest(kind=contents[:1]):
                _, prompt = prompt_for(f'<section><div id="target">{contents}</div></section>')
                self.assertEqual(prompt.edit_scope.reason, "parent_too_large")
                self.assertEqual(prompt.edit_scope.allowed, ["target"])
                self.assertIn(contents, prompt.edit_scope.target_markup)

    def test_html_body_root_retains_shortened_target_only_path(self):
        builder, prompt = prompt_for(
            '<html id="target"><head><title></title></head><body>' + '<p>Text</p>' * 200 + '</body></html>',
            "document-title",
        )
        self.assertEqual(prompt.edit_scope.allowed, ["target"])
        self.assertIn("## Document title repair", prompt.user)
        self.assertLessEqual(len(prompt.edit_scope.target_markup), TARGET_CHAR_LIMIT)
        metadata = prompt.edit_scope.record(builder.element_to_id)
        self.assertTrue(metadata["shortened_root"])
        self.assertIsNone(metadata["element_limit"])

    def test_baseline_still_requests_plain_full_document_html(self):
        prompt = build_baseline_prompt('<p>Text</p>', [])
        self.assertIsNone(prompt.edit_scope)
        self.assertIn("Return ONLY the complete repaired HTML document", prompt.system)
        self.assertNotIn('"scope"', prompt.system)


class TestReplyEnvelope(unittest.TestCase):
    def test_escaped_html_round_trips_without_cleaning_or_guessing_scope(self):
        html = '<input aria-label="A &amp; B">\n'
        reply, error = parse_scoped_reply(sdg_reply(html, "block"))
        self.assertIsNone(error)
        self.assertEqual(reply, ScopedReply("block", html))

    def test_malformed_unknown_extra_and_duplicate_fields_are_rejected(self):
        cases = [
            '<input>', '```json\n{"scope":"target","html":"<input>"}\n```',
            'Explanation {"scope":"target","html":"<input>"}', '[]',
            '{"scope":"target","html":"<input>","selector":"body"}',
            '{"scope":"target","scope":"block","html":"<input>"}',
            '{"scope":"target","html":"<input>","html":"<button>"}',
            '{"scope":"document","html":"<html></html>"}',
            '{"scope":[],"html":"<input>"}', '{"scope":"target","html":null}',
            '{"scope":"target","html":" "}',
        ]
        for text in cases:
            with self.subTest(text=text):
                reply, error = parse_scoped_reply(text)
                self.assertIsNone(reply)
                self.assertIsNotNone(error)

    def test_large_valid_envelope_is_not_rejected_for_size(self):
        html = '<div>' + 'é' * 17_000 + '</div>'
        raw = sdg_reply(html)
        self.assertGreater(len(raw), 96_128)  # Former envelope ceiling.
        reply, error = parse_scoped_reply(raw)
        self.assertIsNone(error)
        self.assertEqual(reply, ScopedReply("target", html))


class TestScopedPatching(unittest.TestCase):
    def apply(self, original, html, mode="block"):
        soup = BeautifulSoup(original, "html.parser")
        target = soup.find(attrs={MARKER: "v1"})
        selection = select_scope(target)
        before = outer_html(soup)
        result = apply_scoped_reply(selection, ScopedReply(mode, html), "v1")
        if not result.applied:
            self.assertEqual(outer_html(soup), before)
        return soup, result

    def test_block_can_edit_existing_label_sibling_and_parent_attributes(self):
        soup, result = self.apply(
            '<section><div class="field" aria-hidden="true"><span>Email</span><input id="email" data-br1dg3="v1"></div>'
            '<p id="outside">Keep</p></section>',
            '<div class="field"><label for="email">Email</label><input id="email"></div>',
        )
        self.assertTrue(result.applied, result)
        self.assertEqual(soup.label["for"], "email")
        self.assertNotIn("aria-hidden", soup.div.attrs)
        self.assertEqual(soup.input[MARKER], "v1")
        self.assertEqual(str(soup.find(id="outside")), '<p id="outside">Keep</p>')

    def test_target_reply_changes_only_its_slot_and_can_add_a_new_label(self):
        soup, result = self.apply(
            '<div class="field"><span id="existing">Keep</span><input id="email" data-br1dg3="v1"></div>',
            '<label for="email">Email</label><input id="email">', "target",
        )
        self.assertTrue(result.applied, result)
        self.assertEqual(soup.div["class"], ["field"])
        self.assertEqual(str(soup.span), '<span id="existing">Keep</span>')
        self.assertEqual(soup.label["for"], "email")

    def test_target_mode_cannot_import_existing_parent_id(self):
        _, result = self.apply(
            '<div id="field"><input id="email" data-br1dg3="v1"></div>',
            '<div id="field"><input id="email"></div>', "target",
        )
        self.assertFalse(result.applied)
        self.assertIn("outside_id_conflict", result.warnings)

    def test_target_payload_keeps_literal_code_fences_inside_html_content(self):
        html = '<div id="sample" data-br1dg3="v1"><code>```html\n&lt;span&gt;Example&lt;/span&gt;\n```</code></div>'
        soup, result = self.apply(html, html, "target")
        self.assertTrue(result.applied, result)
        self.assertEqual(soup.code.get_text(), '```html\n<span>Example</span>\n```')
        self.assertEqual(soup.div[MARKER], "v1")

    def test_block_mode_cannot_copy_id_or_marker_from_readonly_context(self):
        for foreign in ('<p id="external">Copied</p>', '<p data-br1dg3="v3">Copied</p>'):
            with self.subTest(foreign=foreign):
                _, result = self.apply(
                    '<section><div><input id="email" data-br1dg3="v1"></div><p id="external" data-br1dg3="v3">Keep</p></section>',
                    f'<div><input id="email">{foreign}</div>',
                )
                self.assertFalse(result.applied)

    def test_lost_idless_sibling_or_duplicate_marker_rejects_entire_block(self):
        original = '<div><input id="email" data-br1dg3="v1"><img data-br1dg3="v2"></div>'
        for html in ('<div><input id="email"><img></div>', '<div><input id="email"><img data-br1dg3="v2"><img data-br1dg3="v2"></div>'):
            with self.subTest(html=html):
                _, result = self.apply(original, html)
                self.assertEqual(result.status, "tracking_rejected")

    def test_block_recovers_tracked_parent_target_and_sibling_by_unique_ids(self):
        soup, result = self.apply(
            '<div id="parent" data-br1dg3="v0"><input id="email" data-br1dg3="v1"><img id="photo" data-br1dg3="v2"></div>',
            '<fieldset id="parent"><legend>Contact</legend><input id="email"><img id="photo"></fieldset>',
        )
        self.assertTrue(result.applied, result)
        self.assertEqual([soup.fieldset[MARKER], soup.input[MARKER], soup.img[MARKER]], ["v0", "v1", "v2"])

    def test_multiple_roots_prose_or_document_shells_are_rejected(self):
        for html in (
            '<div><input id="email"></div><p>Extra</p>',
            'Explanation<div><input id="email"></div>',
            '<!--outside--><div><input id="email"></div>',
            '<html><body><input id="email"></body></html>',
        ):
            with self.subTest(html=html):
                _, result = self.apply('<div><input id="email" data-br1dg3="v1"></div>', html)
                self.assertEqual(result.status, "patch_rejected")

    def test_block_not_offered_in_target_only_mode(self):
        _, result = self.apply('<body><input id="email" data-br1dg3="v1"></body>', '<div><input id="email"></div>')
        self.assertIn("scope_not_allowed", result.warnings)

    def test_explicit_head_target_can_replace_its_own_head_only(self):
        soup, result = self.apply(
            '<html><head data-br1dg3="v1"><title>Old</title></head><body>Keep</body></html>',
            '<head data-br1dg3="v1"><title>New</title></head>', "target",
        )
        self.assertTrue(result.applied, result)
        self.assertEqual(soup.title.string, "New")
        self.assertEqual(soup.body.string, "Keep")

    def test_ordinary_block_cannot_replace_omitted_content_with_an_ellipsis(self):
        _, result = self.apply(
            '<div><span>Keep this text</span><input id="email" data-br1dg3="v1"></div>',
            '<div><span>…</span><input id="email"></div>',
        )
        self.assertIn("unexpanded_placeholder", result.warnings)
        _, preserved = self.apply(
            '<div><span>…</span><input id="email" data-br1dg3="v1"></div>',
            '<div><span>…</span><input id="email" aria-label="Email"></div>',
        )
        self.assertTrue(preserved.applied)

    def test_large_target_and_block_outputs_are_applied_when_patch_checks_pass(self):
        for mode in ("target", "block"):
            for contents in ('x' * 17_000, '<span></span>' * 170):
                with self.subTest(mode=mode, kind=contents[:1]):
                    soup, result = self.apply(
                        '<section><div><input id="email" data-br1dg3="v1"></div><p id="outside">Keep</p></section>',
                        f'<div><input id="email">{contents}</div>', mode,
                    )
                    self.assertTrue(result.applied, result)
                    self.assertEqual(soup.input[MARKER], "v1")
                    self.assertIn(contents, outer_html(soup))
                    self.assertEqual(soup.find(id="outside").string, "Keep")

    def test_stashed_assets_survive_block_replacement_and_restore_once(self):
        original = '<div><script>keep()</script><span>Email</span><input id="email"><style>.field{color:red}</style></div>'
        prepared, assets = stash_non_essential(original)
        soup = BeautifulSoup(preprocess(prepared), "html.parser")
        soup.input[MARKER] = "v1"
        source = outer_html(soup)
        reply = source.replace('<span>Email</span>', '<label for="email">Email</label>')
        fixed, result = self.apply(source, reply)
        self.assertTrue(result.applied, result)
        restored = unstash_non_essential(strip_markers(outer_html(fixed)), assets)
        self.assertEqual(restored.count('<script>keep()</script>'), 1)
        self.assertEqual(restored.count('<style>.field{color:red}</style>'), 1)
        _, rejected = self.apply(source, '<div><label for="email">Email</label><input id="email"></div>')
        self.assertIn("asset_placeholder_changed", rejected.warnings)


class TestScopedRunner(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(runner.streamer, "log"))
        self.generate = self.enterContext(patch.object(runner, "generate"))

    @staticmethod
    def reply(text):
        return LLMResult(text, True, "completed", "test-model", 10, 5, 0, 15, 0.1, 1)

    @staticmethod
    def violations():
        return [
            {"id": "label", "nodes": [{"target": ["#email"]}]},
            {"id": "image-alt", "nodes": [{"target": ["#photo"]}]},
        ]

    def test_block_then_target_repair_uses_current_context_and_keeps_raw_envelope(self):
        prompts = []
        def generate(prompt):
            prompts.append(prompt)
            target = target_from_prompt(prompt)
            if target.name == "input":
                block = BeautifulSoup(prompt.edit_scope.block_markup, "html.parser").div
                block.span.name = "label"
                block.label["for"] = "email"
                block.img["aria-describedby"] = "caption"
                return self.reply(sdg_reply(str(block), "block"))
            target["alt"] = "Photo"
            return self.reply(sdg_reply(str(target)))
        self.generate.side_effect = generate
        run = runner.run_sdg(
            '<section><div><span id="caption">Email</span><input id="email"><img id="photo"></div>'
            '<p id="outside">Keep</p></section>', self.violations(),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])
        self.assertEqual([s.reply_scope for s in run.steps], ["block", "target"])
        self.assertIn("--aria_describedby-->", prompts[1].user)
        output = BeautifulSoup(run.fixed_html, "html.parser")
        self.assertEqual(output.label["for"], "email")
        self.assertEqual(output.img["alt"], "Photo")
        self.assertEqual(output.find(id="outside").string, "Keep")
        self.assertEqual(run.total_tokens, 30)
        saved = _serialize_steps(run)[0]
        self.assertEqual(json.loads(saved["raw_reply"])["html"], saved["reply_html"])
        self.assertEqual(saved["candidate_html"], saved["reply_html"])
        self.assertEqual(saved["edit_scope"]["allowed"], ["target", "block"])
        self.assertNotIn(MARKER, run.fixed_html)

    def test_rejected_block_leaves_sibling_available_for_its_scheduled_repair(self):
        def generate(prompt):
            target = target_from_prompt(prompt)
            if target.name == "input":
                return self.reply(sdg_reply('<div><label for="email">Changed</label><input id="email"></div>', "block"))
            target["alt"] = "Photo"
            return self.reply(sdg_reply(str(target)))
        self.generate.side_effect = generate
        run = runner.run_sdg('<div><span>Email</span><input id="email"><img id="photo"></div>', self.violations())
        self.assertEqual([s.status for s in run.steps], ["tracking_rejected", "applied"])
        self.assertEqual(run.generation_status, "partial")
        output = BeautifulSoup(run.fixed_html, "html.parser")
        self.assertIsNone(output.label)
        self.assertEqual(output.span.string, "Email")
        self.assertEqual(output.img["alt"], "Photo")

    def test_oversized_target_makes_no_call_but_later_target_continues(self):
        html = '<section id="large">' + 'x' * TARGET_CHAR_LIMIT + '</section><img id="photo">'
        self.generate.return_value = self.reply(sdg_reply('<img id="photo" alt="Photo">'))
        run = runner.run_sdg(html, [
            {"id": "region", "nodes": [{"target": ["#large"]}]}, self.violations()[1],
        ])
        self.assertEqual([s.status for s in run.steps], ["prompt_too_large", "applied"])
        self.generate.assert_called_once()
        self.assertEqual(run.total_tokens, 15)
        self.assertEqual(run.generation_status, "partial")

    def test_only_oversized_target_is_retained_as_fallback(self):
        html = '<div id="large">' + '<span></span>' * TARGET_ELEMENT_LIMIT + '</div>'
        run = runner.run_sdg(html, [{"id": "region", "nodes": [{"target": ["#large"]}]}])
        self.generate.assert_not_called()
        self.assertTrue(run.fallback_used)
        self.assertIsNone(run.candidate_html)
        self.assertEqual(run.fixed_html, preprocess(html))

    def test_invalid_envelope_retains_raw_reply_usage_and_creates_no_candidate(self):
        text = '<input id="email" aria-label="Email">'
        self.generate.return_value = self.reply(text)
        run = runner.run_sdg('<div><input id="email"></div>', self.violations()[:1])
        self.assertEqual(run.steps[0].status, "invalid_reply")
        self.assertEqual(run.total_tokens, 15)
        self.assertTrue(run.fallback_used)
        saved = _serialize_steps(run)[0]
        self.assertEqual(saved["raw_reply"], text)
        self.assertIsNone(saved["reply_html"])
        self.assertIsNone(saved["candidate_html"])

    def test_large_completed_reply_is_retained_as_candidate_with_usage(self):
        html = '<div><input id="email" aria-label="Email">' + 'é' * 17_000 + '</div>'
        raw = sdg_reply(html, "block")
        self.generate.return_value = self.reply(raw)
        run = runner.run_sdg('<div><input id="email"></div>', self.violations()[:1])
        self.assertEqual(run.steps[0].status, "applied")
        self.assertEqual(run.total_tokens, 15)  # Controlled usage, not inferred from size.
        self.assertFalse(run.fallback_used)
        self.assertIsNotNone(run.candidate_html)
        self.assertEqual(BeautifulSoup(run.fixed_html, "html.parser").div.get_text(), 'é' * 17_000)
        saved = _serialize_steps(run)[0]
        self.assertEqual(saved["raw_reply"], raw)
        self.assertEqual(saved["candidate_html"], html)
        self.assertEqual(saved["reply_html"], html)

    def test_saved_scan_failure_keeps_scope_and_decoded_payload(self):
        self.generate.return_value = self.reply(sdg_reply('<input id="email" aria-label="Email">'))
        original = '<div><input id="email"></div>'
        run = runner.run_sdg(original, self.violations()[:1])
        with tempfile.TemporaryDirectory() as directory, patch.object(failed_runs, "FAILED_RUNS_DIR", Path(directory)):
            record_id = failed_runs.save_failed_run(
                original_html=original, evaluation_original_html=original, use_sdg=True,
                violations_before=self.violations()[:1], run=run, error=RuntimeError("Controlled failure"),
            )
            record = json.loads((Path(directory) / f"{record_id}.json").read_text())
        step = record["repair_run"]["steps"][0]
        self.assertEqual(step["reply_scope"], "target")
        self.assertEqual(step["edit_scope"]["reason"], "immediate_parent")
        self.assertEqual(json.loads(step["llm"]["text"])["html"], step["reply_html"])


if __name__ == "__main__":
    unittest.main()
