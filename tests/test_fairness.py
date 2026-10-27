"""Non-blocking fairness visibility for recall differences across loyalty tiers."""

import json
import os
import warnings
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def evaluation_metrics(request):
    path = request.config.getoption("--eval-metrics-path") or os.environ.get(
        "EVAL_METRICS_PATH", "/tmp/eval_metrics.json"
    )
    if not Path(path).exists():
        pytest.skip(f"Evaluation metrics not found at {path}.")
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def test_loyalty_tier_recall_gap_is_reported(evaluation_metrics):
    """Warn for a >10 pp tier gap; keep this diagnostic non-blocking."""
    slices = evaluation_metrics.get("tier_metrics", {})
    assert len(slices) >= 2, "evaluation metrics must include at least two loyalty tiers"
    recalls = {
        tier: float(result["recall_top10"])
        for tier, result in slices.items()
        if result.get("positives", 0) > 0
    }
    assert len(recalls) >= 2, "at least two tiers need positive examples for recall comparison"
    lowest = min(recalls, key=recalls.get)
    highest = max(recalls, key=recalls.get)
    gap = recalls[highest] - recalls[lowest]
    if gap > 0.10:
        warnings.warn(
            f"Fairness flag: loyalty-tier recall@10% gap is {gap:.1%} "
            f"({highest}={recalls[highest]:.3f}; {lowest}={recalls[lowest]:.3f}); "
            "review before approving the model.",
            UserWarning,
        )
    else:
        warnings.warn(
            f"Fairness check: loyalty-tier recall@10% gap is {gap:.1%} "
            f"({highest}={recalls[highest]:.3f}; {lowest}={recalls[lowest]:.3f}).",
            UserWarning,
        )
