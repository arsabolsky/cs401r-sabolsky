# Lab 3 Task 1 — Churn Model Evaluation

## Evaluation setup

The final run queried the SageMaker Feature Store offline table through Athena and loaded **9,999 unique customers** after excluding soft-deleted rows and keeping each customer's latest event. The query ID is recorded in [`train-final.log`](lab3-evidence/train-final.log) and its AWS query details are in [`athena-query.json`](lab3-evidence/athena-query.json).

The model used an 11-column feature matrix, with missing numeric values filled using `-1`. `churn_label`, `customer_id`, and `loyalty_tier` were kept out of the feature matrix; the recency heuristic `churn_risk_score` was also excluded. A stratified 70/30 split produced 6,999 training rows and 3,000 validation rows (seed 42). Top-10% metrics select exactly 300 validation customers, with stable tie ordering.

## Final validation metrics

| Metric | Result | Requirement |
|---|---:|---:|
| XGBoost version | 3.4.1 | Report version |
| Validation AUC-ROC | 0.7821 | Report |
| Recency-only baseline AUC | 0.7232 | Compare against baseline |
| AUC lift over baseline | +0.0589 | Positive |
| Paired bootstrap 95% CI for lift | [0.0404, 0.0776] | Must exclude zero — **pass** |
| Precision at top 10% | 0.7167 | ≥ 0.50 — **pass** |
| Recall at top 10% | 0.3258 | ≥ 0.25 — **pass** |

The lift interval uses 2,000 paired bootstrap resamples of the validation rows. Both models are scored on the same sampled rows in each replicate. The complete machine-readable metrics are in [`evaluation_metrics.json`](lab3-evidence/evaluation_metrics.json).

## Experiments

Three Athena-backed exploratory runs varied depth and learning rate; all logged parameters and metrics to the `northstar-churn` experiment in the SageMaker MLflow App. The final run is also tracked there and is the registered model version.

| Run | max_depth | eta | AUC | Precision@10% | Recall@10% | Lift 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| depth6-eta0.1 | 6 | 0.10 | 0.7764 | 0.6900 | 0.3136 | [0.0331, 0.0731] |
| depth4-eta0.1 | 4 | 0.10 | 0.7821 | 0.7167 | 0.3258 | [0.0404, 0.0776] |
| depth8-eta0.05 | 8 | 0.05 | 0.7751 | 0.7067 | 0.3212 | [0.0314, 0.0713] |

The depth-4, eta-0.10 configuration had the strongest validation AUC and top-10 precision/recall among these runs, so it was selected for the final run. Exported MLflow details are in [`mlflow-runs.csv`](lab3-evidence/mlflow-runs.csv).

## Loyalty-tier slices

The slice `recall_top10` selects the top 10% of scores within each tier. A tier is marked `too_small` if it has fewer than 50 customers or fewer than 30 positive or negative examples. This conservative class-count rule flags Platinum, whose slice has only 21 positive validation cases; its apparently high AUC and recall should not be treated as a reliable ranking. The weakest adequately sized tier is **Silver**: AUC 0.7171 and recall@top10% 0.2566. Its recall is 6.9 percentage points below aggregate recall, so it does not cross the 10-point gap flag.

| Tier | n | Positives | AUC | Recall@top10% | Too small? |
|---|---:|---:|---:|---:|---|
| Bronze | 1,071 | 361 | 0.7517 | 0.2853 | No |
| Gold | 483 | 52 | 0.7480 | 0.2885 | No |
| Platinum | 307 | 21 | 0.8889 | 0.5714 | **Yes** |
| Silver | 1,139 | 226 | 0.7171 | 0.2566 | No |

See the full slice output in [`slice-evaluation.csv`](lab3-evidence/slice-evaluation.csv).

## Plots and registration

The confusion matrix uses a **0.50 probability threshold**: [`confusion-matrix.png`](lab3-evidence/confusion-matrix.png). Gain-based feature importance is in [`feature-importance.png`](lab3-evidence/feature-importance.png).

The final model is registered in `northstar-churn-models` as version 2 with status **PendingManualApproval**. Its `auc_roc`, `precision_top10`, and `recall_top10` metadata match the final evaluation metrics. The exported registry record is [`model-registry.json`](lab3-evidence/model-registry.json).
