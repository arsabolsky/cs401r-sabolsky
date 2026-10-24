import contextlib
import io
import unittest
from datetime import datetime, timezone
from unittest import mock

import numpy as np
import pandas as pd

import churn_training_skeleton as training


class FakeAthenaQuery:
    table_name = "northstar_dev_customer_features_test"

    def __init__(self, dataframe):
        self.dataframe = dataframe
        self.run_kwargs = None
        self.waited = False

    def run(self, **kwargs):
        self.run_kwargs = kwargs

    def wait(self):
        self.waited = True

    def get_query_execution(self):
        return {"QueryExecution": {"QueryExecutionId": "query-123"}}

    def as_dataframe(self):
        if not self.waited:
            raise AssertionError("as_dataframe called before Athena completed")
        return self.dataframe


class FakeFeatureGroup:
    def __init__(self, query):
        self.query = query

    def athena_query(self):
        return self.query


class FeatureStoreLoaderTests(unittest.TestCase):
    def setUp(self):
        self.expected = pd.DataFrame([{
            "customer_id": "CUST-00000001",
            **{name: 1.0 for name in training.FEATURE_COLUMNS},
            training.LABEL_COLUMN: 0,
            training.SLICE_COLUMN: "Bronze",
        }])
        self.query = FakeAthenaQuery(self.expected)

    def test_runs_waits_logs_query_id_and_returns_athena_dataframe(self):
        output = io.StringIO()
        with (
            mock.patch.object(training, "SAGEMAKER_AVAILABLE", True),
            mock.patch.object(training, "Session", return_value=object()),
            mock.patch.object(
                training, "FeatureGroup", return_value=FakeFeatureGroup(self.query)
            ),
            contextlib.redirect_stdout(output),
        ):
            result = training.load_features_from_feature_store(
                "northstar-dev-customer-features",
                "2026-01-01",
                "2027-01-01",
                "northstar-dev-data-573693339848",
            )

        self.assertIs(result, self.expected)
        self.assertTrue(self.query.waited)
        self.assertEqual(
            self.query.run_kwargs["output_location"],
            "s3://northstar-dev-data-573693339848/artifacts/athena-results/",
        )
        self.assertIn("Athena QueryExecutionId: query-123", output.getvalue())

    def test_query_bounds_event_time_and_deduplicates_in_stable_order(self):
        with (
            mock.patch.object(training, "SAGEMAKER_AVAILABLE", True),
            mock.patch.object(training, "Session", return_value=object()),
            mock.patch.object(
                training, "FeatureGroup", return_value=FakeFeatureGroup(self.query)
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            training.load_features_from_feature_store(
                "northstar-dev-customer-features",
                "2026-01-01",
                "2027-01-01",
                "northstar-dev-data-573693339848",
            )

        sql = self.query.run_kwargs["query_string"]
        start_epoch = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
        end_epoch = datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp()
        self.assertIn(f"event_time BETWEEN {start_epoch} AND {end_epoch}", sql)
        self.assertIn("AND NOT is_deleted", sql)
        self.assertIn("PARTITION BY customer_id", sql)
        self.assertIn("ORDER BY event_time DESC, write_time DESC", sql)
        self.assertIn("WHERE rn = 1", sql)
        self.assertTrue(sql.rstrip().endswith("ORDER BY customer_id"))
        self.assertIn(training.SLICE_COLUMN, sql)
        self.assertIn(training.LABEL_COLUMN, sql)


class PreprocessingTests(unittest.TestCase):
    def test_missing_features_use_sentinel_and_metadata_never_enters_matrix(self):
        row = {name: 1.0 for name in training.FEATURE_COLUMNS}
        row[training.FEATURE_COLUMNS[0]] = np.nan
        row.update({
            training.LABEL_COLUMN: 1,
            training.SLICE_COLUMN: "Gold",
            "customer_id": "CUST-00000002",
        })

        X, y = training.preprocess_features(pd.DataFrame([row]))

        self.assertEqual(X.shape, (1, len(training.FEATURE_COLUMNS)))
        self.assertEqual(X[0, 0], -1)
        self.assertEqual(y.tolist(), [1])
        self.assertNotIn(training.LABEL_COLUMN, training.FEATURE_COLUMNS)
        self.assertNotIn(training.SLICE_COLUMN, training.FEATURE_COLUMNS)
        self.assertNotIn("customer_id", training.FEATURE_COLUMNS)


if __name__ == "__main__":
    unittest.main()
