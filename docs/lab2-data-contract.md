## Data Contract: processed/customers

Location: `s3://northstar-dev-data-<account-id>/processed/customers/` (Parquet, snappy).
Catalog: produced from the crawler-registered table `northstar_dev.customers`, whose data
lives in `raw/customers/` (CSV).

### Producer
Team / process: Glue ETL job `northstar-dev-transform` (Glue 4.0, script
`glue-scripts/transform.py`), running as IAM role `northstar-dev-DataEngineer` inside the
private subnet `northstar-dev-private-1` via the `northstar-dev-vpc-connection` NETWORK
connection.

### Consumers
- Feature engineering job `northstar-dev-feature-engineer` (aggregates this dataset to one
  row per customer for `features/customers/` and the `northstar-dev-customer-features`
  Feature Group)
- (Future) Direct model training in Lab 3

### Grain
One row per transaction. `transaction_id` is unique. A customer appears on many rows; that
purchase history is what the feature engineering job aggregates over, so the producer never
deduplicates or aggregates on `customer_id`.

### Schema
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `transaction_id` | string | No | Natural key, `TXN-` + 12 uppercase alphanumerics. Unique per row. |
| `customer_id` | string | No | `CUST-` + 8 digits, whitespace-trimmed. Join key for every downstream feature. |
| `purchase_date` | date | No | Calendar date of the purchase. Parsed from ISO 8601 (`yyyy-MM-dd`) or `MM/dd/yyyy` in raw. |
| `order_value` | double | No | Gross order value in USD. Raw nulls imputed with the column median. |
| `num_items` | int | No | Line items in the order. Raw nulls imputed with the rounded median. |
| `payment_method` | string | No | One of `credit_card`, `debit_card`, `gift_card`, `cash`, or `unknown` if missing in raw. |
| `channel` | string | No | `online` or `store`, or `unknown` if missing in raw. |
| `store_id` | string | No | `STORE-` + 3 digits for store orders, `ONLINE` for online orders, or `unknown`. |
| `product_category` | string | No | Primary category: `Apparel`, `Beauty`, `Electronics`, `Footwear`, `Grocery`, `Home`, `Outdoor`, `Toys`, or `unknown` (imputed for the ~2% missing in raw). |

### Quality Guarantees
Each guarantee is checked on every run; the first three are enforced by assertions in
`transform.py` (the job fails rather than publishing), and all are re-checked by
`scripts/verify-lab2.sh`.

- `customer_id` is never null and has no leading or trailing whitespace (0 null rows).
- No duplicate `transaction_id` rows: `count(distinct transaction_id) == count(*)`. A
  `customer_id` repeating across rows is expected, not a defect.
- `purchase_date` is a valid date (0 nulls after parsing) within 2025-04-01 to 2026-06-30
  inclusive.
- `order_value` is between 15.00 and 620.00 USD inclusive (the observed range of the
  source); a value outside it is a producer bug and blocks publication.
- `num_items` is an integer between 1 and 9 inclusive.
- `channel` is in {`online`, `store`, `unknown`}; `payment_method` is in {`credit_card`,
  `debit_card`, `gift_card`, `cash`, `unknown`}.
- Grain is transaction-level: `count(*) > count(distinct customer_id)` (about 157,600 rows
  over about 10,000 customers for the current sample).
- Completeness: at least 95% of raw rows survive cleaning. Only rows with a missing
  `customer_id` (about 2.0% of raw) or a duplicate `transaction_id` (about 1.5%) are
  removed.

### SLA
- Data is available in `processed/customers/` within 2 hours of landing in `raw/customers/`
  (crawler run plus one transform job run; a typical run completes in under 10 minutes).
- Each run replaces the whole prefix (Spark overwrite mode). Consumers start only after
  the latest `northstar-dev-transform` run reports `SUCCEEDED`; a failed run is not a
  valid snapshot and must be re-run.

### Versioning
- Schema changes require a new S3 prefix (e.g., `processed/customers/v2/`); the current
  prefix keeps its schema until consumers migrate.
- Breaking changes require consumer notification 5 business days in advance. Breaking
  means removing, renaming, or retyping a column, changing the grain, or tightening a
  column from nullable to non-nullable in a way that changes values.
- Non-breaking changes (adding a new nullable column, widening an allowed value set) may
  ship in place with notice in the change log.
- Noncurrent object versions in `processed/` are retained for 30 days by the
  `expire-processed-versions` lifecycle rule, so a bad run can be rolled back within that
  window.
