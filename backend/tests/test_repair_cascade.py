import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from app.services.repair import failed_runs
from app.services.repair.cascade import infer_skips, supported_condition
from app.services.validation.efficiency import calculate_efficiency_from_run

with patch("google.genai.Client"):
    from app.api.repair import RepairRequest, _serialize_steps, _summarize
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


class TestLocalCascadeConditions(unittest.TestCase):
    def condition(self, html, rule):
        return supported_condition(BeautifulSoup(html, "html.parser").find(id="target"), rule)

    def test_listitem_requires_a_direct_supported_parent(self):
        for parent in ("ul", "ol", "menu"):
            with self.subTest(parent=parent):
                self.assertIsNotNone(self.condition(f'<{parent}><li id="target">Item</li></{parent}>', "listitem"))
        for html in (
            '<ul><div><li id="target">Item</li></div></ul>',
            '<div role="list"><section><li id="target">Item</li></section></div>',
            '<ul role="button"><li id="target">Item</li></ul>',
            '<ul><li role="button" id="target">Item</li></ul>',
        ):
            with self.subTest(html=html):
                self.assertIsNone(self.condition(html, "listitem"))

    def test_dlitem_supports_one_plain_div_group_but_not_arbitrary_ancestors(self):
        for html in (
            '<dl><dt id="target">Term</dt></dl>',
            '<dl><div><dd id="target">Definition</dd></div></dl>',
            '<dl role="list"><dt id="target">Term</dt></dl>',
        ):
            with self.subTest(html=html):
                self.assertIsNotNone(self.condition(html, "dlitem"))
        for html in (
            '<dl><section><dt id="target">Term</dt></section></dl>',
            '<dl><div><div><dd id="target">Definition</dd></div></div></dl>',
            '<dl role="button"><dt id="target">Term</dt></dl>',
            '<dl><div role="group"><dt id="target">Term</dt></div></dl>',
        ):
            with self.subTest(html=html):
                self.assertIsNone(self.condition(html, "dlitem"))

    def test_region_supports_simple_native_and_explicit_landmarks(self):
        for html in (
            '<main><p id="target">Text</p></main>',
            '<nav><p id="target">Text</p></nav>',
            '<aside><p id="target">Text</p></aside>',
            '<search><p id="target">Text</p></search>',
            '<div role="main"><p id="target">Text</p></div>',
            '<main id="target">Text</main>',
        ):
            with self.subTest(html=html):
                self.assertIsNotNone(self.condition(html, "region"))

    def test_region_does_not_use_context_labels_hidden_content_or_conflicting_roles_as_proof(self):
        for html in (
            '<main role="none"><p id="target">Text</p></main>',
            '<main role="button"><p id="target">Text</p></main>',
            '<section role="region" aria-labelledby="missing"><p id="target">Text</p></section>',
            '<section aria-label="Named"><p id="target">Text</p></section>',
            '<header><p id="target">Text</p></header>',
            '<div role="unknown main"><p id="target">Text</p></div>',
            '<main aria-hidden="true"><p id="target">Text</p></main>',
            '<main><p id="target" hidden>Text</p></main>',
            '<div inert><main><p id="target">Text</p></main></div>',
        ):
            with self.subTest(html=html):
                self.assertIsNone(self.condition(html, "region"))

    def test_hidden_focus_only_infers_removal_of_the_hiding_condition(self):
        self.assertIsNotNone(self.condition('<div id="target" aria-hidden="false"><button>Go</button></div>', "aria-hidden-focus"))
        for html in (
            '<div aria-hidden="true"><button id="target" aria-hidden="false">Go</button></div>',
            '<div id="target" aria-hidden="true"><button disabled>Go</button></div>',
            '<div id="target" aria-hidden="true"><button tabindex="-1">Go</button></div>',
            '<div id="target" aria-hidden="invalid">Text</div>',
        ):
            with self.subTest(html=html):
                self.assertIsNone(self.condition(html, "aria-hidden-focus"))

    def test_unknown_rule_never_triggers_a_skip(self):
        self.assertIsNone(self.condition('<main><img id="target" alt="Image"></main>', "image-alt"))

    def test_inference_requires_prior_acceptance_and_original_evidence(self):
        target = BeautifulSoup('<main><p id="target">Text</p></main>', "html.parser").p
        self.assertEqual(infer_skips(target, ["region"], {"region": None}, has_accepted_patch=False), [])
        self.assertEqual(infer_skips(target, ["region"], {}, has_accepted_patch=True), [])
        self.assertEqual(infer_skips(target, ["region"], {"region": "already supported"}, has_accepted_patch=True), [])
        evidence = infer_skips(target, ["region"], {"region": None}, has_accepted_patch=True)
        self.assertEqual(evidence[0]["verification"], "local_dom_only")
        self.assertEqual(evidence[0]["basis"], "changed_from_original")


class TestCascadeRunner(unittest.TestCase):
    def setUp(self):
        self.generate = self.enterContext(patch.object(runner, "generate"))
        self.enterContext(patch.object(runner.streamer, "log"))
        self.prompts = []

    @staticmethod
    def violation(rule, selector):
        return {"id": rule, "nodes": [{"target": [selector]}]}

    @staticmethod
    def reply(text):
        return LLMResult(
            text=text, ok=True, status="completed", model="test-model",
            prompt_tokens=10, completion_tokens=5, thought_tokens=0,
            total_tokens=15, latency_s=0.1, attempts=1,
        )

    def run_case(self, html, child_rules, change_parent, *, reject_parent=False):
        violations = [self.violation("aria-valid-attr", "#parent")]
        violations.extend(self.violation(rule, "#child") for rule in child_rules)

        def generate(prompt):
            self.prompts.append(prompt.user)
            markup = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
            target = BeautifulSoup(markup, "html.parser").find(True)
            if target.get("id") == "parent":
                change_parent(target)
                if reject_parent:
                    return self.reply("not HTML")
            return self.reply(str(target))

        self.generate.side_effect = generate
        return runner.run_sdg(html, violations)

    def test_first_target_is_never_skipped_even_if_local_predicate_disagrees_with_scan(self):
        cases = [
            ('<main><p id="child">Text</p></main>', "region"),
            ('<ul><li id="child">Item</li></ul>', "listitem"),
            ('<dl><dt id="child">Term</dt></dl>', "dlitem"),
            ('<div id="child"><button>Go</button></div>', "aria-hidden-focus"),
        ]
        for html, rule in cases:
            with self.subTest(rule=rule):
                self.generate.reset_mock()
                self.generate.return_value = self.reply("not HTML")
                run = runner.run_sdg(html, [self.violation(rule, "#child")])
                self.generate.assert_called_once()
                self.assertEqual(run.steps[0].status, "no_element")
                self.assertEqual(run.steps[0].requested_rules, [rule])
                self.assertEqual(run.steps[0].skipped_rules, [])

    def test_accepted_parent_landmark_skips_child_and_records_unverified_evidence(self):
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><p id="child">Text</p></div>', ["region"],
            lambda target: setattr(target, "name", "main"),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "cascade_skipped"])
        self.assertEqual(self.generate.call_count, 1)
        child = run.steps[1]
        self.assertEqual(child.rules, ["region"])
        self.assertEqual(child.requested_rules, [])
        self.assertIsNone(child.llm)
        self.assertEqual(child.skipped_rules[0]["rule_id"], "region")
        self.assertEqual(child.skipped_rules[0]["verification"], "local_dom_only")
        self.assertIn("main landmark", child.skipped_rules[0]["reason"])
        self.assertEqual(run.failed_steps, 0)
        self.assertEqual(run.generation_status, "accepted")
        self.assertEqual(run.total_tokens, 15)
        metrics = calculate_efficiency_from_run(run)
        self.assertEqual((metrics.cascaded_count, metrics.patched_count, metrics.total_elements), (1, 1, 2))
        self.assertEqual(metrics.cascade_rate, 50)
        self.assertEqual(_serialize_steps(run)[1]["skipped_rules"], child.skipped_rules)
        self.assertIn("locally skipped (not individually Axe-verified)", _summarize(RepairRequest(html="x"), run, 2, 0))

    def test_partial_skip_filters_the_actual_prompt_but_keeps_original_rules(self):
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><img id="child"></div>', ["region", "image-alt"],
            lambda target: setattr(target, "name", "main"),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])
        self.assertEqual(self.generate.call_count, 2)
        child = run.steps[1]
        self.assertEqual(child.rules, ["region", "image-alt"])
        self.assertEqual(child.requested_rules, ["image-alt"])
        self.assertEqual([item["rule_id"] for item in child.skipped_rules], ["region"])
        violations_block = self.prompts[1].split("## Violations on the target element\n", 1)[1].split("\n\n##", 1)[0]
        self.assertIn("image-alt", violations_block)
        self.assertNotIn("region", violations_block)
        self.assertEqual(calculate_efficiency_from_run(run).cascaded_count, 0)

    def test_rejected_parent_cannot_cause_a_skip(self):
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><p id="child">Text</p></div>', ["region"],
            lambda target: setattr(target, "name", "main"), reject_parent=True,
        )
        self.assertEqual([s.status for s in run.steps], ["no_element", "applied"])
        self.assertEqual(run.steps[1].skipped_rules, [])
        self.assertEqual(run.steps[1].requested_rules, ["region"])
        self.assertEqual(self.generate.call_count, 2)

    def test_accepted_unchanged_parent_cannot_cause_a_skip(self):
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><p id="child">Text</p></div>', ["region"], lambda target: None,
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])
        self.assertEqual(run.steps[1].skipped_rules, [])

    def test_preexisting_supported_condition_is_not_attributed_to_parent_patch(self):
        run = self.run_case(
            '<main id="parent" aria-bogus="x"><p id="child">Text</p></main>', ["region"],
            lambda target: target.attrs.pop("aria-bogus"),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])
        self.assertEqual(run.steps[1].skipped_rules, [])

    def test_listitem_parent_conversion_triggers_narrow_skip(self):
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><li id="child">Item</li></div>', ["listitem"],
            lambda target: setattr(target, "name", "ul"),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "cascade_skipped"])

    def test_listitem_with_intervening_wrapper_still_gets_repaired(self):
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><div><li id="child">Item</li></div></div>', ["listitem"],
            lambda target: setattr(target, "name", "ul"),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])
        self.assertEqual(run.steps[1].skipped_rules, [])

    def test_description_list_conversion_supports_one_group(self):
        run = self.run_case(
            '<section id="parent" aria-bogus="x"><div><dt id="child">Term</dt></div></section>', ["dlitem"],
            lambda target: setattr(target, "name", "dl"),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "cascade_skipped"])

    def test_parent_removes_child_hiding_condition_without_guessing_focusability(self):
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><div id="child" aria-hidden="true"><button>Go</button></div></div>',
            ["aria-hidden-focus"], lambda target: target.find(id="child").attrs.pop("aria-hidden"),
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "cascade_skipped"])

    def test_uncertain_named_landmark_remains_scheduled(self):
        def change_parent(target):
            target["role"] = "region"
            target["aria-labelledby"] = "missing"
        run = self.run_case(
            '<div id="parent" aria-bogus="x"><p id="child">Text</p></div>', ["region"], change_parent,
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])

    def test_later_patch_can_remove_the_condition_before_child_is_reached(self):
        def generate(prompt):
            markup = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
            target = BeautifulSoup(markup, "html.parser").find(True)
            if target["id"] == "outer":
                target.find(id="parent").name = "main"
            elif target["id"] == "parent":
                target.name = "section"
            return self.reply(str(target))
        self.generate.side_effect = generate
        run = runner.run_sdg(
            '<div id="outer"><div id="parent"><p id="child">Text</p></div></div>',
            [self.violation("aria-valid-attr", "#outer"), self.violation("aria-valid-attr", "#parent"),
             self.violation("region", "#child")],
        )
        self.assertEqual([s.status for s in run.steps], ["applied", "applied", "applied"])
        self.assertEqual(run.steps[-1].skipped_rules, [])
        self.assertEqual(self.generate.call_count, 3)

    def test_cascade_does_not_invoke_axe_between_steps(self):
        with patch("app.services.detection.detect.detect") as detect:
            run = self.run_case(
                '<div id="parent"><p id="child">Text</p></div>', ["region"],
                lambda target: setattr(target, "name", "main"),
            )
        detect.assert_not_called()
        self.assertEqual(run.steps[-1].status, "cascade_skipped")

    def test_failed_generation_keeps_original_requested_and_locally_skipped_rules(self):
        def generate(prompt):
            if self.generate.call_count == 1:
                markup = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
                target = BeautifulSoup(markup, "html.parser").div
                target.name = "main"
                return self.reply(str(target))
            raise RuntimeError("Controlled failure")
        self.generate.side_effect = generate
        run = runner.run_sdg(
            '<div id="parent"><img id="child"></div>',
            [self.violation("region", "#parent"), self.violation("region", "#child"), self.violation("image-alt", "#child")],
        )
        child = _serialize_steps(run)[1]
        self.assertEqual(child["status"], "llm_error")
        self.assertEqual(child["rules"], ["region", "image-alt"])
        self.assertEqual(child["requested_rules"], ["image-alt"])
        self.assertEqual(child["skipped_rules"][0]["rule_id"], "region")
        self.assertEqual(run.generation_status, "partial")

    def test_saved_failure_record_retains_skip_evidence(self):
        html = '<div id="parent"><p id="child">Text</p></div>'
        run = self.run_case(html, ["region"], lambda target: setattr(target, "name", "main"))
        with tempfile.TemporaryDirectory() as directory, patch.object(failed_runs, "FAILED_RUNS_DIR", Path(directory)):
            record_id = failed_runs.save_failed_run(
                original_html=html, evaluation_original_html=html, use_sdg=True,
                violations_before=[], run=run, error=RuntimeError("Controlled scan failure"),
            )
            saved = json.loads((Path(directory) / f"{record_id}.json").read_text())
        self.assertEqual(saved["repair_run"]["steps"][1]["skipped_rules"], run.steps[1].skipped_rules)
        self.assertEqual(saved["repair_run"]["steps"][1]["requested_rules"], [])

    def test_baseline_keeps_one_generation_and_records_requested_rules(self):
        self.generate.return_value = self.reply('<main><p>Text</p></main>')
        with patch.object(runner, "infer_skips") as infer:
            run = runner.run_baseline('<p>Text</p>', [self.violation("region", "p")])
        infer.assert_not_called()
        self.generate.assert_called_once()
        self.assertEqual(run.steps[0].requested_rules, ["region"])
        self.assertEqual(run.steps[0].skipped_rules, [])

    def test_prompt_construction_failure_does_not_claim_rules_were_requested(self):
        with patch.object(runner, "build_baseline_prompt", side_effect=ValueError("Controlled prompt failure")):
            run = runner.run_baseline('<p>Text</p>', [self.violation("region", "p")])
        self.generate.assert_not_called()
        self.assertEqual(run.steps[0].rules, ["region"])
        self.assertEqual(run.steps[0].requested_rules, [])
        self.assertEqual(run.generation_status, "no_candidate")


if __name__ == "__main__":
    unittest.main()
