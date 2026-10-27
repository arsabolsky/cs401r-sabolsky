"""Register a trained churn model only after the CodeBuild quality gates pass."""

import argparse
import json

import boto3


REQUIRED_METRICS = (
    "auc_roc",
    "precision_top10",
    "recall_top10",
    "lift_ci_low",
    "lift_ci_high",
)
REQUIRED_METADATA = (
    "TrainingDataS3Uri",
    "FeatureEventTimeMax",
    "CodeCommitSha",
    "EvaluationMetricsS3Uri",
)


def build_model_package_request(
    *,
    model_package_group_name,
    image_uri,
    model_data_url,
    metrics_s3_uri,
    metrics,
    metadata,
):
    """Build the pending Model Registry request after validating evidence."""
    missing_metrics = [name for name in REQUIRED_METRICS if name not in metrics]
    if missing_metrics:
        raise ValueError(f"Evaluation metrics missing required gates: {missing_metrics}")
    missing_metadata = [name for name in REQUIRED_METADATA if not metadata.get(name)]
    if missing_metadata:
        raise ValueError(f"Model lineage metadata missing required values: {missing_metadata}")
    if metadata["EvaluationMetricsS3Uri"] != metrics_s3_uri:
        raise ValueError("Metrics URI and EvaluationMetricsS3Uri metadata must match")

    customer_metadata = dict(metadata)
    customer_metadata.update(
        {
            "AucRoc": str(metrics["auc_roc"]),
            "PrecisionTop10": str(metrics["precision_top10"]),
            "RecallTop10": str(metrics["recall_top10"]),
            "LiftCiLow": str(metrics["lift_ci_low"]),
            "LiftCiHigh": str(metrics["lift_ci_high"]),
        }
    )
    return {
        "ModelPackageGroupName": model_package_group_name,
        "ModelApprovalStatus": "PendingManualApproval",
        "InferenceSpecification": {
            "Containers": [{"Image": image_uri, "ModelDataUrl": model_data_url}],
            "SupportedContentTypes": ["text/csv"],
            "SupportedResponseMIMETypes": ["text/csv"],
            "SupportedRealtimeInferenceInstanceTypes": ["ml.m5.large", "ml.t2.medium"],
            "SupportedTransformInstanceTypes": ["ml.m5.large"],
        },
        "ModelMetrics": {
            "ModelQuality": {
                "Statistics": {
                    "ContentType": "application/json",
                    "S3Uri": metrics_s3_uri,
                }
            }
        },
        "CustomerMetadataProperties": customer_metadata,
    }


def register_trained_model(
    *,
    training_job_name,
    model_package_group_name,
    bucket,
    commit_sha,
    feature_event_time_max,
    region,
    metrics,
):
    """Create a pending package from a completed training job and passed gates."""
    sm = boto3.client("sagemaker", region_name=region)
    job = sm.describe_training_job(TrainingJobName=training_job_name)
    metrics_uri = f"s3://{bucket}/artifacts/evaluations/{commit_sha[:8]}/evaluation_metrics.json"
    metadata = {
        "TrainingDataS3Uri": f"s3://{bucket}/features/customers/",
        "FeatureEventTimeMax": str(feature_event_time_max),
        "CodeCommitSha": commit_sha,
        "EvaluationMetricsS3Uri": metrics_uri,
    }
    request = build_model_package_request(
        model_package_group_name=model_package_group_name,
        image_uri=job["AlgorithmSpecification"]["TrainingImage"],
        model_data_url=job["ModelArtifacts"]["S3ModelArtifacts"],
        metrics_s3_uri=metrics_uri,
        metrics=metrics,
        metadata=metadata,
    )
    response = sm.create_model_package(**request)
    package_arn = response["ModelPackageArn"]
    print(f"Created PendingManualApproval package after all model tests passed: {package_arn}")
    print(json.dumps(request["CustomerMetadataProperties"], indent=2, sort_keys=True))
    return package_arn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-job-name", required=True)
    parser.add_argument("--model-package-group", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--feature-event-time-max", required=True)
    parser.add_argument("--metrics-path", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    with open(args.metrics_path, encoding="utf-8") as stream:
        metrics = json.load(stream)
    package_arn = register_trained_model(
        training_job_name=args.training_job_name,
        model_package_group_name=args.model_package_group,
        bucket=args.bucket,
        commit_sha=args.commit_sha,
        feature_event_time_max=args.feature_event_time_max,
        region=args.region,
        metrics=metrics,
    )
    print(package_arn)


if __name__ == "__main__":
    main()
