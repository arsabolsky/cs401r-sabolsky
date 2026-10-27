# NorthStar XOps Maturity Assessment

## Pipeline Stage Mapping

CodePipeline **Source** receives GitHub commits. In `buildspec.yml`, **Test** downloads the raw, processed, and feature datasets and runs `tests/test_data.py` and `tests/test_features.py`; failures stop before training. **Build** upserts the SageMaker Pipeline and trains the Lab 3 XGBoost model on managed spot capacity. **Evaluate** enforces precision@top10% ≥ 0.50, recall@top10% ≥ 0.25, and a paired-bootstrap AUC-lift interval above zero. CodeBuild then checks the model artifact, compares AUC with the newest Approved package, and warns on a loyalty-tier recall gap. **Register** creates a `PendingManualApproval` package only after training gates pass. A separate ManualApproval stage presents the metrics and Registry link for review.

## Champion-Challenger

A candidate must meet the precision, recall, and baseline-lift gates above and satisfy `candidate AUC ≥ newest Approved champion AUC − 0.02`. The first green package becomes the champion after approval; later candidates failing a gate are not promoted. A candidate failing a CodeBuild test after registration is changed to Rejected.

## Retraining Triggers

1. **Schedule:** EventBridge Scheduler starts a Step Functions workflow Mondays at 06:00 UTC. It runs Glue transform and feature jobs, then starts SageMaker training only if features are under 48 hours old.
2. **Performance:** weekly labeled evaluation publishes `PrecisionTop10` to CloudWatch. Two consecutive readings below 0.50 trigger an alarm and Lambda that starts the refresh-and-train workflow.

## DataOps Maturity

**Current level: 2.** `infrastructure/modules/glue/main.tf` defines repeatable ingestion and feature jobs. Glue and tests share `data/feature_engineering.py`. `tests/test_data.py` checks schemas, row grain, leakage, and freshness; the refreshed data passed all 28 checks in `docs/lab4-data-validation.log`. The 21 feature unit tests also passed. These checks block CI before training.

**Gap to Level 3:** checks run only during code-triggered builds. No scheduled refresh or drift alert detects stale features during an idle period.

**Top priority investment:** deploy the scheduled refresh workflow and alarm on row count, null rate, churn rate, and latest `event_time` metrics.

## MLOps Maturity

**Current level: 2.** `models/churn/churn_model.py` carries forward Lab 3 training and baseline gates. `models/churn/pipeline_definition.py` trains on spot and registers as `PendingManualApproval`. `buildspec.yml` checks artifacts, champion regression, fairness, and lineage. The real-data run reproduced Lab 3 metrics: AUC 0.7821, precision 0.7167, and recall 0.3258. `docs/lab4-mlflow-runs.txt` records six runs across three configurations.

**Gap to Level 3:** there is no production endpoint or post-deployment monitor. Promotion remains manual and the retraining triggers are not deployed.

**Top priority investment:** enable SageMaker Model Monitor after deployment and route drift alarms to the automated refresh-and-train workflow.
