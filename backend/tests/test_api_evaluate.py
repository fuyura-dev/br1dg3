import unittest

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


class TestApiEvaluate(unittest.TestCase):
    def test_evaluate_endpoint_success(self):
        orig_html = "<!DOCTYPE html><html><head><title>Store</title></head><body><h1>Store</h1><div id='content'><p>Item 1</p><p>Item 2</p></div></body></html>"
        rep_html = "<!DOCTYPE html><html><head><title>Store</title></head><body><h1>Store</h1><main id='content'><p>Item 1</p><p>Item 2</p></main></body></html>"

        payload = {
            "html_original": orig_html,
            "html_repaired": rep_html,
            "violations_before": [{"id": "landmark-one-main", "nodes": [{"html": "<html>"}]}],
            "violations_after": [],
            "efficiency_data": {
                "api_calls": 1,
                "prompt_tokens": 500,
                "completion_tokens": 100,
                "thought_tokens": 200,
                "cascaded_count": 0,
                "patched_count": 1,
                "total_elements": 1,
            },
            "run_detection_if_missing": False,
        }

        response = client.post("/api/evaluate", json=payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("effectiveness", data)
        self.assertIn("safety", data)
        self.assertIn("structure", data)
        self.assertIn("efficiency", data)
        self.assertIn("semantic", data)

        # Check effectiveness
        eff = data["effectiveness"]
        self.assertEqual(eff["violations_before"], 1)
        self.assertEqual(eff["violations_after"], 0)
        self.assertEqual(eff["violations_reduced"], 1)
        self.assertTrue(eff["compliance_improved"])
        self.assertTrue(eff["fully_fixed"])

        # Check safety
        safety = data["safety"]
        self.assertTrue(safety["is_valid"])
        self.assertEqual(safety["score"], 1)

        # Check structure
        struct = data["structure"]
        self.assertGreater(struct["structure_similarity"], 0.85)
        self.assertTrue(struct["structure_preserved"])

        # Check efficiency
        eff_res = data["efficiency"]
        self.assertEqual(eff_res["api_calls"], 1)
        self.assertEqual(eff_res["total_tokens"], 800)

        # Check semantic
        sem = data["semantic"]
        self.assertIn("preservation_rate", sem)


if __name__ == "__main__":
    unittest.main()
