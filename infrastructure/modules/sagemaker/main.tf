# modules/sagemaker - Studio domain + the MLEngineer user profile.
# New account? Domain creation fails until the service-linked role exists (one-time):
#   aws iam create-service-linked-role --aws-service-name sagemaker.amazonaws.com
# The domain takes several minutes to create and to delete.

resource "aws_sagemaker_domain" "this" {
  domain_name = "${var.project}-${var.environment}-domain"
  auth_mode   = "IAM"
  vpc_id      = var.vpc_id
  subnet_ids  = var.subnet_ids
  default_user_settings {
    execution_role  = var.execution_role_arn
    security_groups = var.security_group_ids
    sharing_settings {
      notebook_output_option = "Disabled"
    }
    # AWS attaches this block server-side even when unset. Declaring it
    # explicitly (empty) stops every `terraform apply` from showing a
    # perpetual "1 to change" diff to remove something AWS keeps re-adding.
    studio_web_portal_settings {}
  }
  # Studio's EFS survives domain deletion by default, and its mount target
  # makes terraform destroy hang on the subnet and security group.
  retention_policy {
    home_efs_file_system = "Delete"
  }
}

resource "aws_sagemaker_user_profile" "this" {
  domain_id         = aws_sagemaker_domain.this.id
  user_profile_name = "MLEngineer"
  user_settings {
    execution_role = var.execution_role_arn
  }
}
