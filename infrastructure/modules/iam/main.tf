# ── modules/iam ──────────────────────────────────────────────────────────────
# Required resources (Task B1). Exactly one of each:
#
#   aws_iam_role                     MLEngineer, trusted by sagemaker.amazonaws.com
#   aws_iam_policy
#   aws_iam_role_policy_attachment
#
# Least privilege is graded in later labs, so start narrow: grant only the S3
# prefixes and SageMaker actions this role actually needs. A wildcard policy
# here will cost you points in Lab 2.

# STEP 1 — aws_iam_role
# Docs: .../resources/iam_role
# Required arguments: name, assume_role_policy
# name: build from var.project + var.environment, e.g. "...-MLEngineer"
# assume_role_policy is a JSON STRING (IAM trust policy), not a native HCL
# block. Build it with jsonencode(...) rather than typing raw JSON text —
# it keeps `terraform fmt` happy and Terraform validates the structure:
#
#   assume_role_policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [{
#       Effect    = "Allow"
#       Principal = { Service = "sagemaker.amazonaws.com" }
#       Action    = "sts:AssumeRole"
#     }]
#   })
#
# This is exactly the trust policy you already verified via the console in
# Task A3 — same shape, just HCL instead of the JSON you pasted there.
resource "aws_iam_role" "ml_engineer" {
  name = "${var.project}-${var.environment}-MLEngineer"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sagemaker.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# STEP 2 — aws_iam_policy
# Docs: .../resources/iam_policy
# Required: name, policy (again a JSON string — use jsonencode())
# The policy document is the SAME six-statement policy
# (NorthStarMLEngineerPolicy) you wrote for Task A3. Go pull it from your own
# notes/history rather than re-deriving it — the Sids, actions, and resource
# ARN patterns (including the raw/ vs artifacts+features/ prefix split) do
# not change between the console version and this one.
# name: also build from var.project + var.environment so the rubric grep
# on modules/ stays clean — do not hardcode "NorthStarMLEngineerPolicy"
# literally if that string would collide with the no-hardcoded-names rule;
# check the rubric wording (it greps for the literal project-env name, not policy names,
# so this specific string is fine to hardcode, but the project/env-based
# parts of ARNs and role names are not).
resource "aws_iam_policy" "this" {
  name = "NorthStarMLEngineerPolicy"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "SageMakerCore",
        "Effect" : "Allow",
        "Action" : [
          "sagemaker:CreateTrainingJob", "sagemaker:DescribeTrainingJob", "sagemaker:StopTrainingJob",
          "sagemaker:CreateEndpoint", "sagemaker:DescribeEndpoint", "sagemaker:DeleteEndpoint",
          "sagemaker:CreateEndpointConfig", "sagemaker:DeleteEndpointConfig",
          "sagemaker:CreateMlflowApp", "sagemaker:DescribeMlflowApp", "sagemaker:ListMlflowApps",
          "sagemaker:CreatePresignedMlflowAppUrl",
          "sagemaker:RegisterModel", "sagemaker:DescribeModelPackage", "sagemaker:ListModelPackages"
        ],
        "Resource" : "*"
      },
      {
        "Sid" : "StudioSelfService",
        "Effect" : "Allow",
        "Action" : [
          "sagemaker:DescribeDomain", "sagemaker:ListDomains",
          "sagemaker:DescribeUserProfile", "sagemaker:ListUserProfiles",
          "sagemaker:DescribeSpace", "sagemaker:ListSpaces", "sagemaker:CreateSpace",
          "sagemaker:UpdateSpace", "sagemaker:DeleteSpace",
          "sagemaker:DescribeApp", "sagemaker:ListApps", "sagemaker:CreateApp", "sagemaker:DeleteApp",
          "sagemaker:CreatePresignedDomainUrl"
        ],
        "Resource" : [
          "arn:aws:sagemaker:*:*:domain/*", "arn:aws:sagemaker:*:*:user-profile/*",
          "arn:aws:sagemaker:*:*:space/*", "arn:aws:sagemaker:*:*:app/*"
        ]
      },
      {
        "Sid" : "S3ArtifactsAndFeatures",
        "Effect" : "Allow",
        "Action" : ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        "Resource" : [
          "arn:aws:s3:::northstar-dev-data-*/artifacts/*",
          "arn:aws:s3:::northstar-dev-data-*/features/*"
        ]
      },
      {
        "Sid" : "S3BucketList",
        "Effect" : "Allow",
        "Action" : ["s3:ListBucket", "s3:GetBucketLocation"],
        "Resource" : "arn:aws:s3:::northstar-dev-data-*"
      },
      {
        "Sid" : "CloudWatchLogs",
        "Effect" : "Allow",
        "Action" : ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource" : "arn:aws:logs:*:*:log-group:/aws/sagemaker/*"
      },
      {
        "Sid" : "ECRRead",
        "Effect" : "Allow",
        "Action" : ["ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "ecr:GetAuthorizationToken"],
        "Resource" : "*"
      }
    ]
  })
}

# STEP 3 — aws_iam_role_policy_attachment
# Docs: .../resources/iam_role_policy_attachment
# Required: role = aws_iam_role.this.name , policy_arn = aws_iam_policy.this.arn
# This is the resource that actually connects Steps 1 and 2 — a role and a
# policy sitting unattached in the same file grant nothing.
resource "aws_iam_role_policy_attachment" "this" {
  role       = aws_iam_role.ml_engineer.name
  policy_arn = aws_iam_policy.this.arn
}
# TODO: implement the three resources above.
