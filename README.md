# NorthStar Retail AI Platform — CS 401R

Course repository for the NorthStar platform. Each lab extends the same Terraform
codebase under `infrastructure/`; graded evidence lives in `docs/`.

## Lab 1 — Platform Foundation

Lab 1 stands up the base of the platform: a VPC, the data bucket, the first IAM role,
and a SageMaker Studio domain. It was built twice, first by hand in the console (Part A)
and then as Terraform (Part B), so the two can be compared.

### What Lab 1 builds

- **Network.** VPC `northstar-dev-vpc` (10.0.0.0/16) with one public subnet
  `northstar-dev-public-1` (10.0.100.0/24, us-east-1a), an Internet Gateway, a public
  route table, and the `northstar-dev-sagemaker-sg` security group.
- **Storage.** Bucket `northstar-dev-data-<account-id>` with versioning, SSE-S3
  encryption, all public access blocked, and four prefixes: `raw/`, `processed/`,
  `features/`, `artifacts/`.
- **Identity.** Role `northstar-dev-MLEngineer`, trusted by SageMaker. It can read and
  write `features/` and `artifacts/`, run SageMaker training and Studio, and pull ECR
  images; it is denied writes to `raw/` by omission.
- **ML environment.** SageMaker domain `northstar-dev-domain` (IAM auth, notebook output
  sharing disabled) with user profile `MLEngineer`.

### Part A — manual (console)

Each resource was created in the AWS console, captured in a screenshot under
`docs/lab1a-*.png`, then torn down before Part B.

### Part B — Terraform

| Module | Resources |
|---|---|
| `vpc` | VPC, public subnet, Internet Gateway, route table + association, security group |
| `storage` | Data bucket, versioning, encryption, public-access block, the four prefixes |
| `iam` | MLEngineer role, its policy, and the attachment |
| `sagemaker` | Studio domain (EFS deleted with the domain) and the MLEngineer user profile |

- **Remote state.** `scripts/bootstrap-state.sh` creates the state bucket
  `northstar-tfstate-<account-id>` and the `northstar-tfstate-lock` DynamoDB table once;
  `environments/dev/backend.tf` points Terraform at them. Safe to re-run.
- **Parameterized.** Every name comes from `var.project` and `var.environment`; nothing in
  `modules/` hardcodes one.
- **LocalStack.** `make local-validate` applies vpc, storage and iam to a local emulator
  before anything touches AWS.

```bash
bash scripts/bootstrap-state.sh            # once
cd infrastructure/environments/dev
terraform init && terraform apply
cd ../../.. && bash scripts/verify-lab1.sh # while the stack is up
```

### Lab 1 evidence

| File | Contents |
|---|---|
| `docs/lab1-architecture-diagram.png` / `.drawio` | Architecture diagram |
| `docs/lab1a-*.png` | Part A console screenshots (VPC, subnet, IGW, route table, IAM role, S3, domain) |
| `docs/lab1-studio-shutdown.png` | Studio with no running instances |
| `docs/lab1b-apply-output.txt` | Part B `terraform apply` |
| `docs/lab1b-*.png` | Part B screenshots (domain, S3, subnet, IAM role) |
| `docs/lab1b-localstack-output.txt` | LocalStack validation |
| `docs/lab1-verify-output.txt` | `verify-lab1.sh` output |
| `docs/lab1-adr.md` | ADR-001: platform foundation decisions |
| `docs/lab1-cost-estimate.md` | Monthly cost estimate with assumptions |

Lab 2 later moves Studio into a private subnet and tightens the security group; see below.

## Lab 2 — Data & Feature Engineering

Lab 2 hardens the Lab 1 platform and adds a data pipeline that turns raw transaction
CSVs into labeled customer features in SageMaker Feature Store.

### What Lab 2 adds

- **Private networking.** A private subnet `northstar-dev-private-1` (10.0.1.0/24) behind a
  NAT Gateway in the public subnet. SageMaker Studio moves there with `VpcOnly` access,
  and Glue workers run there through a NETWORK connection.
- **Security group fix.** The SageMaker security group now lives in the VPC, accepts
  inbound traffic only from the VPC CIDR, and has the self-referencing rule Glue requires.
- **Two new IAM roles.** `northstar-dev-DataEngineer` runs the pipeline and writes `raw/`,
  `processed/`, `features/` and Feature Store, with read-only access to its job scripts
  under `artifacts/glue/`. `northstar-dev-ModelMonitor` reads `artifacts/` and writes
  CloudWatch metrics only.
- **S3 lifecycle rules.** Raw data expires after 90 days, noncurrent versions after 30–60
  days, and `datacapture/` after 7 days.
- **Glue pipeline.** A crawler registers `raw/customers/` as `northstar_dev.customers`; the
  `transform` job cleans it into Parquet in `processed/customers/`; the
  `feature-engineer` job builds one labeled row per customer.
- **Feature Store.** Feature Group `northstar-dev-customer-features` (16 features, online
  and offline store).

### Modules

| Module | Resources |
|---|---|
| `vpc` | VPC, public + private subnets, IGW, EIP + NAT Gateway, public + private route tables, security group |
| `storage` | Data bucket with versioning, encryption, public-access block, prefixes, lifecycle rules |
| `iam` | MLEngineer, DataEngineer, ModelMonitor roles with their policies |
| `sagemaker` | Studio domain (private subnet, VpcOnly) and the MLEngineer user profile |
| `glue` | Catalog database, raw crawler, VPC connection, job scripts, transform and feature-engineer jobs |
| `feature_store` | The customer Feature Group |

`environments/dev` wires all six together against AWS. `environments/local` runs `vpc`,
`storage` and `iam` against LocalStack, with the NAT Gateway and lifecycle rules switched
off.

### Prerequisites

- Terraform >= 1.5, AWS CLI, Docker (for LocalStack), Python 3 with `pandas` and
  `pyarrow` (for the verify script's data-quality checks).
- AWS credentials for the lab account, region `us-east-1`:
  `export AWS_PROFILE=northstar AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1`
- Remote state bootstrapped once with `bash scripts/bootstrap-state.sh`.

### Validate locally (free)

```bash
terraform fmt -check -recursive infrastructure
terraform -chdir=infrastructure/environments/dev init -backend=false && terraform -chdir=infrastructure/environments/dev validate
make local-validate LOCAL_OUT=docs/lab2-localstack-output.txt
make local-clean
```

### Run the pipeline end to end

From `infrastructure/environments/dev`:

```bash
terraform init
terraform apply
BUCKET=$(terraform output -raw s3_bucket_name)
```

From the repository root:

```bash
# 1. Land the raw data
aws s3 cp northstar-raw-sample.csv s3://$BUCKET/raw/customers/northstar-raw-sample.csv

# 2. Crawl raw/ into the Glue catalog (wait for READY)
aws glue start-crawler --name northstar-dev-raw-crawler
aws glue get-crawler --name northstar-dev-raw-crawler --query 'Crawler.State'

# 3. Clean raw CSV into processed/ Parquet (wait for SUCCEEDED)
aws glue start-job-run --job-name northstar-dev-transform
aws glue get-job-runs --job-name northstar-dev-transform --query 'JobRuns[0].JobRunState'

# 4. Build labeled features into features/ and the Feature Store (wait for SUCCEEDED)
aws glue start-job-run --job-name northstar-dev-feature-engineer
aws glue get-job-runs --job-name northstar-dev-feature-engineer --query 'JobRuns[0].JobRunState'

# 5. Read a record back from the online store
aws sagemaker-featurestore-runtime get-record \
  --feature-group-name northstar-dev-customer-features \
  --record-identifier-value-as-string CUST-10000776
```

Features are computed only from purchases on or before 2026-04-01; `churn_label` comes
only from the 90 days after it. Job logs are in CloudWatch under `/aws-glue/jobs/`.

### Verify and tear down

```bash
bash scripts/verify-lab2.sh 2>&1 | tee docs/lab2-verify-output.txt
bash scripts/teardown-lab2.sh
```

The NAT Gateway bills about $0.045 per hour while it exists. Tear down promptly with
`teardown-lab2.sh`; `terraform destroy` alone leaves Glue ENIs, the Studio EFS volume,
SageMaker NFS security groups and Feature Store leftovers behind.

### Lab 2 evidence

| File | Contents |
|---|---|
| `docs/lab2-extend-output.txt` | Every `terraform apply` in the lab, appended in order |
| `docs/lab2-localstack-output.txt` | LocalStack validation |
| `docs/lab2-verify-output.txt` | `verify-lab2.sh` output, run before teardown |
| `docs/lab2-data-contract.md` | Data contract for `processed/customers/` |
| `docs/lab2-data-lineage.png` | Data lineage diagram |
| `docs/lab2-destroy-output.txt` | Teardown evidence (on `main`, after the submit tag) |

## Lab 3 — Model development and Track B

Lab 3 trains the churn ranker from the Lab 2 Feature Store through Athena and demonstrates
policy-grounded retention offers with local FAISS retrieval. Use the personal AWS CLI profile
and `us-east-1` for every AWS operation; verify account `573693339848` before running the
training or evidence scripts. Never use the `default` work profile.

### Local Python setup

```bash
mkdir -p ~/.venvs
python3.12 -m venv ~/.venvs/cs401r-lab3
source ~/.venvs/cs401r-lab3/bin/activate
python -m pip install --upgrade pip
python -m pip install boto3 pandas xgboost matplotlib scikit-learn \
  ragas datasets 'langchain-community<0.4' langchain-aws faiss-cpu jupyter nbformat
```

### Athena-backed Task 1 training

Set the AWS environment for the personal account, check the returned account ID, then run
from the repository root. The MLflow ARN is read from the evidence export; the listed
hyperparameters match the recorded graded run.

```bash
export AWS_PROFILE=northstar AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
aws sts get-caller-identity --query Account --output text
MLFLOW_ARN="$(cat docs/lab3-evidence/mlflow-app-arn.txt)"
FEATURE_GROUP="$(terraform -chdir=infrastructure/environments/dev output -raw feature_group_name)"
BUCKET="$(terraform -chdir=infrastructure/environments/dev output -raw s3_bucket_name)"
python churn_training_skeleton.py \
  --feature-group-name "$FEATURE_GROUP" \
  --artifacts-bucket "$BUCKET" \
  --mlflow-arn "$MLFLOW_ARN" --run-name final \
  --max-depth 4 --eta 0.1 --num-round 200 --seed 42 \
  --early-stopping-rounds 20 --verbose-eval 25 \
  --min-child-weight 5 --subsample 0.8 --colsample-bytree 0.8 \
  --output-data-dir docs/lab3-evidence 2>&1 | tee docs/lab3-evidence/train-final.log
```

### Track B demo and evaluation

The demo notebook builds a local index, prints retrieved chunks, generates one offer, and
checks that its benefit and category have support. Run it with the same account verification
in the first notebook cell:

```bash
jupyter notebook notebooks/lab3-demo.ipynb
```

The personal account's Anthropic first-time-use form is submitted and the Haiku agreement is available.
Run the four-case RAGAS evaluation with explicit strategy and model IDs. Haiku is billed for
both generation and judging; the model IDs and case scores are recorded in the output CSV.

```bash
export AWS_PROFILE=northstar AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
aws sts get-caller-identity --query Account --output text
python evaluation_harness.py --track B --region us-east-1 \
  --retrieval-strategy C \
  --generation-model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --bedrock-model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --run-id haiku45-trackb-rerun \
  --output-dir docs/lab3-evidence
```

Each run writes a timestamped CSV and appends to `docs/lab3-evidence/rag_eval.csv`, replacing
rows with the same run ID and customer ID. Raw per-run logs, the metric summary, example
outputs, and failure analysis are under `docs/lab3-evidence/`.

### Export and validate evidence

Run the collector while the Lab 3 stack is still available, then resolve every reported FAIL.
The final secret scan must be clean before tagging the submission.

```bash
export AWS_PROFILE=northstar AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
aws sts get-caller-identity --query Account --output text
bash scripts/collect-lab3-evidence.sh --track B
bash scripts/check-secrets.sh
```
