"""Glue adapter for the shared, testable Lab 2/4 pandas feature calculations.

The pandas module is shipped to Glue through --extra-py-files by Terraform.
Feature definitions live only in data/feature_engineering.py; this file owns
the Glue/S3 and SageMaker Feature Store integration.
"""

import sys
import time

import boto3
import pandas as pd
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from feature_engineering import (
    FEATURE_COLUMNS,
    FEATURE_CUTOFF,
    SNAPSHOT,
    build_churn_feature_set,
)


FEATURE_STORE_COLUMNS = [
    *FEATURE_COLUMNS,
    "loyalty_tier",
    "churn_risk_score",
    "churn_label",
]


def ingest_to_feature_store(rows, feature_group_name, region, event_time):
    """Write each customer row to the online Feature Store."""
    client = boto3.client("sagemaker-featurestore-runtime", region_name=region)
    ingested = 0
    for row in rows:
        record = [
            {"FeatureName": "customer_id", "ValueAsString": str(row["customer_id"])},
            {"FeatureName": "event_time", "ValueAsString": str(event_time)},
        ] + [
            {"FeatureName": name, "ValueAsString": str(row[name])}
            for name in FEATURE_STORE_COLUMNS
        ]
        client.put_record(FeatureGroupName=feature_group_name, Record=record)
        ingested += 1
    return ingested


def main():
    args = getResolvedOptions(
        sys.argv,
        ["JOB_NAME", "input_path", "output_path", "feature_group_name", "region"],
    )

    spark_context = SparkContext()
    glue_context = GlueContext(spark_context)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    source = spark.read.parquet(args["input_path"])
    transaction_count = source.count()
    print(f"[features] read {transaction_count} processed transaction rows")

    # This course sample is small enough for one pandas pass. Keeping the
    # calculations in the shared module makes the unit tests exercise the same
    # definitions Glue uses, including the feature/label time boundary.
    transactions = source.toPandas()
    customers = transactions[["customer_id"]].dropna().drop_duplicates()
    features = build_churn_feature_set(
        customers=customers,
        transactions=transactions,
        snapshot_date=FEATURE_CUTOFF,
    )
    print(
        f"[features] history cutoff: {FEATURE_CUTOFF.date()}; "
        f"label holdout ends: {SNAPSHOT.date()}"
    )

    required_columns = [
        "customer_id",
        *FEATURE_STORE_COLUMNS,
    ]
    null_counts = features[required_columns].isna().sum()
    assert int(null_counts.sum()) == 0, (
        f"feature output contains null values: {null_counts[null_counts > 0].to_dict()}"
    )

    risk = features["churn_risk_score"]
    assert risk.between(0, 1).all(), "churn_risk_score out of [0,1]"
    churn_rate = float(features["churn_label"].mean())
    print(f"[features] churn_label rate: {churn_rate:.1%}")
    assert 0.05 < churn_rate < 0.50, (
        f"churn rate {churn_rate:.1%} is implausible - check the window split"
    )

    tiers = set(features["loyalty_tier"].unique())
    print(f"[features] tier distribution present: {sorted(tiers)}")
    assert tiers == {"Bronze", "Silver", "Gold", "Platinum"}, (
        f"tier distribution is degenerate: {sorted(tiers)}"
    )

    event_time = float(int(time.time()))
    output = features.copy()
    output["customer_id"] = output["customer_id"].astype(str)
    output["loyalty_tier"] = output["loyalty_tier"].astype(str)
    output["churn_label"] = output["churn_label"].astype("int64")
    output["event_time"] = event_time
    for column in FEATURE_COLUMNS + ["churn_risk_score"]:
        output[column] = pd.to_numeric(output[column], errors="raise").astype("float64")

    output_spark = spark.createDataFrame(output)
    customer_count = len(output)
    (output_spark.coalesce(2)
                 .write
                 .mode("overwrite")
                 .parquet(args["output_path"]))
    print(f"[features] wrote {customer_count} rows to {args['output_path']}")

    ingested = ingest_to_feature_store(
        output.to_dict(orient="records"),
        args["feature_group_name"],
        args["region"],
        event_time,
    )
    print(
        f"[features] ingested {ingested} records into "
        f"{args['feature_group_name']} at event_time {event_time}"
    )

    job.commit()


if __name__ == "__main__":
    main()
