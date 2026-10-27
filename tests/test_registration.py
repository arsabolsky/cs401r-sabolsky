"""The CI quality gates must finish before any model is registered."""

from pathlib import Path

import boto3
import pytest
from botocore.validate import validate_parameters

from models.churn.register_model import build_model_package_request


def test_package_request_is_pending_and_carries_metrics_and_lineage():
    metrics = {
        "auc_roc": 0.78,
        "precision_top10": 0.71,
        "recall_top10": 0.32,
        "lift_ci_low": 0.04,
        "lift_ci_high": 0.08,
    }
    metadata = {
        "TrainingDataS3Uri": "s3://northstar-dev-data/features/customers/",
        "FeatureEventTimeMax": "1793049600",
        "CodeCommitSha": "a1b2c3d4e5f6",
        "EvaluationMetricsS3Uri": "s3://northstar-dev-data/artifacts/evaluations/a1b2c3d4/evaluation_metrics.json",
    }

    request = build_model_package_request(
        model_package_group_name="northstar-churn-models",
        image_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/xgboost:1.7-1",
        model_data_url="s3://northstar-dev-data/artifacts/training/model.tar.gz",
        metrics_s3_uri=metadata["EvaluationMetricsS3Uri"],
        metrics=metrics,
        metadata=metadata,
    )

    assert request["ModelApprovalStatus"] == "PendingManualApproval"
    assert request["ModelPackageGroupName"] == "northstar-churn-models"
    assert request["InferenceSpecification"]["Containers"][0]["ModelDataUrl"] == (
        "s3://northstar-dev-data/artifacts/training/model.tar.gz"
    )
    assert request["ModelMetrics"]["ModelQuality"]["Statistics"]["S3Uri"] == (
        metadata["EvaluationMetricsS3Uri"]
    )
    package_metadata = request["CustomerMetadataProperties"]
    assert all(package_metadata[key] == value for key, value in metadata.items())
    assert package_metadata["AucRoc"] == "0.78"
    assert package_metadata["PrecisionTop10"] == "0.71"
    assert package_metadata["RecallTop10"] == "0.32"

    client = boto3.client(
        "sagemaker",
        region_name="us-east-1",
        aws_access_key_id="local-test",
        aws_secret_access_key="local-test",
    )
    operation = client.meta.service_model.operation_model("CreateModelPackage")
    validate_parameters(request, operation.input_shape)


def test_package_request_rejects_missing_gate_metric():
    with pytest.raises(ValueError, match="lift_ci_high"):
        build_model_package_request(
            model_package_group_name="northstar-churn-models",
            image_uri="xgboost-image",
            model_data_url="s3://bucket/model.tar.gz",
            metrics_s3_uri="s3://bucket/metrics.json",
            metrics={"auc_roc": 0.7},
            metadata={},
        )


def test_ci_model_gate_runs_before_package_registration():
    root = Path(__file__).resolve().parents[1]
    buildspec = (root / "buildspec.yml").read_text(encoding="utf-8")
    pipeline_definition = (root / "models/churn/pipeline_definition.py").read_text(
        encoding="utf-8"
    )

    assert buildspec.index("python -m pytest tests/test_model.py") < buildspec.index(
        "models/churn/register_model.py"
    )
    assert "RegisterModel(" not in pipeline_definition
