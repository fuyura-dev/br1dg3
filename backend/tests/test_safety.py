import unittest

from app.services.validation.safety import calculate_safety


class TestRepairSafety(unittest.TestCase):
    def test_valid_full_html_document(self):
        html = '<!DOCTYPE html><html lang="en"><head><title>Test</title></head><body><h1>Hello</h1></body></html>'
        result = calculate_safety(html)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.score, 1)
        self.assertEqual(result.reason, "valid")
        self.assertGreater(result.element_count, 0)
        self.assertEqual(len(result.warnings), 0)

    def test_valid_fragment(self):
        html = '<div role="region" aria-label="Main"><p>Content</p></div>'
        result = calculate_safety(html)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.score, 1)
        self.assertEqual(result.reason, "valid")
        self.assertEqual(result.element_count, 2)

    def test_empty_and_whitespace(self):
        for empty in ["", "   ", "\n\t  \n", None]:
            result = calculate_safety(empty)
            self.assertFalse(result.is_valid)
            self.assertEqual(result.score, 0)
            self.assertEqual(result.reason, "empty_html")

    def test_conversational_text_without_elements(self):
        text = "Sorry, I am an AI model and I cannot generate accessibility repairs for this document."
        result = calculate_safety(text)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.reason, "no_elements")

    def test_truncated_tag(self):
        truncated = '<html><body><div><p>Hello</p><div id="incomplete'
        result = calculate_safety(truncated)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.reason, "truncated_tag")

    def test_markdown_fence_warning(self):
        fence = '```html\n<div><button>Submit</button></div>\n```'
        result = calculate_safety(fence)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.score, 1)
        self.assertIn("contains_markdown_fences", result.warnings)


if __name__ == "__main__":
    unittest.main()
