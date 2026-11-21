import unittest
from unittest.mock import patch

from app.services.sdg.builder import SDGBuilder
from app.services.validation import semantic

LABEL = '<label id="label" for="field">Name</label><input id="field">'
RADIOS = '<form id="f">' + '<input type="radio" name="x">' * 4 + '</form>'


class TestSDGPreservation(unittest.TestCase):
    def test_repeated_controls_count_as_distinct_occurrences(self):
        result = semantic.calculate_semantic_preservation(RADIOS, RADIOS)
        self.assertEqual(result.dependencies_before, 10)  # 4 ownership + 3 group + 3 focus
        self.assertEqual(result.dependencies_valid, 10)
        self.assertEqual(result.dependencies_before, sum(result.breakdown_before.values()))
        self.assertEqual(result.dependencies_valid, sum(result.breakdown_valid.values()))
        self.assertEqual(len(result.edge_outcomes), 10)

    def test_adding_id_does_not_lose_form_relationship(self):
        before = '<form id="f"><input name="x"></form>'
        after = before.replace('name="x"', 'name="x" id="new"')
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.preservation_rate, 100)

    def test_consistent_reference_and_id_rename_retains_edge(self):
        result = semantic.calculate_semantic_preservation(LABEL, LABEL.replace('field', 'renamed'))
        self.assertEqual(result.dependencies_valid, 1)

    def test_fragment_reference_rename_does_not_lose_anchor_identity(self):
        before = '<a href="#old">Go</a><div id="old"></div>'
        result = semantic.calculate_semantic_preservation(before, before.replace('old', 'new'))
        self.assertEqual(result.preservation_rate, 100)

    def test_redirected_label_loses_original_edge(self):
        before = LABEL + '<input id="other">'
        after = before.replace('for="field"', 'for="other"')
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.status, "measured")
        self.assertEqual(result.broken_count, 1)
        self.assertEqual(result.broken_examples[0]["relation"], "label_input")

    def test_metric_does_not_claim_validity_for_preserved_invalid_edge(self):
        # The unchanged SDG extractor still emits label -> div by reference.
        result = semantic.calculate_semantic_preservation(LABEL, LABEL.replace('<input id="field">', '<div id="field"></div>'))
        self.assertEqual(result.preservation_rate, 100)
        self.assertEqual(result.metric, "sdg_relationship_preservation")

    def test_different_edge_types_between_same_nodes_are_distinct(self):
        before = '<input id="i" aria-labelledby="t" aria-describedby="t"><span id="t">Text</span>'
        result = semantic.calculate_semantic_preservation(before, before.replace(' aria-describedby="t"', ''))
        self.assertEqual(result.dependencies_before, 2)
        self.assertEqual(result.dependencies_valid, 1)

    def test_added_heading_can_change_direct_edge_despite_beneficial_edit(self):
        before = '<h1 id="a">Products</h1><h2 id="b">Laptops</h2>'
        after = '<h1 id="a">Products</h1><h2 id="x">Computers</h2><h3 id="b">Laptops</h3>'
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.dependencies_before, 1)
        self.assertEqual(result.preservation_rate, 0)

    def test_focus_measures_existing_direct_chain_edges(self):
        before = '<button id="a">A</button><button id="b">B</button>'
        after = before.replace('<button id="b">', '<button id="x">X</button><button id="b">')
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.preservation_rate, 0)
        self.assertEqual(result.broken_examples[0]["relation"], "focus_order")

    def test_new_relationships_do_not_inflate_numerator(self):
        result = semantic.calculate_semantic_preservation(LABEL, LABEL + '<label for="new">New</label><input id="new">')
        self.assertEqual(result.dependencies_before, 1)
        self.assertEqual(result.dependencies_valid, 1)
        self.assertEqual(result.preservation_rate, 100)

    def test_zero_original_edges_is_not_applicable_even_after_additions(self):
        result = semantic.calculate_semantic_preservation('<p>Text</p>', LABEL)
        self.assertEqual(result.status, "no_relationships")
        self.assertFalse(result.has_dependencies)
        self.assertIsNone(result.preservation_rate)

    def test_repeated_insertions_remain_unresolved_without_false_perfect_score(self):
        before = LABEL + RADIOS
        after = LABEL + RADIOS.replace('</form>', '<input type="radio" name="x"></form>')
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.status, "unresolved_matching")
        self.assertIsNone(result.dependencies_valid)
        self.assertIsNone(result.broken_count)
        self.assertIsNone(result.preservation_rate)
        self.assertGreater(result.preserved_observed, 0)
        self.assertGreater(result.unresolved_count, 0)
        self.assertEqual(result.dependencies_before,
                         result.preserved_observed + result.not_preserved_observed + result.unresolved_count)

    def test_original_extraction_failure_is_not_no_dependencies(self):
        with patch.object(semantic, 'SDGBuilder', side_effect=RuntimeError('controlled')):
            result = semantic.calculate_semantic_preservation(LABEL, LABEL)
        self.assertEqual(result.status, "extraction_error")
        self.assertIsNone(result.dependencies_before)
        self.assertIsNone(result.has_dependencies)
        self.assertIsNone(result.preservation_rate)
        self.assertEqual(result.error['stage'], 'original')

    def test_candidate_extraction_failure_keeps_original_denominator(self):
        with patch.object(semantic, 'SDGBuilder', side_effect=[SDGBuilder(LABEL), RuntimeError('controlled')]):
            result = semantic.calculate_semantic_preservation(LABEL, LABEL)
        self.assertEqual(result.dependencies_before, 1)
        self.assertTrue(result.has_dependencies)
        self.assertEqual(result.status, 'extraction_error')
        self.assertIsNone(result.dependencies_valid)

    def test_malformed_graph_is_not_silently_partially_counted(self):
        builder = SDGBuilder(LABEL)
        builder.graph.add_edge('missing', 'other', relation='label_input')
        with patch.object(semantic, 'SDGBuilder', return_value=builder):
            result = semantic.calculate_semantic_preservation(LABEL, LABEL)
        self.assertEqual(result.status, 'extraction_error')
        self.assertIsNone(result.dependencies_before)

    def test_no_candidate_policy_does_not_measure_fallback(self):
        with patch.object(semantic, 'SDGBuilder', wraps=SDGBuilder) as builder:
            result = semantic.calculate_semantic_preservation(LABEL, LABEL, no_candidate=True)
        self.assertEqual(builder.call_count, 1)
        self.assertEqual(result.status, 'no_candidate_failure_policy')
        self.assertEqual(result.dependencies_valid, 0)
        self.assertEqual(result.preservation_rate, 0)
        self.assertIsNone(result.broken_count)
        self.assertIsNone(result.preserved_observed)
        self.assertEqual(result.edge_outcomes, [])

    def test_no_candidate_cannot_hide_unknown_original_inventory(self):
        with patch.object(semantic, 'SDGBuilder', side_effect=RuntimeError('controlled')):
            result = semantic.calculate_semantic_preservation(LABEL, None, no_candidate=True)
        self.assertEqual(result.status, 'extraction_error')
        self.assertIsNone(result.preservation_rate)

    def test_no_candidate_without_original_edges_remains_na(self):
        result = semantic.calculate_semantic_preservation('<p>Text</p>', None, no_candidate=True)
        self.assertEqual(result.status, 'no_relationships')
        self.assertIsNone(result.preservation_rate)

    def test_empty_supplied_candidate_has_measured_zero_preservation(self):
        result = semantic.calculate_semantic_preservation(LABEL, '')
        self.assertEqual(result.status, 'measured')
        self.assertEqual(result.broken_count, 1)
        self.assertEqual(result.preservation_rate, 0)

    def test_absent_input_is_unavailable_not_empty_candidate(self):
        result = semantic.calculate_semantic_preservation(LABEL, None)
        self.assertEqual(result.status, 'extraction_error')
        self.assertIsNone(result.preservation_rate)

    def test_removed_unmatched_endpoint_is_unresolved_not_assumed_deleted(self):
        result = semantic.calculate_semantic_preservation(LABEL, '<input id="field">')
        self.assertEqual(result.status, 'unresolved_matching')
        self.assertEqual(result.unresolved_count, 1)

    def test_duplicate_id_is_not_used_as_unique_anchor(self):
        before = '<form id="f"><input id="x"><input id="x"></form>'
        after = before.replace('</form>', '<input id="x"></form>')
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.matching['duplicate_original_ids'], ['x'])
        self.assertEqual(result.status, 'unresolved_matching')
        self.assertEqual(result.matching['methods']['unique_id'], 1)  # Only form f.

    def test_tracking_markers_cannot_bias_either_method(self):
        after = LABEL.replace('id="field"', 'id="new"').replace('for="field"', 'for="new"')
        stamped = after.replace('<input ', '<input data-br1dg3="v1" ')
        self.assertEqual(semantic.calculate_semantic_preservation(LABEL, after).preservation_rate,
                         semantic.calculate_semantic_preservation(LABEL, stamped).preservation_rate)

    def test_id_anchors_cannot_be_overwritten_by_subtree_alignment(self):
        before = '<div><button id="a">Same</button><button id="b">Same</button></div>'
        after = '<div><button id="b">Same</button><button id="a">Same</button></div>'
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.preservation_rate, 0)
        pairs = result.matching['pairs']
        self.assertEqual(len({p['candidate'] for p in pairs}), len(pairs))

    def test_unchanged_repeated_subtrees_under_id_anchors_are_matchable(self):
        before = RADIOS + RADIOS.replace('id="f"', 'id="g"')
        result = semantic.calculate_semantic_preservation(before, '<h1>New</h1>' + before)
        self.assertEqual(result.preservation_rate, 100)

    def test_evidence_is_deterministic(self):
        after = LABEL.replace('field', 'renamed')
        results = [semantic.calculate_semantic_preservation(LABEL, after).to_dict() for _ in range(4)]
        self.assertTrue(all(result == results[0] for result in results))

    def test_api_names_identify_new_meaning_and_keep_legacy_aliases(self):
        result = semantic.calculate_semantic_preservation(LABEL, LABEL).to_dict()
        self.assertEqual(result['metric_version'], 2)
        self.assertEqual(result['relationships_preserved'], result['dependencies_valid'])
        self.assertEqual(result['preservation_rate'], 100)

    def test_shared_repair_graph_is_not_modified_by_matching(self):
        original, repaired = SDGBuilder(LABEL), SDGBuilder(LABEL)
        original_state, repaired_state = original.to_dict(), repaired.to_dict()
        from app.services.validation.semantic_matching import match_elements
        match_elements(original, repaired)
        self.assertEqual(original.to_dict(), original_state)
        self.assertEqual(repaired.to_dict(), repaired_state)

    def test_evaluator_keeps_other_metrics_and_serializes_missing_result(self):
        with patch('google.genai.Client'):
            from app.services.validation.evaluator import evaluate_repair
        with (patch.object(semantic, 'SDGBuilder', side_effect=[SDGBuilder(LABEL), RuntimeError('controlled')]),
              patch('app.services.validation.evaluator.streamer.log')):
            report = evaluate_repair(LABEL, LABEL, violations_before=[], violations_after=[], run_detection_if_missing=False)
        self.assertEqual(report.structure.structure_similarity, 1)
        self.assertTrue(report.safety.is_valid)
        data = report.to_dict()['semantic']
        self.assertEqual(data['relationships_before'], 1)
        self.assertIsNone(data['relationships_preserved'])
        self.assertEqual(data['status'], 'extraction_error')


if __name__ == '__main__':
    unittest.main()
