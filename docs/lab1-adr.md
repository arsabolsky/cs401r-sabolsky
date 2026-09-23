## ADR-001: NorthStar Platform Foundation

### Status

Accepted

### Context

NorthStar Retail is building three AI systems on one shared platform: a weekly batch churn model scoring every active customer by Monday 6 AM ET, an LLM/RAG offer-generation system responding within 2 seconds, and an agentic customer-service system holding 99.5% availability during business hours. All three read the same customer, transaction, and product data, and all three share regulatory constraints — GDPR (Canada), CCPA (California), and a 24-month raw-data retention policy, with the offer system additionally subject to FCRA/ECOA non-discrimination rules on its credit-offer component.

Because the systems share data but have different owners, latency requirements, and regulatory exposure, a shared platform cannot treat "the AI team" as one identity with blanket access. The churn model's batch job has no legitimate reason to touch raw customer-service transcripts, and an engineer debugging offer generation has no legitimate reason to write to the `raw/` prefix data engineering owns. Lab 1 builds the foundation this depends on: a network boundary, a storage layout separated by processing stage, and an identity model that enforces who can do what before any of the three systems exist to test it against.

### Decision

This is the base layer all three systems — churn scoring, LLM/RAG offer generation, and the agentic customer-service system — share, so every choice below is scoped to what that three-system platform needs on day one, not general best practice.

The platform runs in a single VPC (`northstar-dev-vpc`, `10.0.0.0/16`) with one public subnet (`northstar-dev-public-1`, `10.0.100.0/24`) in `us-east-1a`. An Internet Gateway and a dedicated route table (`northstar-dev-public-rt`) give the subnet internet egress, and a security group scopes inbound traffic to the VPC's own CIDR — nothing reaches Studio directly from the internet, only from resources inside the boundary. This is intentionally minimal: Lab 1 has one workload, so private subnets and a NAT Gateway are deferred to Lab 2, when the DataEngineer and ModelMonitor roles give the platform actual reasons to separate network tiers.

Storage is one S3 bucket (`northstar-dev-data-<account-id>`) with four prefixes — `raw/`, `processed/`, `features/`, `artifacts/` — rather than four buckets, keeping versioning, encryption, and public-access-block configuration in one place instead of four, while the prefix boundary still gives IAM something concrete to scope against. This answers NorthStar's retention constraint directly: the 24-month policy applies to `raw/` specifically, and a future lifecycle rule can target that prefix without touching `features/` or `artifacts/`, which have different (or no) retention requirements.

Identity is one role in Lab 1 — `northstar-dev-MLEngineer`, trusted only by `sagemaker.amazonaws.com` — with an inline policy split into six statements rather than one blanket S3 grant. The object-action statement (`GetObject`/`PutObject`/`DeleteObject`) is scoped to `arn:aws:s3:::northstar-dev-data-*/artifacts/*` and `.../features/*` only; it deliberately excludes `raw/` and `processed/`, which belong to Lab 2's DataEngineer role. This was not theoretical: `s3:ListBucket` is granted separately on the bucket ARN because a bucket-level wildcard on the object-action statement would also match `raw/anything`, silently granting the write access this role is supposed to lack. `scripts/verify-lab1.sh` simulates `s3:PutObject` on `raw/` against the live role and asserts a deny — a tested property, not a documentation claim.

The ML development environment is a SageMaker AI Studio domain in IAM auth mode, with `PublicInternetOnly` network access rather than VPC-only. VPC-only would put Studio's ENI in the subnet with no route to the internet — no NAT Gateway exists in Lab 1 — so JupyterLab could not pull its container image. This also matches the AWS provider's own default, keeping the console-built and Terraform-built domains identical.

### Consequences

#### What this makes easy

Adding DataEngineer and ModelMonitor in Lab 2 needs no restructuring — the prefix split already exists, so those roles are additional statements against `raw/` and `processed/`, not a redesign. Verifying least privilege is one `iam simulate-principal-policy` call, since the policy's Sids map directly onto stated actions.

#### What this makes harder

A single bucket means a single blast radius for a bucket-level misconfiguration — a bucket policy error affects `artifacts/` and `raw/` simultaneously, where four separate buckets would contain that error to one prefix. Rebuilding the domain costs 8–12 minutes each time, and skipping `retention_policy { home_efs_file_system = "Delete" }` leaves an EFS filesystem that blocks subnet and VPC deletion for roughly ten minutes — observed directly during Part A's teardown, not anticipated in the abstract.

#### What would cause you to revisit this decision

Per-prefix encryption keys (PII in `raw/` under a dedicated KMS key, artifacts under a shared one) would break the single-bucket design, since SSE configuration is bucket-level, not prefix-level. If the offer system's 2-second latency requirement pushes Studio into VPC-only mode for compliance, a NAT Gateway becomes mandatory ahead of Lab 2's schedule.

### Alternative Considered

Four separate buckets — `northstar-dev-raw`, `-processed`, `-features`, `-artifacts` — instead of one with four prefixes. Each stage would get independent versioning, lifecycle, and encryption without a shared blast radius, and IAM ARNs would be simpler (`arn:...:bucket/*` instead of prefix patterns). Rejected because later labs depend on a single bucket name derived from `${project}-${environment}-data-${account_id}`, and four buckets means four sets of public-access-block and encryption config to keep in sync — more state to drift, not less.

### AWS Service Selection

- **Networking isolation model:** VPC with one public subnet — the churn/offer/agent workloads have no network-tier separation needs yet; a NAT Gateway is deferred until Lab 2 gives private compute a reason to exist.
- **Storage design:** one S3 bucket, four prefixes — matches the regulatory need to treat `raw/` (24-month retention) differently from derived data, without multiplying bucket-level configuration.
- **Identity model:** one IAM role with a six-statement least-privilege policy — the `raw/`-deny is the load-bearing property this lab tests, since it is the boundary between what the ML engineer owns and what the (future) data engineer owns.
- **ML development environment:** SageMaker AI Studio, public internet access — the standard environment for all three AI systems' development work, configured to match the Terraform provider's default so Part A and Part B build the same thing. AI SLOP ADR
