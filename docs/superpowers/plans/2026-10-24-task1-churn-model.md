# Lab 3 Task 1 Churn Model Implementation Plan

> **For agentic workers:** Execute inline in this checkout. Use test-driven development for each code task and commit each verified task.

**Goal:** Complete Task 1 in `churn_training_skeleton.py`, run three meaningful Athena-backed MLflow experiments, register the final model for manual approval, and save all Task 1 evidence.

**Architecture:** Train locally with XGBoost 3.4.1. Load the latest non-deleted feature record per customer through the Feature Store Athena table, evaluate the held-out split and loyalty-tier slices, log every run to the existing SageMaker MLflow App, and register only the final run in the SageMaker Model Registry.

**Tech Stack:** Python 3.12, SageMaker Python SDK 2.257.7, pandas, scikit-learn, XGBoost 3.4.1, boto3, MLflow, sagemaker-mlflow, matplotlib.

**Spec:** `lab-3-model-development/Lab_3--Model Development.html`; `lab-3-model-development/LAB3-TODO.md`; `churn_training_skeleton.py`.

## Global Constraints

- Use AWS profile `northstar`, account `573693339848`, region `us-east-1`; verify identity before any AWS write or Athena query.
- Read training rows from the Feature Store offline store through Athena; do not use the local CSV for the graded run.
- Select model features separately from `customer_id`, `loyalty_tier`, and `churn_label`; exclude deleted records and keep the latest `event_time` per customer.
- Keep a stable `ORDER BY customer_id` so the seeded train/test split is reproducible.
- Use the existing `northstar-mlflow` MLflow App and its current ARN; never create a Tracking Server.
- Train locally; do not create SageMaker training jobs or endpoints.
- Final run must pass the precision/recall gates and have a paired 95% AUC-lift interval above zero.
- Register only the graded run in model group `northstar-churn-models` with `PendingManualApproval` and matching numeric metrics in `CustomerMetadataProperties`.
- Save the exact Task 1 evidence names under `docs/lab3-evidence/` and the report at `docs/lab3-evaluation-report.md`.

## Review Focus

- Duplicate or soft-deleted offline-store rows: the loader test verifies deduplication clauses and deterministic ordering in the Athena SQL.
- Mismatched date types: test that ISO date bounds become UTC epoch seconds for the `Fractional` `event_time` column.
- Missing features or labels: test the documented imputation behavior and that labels never enter the feature matrix.
- Tier alignment after splitting: test that each validation score is evaluated against its original tier.
- Small or single-class slices: test that AUC and recall are safely undefined and `too_small` is set when evidence is insufficient.
- Tied prediction scores: test that top-10% selection is deterministic and selects the intended count.
- Model Registry consistency: test that only the explicit final registration call creates a package and that its metadata mirrors the evaluation metrics.

---

### Task 1: Athena Loader and Preprocessing

**Files:**
- Modify: `churn_training_skeleton.py`
- Create: `tests/test_churn_training_skeleton.py`

**Interfaces:** `load_features_from_feature_store(...) -> pd.DataFrame`; `preprocess_features(df) -> (X, y)`.

- [x] Add tests for the query lifecycle, query ID logging, result DataFrame, epoch bounds, and required SQL clauses.
- [x] Run the focused unit tests and confirm they fail for the unimplemented loader.
- [x] Execute the prepared query, wait, print the prescribed Athena ID, and return `query.as_dataframe()`.
- [x] Add preprocessing tests for missing values and label exclusion; the existing feature-only matrix already satisfies them.
- [x] Run the focused tests and commit.

### Task 2: Slice Evaluation and Evidence Plots

**Files:**
- Modify: `churn_training_skeleton.py`
- Modify: `tests/test_churn_training_skeleton.py`

**Interfaces:** `evaluate_slices(model, X_val, y_val, slice_column) -> dict` and `main()` writes `slice-evaluation.csv`, `confusion-matrix.png`, and `feature-importance.png`.

- [x] Add synthetic-data tests for per-tier sample/positive counts, AUC, recall@top10%, too-small flags, and stable ordering.
- [x] Run the focused tests and confirm the slice stub fails them.
- [x] Implement slice metrics and pass tier values through the same stratified split indices as validation rows.
- [x] Add tests for output files and threshold labeling; implement the plots and CSV writer.
- [x] Run the full unit suite and commit.

### Task 3: MLflow and Model Registry

**Files:**
- Modify: `churn_training_skeleton.py`
- Modify: `tests/test_churn_training_skeleton.py`

**Interfaces:** `track_run(args, metrics, scale_pos_weight)` and `save_and_register_model(model, metrics, args)`.

- [x] Add tests that assert run parameters/metrics and opt-in final-only registration.
- [x] Log hyperparameters, resolved class weight, XGBoost version, and numeric evaluation metrics to the MLflow App.
- [x] Create the local model archive and register only when `--register-model` is supplied; set `PendingManualApproval` and metric metadata.
- [x] Run the full unit suite and commit.

### Task 4: Athena-Backed Experiments and Final Evidence

**Files:**
- Modify: `churn_training_skeleton.py` as needed
- Create: `docs/lab3-evidence/train-final.log`, `evaluation_metrics.json`, `slice-evaluation.csv`, `confusion-matrix.png`, `feature-importance.png`
- Create: `docs/lab3-evaluation-report.md`

- [x] Verify AWS identity, Feature Store state, MLflow App status, and existing model package group.
- [x] Run meaningful parameter variations through Athena and log each run to the MLflow App without registering exploratory models.
- [x] Select a passing configuration; run the final Athena-backed experiment with `--register-model` and save its console output.
- [x] Verify 9,999 customers, required metrics, tier slices, MLflow run, and PendingManualApproval package metrics.
- [x] Write the evaluation report from the actual outputs, rerun the full unit suite, inspect `git diff`, and commit final evidence.
