output "feature_group_name" {
  description = "Name of the customer Feature Group - the feature-engineer Glue job writes to it"
  value       = aws_sagemaker_feature_group.feature_group.feature_group_name
}
