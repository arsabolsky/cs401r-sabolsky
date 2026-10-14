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
