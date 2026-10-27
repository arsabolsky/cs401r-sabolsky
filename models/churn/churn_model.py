"""Your Lab 3 churn model, packaged for the Lab 4 pipeline.

YOU WRITE THIS FILE. The pipeline's training job runs train_sagemaker.py
(beside this file; do not edit it), which imports this module and calls
train(). Everything the job needs from you goes through the three names below.

Contract (train_sagemaker.py checks it in the first seconds of the job):

    FEATURE_COLUMNS   list[str]   model input columns, in order
    LABEL             str         "churn_label"
    train(df, seed=42) -> (xgboost.Booster, dict)

`df` is the full labeled feature table: every column of your Lab 2 output,
including `loyalty_tier` for slice evaluation. It is already loaded. Do not
query Athena or the Feature Store from here; the training container stages
the data for you and has no business making service calls for its input.

The metrics dict must include the four numbers the CI gate in
tests/test_model.py reads. Your Lab 3 evaluate_model() already returns them:

    precision_top10, recall_top10      gated at 0.50 / 0.25
    lift_ci_low, lift_ci_high          bootstrap 95% CI on AUC lift over the
                                       recency-only baseline; lift_ci_low > 0

Include anything else you reported in Lab 3 (auc_roc, baseline_auc,
positive_rate_val, slice results). It is all written to evaluation_metrics.json
and attached to the registered model.

What runs in the container: the SageMaker XGBoost 1.7-1 image ships pandas,
numpy, scikit-learn, xgboost and boto3. It does NOT ship mlflow or sagemaker,
so do not import them at the top of this file. MLflow tracking stays in your
Lab 3 script.

Only this directory (models/churn/) is uploaded to the training job, so the
code must live here. `import churn_training_skeleton` will fail inside the
container even though it works on your laptop. Copy the functions you need.

Test it locally before pushing:

    python models/churn/train_sagemaker.py \
        --train-channel <dir containing your features CSV or Parquet> \
        --model-dir /tmp/model --output-data-dir /tmp/out
"""

# Keeps Lab 3 annotations like `-> tuple[np.ndarray, np.ndarray]` from being
# evaluated, whatever Python the training container runs.
from __future__ import annotations

import numpy as np  # noqa: F401
import pandas as pd  # noqa: F401
import xgboost as xgb  # noqa: F401
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

# Must match the columns your Lab 3 model was trained on, in the same order.
FEATURE_COLUMNS = [
    "days_since_last_purchase",
    "customer_tenure_days",
    "purchase_frequency_30d",
    "purchase_frequency_90d",
    "purchase_frequency_180d",
    "avg_order_value",
    "total_spend_90d",
    "total_lifetime_value",
    "avg_basket_size_6m",
    "category_diversity_score",
    "online_to_store_ratio",
]

LABEL = "churn_label"

BASELINE_FEATURE = "days_since_last_purchase"
EVAL_THRESHOLDS = {"precision_top10": 0.50, "recall_top10": 0.25}


def _top_fraction_mask(scores: np.ndarray, fraction: float = 0.10) -> np.ndarray:
    """Select exactly ceil(fraction * n) highest scores, stably on ties."""
    scores = np.asarray(scores)
    count = int(np.ceil(len(scores) * fraction))
    mask = np.zeros(len(scores), dtype=bool)
    if count:
        mask[np.argsort(-scores, kind="stable")[:count]] = True
    return mask


def _bootstrap_lift_ci(y_true, proba, baseline_proba, n=2000, seed=42, alpha=0.05):
    """Paired bootstrap confidence interval for candidate AUC minus recency AUC."""
    rng = np.random.default_rng(seed)
    indices = np.arange(len(y_true))
    differences = []
    for _ in range(n):
        sample = rng.choice(indices, size=len(indices), replace=True)
        labels = y_true[sample]
        if len(np.unique(labels)) < 2:
            continue
        differences.append(
            roc_auc_score(labels, proba[sample])
            - roc_auc_score(labels, baseline_proba[sample])
        )
    if len(differences) < n // 2:
        raise ValueError("Too few usable bootstrap samples to evaluate baseline lift")
    return tuple(float(value) for value in np.quantile(
        differences, [alpha / 2, 1 - alpha / 2]
    ))


def _evaluate_slices(model, X_val, y_val, tiers):
    """Return per-tier recall@10% used by the non-blocking fairness gate."""
    scores = model.predict(xgb.DMatrix(X_val, feature_names=FEATURE_COLUMNS))
    labels = np.asarray(y_val).astype(int)
    tier_values = pd.Series(tiers).fillna("Unknown").astype(str).reset_index(drop=True)
    if len(tier_values) != len(labels):
        raise ValueError("loyalty_tier and validation labels must have equal lengths")
    output = {}
    for tier in sorted(tier_values.unique()):
        mask = tier_values.eq(tier).to_numpy()
        tier_labels = labels[mask]
        top = _top_fraction_mask(scores[mask])
        positives = int(tier_labels.sum())
        output[tier] = {
            "n": int(mask.sum()),
            "positives": positives,
            "recall_top10": float(tier_labels[top].sum() / positives) if positives else 0.0,
            "too_small": bool(mask.sum() < 50 or positives < 30 or mask.sum() - positives < 30),
        }
    return output


def train(df: pd.DataFrame, seed: int = 42):
    """Train the churn model on `df` and return (booster, metrics).

    TODO (Lab 4): implement this from your Lab 3 code. The usual shape:

      1. X, y from FEATURE_COLUMNS and LABEL (handle missing values the way
         your Lab 3 preprocess_features() did)
      2. train_test_split(..., test_size=0.30, random_state=seed, stratify=y)
         -- carry the tier through the same call if you report slices. Pass
         df["loyalty_tier"] (a Series) or .to_numpy(dtype=object); NOT
         .values, which under pandas 3 is an Arrow array that
         train_test_split cannot index
      3. train the XGBoost model (your Lab 3 train_model())
      4. train the recency-only baseline (train_recency_baseline())
      5. metrics = evaluate_model(...)   # keep Lab 3's raise on a failed gate:
                                         # it fails the training step, so a
                                         # model that misses a gate is never
                                         # registered
      6. return model, metrics

    Return an xgboost.Booster (what xgb.train() gives you). If you used
    XGBClassifier, return clf.get_booster().
    """
    required = FEATURE_COLUMNS + [LABEL, "loyalty_tier"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Training data missing required columns: {missing}")

    clean = df.dropna(subset=[LABEL]).copy()
    if clean[LABEL].nunique() != 2:
        raise ValueError("Training requires both churn_label classes")
    X = clean[FEATURE_COLUMNS].fillna(-1).to_numpy(dtype=np.float32)
    y = pd.to_numeric(clean[LABEL], errors="raise").to_numpy(dtype=np.int32)
    if set(np.unique(y)) != {0, 1}:
        raise ValueError("churn_label must contain only binary values 0 and 1")
    tiers = clean["loyalty_tier"].fillna("Unknown").astype(str).reset_index(drop=True)

    X_train, X_val, y_train, y_val, tiers_train, tiers_val = train_test_split(
        X, y, tiers, test_size=0.30, random_state=seed, stratify=y
    )
    del tiers_train

    positive_count = int((y_train == 1).sum())
    negative_count = int((y_train == 0).sum())
    if positive_count == 0:
        raise ValueError("Training split has no positive churn examples")
    scale_pos_weight = negative_count / positive_count

    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "max_depth": 6,
        "eta": 0.1,
        "min_child_weight": 5,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": scale_pos_weight,
        "seed": seed,
        "verbosity": 1,
    }
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_COLUMNS)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
    model = xgb.train(
        params=params,
        dtrain=dtrain,
        num_boost_round=200,
        evals=[(dtrain, "train"), (dval, "validation")],
        early_stopping_rounds=20,
        verbose_eval=25,
    )

    # Match Lab 3's baseline: same training rows, only days_since_last_purchase.
    recency_index = FEATURE_COLUMNS.index(BASELINE_FEATURE)
    baseline_train = xgb.DMatrix(
        X_train[:, [recency_index]], label=y_train, feature_names=[BASELINE_FEATURE]
    )
    baseline_val = xgb.DMatrix(
        X_val[:, [recency_index]], feature_names=[BASELINE_FEATURE]
    )
    baseline = xgb.train(
        {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "max_depth": 4,
            "eta": 0.1,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "scale_pos_weight": scale_pos_weight,
            "seed": 42,
            "verbosity": 0,
        },
        baseline_train,
        num_boost_round=200,
    )

    probabilities = model.predict(dval)
    baseline_probabilities = baseline.predict(baseline_val)
    top10 = _top_fraction_mask(probabilities)
    precision = float(y_val[top10].mean()) if top10.any() else 0.0
    recall = float(y_val[top10].sum() / y_val.sum()) if y_val.sum() else 0.0
    auc = float(roc_auc_score(y_val, probabilities))
    baseline_auc = float(roc_auc_score(y_val, baseline_probabilities))
    ci_low, ci_high = _bootstrap_lift_ci(y_val, probabilities, baseline_probabilities)

    metrics = {
        "auc_roc": round(auc, 4),
        "precision_top10": round(precision, 4),
        "recall_top10": round(recall, 4),
        "baseline_auc": round(baseline_auc, 4),
        "baseline_auc_roc": round(baseline_auc, 4),
        "auc_vs_baseline": round(auc - baseline_auc, 4),
        "auc_lift_over_baseline": round(auc - baseline_auc, 4),
        "lift_ci_low": round(ci_low, 4),
        "lift_ci_high": round(ci_high, 4),
        "auc_lift_ci_low": round(ci_low, 4),
        "auc_lift_ci_high": round(ci_high, 4),
        "positive_rate_val": round(float(y_val.mean()), 4),
        "n_val_samples": int(len(y_val)),
        "hyperparameters": {
            "max_depth": 6,
            "eta": 0.1,
            "min_child_weight": 5,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "num_boost_round": 200,
            "early_stopping_rounds": 20,
            "scale_pos_weight": scale_pos_weight,
            "seed": seed,
        },
        "tier_metrics": _evaluate_slices(model, X_val, y_val, tiers_val),
    }

    failures = [
        f"{name}={metrics[name]:.4f} < {threshold:.2f}"
        for name, threshold in EVAL_THRESHOLDS.items()
        if metrics[name] < threshold
    ]
    if ci_low <= 0:
        failures.append(f"baseline lift 95% CI [{ci_low:.4f}, {ci_high:.4f}] includes zero")
    if failures:
        raise ValueError("Model failed Lab 3 evaluation gates: " + "; ".join(failures))

    return model, metrics
