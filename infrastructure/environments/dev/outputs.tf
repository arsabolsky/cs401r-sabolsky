
# Read by the verify scripts and later labs via `terraform output -raw`.

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "public_subnet_id" {
  description = "ID of the public subnet"
  value       = module.vpc.public_subnet_id
}

output "s3_bucket_name" {
  description = "Name of the data bucket"
  value       = module.storage.bucket_name
}

output "ml_engineer_role_arn" {
  description = "ARN of the MLEngineer role"
  value       = module.iam.ml_engineer_role_arn
}

output "sagemaker_domain_id" {
  description = "ID of the SageMaker Domain"
  value       = module.sagemaker.domain_id
}

output "private_subnet_id" {
  description = "ID of the private subnet"
  value       = module.vpc.private_subnet_id
}

output "data_engineer_role_arn" {
  description = "ARN of the DataEngineer role"
  value       = module.iam.data_engineer_role_arn
}

output "model_monitor_role_arn" {
  description = "ARN of the ModelMonitor role"
  value       = module.iam.model_monitor_role_arn
}

output "feature_group_name" {
  description = "Name of the customer Feature Group"
  value       = module.feature_store.feature_group_name
}

output "glue_crawler_name" {
  description = "Name of the raw/ Glue crawler"
  value       = module.glue.crawler_name
}

output "glue_transform_job_name" {
  description = "Name of the transform Glue job"
  value       = module.glue.transform_job_name
}

output "glue_feature_job_name" {
  description = "Name of the feature-engineer Glue job"
  value       = module.glue.feature_job_name
}
