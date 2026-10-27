"""Pandas feature calculations shared by the Glue job and local unit tests.

The history window ends at FEATURE_CUTOFF. Transactions after that cutoff are
used only to derive churn_label; they never contribute to model features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_CUTOFF = pd.Timestamp("2026-04-01")
SNAPSHOT = pd.Timestamp("2026-06-30")
NO_PURCHASE_SENTINEL_DAYS = 999
CATEGORY_COUNT = 8

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


def _timestamp(value) -> pd.Timestamp:
    """Return a timezone-naive timestamp for consistent date comparisons."""
    stamp = pd.Timestamp(value)
    return stamp.tz_convert(None) if stamp.tzinfo is not None else stamp


def _prepare_transactions(transactions: pd.DataFrame,
                          upper_bound: pd.Timestamp | None = None) -> pd.DataFrame:
    """Copy transactions, parse dates once, and reject invalid nonempty dates."""
    if not isinstance(transactions, pd.DataFrame):
        raise TypeError("transactions must be a pandas DataFrame")
    missing = {"customer_id", "purchase_date"} - set(transactions.columns)
    if missing:
        raise ValueError(f"transactions missing required columns: {sorted(missing)}")

    prepared = transactions.copy()
    prepared["_purchase_date"] = pd.to_datetime(
        prepared["purchase_date"], errors="coerce", utc=True
    ).dt.tz_convert(None)
    if len(prepared) and prepared["_purchase_date"].isna().any():
        bad_count = int(prepared["_purchase_date"].isna().sum())
        raise ValueError(f"transactions contain {bad_count} invalid purchase_date values")
    prepared = prepared.loc[prepared["customer_id"].notna()]
    if upper_bound is not None:
        prepared = prepared.loc[prepared["_purchase_date"] <= upper_bound]
    return prepared


def _customer_ids(customers: pd.DataFrame | None,
                  transactions: pd.DataFrame) -> pd.DataFrame:
    if customers is None:
        return transactions[["customer_id"]].drop_duplicates().reset_index(drop=True)
    if not isinstance(customers, pd.DataFrame) or "customer_id" not in customers:
        raise ValueError("customers must contain a customer_id column")
    return customers[["customer_id"]].dropna().drop_duplicates().reset_index(drop=True)


def _empty_result(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def compute_recency_features(transactions, snapshot_date, customers=None):
    """Compute recency and tenure; rostered customers without history get safe defaults."""
    cutoff = _timestamp(snapshot_date)
    history = _prepare_transactions(transactions, upper_bound=cutoff)
    if history.empty:
        result = _customer_ids(customers, history)
        result["days_since_last_purchase"] = NO_PURCHASE_SENTINEL_DAYS
        result["customer_tenure_days"] = 0
        return result

    bounds = history.groupby("customer_id", as_index=False, sort=False).agg(
        last_purchase=("_purchase_date", "max"),
        first_purchase=("_purchase_date", "min"),
    )
    bounds["days_since_last_purchase"] = (
        cutoff.normalize() - bounds["last_purchase"].dt.normalize()
    ).dt.days
    bounds["customer_tenure_days"] = (
        cutoff.normalize() - bounds["first_purchase"].dt.normalize()
    ).dt.days
    bounds = bounds[["customer_id", "days_since_last_purchase", "customer_tenure_days"]]

    result = _customer_ids(customers, history).merge(bounds, on="customer_id", how="left")
    result["days_since_last_purchase"] = (
        result["days_since_last_purchase"].fillna(NO_PURCHASE_SENTINEL_DAYS).astype("int64")
    )
    result["customer_tenure_days"] = result["customer_tenure_days"].fillna(0).astype("int64")
    return result


def compute_frequency_features(transactions, snapshot_date):
    """Count orders in open trailing windows: (T-N days, T]."""
    cutoff = _timestamp(snapshot_date)
    history = _prepare_transactions(transactions, upper_bound=cutoff)
    result = _customer_ids(None, history)
    for days in (30, 90, 180):
        name = f"purchase_frequency_{days}d"
        counts = history.loc[
            history["_purchase_date"] > cutoff - pd.Timedelta(days=days)
        ].groupby("customer_id", sort=False).size()
        result[name] = result["customer_id"].map(counts).fillna(0).astype("int64")
    return result


def compute_monetary_features(transactions, snapshot_date):
    """Compute order-value totals and item-per-order basket size from history."""
    cutoff = _timestamp(snapshot_date)
    history = _prepare_transactions(transactions, upper_bound=cutoff)
    needed = {"order_value", "num_items"} - set(history.columns)
    if needed:
        raise ValueError(f"transactions missing monetary columns: {sorted(needed)}")
    if history.empty:
        return _empty_result([
            "customer_id", "avg_order_value", "total_spend_90d",
            "total_lifetime_value", "avg_basket_size_6m",
        ])

    history["_order_value"] = pd.to_numeric(history["order_value"], errors="coerce").fillna(0.0)
    history["_num_items"] = pd.to_numeric(history["num_items"], errors="coerce").fillna(0.0)
    grouped = history.groupby("customer_id", sort=False)
    result = grouped.agg(
        avg_order_value=("_order_value", "mean"),
        total_lifetime_value=("_order_value", "sum"),
    ).reset_index()

    recent_90 = history.loc[
        history["_purchase_date"] > cutoff - pd.Timedelta(days=90)
    ]
    spend_90 = recent_90.groupby("customer_id", sort=False)["_order_value"].sum()
    result["total_spend_90d"] = result["customer_id"].map(spend_90).fillna(0.0)

    recent_180 = history.loc[
        history["_purchase_date"] > cutoff - pd.Timedelta(days=180)
    ]
    items_180 = recent_180.groupby("customer_id", sort=False)["_num_items"].sum()
    orders_180 = recent_180.groupby("customer_id", sort=False).size()
    result["avg_basket_size_6m"] = (
        result["customer_id"].map(items_180).fillna(0.0)
        / result["customer_id"].map(orders_180).replace(0, np.nan).fillna(1.0)
    )
    return result[[
        "customer_id", "avg_order_value", "total_spend_90d",
        "total_lifetime_value", "avg_basket_size_6m",
    ]]


def compute_behavioral_features(transactions):
    """Compute category breadth and the fraction of orders placed online."""
    if not isinstance(transactions, pd.DataFrame):
        raise TypeError("transactions must be a pandas DataFrame")
    missing = {"customer_id", "product_category", "channel"} - set(transactions.columns)
    if missing:
        raise ValueError(f"transactions missing behavioral columns: {sorted(missing)}")
    if transactions.empty:
        return _empty_result([
            "customer_id", "category_diversity_score", "online_to_store_ratio",
        ])

    rows = []
    for customer_id, group in transactions.loc[transactions["customer_id"].notna()].groupby(
        "customer_id", sort=False
    ):
        categories = group["product_category"].dropna().astype("string").str.strip()
        categories = categories.loc[
            categories.ne("") & categories.str.lower().ne("unknown")
        ]
        diversity = min(float(categories.nunique()) / CATEGORY_COUNT, 1.0)
        channels = group["channel"].astype("string").str.lower()
        online_share = float(channels.eq("online").mean()) if len(group) else 0.0
        rows.append({
            "customer_id": customer_id,
            "category_diversity_score": diversity,
            "online_to_store_ratio": online_share,
        })
    return pd.DataFrame(rows, columns=[
        "customer_id", "category_diversity_score", "online_to_store_ratio",
    ])


def split_windows(transactions: pd.DataFrame,
                  feature_cutoff=FEATURE_CUTOFF,
                  snapshot=SNAPSHOT) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split processed transactions into feature history and label holdout."""
    cutoff = _timestamp(feature_cutoff)
    snapshot_end = _timestamp(snapshot)
    prepared = _prepare_transactions(transactions)
    history_mask = prepared["_purchase_date"] <= cutoff
    holdout_mask = (
        (prepared["_purchase_date"] > cutoff)
        & (prepared["_purchase_date"] <= snapshot_end)
    )
    original_columns = list(transactions.columns)
    return (
        prepared.loc[history_mask, original_columns].copy(),
        prepared.loc[holdout_mask, original_columns].copy(),
    )


def _loyalty_tiers(lifetime_value: pd.Series) -> pd.Series:
    return pd.Series(
        np.select(
            [lifetime_value < 500, lifetime_value < 2000, lifetime_value < 5000],
            ["Bronze", "Silver", "Gold"],
            default="Platinum",
        ),
        index=lifetime_value.index,
        dtype="object",
    )


def _risk_score(days_since_last_purchase: pd.Series,
                purchase_frequency_30d: pd.Series) -> pd.Series:
    days = pd.to_numeric(days_since_last_purchase, errors="coerce").fillna(
        NO_PURCHASE_SENTINEL_DAYS
    )
    frequency = pd.to_numeric(purchase_frequency_30d, errors="coerce").fillna(0)
    high = 0.7 + 0.3 * ((days - 60) / 120).clip(upper=1.0)
    medium = 0.4 + 0.3 * (days - 30) / 30
    low = 0.4 * days / 30
    score = np.where(
        (days > 60) & (frequency == 0), high,
        np.where(days > 30, medium, low),
    )
    return pd.Series(score, index=days.index).clip(lower=0.0, upper=1.0)


def build_churn_feature_set(customers, transactions, snapshot_date=SNAPSHOT):
    """Build one complete, null-free customer feature row from processed orders.

    ``snapshot_date`` is the feature cutoff (T). Orders in the subsequent
    holdout window can change only ``churn_label``; they are excluded from all
    features to prevent temporal leakage.
    """
    cutoff = _timestamp(snapshot_date)
    all_transactions = _prepare_transactions(transactions)
    if customers is None:
        customer_table = _customer_ids(None, all_transactions)
    elif not isinstance(customers, pd.DataFrame) or "customer_id" not in customers:
        raise ValueError("customers must contain a customer_id column")
    else:
        customer_table = customers.dropna(subset=["customer_id"]).drop_duplicates(
            "customer_id", keep="last"
        ).reset_index(drop=True)

    roster = customer_table[["customer_id"]].drop_duplicates().reset_index(drop=True)
    history = all_transactions.loc[all_transactions["_purchase_date"] <= cutoff]
    holdout = all_transactions.loc[
        (all_transactions["_purchase_date"] > cutoff)
        & (all_transactions["_purchase_date"] <= SNAPSHOT)
    ]

    recency = compute_recency_features(history, cutoff, roster)
    frequency = compute_frequency_features(history, cutoff)
    monetary = compute_monetary_features(history, cutoff)
    behavior = compute_behavioral_features(history)

    features = roster
    for part in (recency, frequency, monetary, behavior):
        features = features.merge(part, on="customer_id", how="left", validate="one_to_one")

    numeric_defaults = {
        "days_since_last_purchase": NO_PURCHASE_SENTINEL_DAYS,
        "customer_tenure_days": 0,
        "purchase_frequency_30d": 0,
        "purchase_frequency_90d": 0,
        "purchase_frequency_180d": 0,
        "avg_order_value": 0.0,
        "total_spend_90d": 0.0,
        "total_lifetime_value": 0.0,
        "avg_basket_size_6m": 0.0,
        "category_diversity_score": 0.0,
        "online_to_store_ratio": 0.0,
    }
    for name, default in numeric_defaults.items():
        features[name] = pd.to_numeric(features[name], errors="coerce").fillna(default)

    if "loyalty_tier" in customer_table:
        tier_by_customer = customer_table[["customer_id", "loyalty_tier"]]
        features = features.merge(
            tier_by_customer, on="customer_id", how="left", validate="one_to_one"
        )
        features["loyalty_tier"] = features["loyalty_tier"].where(
            features["loyalty_tier"].notna(), _loyalty_tiers(features["total_lifetime_value"])
        )
    else:
        features["loyalty_tier"] = _loyalty_tiers(features["total_lifetime_value"])

    bought_again = set(holdout["customer_id"].dropna().unique())
    derived_labels = (~features["customer_id"].isin(bought_again)).astype("int64")
    if "churn_label" in customer_table:
        labels = customer_table[["customer_id", "churn_label"]]
        features = features.merge(labels, on="customer_id", how="left", validate="one_to_one")
        provided_labels = pd.to_numeric(features["churn_label"], errors="coerce")
        features["churn_label"] = provided_labels.fillna(derived_labels).astype("int64")
    else:
        features["churn_label"] = derived_labels

    features["churn_risk_score"] = _risk_score(
        features["days_since_last_purchase"], features["purchase_frequency_30d"]
    )
    for name in FEATURE_COLUMNS:
        features[name] = features[name].round(4)
    features["churn_risk_score"] = features["churn_risk_score"].round(4)

    ordered_columns = [
        "customer_id", *FEATURE_COLUMNS, "loyalty_tier", "churn_risk_score", "churn_label",
    ]
    return features[ordered_columns]
