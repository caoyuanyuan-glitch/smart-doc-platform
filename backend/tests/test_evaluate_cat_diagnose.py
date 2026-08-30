import importlib.util
import unittest
from pathlib import Path


def _load_evaluate_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_cat_diagnose.py"
    spec = importlib.util.spec_from_file_location("evaluate_cat_diagnose", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvaluateCatDiagnoseRunsTest(unittest.TestCase):
    def test_mean_of_three_runs_decides_pass(self):
        module = _load_evaluate_module()
        summaries = [
            {"a_hits": 8, "b_hits": 1, "recall": 0.80, "false_positive_rate": 0.10, "diagnoses": [1] * 8},
            {"a_hits": 7, "b_hits": 2, "recall": 0.70, "false_positive_rate": 0.20, "diagnoses": [1] * 7},
            {"a_hits": 9, "b_hits": 0, "recall": 0.90, "false_positive_rate": 0.00, "diagnoses": [1] * 9},
        ]
        aggregated = module.aggregate_run_summaries(summaries)
        self.assertEqual(aggregated["runs"], 3)
        self.assertAlmostEqual(aggregated["mean_recall"], 0.80)
        self.assertAlmostEqual(aggregated["mean_false_positive_rate"], 0.10)
        self.assertTrue(aggregated["recall_pass"])
        self.assertTrue(aggregated["false_positive_pass"])


if __name__ == "__main__":
    unittest.main()
