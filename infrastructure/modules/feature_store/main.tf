# The 16 feature definitions: 2 keys, 13 features, 1 label. Names must match the
# columns feature_engineer.py writes. Types are "String", "Fractional", or "Integral";
# event_time must be Fractional because the job sends epoch seconds.
locals {
  feature_definitions = {
    # keys
    customer_id = "String"
    event_time  = "Fractional"
    # features (computed as of FEATURE_CUTOFF)
    days_since_last_purchase = "Fractional"
    customer_tenure_days     = "Fractional"
    purchase_frequency_30d   = "Fractional"
    purchase_frequency_90d   = "Fractional"
    purchase_frequency_180d  = "Fractional"
    avg_order_value          = "Fractional"
    total_spend_90d          = "Fractional"
    total_lifetime_value     = "Fractional"
    avg_basket_size_6m       = "Fractional"
    category_diversity_score = "Fractional"
    online_to_store_ratio    = "Fractional"
    loyalty_tier             = "String"
    churn_risk_score         = "Fractional"
    # label (from the outcome window)
    churn_label = "Integral"
  }
}

resource "aws_sage_maker_feature_group" "feature_group" {
  name                           = "${var.project}-${var.environment}-customer-features"
  record_identifier_feature_name = "customer_id"
  event_time_feature_name        = "event_time"
  role_arn                       = var.role_arn
  online_store_config {
    enable_online_store = true
  }
  offline_store_config {
    s3_storage_config {
      s3_uri = "s3://${var.s3_bucket_name}/features/offline-store/"
    }
  }
  # One feature_definition block per entry in local.feature_definitions.
  dynamic "feature_definition" {
    for_each = local.feature_definitions
    content {
      feature_name = feature_definition.key
      feature_type = feature_definition.value
    }
  }
}
