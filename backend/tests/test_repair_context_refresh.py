import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from app.services.repair.context import ContextExtractor
from app.services.repair.prompt import build_sdg_prompt
from app.services.sdg.builder import SDGBuilder

with patch("google.genai.Client"):
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


class TestRepairContextRefresh(unittest.TestCase):
    """Exercise real scheduling, patching and context with controlled LLM replies."""

    @staticmethod
    def _violation(rule, element_id):
        return {
            "id": rule, "help": "Controlled context-refresh fixture",
            "nodes": [{"target": [f"#{element_id}"]}],
        }

    @staticmethod
    def _snapshot(ctx, element_ids):
        ids = {node: element_ids.element(node).get("id", node) for node in ctx}
        return {
            "target": ids[ctx.graph["target"]],
            "edges": sorted((ids[u], data["relation"], ids[v]) for u, v, data in ctx.edges(data=True)),
            "nodes": {
                ids[node]: {"tag": element_ids.element(node).name, "attributes": dict(element_ids.element(node).attrs)}
                for node in ctx
            },
            "prompt": build_sdg_prompt(ctx, element_ids),
        }

    def _run_case(self, html, violations, change_parent, *, reject_parent=False):
        original = SDGBuilder(html, violations)
        child = original.element_to_id[original.soup.find(id="child")]
        before = self._snapshot(ContextExtractor.from_builder(original).extract(child), original.element_to_id)
        calls = []
        prompts = []

        def capture(ctx, element_ids):
            snapshot = self._snapshot(ctx, element_ids)
            prompts.append(snapshot)
            return snapshot["prompt"]

        def generate(prompt):
            markup = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
            target = BeautifulSoup(markup, "html.parser").find(True)
            calls.append(target["id"])
            if target["id"] == "parent":
                change_parent(target)
                text = "not HTML" if reject_parent else str(target)
            else:
                target.attrs.pop("aria-bogus", None)
                if target.name == "img":
                    target["alt"] = "Product photo"
                elif target.name == "button" and not target.has_attr("aria-labelledby"):
                    target.string = "Save"
                text = str(target)
            return LLMResult(
                text=text, ok=True, status="completed", model="controlled-test",
                prompt_tokens=10, completion_tokens=5, thought_tokens=0,
                total_tokens=15, latency_s=0.1, attempts=1,
            )

        with (
            patch.object(runner, "generate", side_effect=generate),
            patch.object(runner, "build_sdg_prompt", side_effect=capture),
            patch.object(runner.streamer, "log"),
        ):
            run = runner.run_sdg(html, violations)

        self.assertEqual(calls, ["parent", "child"])
        self.assertEqual([p["target"] for p in prompts], ["parent", "child"])
        self.assertEqual([s.status for s in run.steps], ["no_element" if reject_parent else "applied", "applied"])
        return before, prompts[1], run

    def test_child_gains_landmark_context_after_parent_becomes_region(self):
        html = '<div id="parent"><img id="child"></div>'
        violations = [self._violation("region", "parent"), self._violation("image-alt", "child")]

        def change_parent(target):
            target["role"] = "region"
            target["aria-label"] = "Product gallery"

        before, after, run = self._run_case(html, violations, change_parent)
        self.assertIn(("parent", "parent_context", "child"), before["edges"])
        self.assertNotIn(("parent", "landmark_context", "child"), before["edges"])
        self.assertIn(("parent", "landmark_context", "child"), after["edges"])
        self.assertNotIn(("parent", "parent_context", "child"), after["edges"])
        self.assertEqual(after["nodes"]["parent"]["attributes"]["role"], "region")
        self.assertIn('aria-label="Product gallery"', after["prompt"].user)
        self.assertIn("--landmark_context-->", after["prompt"].user)
        self.assertEqual(run.generation_status, "accepted")

    def test_child_loses_hidden_context_after_parent_is_unhidden(self):
        html = '<div id="parent" aria-hidden="true"><button id="child"></button></div>'
        violations = [self._violation("aria-hidden-focus", "parent"), self._violation("button-name", "child")]

        def change_parent(target):
            del target["aria-hidden"]

        before, after, _ = self._run_case(html, violations, change_parent)
        self.assertIn(("parent", "hidden_context", "child"), before["edges"])
        self.assertNotIn(("parent", "hidden_context", "child"), after["edges"])
        self.assertIn(("parent", "parent_context", "child"), after["edges"])
        self.assertNotIn("aria-hidden", after["nodes"]["parent"]["attributes"])
        self.assertNotIn('aria-hidden="true"', after["prompt"].user)
        self.assertNotIn("--hidden_context-->", after["prompt"].user)

    def test_child_reference_and_prompt_follow_rewired_label(self):
        html = (
            '<div id="parent" aria-bogus="x">'
            '<button id="child" aria-labelledby="old-label" aria-bogus="x"></button>'
            '<span id="old-label">Old label</span><span id="new-label">New label</span></div>'
        )
        violations = [self._violation("aria-valid-attr", target) for target in ("parent", "child")]

        def change_parent(target):
            del target["aria-bogus"]
            target.find(id="child")["aria-labelledby"] = "new-label"

        before, after, _ = self._run_case(html, violations, change_parent)
        self.assertIn(("child", "aria_labelledby", "old-label"), before["edges"])
        self.assertIn(("child", "aria_labelledby", "new-label"), after["edges"])
        self.assertNotIn(("child", "aria_labelledby", "old-label"), after["edges"])
        self.assertNotIn("old-label", after["nodes"])
        self.assertIn('aria-labelledby="new-label"', after["prompt"].user)
        self.assertIn("New label", after["prompt"].user)
        self.assertNotIn("Old label", after["prompt"].user)

    def test_deleted_reference_target_does_not_leave_a_stale_graph_edge(self):
        html = (
            '<div id="parent" aria-bogus="x">'
            '<button id="child" aria-labelledby="old-label" aria-bogus="x"></button>'
            '<span id="old-label">Old label</span></div>'
        )
        violations = [self._violation("aria-valid-attr", target) for target in ("parent", "child")]

        def change_parent(target):
            del target["aria-bogus"]
            target.find(id="old-label").decompose()

        before, after, _ = self._run_case(html, violations, change_parent)
        self.assertIn(("child", "aria_labelledby", "old-label"), before["edges"])
        self.assertNotIn(("child", "aria_labelledby", "old-label"), after["edges"])
        self.assertNotIn("old-label", after["nodes"])
        # The unresolved attribute is still shown; rebuilding context is not
        # automatic repair or an Axe revalidation of this new problem.
        self.assertIn('aria-labelledby="old-label"', after["prompt"].user)
        self.assertNotIn("--aria_labelledby-->", after["prompt"].user)

    def test_rejected_parent_reply_keeps_child_context_on_accepted_html(self):
        html = '<div id="parent"><img id="child"></div>'
        violations = [self._violation("region", "parent"), self._violation("image-alt", "child")]

        def change_parent(target):
            target["role"] = "region"
            target["aria-label"] = "Rejected gallery"

        before, after, run = self._run_case(html, violations, change_parent, reject_parent=True)
        self.assertEqual(before["edges"], after["edges"])
        self.assertIn(("parent", "parent_context", "child"), after["edges"])
        self.assertNotIn("role", after["nodes"]["parent"]["attributes"])
        self.assertNotIn("Rejected gallery", after["prompt"].user)
        self.assertEqual(run.generation_status, "partial")


if __name__ == "__main__":
    unittest.main()
