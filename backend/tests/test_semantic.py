import unittest

from app.services.validation.semantic import calculate_semantic_preservation


class TestSemanticDependencyPreservation(unittest.TestCase):
    def setUp(self):
        self.sample_html = """
        <header>
            <nav aria-label="Main menu">
                <ul>
                    <li><a href="#content">Skip to content</a></li>
                </ul>
            </nav>
        </header>
        <div id="content">
            <h1>Store</h1>
            <h2>Search</h2>
            <form id="signup">
                <label for="email" id="email-label">Email</label>
                <input type="email" id="email" aria-labelledby="email-label" aria-describedby="email-hint">
                <span id="email-hint">We never share it</span>
                <input type="radio" name="plan" value="basic">
                <input type="radio" name="plan" value="pro">
                <button type="submit">Send</button>
            </form>
        </div>
        """

    def test_identical_html_100_percent_preserved(self):
        result = calculate_semantic_preservation(self.sample_html, self.sample_html)
        self.assertGreater(result.dependencies_before, 0)
        self.assertEqual(result.dependencies_valid, result.dependencies_before)
        self.assertEqual(result.preservation_rate, 100.0)
        self.assertEqual(result.broken_count, 0)
        self.assertTrue(result.has_dependencies)
        self.assertEqual(len(result.broken_examples), 0)

    def test_accessibility_repair_preserves_relationships(self):
        # Changing div#content to main#content preserves all child relationships
        repaired = self.sample_html.replace('<div id="content">', '<main id="content">')
        result = calculate_semantic_preservation(self.sample_html, repaired)
        self.assertEqual(result.preservation_rate, 100.0)
        self.assertEqual(result.broken_count, 0)

    def test_breaking_edit_detected(self):
        # Delete the form and its inputs
        bad_repair = self.sample_html.replace(
            '<form id="signup">', '<!-- form removed -->'
        ).replace('</form>', '')
        result = calculate_semantic_preservation(self.sample_html, bad_repair)
        self.assertLess(result.preservation_rate, 100.0)
        self.assertGreater(result.broken_count, 0)
        self.assertGreater(len(result.broken_examples), 0)
        broken_relations = [b["relation"] for b in result.broken_examples]
        self.assertIn("form_group", broken_relations)

    def test_empty_or_no_dependencies(self):
        plain = "<div>Just some plain text without forms, headings, or aria</div>"
        result = calculate_semantic_preservation(plain, plain)
        self.assertEqual(result.dependencies_before, 0)
        self.assertFalse(result.has_dependencies)

    def test_unparseable_or_empty_repaired_html(self):
        result = calculate_semantic_preservation(self.sample_html, "")
        self.assertGreater(result.dependencies_before, 0)
        self.assertEqual(result.dependencies_valid, 0)
        self.assertEqual(result.preservation_rate, 0.0)
        self.assertEqual(result.broken_count, result.dependencies_before)


if __name__ == "__main__":
    unittest.main()

