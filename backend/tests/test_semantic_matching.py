"""Correspondence and v4 unmatched-endpoint scoring, shared by both repair methods."""

import unittest

from app.services.sdg.builder import SDGBuilder
from app.services.validation import semantic, semantic_matching


class TestSemanticMatchingV4(unittest.TestCase):
    def match(self, before, after):
        original, candidate = SDGBuilder(before), SDGBuilder(after)
        mapping, evidence = semantic_matching.match_elements(original, candidate)
        self.assertEqual(len(mapping), len(set(mapping.values())))
        return original, candidate, mapping, evidence

    def test_each_label_attribute_can_be_added_changed_or_removed(self):
        for attribute, element in (("aria-label", "button"), ("alt", "input"), ("title", "button")):
            for old, new in (("", f' {attribute}="Name"'),
                             (f' {attribute}="Old"', f' {attribute}="New"'),
                             (f' {attribute}="Name"', "")):
                with self.subTest(attribute=attribute, old=old, new=new):
                    template = '<form id="f"><' + element + '{}></' + element + '></form>'
                    result = semantic.calculate_semantic_preservation(template.format(old), template.format(new))
                    self.assertEqual(result.status, "measured")
                    self.assertEqual(result.preservation_rate, 100)
                    self.assertEqual(result.matching["methods"]["label_attributes_in_matched_parent"], 1)

    def test_strong_matches_take_priority_over_fallback_and_block_cross_gap_match(self):
        before = '<form id="f"><button aria-label="A"></button><button aria-label="B"></button></form>'
        after = '<form id="f"><button aria-label="B"></button><button aria-label="C"></button></form>'
        original, candidate, mapping, evidence = self.match(before, after)
        old_buttons = [n for n in original.graph if original.element_to_id.element(n).name == "button"]
        new_buttons = [n for n in candidate.graph if candidate.element_to_id.element(n).name == "button"]
        self.assertEqual(mapping[old_buttons[1]], new_buttons[0])
        self.assertNotIn(old_buttons[0], mapping)  # Different gaps around matched anchor B.
        self.assertNotIn("label_attributes_in_matched_parent", evidence["methods"])
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.status, "measured")
        self.assertGreater(result.unmatched_endpoint_count, 0)
        self.assertLess(result.preservation_rate, 100)

    def test_identical_siblings_pair_in_order_only_when_same_gap_and_same_count(self):
        before = '<section id="s"><form><button></button><button></button></form></section>'
        after = '<section id="s"><form title="Search"><button aria-label="A"></button><button aria-label="B"></button></form></section>'
        original, candidate, mapping, evidence = self.match(before, after)
        old_buttons = [n for n in original.graph if original.element_to_id.element(n).name == "button"]
        new_buttons = [n for n in candidate.graph if candidate.element_to_id.element(n).name == "button"]
        self.assertEqual(mapping[old_buttons[0]], new_buttons[0])
        self.assertEqual(mapping[old_buttons[1]], new_buttons[1])
        self.assertEqual(evidence["methods"]["same_gap_identical_siblings"], 2)
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.status, "measured")
        self.assertEqual(result.preservation_rate, 100)

    def test_repeated_controls_with_insertion_or_removal_do_not_match(self):
        before = '<form id="f">' + '<button></button>' * 2 + '</form>'
        for count in (1, 3):
            with self.subTest(count=count):
                after = '<form id="f">' + '<button aria-label="Go"></button>' * count + '</form>'
                original, _, mapping, _ = self.match(before, after)
                buttons = [n for n in original.graph if original.element_to_id.element(n).name == "button"]
                self.assertTrue(all(n not in mapping for n in buttons))
                result = semantic.calculate_semantic_preservation(before, after)
                self.assertEqual(result.status, "measured")
                self.assertEqual(result.unmatched_endpoint_count, result.dependencies_before)
                self.assertEqual(result.preservation_rate, 0)

    def test_ordinary_attributes_non_heading_tags_and_direct_text_still_matter(self):
        before = '<form id="f"><button class="go"><span>Go</span></button></form>'
        labeled = before.replace('<button ', '<button aria-label="Submit" ')
        for after in (labeled.replace('class="go"', 'class="other"'),
                      labeled.replace('button', 'a'),
                      labeled.replace('<span>Go</span>', 'Go')):
            with self.subTest(after=after):
                original, _, mapping, _ = self.match(before, after)
                button = next(n for n in original.graph if original.element_to_id.element(n).name == "button")
                self.assertNotIn(button, mapping)
                result = semantic.calculate_semantic_preservation(before, after)
                self.assertEqual(result.status, "measured")
                self.assertEqual(result.unmatched_endpoint_count, 1)
                self.assertEqual(result.preservation_rate, 0)

    def test_reordered_distinct_controls_match_but_lose_focus_edge(self):
        before = '<form id="f"><button class="go">Go</button><button class="close">Close</button></form>'
        after = '<form id="f"><button class="close" aria-label="Close">Close</button><button class="go" aria-label="Go">Go</button></form>'
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.status, "measured")
        self.assertEqual(result.dependencies_before, 3)
        self.assertEqual(result.dependencies_valid, 2)
        self.assertEqual(result.broken_examples[0]["relation"], "focus_order")

    def test_inserted_distinct_control_is_not_an_extra_preserved_edge(self):
        before = '<form id="f"><button class="go">Go</button></form>'
        after = before.replace('<button ', '<button aria-label="Go" ').replace('</form>', '<button>New</button></form>')
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.dependencies_before, 1)
        self.assertEqual(result.dependencies_valid, 1)

    def test_changed_reference_is_compared_after_label_fallback(self):
        before = '<div id="p"><button aria-controls="a"></button><div id="a"></div><div id="b"></div></div>'
        after = before.replace('aria-controls="a"', 'aria-controls="b" aria-label="Open"')
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.status, "measured")
        self.assertEqual(result.dependencies_before, 1)
        self.assertEqual(result.dependencies_valid, 0)
        self.assertEqual(result.not_preserved_observed, 1)
        self.assertEqual(result.unmatched_endpoint_count, 0)

    def test_bottom_up_parent_matching_survives_html_lang_and_main_wrapper(self):
        before = '<html><body><div class="box"><a href="/a">A</a><a href="/b"><span></span></a></div></body></html>'
        after = '<html lang="en"><body><main><div class="box"><a href="/a">A</a><a href="/b"><span>Next</span></a></div></main></body></html>'
        result = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(result.status, "measured")
        self.assertEqual(result.preservation_rate, 100)
        self.assertIn("parent_of_matched_children", result.matching["methods"])

    def test_bottom_up_rejects_parent_whose_matched_children_split(self):
        before = '<section><div class="g"><a id="a" href="/a">A</a><a id="b" href="/b">B</a></div></section>'
        after = '<main><div class="g"><a id="a" href="/a">A</a></div><div class="g"><a id="b" href="/b">B</a></div></main>'
        original, _, mapping, _ = self.match(before, after)
        old_div = next(n for n in original.graph if original.element_to_id.element(n).name == "div")
        self.assertNotIn(old_div, mapping)

    def test_label_relaxed_own_and_global_unique_subtree_match(self):
        before = '<ol><div><ul><fi><a href="https://example.org/fb"><img src="fb.png"></a></fi></ul></div></ol>'
        after = '<ol><li><ul><li><a aria-label="FB" href="https://example.org/fb"><img alt="FB" src="fb.png"></a></li></ul></li></ol>'
        original, _, mapping, evidence = self.match(before, after)
        link = next(n for n in original.graph if original.element_to_id.element(n).name == "a")
        self.assertIn(link, mapping)
        self.assertEqual(evidence["methods"]["unique_label_relaxed_subtree"], 2)  # Both <a> and <img>.

        # Label added while inner decorative child removed still matches unique own node in matched parent.
        before_nav = '<li id="item"><a href="/x"><span>Go</span><i></i></a></li>'
        after_nav = '<li id="item"><a aria-label="Go" href="/x"></a></li>'
        original2, _, mapping2, evidence2 = self.match(before_nav, after_nav)
        link2 = next(n for n in original2.graph if original2.element_to_id.element(n).name == "a")
        self.assertIn(link2, mapping2)
        self.assertEqual(evidence2["methods"]["label_own_in_matched_parent"], 1)

    def test_heading_retagging_matches_and_still_detects_broken_hierarchy(self):
        preserved = '<h1>Title</h1><header><h3>Section</h3></header>'
        repaired_ok = '<h1>Title</h1><header><h2>Section</h2></header>'
        res_ok = semantic.calculate_semantic_preservation(preserved, repaired_ok)
        self.assertEqual(res_ok.preservation_rate, 100)

        # Flattening h1 + h3 to h2 + h2 matches both headings and detects the lost hierarchy edge.
        before_flat = '<h1>Root</h1><div><h1>Group</h1><h3>Item</h3></div>'
        after_flat = '<h1>Root</h1><div><h2>Group</h2><h2>Item</h2></div>'
        res_flat = semantic.calculate_semantic_preservation(before_flat, after_flat)
        self.assertEqual(res_flat.dependencies_before, 1)
        self.assertEqual(res_flat.dependencies_valid, 0)
        self.assertEqual(res_flat.not_preserved_observed, 1)
        self.assertEqual(res_flat.unmatched_endpoint_count, 0)

        # Non-heading tag replacement must not match through heading fallback.
        original, _, mapping, _ = self.match('<header id="h"><h3>Section</h3></header>', '<header id="h"><p>Section</p></header>')
        h3 = next(n for n in original.graph if original.element_to_id.element(n).name == "h3")
        self.assertNotIn(h3, mapping)

    def test_repair_attributes_and_deferred_empty_attributes(self):
        # Removing role="navigation" matches the element and detects the broken landmark edge.
        before = '<header id="h"><div class="nav" role="navigation">Links</div></header>'
        after = '<header id="h"><div class="nav">Links</div></header>'
        res = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(res.dependencies_before, 1)
        self.assertEqual(res.dependencies_valid, 0)
        self.assertEqual(res.not_preserved_observed, 1)
        self.assertEqual(res.unmatched_endpoint_count, 0)

        # Preserving class="" before dropping empty attrs keeps distinct empty links separated.
        before_links = '<div id="d"><a href="/p" target=""> </a><a class="" href="/p" target=""></a></div>'
        after_links = '<div id="d"><a href="/p"> </a><a class="" href="/p"></a></div>'
        res_links = semantic.calculate_semantic_preservation(before_links, after_links)
        self.assertEqual(res_links.preservation_rate, 100)

    def test_empty_heading_and_label_fill_require_empty_original_and_exact_tag(self):
        before = '<div id="d"><h2></h2><h3>Events</h3></div>'
        after_fill = '<div id="d"><h2>Key Features</h2><h3>Events</h3></div>'
        res_fill = semantic.calculate_semantic_preservation(before, after_fill)
        self.assertEqual(res_fill.preservation_rate, 100)
        self.assertEqual(res_fill.matching["methods"]["empty_heading_or_label_fill"], 1)

        # Merging empty h2 + h3 Events into one h2 Events matches h3 and leaves empty h2 unmatched (lost).
        after_merged = '<div id="d"><h2>Events</h2></div>'
        res_merged = semantic.calculate_semantic_preservation(before, after_merged)
        self.assertEqual(res_merged.dependencies_valid, 0)
        self.assertEqual(res_merged.unmatched_endpoint_count, 1)

        # Non-empty heading text change must not match through empty-fill fallback.
        original, _, mapping, _ = self.match('<div id="d"><h6>Old</h6></div>', '<div id="d"><h6>New</h6></div>')
        h6 = next(n for n in original.graph if original.element_to_id.element(n).name == "h6")
        self.assertNotIn(h6, mapping)

        # Empty wrapping label filled with text and explicit for preserves label_input.
        before_lbl = '<form id="f"><label class="s"><input id="q"></label></form>'
        after_lbl = '<form id="f"><label class="s" for="q">Search</label><input id="q"></form>'
        res_lbl = semantic.calculate_semantic_preservation(before_lbl, after_lbl)
        self.assertEqual(res_lbl.preservation_rate, 100)

    def test_anchored_sibling_gap_matches_separated_clones(self):
        before = '<div id="s"><div class="item"><h6>Clone</h6></div><div class="item"><h6>Mid</h6></div><div class="item"><h6>Clone</h6></div></div>'
        after = '<div id="s"><div class="item"><h3>Clone</h3></div><div class="item"><h6>Mid</h6></div><div class="item"><h6>Clone</h6></div></div>'
        original, candidate, mapping, evidence = self.match(before, after)
        orig_items = [n for n in original.graph if original.element_to_id.element(n).get("class") == ["item"]]
        cand_items = [n for n in candidate.graph if candidate.element_to_id.element(n).get("class") == ["item"]]
        self.assertEqual([mapping[n] for n in orig_items], cand_items)
        self.assertEqual(evidence["methods"]["anchored_sibling_gap"], 2)

    def test_corrupted_table_cell_counts_as_lost_not_forced_match(self):
        before = '<table><tbody><tr><td>Alice</td><td>Smith</td><td>CityA</td></tr></tbody></table>'
        after = '<table><tbody><tr><td>Alice</td><td>Smith</td><td>WrongCity</td></tr></tbody></table>'
        res = semantic.calculate_semantic_preservation(before, after)
        self.assertEqual(res.status, "measured")
        self.assertEqual(res.dependencies_before, 5)  # table->tbody, tbody->tr, 3 tr->td
        self.assertEqual(res.dependencies_valid, 4)
        self.assertEqual(res.broken_count, 1)
        self.assertEqual(res.not_preserved_observed, 0)
        self.assertEqual(res.unmatched_endpoint_count, 1)
        self.assertEqual(res.unresolved_count, 0)

    def test_fallback_preserves_graphs_and_produces_repeatable_evidence(self):
        before = '<form id="f"><button><img src="icon.png"></button></form>'
        after = before.replace('<button>', '<button aria-label="Go">').replace('<img ', '<img alt="Go" ')
        original, candidate = SDGBuilder(before), SDGBuilder(after)
        snapshots = original.to_dict(), candidate.to_dict()
        first = semantic_matching.match_elements(original, candidate)
        self.assertEqual(first, semantic_matching.match_elements(original, candidate))
        self.assertEqual((original.to_dict(), candidate.to_dict()), snapshots)
        self.assertEqual(first[1]["policy"], "unique_ids_then_normalized_subtrees_then_matched_parent_v3")
        self.assertEqual(first[1]["fallback_ignored_attributes"], ["alt", "aria-label", "lang", "role", "title", "type"])
        self.assertEqual(first[1]["methods"]["label_attributes_in_matched_parent"], 2)


if __name__ == "__main__":
    unittest.main()
