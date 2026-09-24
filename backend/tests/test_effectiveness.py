import unittest

from app.services.validation.effectiveness import (
    calculate_effectiveness,
    count_unique_rules,
    count_violations,
)


class TestRepairEffectiveness(unittest.TestCase):
    def test_normal_improvement(self):
        result = calculate_effectiveness(violations_before=10, violations_after=2)
        self.assertEqual(result.violations_before, 10)
        self.assertEqual(result.violations_after, 2)
        self.assertEqual(result.violations_reduced, 8)
        self.assertTrue(result.compliance_improved)
        self.assertFalse(result.fully_fixed)
        self.assertEqual(result.reduction_rate, 80.0)
        self.assertFalse(result.scan_failed)

    def test_fully_fixed(self):
        result = calculate_effectiveness(violations_before=5, violations_after=0)
        self.assertEqual(result.violations_reduced, 5)
        self.assertTrue(result.compliance_improved)
        self.assertTrue(result.fully_fixed)
        self.assertEqual(result.reduction_rate, 100.0)

    def test_regression_handled_safely(self):
        result = calculate_effectiveness(violations_before=4, violations_after=6)
        self.assertEqual(result.violations_reduced, -2)
        self.assertFalse(result.compliance_improved)
        self.assertFalse(result.fully_fixed)
        self.assertEqual(result.reduction_rate, -50.0)

    def test_scan_failed_fallback_per_manuscript(self):
        # Per manuscript: "If the repaired HTML output cannot be parsed or scanned after repair...
        # post-repair violation count will be recorded as equal to pre-repair violation count"
        result = calculate_effectiveness(violations_before=10, violations_after=None, scan_failed=True)
        self.assertEqual(result.violations_before, 10)
        self.assertEqual(result.violations_after, 10)
        self.assertEqual(result.violations_reduced, 0)
        self.assertFalse(result.compliance_improved)
        self.assertFalse(result.fully_fixed)
        self.assertEqual(result.reduction_rate, 0.0)
        self.assertTrue(result.scan_failed)

    def test_raw_axe_violations_list(self):
        before = [
            {"id": "region", "nodes": [{"html": "<div>1</div>"}, {"html": "<div>2</div>"}]},
            {"id": "image-alt", "nodes": [{"html": "<img>"}]},
        ]
        after = [
            {"id": "region", "nodes": [{"html": "<div>1</div>"}]},
        ]
        self.assertEqual(count_violations(before), 3)
        self.assertEqual(count_unique_rules(before), 2)
        self.assertEqual(count_violations(after), 1)
        self.assertEqual(count_unique_rules(after), 1)

        result = calculate_effectiveness(before, after)
        self.assertEqual(result.violations_before, 3)
        self.assertEqual(result.violations_after, 1)
        self.assertEqual(result.violations_reduced, 2)
        self.assertTrue(result.compliance_improved)
        self.assertFalse(result.fully_fixed)
        self.assertEqual(result.rules_before, 2)
        self.assertEqual(result.rules_after, 1)
        self.assertEqual(result.reduction_rate, 66.67)


if __name__ == "__main__":
    unittest.main()
