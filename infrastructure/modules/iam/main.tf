# modules/iam - platform IAM roles. Each role = aws_iam_role (trust)
# + aws_iam_policy (permissions) + aws_iam_role_policy_attachment.
# Least privilege: grant only the prefixes and actions each role needs.

# Account ID and region, for building ARNs without hardcoding them.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# MLEngineer - assumed by SageMaker Studio.
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

# Same six statements as the Lab 1 console policy. S3 access is limited to
# artifacts/ and features/ - no write on raw/.
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

resource "aws_iam_role_policy_attachment" "this" {
  role       = aws_iam_role.ml_engineer.name
  policy_arn = aws_iam_policy.this.arn
}

# DataEngineer - runs the Glue pipeline (trusted by Glue, Lambda, SageMaker).
# Writes raw/, processed/, features/ and Feature Store; read-only on artifacts/glue/.
resource "aws_iam_role" "data_engineer" {
  name = "${var.project}-${var.environment}-DataEngineer"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = ["sagemaker.amazonaws.com", "glue.amazonaws.com", "lambda.amazonaws.com"] }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "data_engineer_policy" {
  name = "${var.project}-${var.environment}-DataEngineerPolicy"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "GlueAccess",
        "Effect" : "Allow",
        "Action" : "glue:*",
        "Resource" : "*"
      },
      {
        "Sid" : "EniLifecycle",
        "Effect" : "Allow",
        "Action" : ["ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeVpcs", "ec2:DescribeVpcAttribute", "ec2:DescribeVpcEndpoints", "ec2:DescribeRouteTables"],
        "Resource" : "*"
      },
      {
        "Sid" : "EniTags",
        "Effect" : "Allow",
        "Action" : ["ec2:CreateTags", "ec2:DeleteTags"],
        "Resource" : "arn:aws:ec2:*:*:network-interface/*"
      },
      {
        "Sid" : "PipelineData",
        "Effect" : "Allow",
        "Action" : ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        "Resource" : ["${var.bucket_arn}/raw/*", "${var.bucket_arn}/processed/*", "${var.bucket_arn}/features/*"]
      },
      {
        "Sid" : "BucketLevel",
        "Effect" : "Allow",
        "Action" : ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketAcl"]
        "Resource" : var.bucket_arn
      },
      {
        "Sid" : "OfflineStoreAcl",
        "Effect" : "Allow",
        "Action" : "s3:PutObjectAcl",
        "Resource" : "${var.bucket_arn}/features/*"
      },
      {
        "Sid" : "GlueScripts",
        "Effect" : "Allow",
        "Action" : "s3:GetObject",
        "Resource" : "${var.bucket_arn}/artifacts/glue/*"
      },
      {
        "Sid" : "FeatureStore",
        "Effect" : "Allow",
        "Action" : ["sagemaker:CreateFeatureGroup", "sagemaker:DescribeFeatureGroup", "sagemaker:PutRecord"],
        "Resource" : "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:feature-group/*"
      },
      {
        "Sid" : "Logs",
        "Effect" : "Allow",
        "Action" : ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource" : "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "data_engineer" {
  role       = aws_iam_role.data_engineer.name
  policy_arn = aws_iam_policy.data_engineer_policy.arn
}

# ModelMonitor - observes drift runs and writes CloudWatch metrics. Read-only
# on artifacts/; no S3 writes, no endpoint invocation, cannot start jobs.
resource "aws_iam_role" "model_monitor" {
  name = "${var.project}-${var.environment}-ModelMonitor"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sagemaker.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "model_monitor_policy" {
  name = "${var.project}-${var.environment}-ModelMonitorPolicy"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "CloudWatchMetrics",
        "Effect" : "Allow",
        "Action" : ["cloudwatch:PutMetricData", "cloudwatch:GetMetricStatistics", "cloudwatch:PutMetricAlarm", "cloudwatch:DescribeAlarms"],
        "Resource" : "*"
      },
      {
        "Sid" : "ProcessingJobsRead",
        "Effect" : "Allow",
        "Action" : ["sagemaker:ListProcessingJobs", "sagemaker:DescribeProcessingJob"],
        "Resource" : "*"
      },
      {
        "Sid" : "ArtifactsRead",
        "Effect" : "Allow",
        "Action" : "s3:GetObject",
        "Resource" : "${var.bucket_arn}/artifacts/*"
      },
      {
        "Sid" : "Logs",
        "Effect" : "Allow",
        "Action" : ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource" : "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "model_monitor" {
  role       = aws_iam_role.model_monitor.name
  policy_arn = aws_iam_policy.model_monitor_policy.arn
}
