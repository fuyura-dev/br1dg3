import unittest
from unittest.mock import Mock, patch

from app.services.detection import detect as detection
from selenium.common.exceptions import TimeoutException


class TestDetectionResults(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.enterContext(patch.object(detection, "_get_driver", return_value=self.driver))
        self.html = '<html><body><img src="test.png"></body></html>'

    def test_successful_empty_scan_returns_no_violations(self):
        self.driver.execute_async_script.return_value = {"violations": []}

        self.assertEqual(detection.detect(self.html), [])
        self.driver.quit.assert_called_once()

    def test_successful_scan_keeps_selected_rules(self):
        selected = {"id": "image-alt", "nodes": [{"target": ["img"]}]}
        unselected = {"id": "color-contrast", "nodes": [{"target": ["p"]}]}
        self.driver.execute_async_script.return_value = {
            "violations": [unselected, selected],
        }

        self.assertEqual(detection.detect(self.html), [selected])
        self.driver.quit.assert_called_once()

    def test_successful_scan_with_only_unselected_rules_is_empty(self):
        self.driver.execute_async_script.return_value = {
            "violations": [{"id": "color-contrast", "nodes": [{"target": ["p"]}]}],
        }

        self.assertEqual(detection.detect(self.html), [])

    def test_error_payload_is_not_a_clean_scan(self):
        self.driver.execute_async_script.return_value = {
            "error": "Axe crashed",
            "violations": [],
        }

        with self.assertRaisesRegex(detection.DetectionError, "Axe crashed"):
            detection.detect(self.html)
        self.driver.quit.assert_called_once()

    def test_missing_or_malformed_results_fail_and_close_driver(self):
        malformed_results = [
            None,
            [],
            "not a result",
            {},
            {"violations": None},
            {"violations": {}},
            {"violations": ""},
            {"violations": [None]},
            {"violations": [{}]},
            {"violations": [{"id": None, "nodes": [{}]}]},
            {"violations": [{"id": " ", "nodes": [{}]}]},
            {"violations": [{"id": "image-alt"}]},
            {"violations": [{"id": "image-alt", "nodes": None}]},
            {"violations": [{"id": "image-alt", "nodes": []}]},
            {"violations": [{"id": "image-alt", "nodes": "img"}]},
            {"violations": [{"id": "image-alt", "nodes": [None]}]},
        ]
        for result in malformed_results:
            with self.subTest(result=result):
                self.driver.reset_mock()
                self.driver.execute_async_script.return_value = result
                with self.assertRaises(detection.DetectionError):
                    detection.detect(self.html)
                self.driver.quit.assert_called_once()

    def test_browser_timeout_propagates_and_closes_driver(self):
        self.driver.execute_async_script.side_effect = TimeoutException("Scan timed out")

        with self.assertRaises(TimeoutException):
            detection.detect(self.html)
        self.driver.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
