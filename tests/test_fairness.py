"""Non-blocking fairness visibility for recall differences across loyalty tiers."""

import json
import math
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


def _report_tier_fairness(slices):
    """Report a non-blocking warning when positive-example tier recalls differ."""
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

    # The lab flags gaps above 10 percentage points; isclose keeps decimal
    # representation noise from turning an exact 10-point gap into a flag.
    exceeds_threshold = gap > 0.10 and not math.isclose(gap, 0.10, abs_tol=1e-12)
    label = "Fairness flag" if exceeds_threshold else "Fairness check"
    suffix = "; review before approving the model." if exceeds_threshold else "."
    warnings.warn(
        f"{label}: loyalty-tier recall@10% gap is {gap:.1%} "
        f"({highest}={recalls[highest]:.3f}; {lowest}={recalls[lowest]:.3f}){suffix}",
        UserWarning,
    )


def test_loyalty_tier_recall_gap_is_reported(evaluation_metrics):
    """Warn for a >10 pp tier gap; keep this diagnostic non-blocking."""
    slices = evaluation_metrics.get("tier_metrics", {})
    _report_tier_fairness(slices)


def test_gap_at_ten_percentage_points_is_informational():
    """The rubric flags gaps that exceed 10 pp, not a gap equal to 10 pp."""
    slices = {
        "Bronze": {"recall_top10": 0.30, "positives": 40},
        "Platinum": {"recall_top10": 0.40, "positives": 40},
    }

    with pytest.warns(UserWarning, match="Fairness check:") as recorded:
        _report_tier_fairness(slices)

    assert "Fairness flag:" not in str(recorded[0].message)
