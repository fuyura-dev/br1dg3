import unittest
from copy import deepcopy
from itertools import permutations
from unittest.mock import patch

import networkx as nx
from bs4 import BeautifulSoup

from app.services.repair.order import dependency_view, order_violations_by_dependency
from app.services.sdg.builder import SDGBuilder
from tests.repair_fixtures import sdg_reply, target_from_prompt

with patch("google.genai.Client"):
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


class TestRepairOrder(unittest.TestCase):
    @staticmethod
    def _ids(builder):
        return {
            tag["id"]: builder.element_to_id[tag]
            for tag in builder.soup.find_all(id=True)
        }

    @staticmethod
    def _graph(nodes, edges=()):
        graph = nx.DiGraph()
        graph.add_nodes_from(nodes)
        graph.add_edges_from(edges)
        return graph

    def test_parent_waits_for_provider_before_child_without_mutating_sdg(self):
        builder = SDGBuilder(
            '<div id="container" aria-describedby="description"><img id="photo"></div>'
            '<span id="description">Description</span>'
        )
        ids = self._ids(builder)
        original = deepcopy(builder.graph)
        self.assertFalse(builder.graph.has_edge(ids["container"], ids["photo"]))

        view = dependency_view(builder.graph, builder.element_to_id)
        self.assertTrue(view.has_edge(ids["container"], ids["photo"]))
        self.assertTrue(view.has_edge(ids["description"], ids["container"]))
        self.assertEqual(
            order_violations_by_dependency(view, list(ids.values())),
            [ids["description"], ids["container"], ids["photo"]],
        )
        self.assertTrue(nx.utils.graphs_equal(builder.graph, original))

    def test_ancestor_constraint_crosses_unaffected_wrappers(self):
        builder = SDGBuilder(
            '<div id="container" aria-describedby="description">'
            '<section><span><img id="photo"></span></section></div>'
            '<p id="description">Description</p>'
        )
        ids = self._ids(builder)
        view = dependency_view(builder.graph, builder.element_to_id)
        self.assertEqual(
            order_violations_by_dependency(view, list(reversed(ids.values()))),
            [ids["description"], ids["container"], ids["photo"]],
        )

    def test_reference_directions_and_sequence_exclusions(self):
        graph = nx.MultiDiGraph()
        references = (
            "aria_labelledby", "aria_describedby", "aria_controls", "aria_owns",
            "aria_errormessage", "id_reference",
        )
        for relation in references:
            graph.add_edge(f"source_{relation}", f"provider_{relation}", relation=relation)
        for relation in ("label_input", "heading_hierarchy", "landmark_structure", "form_group"):
            graph.add_edge(f"provider_{relation}", f"dependent_{relation}", relation=relation)
        for relation in ("focus_order", "name_group"):
            graph.add_edge(f"a_{relation}", f"b_{relation}", relation=relation)

        view = dependency_view(graph)
        self.assertEqual(list(view), list(graph))
        for relation in references:
            self.assertTrue(view.has_edge(f"provider_{relation}", f"source_{relation}"))
            self.assertFalse(view.has_edge(f"source_{relation}", f"provider_{relation}"))
        for relation in ("label_input", "heading_hierarchy", "landmark_structure", "form_group"):
            self.assertTrue(view.has_edge(f"provider_{relation}", f"dependent_{relation}"))
        for relation in ("focus_order", "name_group"):
            self.assertFalse(view.has_edge(f"a_{relation}", f"b_{relation}"))
            self.assertFalse(view.has_edge(f"b_{relation}", f"a_{relation}"))

    def test_paths_through_unaffected_dependency_nodes(self):
        graph = self._graph(
            ["dependent", "independent", "bridge", "provider"],
            [("provider", "bridge"), ("bridge", "dependent")],
        )
        self.assertEqual(
            order_violations_by_dependency(graph, ["dependent", "provider", "independent"]),
            ["independent", "provider", "dependent"],
        )

    def test_unaffected_provider_does_not_delay_an_independent_target(self):
        graph = self._graph(
            ["early_target", "late_target", "healthy_provider"],
            [("healthy_provider", "early_target")],
        )
        self.assertEqual(
            order_violations_by_dependency(graph, ["late_target", "early_target"]),
            ["early_target", "late_target"],
        )

    def test_document_order_breaks_ties_after_dependency_is_released(self):
        graph = self._graph(
            ["dependent", "provider", "independent"], [("provider", "dependent")],
        )
        expected = ["provider", "dependent", "independent"]
        for targets in permutations(graph):
            with self.subTest(targets=targets):
                self.assertEqual(order_violations_by_dependency(graph, list(targets)), expected)

    def test_cycle_through_unaffected_node_preserves_external_dependencies(self):
        graph = self._graph(
            ["after", "b", "provider", "a", "bridge"],
            [("provider", "a"), ("a", "bridge"), ("bridge", "b"), ("b", "a"), ("a", "after")],
        )
        original = deepcopy(graph)
        for targets in permutations(["after", "a", "b", "provider"]):
            with self.subTest(targets=targets):
                self.assertEqual(
                    order_violations_by_dependency(graph, list(targets)),
                    ["provider", "b", "a", "after"],
                )
        self.assertTrue(nx.utils.graphs_equal(graph, original))

    def test_parent_child_reference_cycle_uses_document_order(self):
        builder = SDGBuilder('<div id="parent" aria-labelledby="child"><span id="child">Name</span></div>')
        ids = self._ids(builder)
        view = dependency_view(builder.graph, builder.element_to_id)
        self.assertTrue(view.has_edge(ids["child"], ids["parent"]))
        self.assertTrue(view.has_edge(ids["parent"], ids["child"]))
        self.assertEqual(
            order_violations_by_dependency(view, [ids["child"], ids["parent"]]),
            [ids["parent"], ids["child"]],
        )

    def test_dependencies_between_cycles(self):
        graph = self._graph(
            ["down_b", "down_a", "up_b", "up_a"],
            [("up_a", "up_b"), ("up_b", "up_a"), ("down_a", "down_b"),
             ("down_b", "down_a"), ("up_b", "down_a")],
        )
        self.assertEqual(
            order_violations_by_dependency(graph, list(graph)),
            ["up_b", "up_a", "down_b", "down_a"],
        )

    def test_self_reference_does_not_prevent_scheduling(self):
        graph = self._graph(["first", "second"], [("first", "first")])
        self.assertEqual(order_violations_by_dependency(graph, ["second", "first"]), ["first", "second"])

    def test_empty_missing_and_duplicate_targets(self):
        graph = self._graph(["first", "healthy", "second"])
        self.assertEqual(order_violations_by_dependency(graph, []), [])
        self.assertEqual(order_violations_by_dependency(graph, ["absent"]), [])
        self.assertEqual(
            order_violations_by_dependency(graph, ["second", "absent", "first", "second"]),
            ["first", "second"],
        )


class TestRepairOrderIntegration(unittest.TestCase):
    def setUp(self):
        self.html = (
            '<div id="container" aria-describedby="description" aria-bogus="x"><img id="photo"></div>'
            '<span id="description" aria-bogus="x">Description</span>'
        )
        self.violations = [
            {"id": "aria-valid-attr", "help": "Remove invalid ARIA attributes", "nodes": [
                {"target": ["#container"]}, {"target": ["#description"]},
            ]},
            {"id": "image-alt", "help": "Provide an image alternative", "nodes": [{"target": ["#photo"]}]},
        ]
        self.generate = self.enterContext(patch.object(runner, "generate"))
        self.enterContext(patch.object(runner.streamer, "log"))

    @staticmethod
    def _reply(html):
        return LLMResult(
            text=html, ok=True, status="completed", model="test-model",
            prompt_tokens=10, completion_tokens=5, thought_tokens=0,
            total_tokens=15, latency_s=0.1, attempts=1,
        )

    def test_runner_schedules_once_and_rebuilds_context_after_each_patch(self):
        targets = []
        prompts = []

        def generate(prompt):
            prompts.append(prompt.user)
            target = target_from_prompt(prompt)
            targets.append(target["id"])
            target.attrs.pop("aria-bogus", None)
            if target["id"] == "description":
                target.string = "Updated description"
            elif target["id"] == "container":
                target["title"] = "Updated container"
            else:
                target["alt"] = "Photo"
            return self._reply(sdg_reply(str(target)))

        self.generate.side_effect = generate
        with patch.object(runner, "order_violations_by_dependency", wraps=order_violations_by_dependency) as order:
            run = runner.run_sdg(self.html, self.violations)

        order.assert_called_once()
        self.assertEqual(targets, ["description", "container", "photo"])
        self.assertEqual([step.status for step in run.steps], ["applied"] * 3)
        self.assertEqual(run.generation_status, "accepted")
        self.assertIn("Updated description", prompts[1])
        self.assertIn("Updated container", prompts[2])
        self.assertEqual(BeautifulSoup(run.fixed_html, "html.parser").find("img")["alt"], "Photo")
        self.assertNotIn("data-br1dg3", run.fixed_html)

    def test_baseline_keeps_one_full_document_generation_without_scheduling(self):
        self.generate.return_value = self._reply(self.html)
        with patch.object(runner, "dependency_view") as view, patch.object(runner, "order_violations_by_dependency") as order:
            run = runner.run_baseline(self.html, self.violations)
        view.assert_not_called()
        order.assert_not_called()
        self.generate.assert_called_once()
        self.assertEqual(len(run.steps), 1)
        self.assertEqual(run.generation_status, "accepted")
        self.assertIn("## HTML document", self.generate.call_args.args[0].user)


if __name__ == "__main__":
    unittest.main()
