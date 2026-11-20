import unittest
from unittest.mock import patch

from app.services.validation.evaluator import evaluate_repair
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
        self.assertEqual(result.to_dict()["error_count"], 0)
        self.assertEqual(result.parse_mode, "document")

    def test_valid_fragment(self):
        html = '<div role="region" aria-label="Main"><p>Content</p></div>'
        result = calculate_safety(html)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.score, 1)
        self.assertEqual(result.reason, "valid")
        self.assertEqual(result.element_count, 2)
        self.assertEqual(result.parse_mode, "fragment")
        self.assertEqual(result.to_dict()["fragment_context"], "div")

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
        self.assertEqual(result.reason, "parse_errors")
        self.assertIn("eof-in-attribute-value-double-quote", [e["code"] for e in result.parse_errors])

    def test_markdown_fence_warning(self):
        fence = '```html\n<div><button>Submit</button></div>\n```'
        result = calculate_safety(fence)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.score, 1)
        self.assertIn("contains_markdown_fences", result.warnings)

    def test_recovered_malformed_markup_is_invalid(self):
        for html, code in [
            ("<div>Hello</div></span>", "unexpected-end-tag"),
            ('<div id="a" id="b">Hello</div>', "duplicate-attribute"),
            ("<div><span>Hello</div>", "end-tag-too-early"),
        ]:
            with self.subTest(html=html):
                result = calculate_safety(html)
                self.assertFalse(result.is_valid)
                self.assertEqual(result.score, 0)
                self.assertIn(code, [error["code"] for error in result.parse_errors])
                self.assertGreater(result.element_count, 0)

    def test_error_positions_refer_to_supplied_html_without_stripping(self):
        result = calculate_safety("\n<div>Hello</div>\n</span>\n</aside>")
        errors = result.to_dict()["errors"]
        self.assertEqual(result.to_dict()["error_count"], 2)
        self.assertEqual([error["line"] for error in errors], [3, 4])
        self.assertEqual(errors[0]["column"], 7)
        self.assertIn("span", errors[0]["message"])

    def test_legal_optional_end_tags_and_void_elements(self):
        result = calculate_safety("<ul><li>One<li>Two</ul><img src='photo.png'><br>")
        self.assertTrue(result.is_valid)
        self.assertEqual(result.parse_errors, [])

    def test_escaped_text_and_raw_script_content(self):
        for html in [
            "<p>1 &lt; 2</p>",
            '<script>const text = "<html>"; if (x < 2) y();</script>',
            '<div data-example="<html>">Text</div>',
            '<!-- <html> --><div>Text</div>',
            '<textarea><html></textarea>',
            '<title><html></title>',
        ]:
            with self.subTest(html=html):
                result = calculate_safety(html)
                self.assertTrue(result.is_valid)
                self.assertEqual(result.parse_mode, "fragment")

    def test_comments_and_doctype_alone_are_not_usable_output(self):
        for html in ["<!-- comment -->", "<!DOCTYPE html>"]:
            with self.subTest(html=html):
                result = calculate_safety(html)
                self.assertFalse(result.is_valid)
                self.assertEqual(result.reason, "no_elements")

    def test_missing_doctype_is_a_document_parse_error(self):
        result = calculate_safety("<html><body><p>Text</p></body></html>")
        self.assertFalse(result.is_valid)
        self.assertEqual(result.parse_mode, "document")
        self.assertIn("expected-doctype-but-got-start-tag", [e["code"] for e in result.parse_errors])

    def test_original_document_prevents_downgrading_to_fragment_checks(self):
        result = calculate_safety(
            "<p>Text</p>", html_original="<!DOCTYPE html><html><body><p>Text</p></body></html>",
        )
        self.assertFalse(result.is_valid)
        self.assertEqual(result.parse_mode, "document")

    def test_document_output_from_fragment_input_uses_document_checks(self):
        result = calculate_safety(
            "<html><body><p>Text</p></body></html>", html_original="<p>Text</p>",
        )
        self.assertFalse(result.is_valid)
        self.assertEqual(result.parse_mode, "document")

    def test_table_fragments_use_declared_div_context(self):
        result = calculate_safety("<tr><td>Text</td></tr>")
        self.assertFalse(result.is_valid)
        self.assertEqual(result.to_dict()["fragment_context"], "div")
        self.assertTrue(calculate_safety("<table><tr><td>Text</td></tr></table>").is_valid)

    def test_content_models_and_accessibility_are_outside_the_check(self):
        # Neither a disallowed child of ul nor missing alt is an HTML parsing error.
        result = calculate_safety("<ul><div>Text</div></ul><img src='photo.png'>")
        self.assertTrue(result.is_valid)
        self.assertEqual(result.parse_errors, [])

    def test_validator_failure_is_unavailable_instead_of_invalid(self):
        with patch("app.services.validation.safety.html5lib.HTMLParser", side_effect=RuntimeError("Unavailable")):
            result = calculate_safety("<p>Text</p>")
        self.assertIsNone(result.is_valid)
        self.assertIsNone(result.score)
        self.assertEqual(result.reason, "validator_error")
        self.assertIsNone(result.to_dict()["error_count"])
        self.assertIsNone(result.to_dict()["errors"])


class TestSafetyIntegration(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("app.services.validation.evaluator.streamer.log"))

    def test_parse_failure_does_not_change_other_metrics_or_output(self):
        original = '<label for="name">Name</label><input id="name">'
        repaired = original + "</span>"
        report = evaluate_repair(original, repaired, [], [], run_detection_if_missing=False)
        self.assertEqual(report.safety.score, 0)
        self.assertEqual(report.safety.reason, "parse_errors")
        self.assertEqual(report.structure.structure_similarity, 1)
        self.assertEqual(report.semantic.preservation_rate, 100)
        self.assertEqual(report.effectiveness.violations_after, 0)
        self.assertFalse(report.effectiveness.scan_failed)
        self.assertIsNone(report.efficiency.api_calls)

    def test_evaluator_passes_original_document_context(self):
        report = evaluate_repair(
            "<!DOCTYPE html><html><body><p>Text</p></body></html>", "<p>Text</p>",
            [], [], run_detection_if_missing=False,
        )
        self.assertEqual(report.safety.parse_mode, "document")
        self.assertEqual(report.safety.score, 0)

    def test_fallback_is_policy_zero_without_a_parser_result(self):
        with patch("app.services.validation.safety.html5lib.HTMLParser") as parser:
            report = evaluate_repair(
                "<p>Text</p>", "<p>Text</p>", [], [],
                run_detection_if_missing=False, fallback_used=True,
            )
        parser.assert_not_called()
        self.assertEqual(report.safety.score, 0)
        self.assertEqual(report.safety.reason, "no_candidate")
        self.assertIsNone(report.safety.to_dict()["error_count"])

    def test_validator_failure_keeps_other_results_available(self):
        with patch("app.services.validation.safety.html5lib.HTMLParser", side_effect=RuntimeError("Unavailable")):
            report = evaluate_repair("<p>Text</p>", "<p>Text</p>", [], [], run_detection_if_missing=False)
        self.assertIsNone(report.safety.score)
        self.assertEqual(report.safety.reason, "validator_error")
        self.assertEqual(report.structure.structure_similarity, 1)
        self.assertEqual(report.effectiveness.violations_after, 0)


if __name__ == "__main__":
    unittest.main()
