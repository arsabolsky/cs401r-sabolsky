# Lab 1 — Monthly Cost Estimate

Steady-state estimate for the NorthStar Lab 1 platform, using AWS Pricing Calculator
figures for `us-east-1`. Assumes the discipline this lab requires — shutting down
Studio every session and destroying the stack between work sessions (B2) — rather
than a domain left running continuously.

| Component | Monthly Estimate | Key Assumptions | One Optimization |
|---|---|---|---|
| SageMaker Studio | $1.50 | `ml.t3.medium` at $0.05/hr, 1.5 hrs/day, 20 active days/month (30 hrs total) — matches the "shut down every session" requirement, not continuous uptime | Use the JupyterLab idle-shutdown setting (120 min default, observed on the deployed domain) as a backstop; it does not replace manual shutdown but caps runaway sessions at ~2 hrs of waste instead of a full day |
| S3 storage | $0.12 | 5 GB steady-state across `raw/`/`processed/`/`features/`/`artifacts/` at $0.023/GB — the data bucket currently holds 0 bytes (four empty prefix markers only, verified via `aws s3api list-objects-v2`), so this projects forward to Lab 2–3 volumes, not current usage | Apply a lifecycle rule transitioning `raw/` to S3 Standard-IA after 30 days; at 5 GB this saves roughly $0.03/month, small in isolation but the mechanism that matters once `raw/` volume grows toward the 24-month retention window |
| Internet Gateway | $0.05 | No hourly IGW charge; 5 GB/month egress (Studio container image pulls, package installs) at $0.01/GB | — |
| DynamoDB (state lock) | $0.01 | On-demand (`PAY_PER_REQUEST`) billing; ~20 `terraform` operations/month across this semester's labs, each acquiring/releasing one lock (~100 read+write request units total) — well under $1.25/million writes and $0.25/million reads, rounds to the smallest billable unit | — |
| S3 state bucket | $0.01 | Minimal storage — the actual `terraform.tfstate` object is 35,461 bytes today (verified via `aws s3api list-objects-v2 --bucket northstar-tfstate-573693339848`), effectively free at $0.023/GB; rounds to $0.01 as the smallest practical line item | — |
| **Total** | **$1.69** | | |

## The optimization actually worth quantifying

The single largest cost lever in this lab isn't in the table above, because it's not
a component — it's a practice: **destroying the domain between work sessions instead
of leaving it InService.** SageMaker Studio provisions an EFS filesystem for home
directories (`AutoMountHomeEFS: Enabled`) that is billed separately from Studio
compute, at EFS Standard's $0.30/GB-month, and it persists independent of whether any
JupyterLab app is running. A ~0.5 GB home directory (realistic for this lab's scope —
no large datasets belong in a Studio home directory per the module's own comments)
left running continuously would add **$0.15/month**, on top of whatever compute time
accrues.

Against a $1.69/month baseline, $0.15/month is a 9% addition for a resource this lab's
own `retention_policy { home_efs_file_system = "Delete" }` setting exists specifically
to avoid. Scaled across all seven labs and a full semester of iteration rather than one
clean build/destroy cycle, an always-on EFS filesystem is the difference between
staying comfortably inside the $200 credit budget and eroding it on storage nobody is
actively using — the exact failure mode `aws-account-setup.md`'s cost-control section
warns about.
