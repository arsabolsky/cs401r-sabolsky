import tempfile
import unittest
from pathlib import Path

import pandas as pd

from evaluation_harness import append_rag_results


class RAGEvaluationOutputTests(unittest.TestCase):
    def test_append_deduplicates_customer_rows_within_run_but_keeps_other_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "rag_eval.csv")
            append_rag_results(pd.DataFrame([
                {"run_id": "run-1", "customer_id": "C1", "score": 0.2},
                {"run_id": "run-1", "customer_id": "C2", "score": 0.3},
            ]), str(output))
            append_rag_results(pd.DataFrame([
                {"run_id": "run-1", "customer_id": "C1", "score": 0.9},
                {"run_id": "run-2", "customer_id": "C1", "score": 0.4},
            ]), str(output))

            result = pd.read_csv(output)

        self.assertEqual(len(result), 3)
        self.assertEqual(
            result.loc[(result.run_id == "run-1") & (result.customer_id == "C1"),
                       "score"].iloc[0],
            0.9,
        )
        self.assertEqual(set(result.run_id), {"run-1", "run-2"})


if __name__ == "__main__":
    unittest.main()
