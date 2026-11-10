import unittest

from app.services.validation.structure import (
    calculate_legacy_pruned_structural_preservation,
    calculate_structural_preservation,
)


class TestStructuralPreservation(unittest.TestCase):
    def test_identical_html(self):
        html = '<!DOCTYPE html><html><head><title>Test</title></head><body><h1>Title</h1><p>Text</p></body></html>'
        result = calculate_structural_preservation(html, html)
        self.assertEqual(result.tree_edit_distance, 0)
        self.assertEqual(result.structure_similarity, 1.0)
        self.assertTrue(result.structure_preserved)
        self.assertFalse(result.unparseable)

    def test_minor_accessibility_edit_preserved(self):
        # 1 tag renamed: div -> main in a 10-node tree
        orig = '<html><body><div><nav><a>1</a><a>2</a></nav><div id="content"><p>Para 1</p><p>Para 2</p></div></div></body></html>'
        rep = '<html><body><div><nav><a>1</a><a>2</a></nav><main id="content"><p>Para 1</p><p>Para 2</p></main></div></body></html>'
        result = calculate_structural_preservation(orig, rep)
        self.assertEqual(result.tree_edit_distance, 1)
        self.assertGreater(result.structure_similarity, 0.85)
        self.assertTrue(result.structure_preserved)

    def test_wrapping_element_inserted(self):
        # Inserting <main> wrapping children
        orig = '<html><body><header>Head</header><div>P1</div><div>P2</div><footer>Foot</footer></body></html>'
        rep = '<html><body><header>Head</header><main><div>P1</div><div>P2</div></main><footer>Foot</footer></body></html>'
        result = calculate_structural_preservation(orig, rep)
        self.assertEqual(result.tree_edit_distance, 1)
        self.assertGreaterEqual(result.structure_similarity, 0.85)
        self.assertTrue(result.structure_preserved)

    def test_repeated_subtree_deletion_counts_all_deleted_nodes(self):
        subtree = '<div><p><span>Keep</span></p></div>'
        orig = '<html><body>' + subtree * 4 + '</body></html>'
        rep = '<html><body>' + subtree * 3 + '</body></html>'

        result = calculate_structural_preservation(orig, rep)
        self.assertEqual(result.original_nodes, 14)
        self.assertEqual(result.repaired_nodes, 11)
        self.assertEqual(result.max_nodes, 14)
        self.assertEqual(result.tree_edit_distance, 3)
        self.assertEqual(result.structure_similarity, 0.7857)
        self.assertFalse(result.structure_preserved)

        legacy = calculate_legacy_pruned_structural_preservation(orig, rep)
        self.assertEqual(legacy.max_nodes, 14)
        self.assertEqual(legacy.tree_edit_distance, 1)
        self.assertEqual(legacy.structure_similarity, 0.9286)
        self.assertTrue(legacy.structure_preserved)

    def test_repeated_subtree_insertion_counts_all_inserted_nodes(self):
        subtree = '<div><p><span>Keep</span></p></div>'
        orig = '<html><body>' + subtree * 3 + '</body></html>'
        rep = '<html><body>' + subtree * 4 + '</body></html>'

        result = calculate_structural_preservation(orig, rep)
        self.assertEqual(result.tree_edit_distance, 3)
        self.assertEqual(result.structure_similarity, 0.7857)
        self.assertFalse(result.structure_preserved)

        legacy = calculate_legacy_pruned_structural_preservation(orig, rep)
        self.assertEqual(legacy.tree_edit_distance, 1)
        self.assertTrue(legacy.structure_preserved)

    def test_text_and_attribute_changes_do_not_change_element_tree(self):
        orig = '<html><body><button>Old</button></body></html>'
        rep = '<html><body><button aria-label="New label">New</button></body></html>'

        for calculate in (
            calculate_structural_preservation,
            calculate_legacy_pruned_structural_preservation,
        ):
            with self.subTest(method=calculate.__name__):
                result = calculate(orig, rep)
                self.assertEqual(result.tree_edit_distance, 0)
                self.assertEqual(result.structure_similarity, 1.0)
                self.assertTrue(result.structure_preserved)

    def test_drastic_structural_destruction_not_preserved(self):
        # Large original page wiped out by LLM hallucination down to a single tag
        orig = '<html><body>' + ''.join(f'<div id="block{i}"><p>Item {i}</p><span>Details</span></div>' for i in range(20)) + '</body></html>'
        rep = '<html><body><div>Hallucinated content</div></body></html>'
        result = calculate_structural_preservation(orig, rep)
        self.assertLess(result.structure_similarity, 0.50)
        self.assertFalse(result.structure_preserved)

    def test_unparseable_repaired_html_fallback(self):
        # Per manuscript: "If the repaired HTML cannot be parsed into a DOM tree, its structure
        # similarity score will be recorded as 0, and it will be counted as not structurally preserved."
        orig = '<html><body><h1>Valid Page</h1></body></html>'
        rep = '   \n  '
        result = calculate_structural_preservation(orig, rep)
        self.assertEqual(result.structure_similarity, 0.0)
        self.assertFalse(result.structure_preserved)
        self.assertTrue(result.unparseable)

    def test_none_input(self):
        result = calculate_structural_preservation(None, None)
        self.assertEqual(result.structure_similarity, 0.0)
        self.assertFalse(result.structure_preserved)
        self.assertTrue(result.unparseable)


if __name__ == "__main__":
    unittest.main()
