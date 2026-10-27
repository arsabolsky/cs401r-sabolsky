import contextlib
import csv
import io
import os
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
from botocore.exceptions import ClientError

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


class SliceEvaluationTests(unittest.TestCase):
    def test_top_fraction_mask_uses_exact_count_and_stable_tie_order(self):
        mask = training._top_fraction_mask(np.ones(10), fraction=0.10)

        self.assertEqual(int(mask.sum()), 1)
        self.assertTrue(mask[0])

    def test_evaluate_slices_reports_metrics_and_flags_small_tier(self):
        small_scores = np.linspace(1.0, 0.05, 20)
        large_scores = np.linspace(0.99, 0.01, 100)
        platinum_scores = np.linspace(0.98, 0.02, 100)
        scores = np.concatenate([small_scores, large_scores, platinum_scores])
        labels = np.zeros(220, dtype=int)
        labels[[0, 1, 2, 19]] = 1
        labels[20 + np.array([0, 1, 2, 3, 4] + list(range(10, 35)))] = 1
        labels[120 + np.arange(21)] = 1
        tiers = pd.Series(["Silver"] * 20 + ["Gold"] * 100 + ["Platinum"] * 100)
        features = np.zeros((220, len(training.FEATURE_COLUMNS)))

        class FixedPredictor:
            def predict(self, _matrix):
                return scores

        with mock.patch.object(training.xgb, "DMatrix", side_effect=lambda X, **_: X):
            results = training.evaluate_slices(
                FixedPredictor(), features, labels, tiers
            )

        self.assertEqual(results["Silver"]["n"], 20)
        self.assertEqual(results["Silver"]["positives"], 4)
        self.assertTrue(results["Silver"]["too_small"])
        self.assertAlmostEqual(results["Silver"]["recall_top10"], 0.5)
        self.assertEqual(results["Gold"]["n"], 100)
        self.assertEqual(results["Gold"]["positives"], 30)
        self.assertFalse(results["Gold"]["too_small"])
        self.assertIsInstance(results["Gold"]["auc_roc"], float)
        self.assertIn("aggregate_recall_top10", results["Gold"])
        self.assertEqual(results["Platinum"]["positives"], 21)
        self.assertTrue(results["Platinum"]["too_small"])

    def test_slice_csv_has_rubric_columns(self):
        rows = {
            "Gold": {
                "n": 100,
                "positives": 30,
                "auc_roc": 0.75,
                "recall_top10": 0.2,
                "too_small": False,
                "below_aggregate_by_10pp": True,
                "weakest": True,
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "slice-evaluation.csv"
            training.save_slice_evaluation_csv(rows, path)

            with path.open(newline="") as f:
                reader = csv.DictReader(f)
                self.assertTrue({"tier", "n", "positives", "auc_roc",
                                 "recall_top10", "too_small"}.issubset(reader.fieldnames))
                saved = next(reader)
        self.assertEqual(saved["tier"], "Gold")
        self.assertEqual(saved["too_small"], "False")

    def test_evaluation_plots_are_saved(self):
        rng = np.random.default_rng(5)
        features = rng.normal(size=(60, len(training.FEATURE_COLUMNS)))
        labels = np.array([0, 1] * 30)
        dtrain = training.xgb.DMatrix(
            features, label=labels, feature_names=training.FEATURE_COLUMNS
        )
        model = training.xgb.train(
            {"objective": "binary:logistic", "max_depth": 2, "nthread": 1},
            dtrain,
            num_boost_round=3,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            saved = training.save_evaluation_plots(
                model, features, labels, temp_dir, threshold=0.5
            )

            self.assertTrue(os.path.isfile(saved["confusion_matrix"]))
            self.assertTrue(os.path.isfile(saved["feature_importance"]))
            self.assertGreater(os.path.getsize(saved["confusion_matrix"]), 0)
            self.assertGreater(os.path.getsize(saved["feature_importance"]), 0)


class TrackingAndRegistryTests(unittest.TestCase):
    def test_track_run_logs_params_and_numeric_metrics_to_app(self):
        calls = []
        class FakeMlflow:
            def set_tracking_uri(self, uri): calls.append(("uri", uri))
            def set_experiment(self, name): calls.append(("experiment", name))
            @contextlib.contextmanager
            def start_run(self, run_name=None):
                calls.append(("run", run_name))
                yield
            def log_params(self, params): calls.append(("params", params))
            def log_metrics(self, metrics): calls.append(("metrics", metrics))

        args = types.SimpleNamespace(
            mlflow_arn="arn:aws:sagemaker:us-east-1:573693339848:mlflow-app/app-test",
            mlflow_experiment="northstar-churn", run_name="depth-test",
            max_depth=4, eta=0.05, num_round=100, min_child_weight=2,
            subsample=0.8, colsample_bytree=0.9, seed=42,
            early_stopping_rounds=20, verbose_eval=25,
        )
        with mock.patch.dict("sys.modules", {"mlflow": FakeMlflow()}):
            training.track_run(args, {"auc_roc": 0.8, "slice_name": "Gold"}, 3.5)

        params = next(value for kind, value in calls if kind == "params")
        metrics = next(value for kind, value in calls if kind == "metrics")
        self.assertEqual(params["scale_pos_weight"], 3.5)
        self.assertEqual(params["xgboost_version"], training.xgb.__version__)
        self.assertEqual(metrics, {"auc_roc": 0.8})
        self.assertIn(("uri", args.mlflow_arn), calls)

    def test_registration_is_opt_in_and_sets_pending_metrics(self):
        class FakeModel:
            def save_model(self, path):
                with open(path, "wb") as f:
                    f.write(b"test-model")

        class FakeS3:
            def __init__(self): self.upload = None
            def upload_file(self, *args): self.upload = args

        class FakeSM:
            def __init__(self): self.package = None
            def describe_model_package_group(self, **kwargs):
                raise ClientError(
                    {"Error": {"Code": "ValidationException",
                               "Message": "ModelPackageGroup does not exist"}},
                    "DescribeModelPackageGroup",
                )
            def create_model_package_group(self, **kwargs): pass
            def create_model_package(self, **kwargs):
                self.package = kwargs
                return {"ModelPackageArn": "arn:package:test"}

        model = FakeModel()
        with tempfile.TemporaryDirectory() as temp_dir:
            args = types.SimpleNamespace(
                model_dir=temp_dir, register_model=False,
                artifacts_bucket="northstar-dev-data-573693339848",
                max_depth=4, eta=0.1, num_round=20,
                seed=42, early_stopping_rounds=20, verbose_eval=25,
            )
            training.save_and_register_model(model, {"auc_roc": 0.8}, args)
            # Local artifacts are saved even when exploratory run is not registered.
            self.assertTrue(os.path.isfile(Path(temp_dir) / "model_metadata.json"))

            args.register_model = True
            s3, sm = FakeS3(), FakeSM()
            def fake_client(name, **kwargs):
                return {"s3": s3, "sagemaker": sm}[name]
            with (
                mock.patch.object(training.boto3, "client", side_effect=fake_client),
                mock.patch.object(training.sagemaker, "image_uris",
                                  types.SimpleNamespace(retrieve=lambda **_: "image-uri"),
                                  create=True),
                mock.patch.dict(os.environ, {"AWS_REGION": "us-east-1"}),
            ):
                training.save_and_register_model(model, {"auc_roc": 0.8}, args)

        self.assertIsNotNone(s3.upload)
        self.assertEqual(sm.package["ModelApprovalStatus"], "PendingManualApproval")
        self.assertEqual(sm.package["CustomerMetadataProperties"]["auc_roc"], "0.8")
        self.assertEqual(sm.package["InferenceSpecification"]["Containers"][0]["Image"],
                         "image-uri")


if __name__ == "__main__":
    unittest.main()
