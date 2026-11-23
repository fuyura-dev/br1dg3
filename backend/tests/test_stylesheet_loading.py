"""Local browser regression checks; enable with BR1DG3_BROWSER_TESTS=1."""

import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.services.detection import detect as detection


class StylesheetHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/blank.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><html><head></head><body></body></html>")
            return
        if self.path == "/missing.css":
            self.send_error(404)
            return
        if self.path == "/slow.css":
            time.sleep(1)
        css = b'@import url("/slow.css");' if self.path == "/import.css" else b".target {display: none}"
        self.send_response(200)
        self.send_header("Content-Type", "text/css")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(css)
        except BrokenPipeError:
            pass  # The timeout test closes its browser before the response arrives.

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get("BR1DG3_BROWSER_TESTS") == "1", "Requires opt-in local Chrome")
class TestStylesheetLoading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StylesheetHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        get_driver = detection._get_driver
        self.local_origin = True

        def local_driver():
            driver = get_driver()
            navigate = driver.get
            # Keep HTTP fixtures on a local origin; do not relax Chrome's network security.
            driver.get = lambda url: navigate(
                self.url + "/blank.html" if self.local_origin and url == "data:text/html," else url
            )
            return driver

        self.enterContext(patch.object(detection, "_get_driver", side_effect=local_driver))

    def scan(self, links=""):
        return detection.scan_with_report(
            f'<!doctype html><html lang="en"><head><title>Stylesheet test</title>{links}</head>'
            '<body><main><h1>Test</h1><button class="target"></button></main></body></html>'
        )

    def test_no_stylesheet_keeps_visible_button_violation(self):
        result = self.scan()
        self.assertIn("button-name", [v["id"] for v in result.violations])
        self.assertEqual(result.report["stylesheet_warnings"], [])

    def test_delayed_stylesheet_applies_before_axe(self):
        result = self.scan(f'<link rel="stylesheet" href="{self.url}/slow.css">')
        self.assertEqual(result.violations, [])

    def test_imported_stylesheet_also_finishes_before_axe(self):
        result = self.scan(f'<link rel="stylesheet" href="{self.url}/import.css">')
        self.assertEqual(result.violations, [])

    def test_fast_stylesheet_with_mixed_case_rel_is_observed(self):
        result = self.scan('<link rel="StyleSheet" href="data:text/css,.target%7Bdisplay:none%7D">')
        self.assertEqual(result.violations, [])

    def test_failed_stylesheet_is_a_warning_and_axe_still_runs(self):
        result = self.scan(f'<link rel="stylesheet" href="{self.url}/missing.css">')
        self.assertIn("button-name", [v["id"] for v in result.violations])
        self.assertEqual(result.report["stylesheet_warnings"], [
            {"status": "load_error", "href": f"{self.url}/missing.css"}
        ])

    def test_timed_out_stylesheet_cannot_apply_late_during_axe(self):
        # Let the CSS response arrive before Axe evaluates the button.
        delayed_axe = detection.AXE_SCRIPT + """
            const run = axe.run.bind(axe);
            axe.run = (...args) => setTimeout(() => run(...args), 1200);
        """
        with patch.object(detection, "STYLESHEET_TIMEOUT_MS", 100), patch.object(
            detection, "AXE_SCRIPT", delayed_axe
        ):
            result = self.scan(f'<link rel="stylesheet" href="{self.url}/slow.css">')
        self.assertIn("button-name", [v["id"] for v in result.violations])
        self.assertEqual(result.report["stylesheet_warnings"], [
            {"status": "timeout", "href": f"{self.url}/slow.css"}
        ])

    def test_relative_stylesheet_without_base_is_a_warning(self):
        self.local_origin = False
        result = self.scan('<link rel="stylesheet" href="/theme.css">')
        self.assertIn("button-name", [v["id"] for v in result.violations])
        self.assertEqual(result.report["stylesheet_warnings"], [
            {"status": "unresolved_url", "href": "/theme.css"}
        ])

    def test_inactive_stylesheets_do_not_block_screen_scan(self):
        links = (
            f'<link rel="stylesheet" href="{self.url}/missing.css" media="print">'
            f'<link rel="stylesheet" href="{self.url}/missing.css" disabled>'
            f'<link rel="alternate stylesheet" href="{self.url}/missing.css" title="Alternate">'
        )
        self.assertIn("button-name", [v["id"] for v in self.scan(links).violations])


if __name__ == "__main__":
    unittest.main()
