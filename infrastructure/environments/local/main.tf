# environments/local - same modules as dev, against LocalStack (make local-validate).
# Only vpc, storage, iam: LocalStack here runs S3, IAM, EC2, STS - no SageMaker or Glue.

module "vpc" {
  source             = "../../modules/vpc"
  project            = var.project
  environment        = var.environment
  enable_nat_gateway = false
}

module "storage" {
  source                 = "../../modules/storage"
  project                = var.project
  environment            = var.environment
  enable_lifecycle_rules = false
}

module "iam" {
  source      = "../../modules/iam"
  project     = var.project
  environment = var.environment
  bucket_arn  = module.storage.bucket_arn
}

