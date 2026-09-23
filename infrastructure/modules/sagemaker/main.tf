# ── modules/sagemaker ────────────────────────────────────────────────────────
# Required resources (Task B1). Only these belong in this module:
#
#   aws_sagemaker_domain
#   aws_sagemaker_user_profile
#
# A brand-new AWS account has no service-linked role for Studio, and the
# Domain fails to create with a service-linked role error. Fix it once in the
# console (IAM -> Roles -> Create Role -> AWS Service -> SageMaker -> SageMaker
# Studio) and re-apply. See the New Account Bootstrap note in the lab.
# NOTE (learned the hard way in Task A4): that console path does NOT actually
# create the service-linked role either. The real fix, one-time, is:
#   aws iam create-service-linked-role --aws-service-name sagemaker.amazonaws.com
#
# The Domain is also the slowest resource here by a wide margin -- several
# minutes to create and to delete. Factor that into your apply/destroy timings
# for Task B2.

# The Domain needs an execution role (default_user_settings.execution_role)
# and the security group from modules/vpc; both arrive as variables. See the
# module call in environments/dev/main.tf.

# STEP 1 — aws_sagemaker_domain
# Docs: .../resources/sagemaker_domain
# Required top-level arguments: domain_name, auth_mode, vpc_id, subnet_ids
#   domain_name: build from var.project + var.environment
#   auth_mode:   "IAM"
#   vpc_id:      var.vpc_id
#   subnet_ids:  var.subnet_ids
#
# Then a required NESTED block, default_user_settings, containing at least:
#   execution_role   = var.execution_role_arn
#   security_groups  = var.security_group_ids
#
# And inside THAT, another nested block for notebook output sharing
# (Task A4 spec: Disabled):
#   sharing_settings {
#     notebook_output_option = "Disabled"
#   }
#
# Finally, a SEPARATE top-level nested block (sibling to
# default_user_settings, not inside it) that is not optional in practice —
# skip it and terraform destroy will hang on the subnet/security group for
# ~10 minutes because Studio's EFS filesystem survives domain deletion by
# default (you hit exactly this failure mode manually in Task A's teardown):
#   retention_policy {
#     home_efs_file_system = "Delete"
#   }
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
  retention_policy {
    home_efs_file_system = "Delete"
  }
}


# STEP 2 — aws_sagemaker_user_profile
# Docs: .../resources/sagemaker_user_profile
# Required: domain_id, user_profile_name
#   domain_id:         aws_sagemaker_domain.this.id
#   user_profile_name: "MLEngineer"   (exact name from the Architecture Reference)
# Then a nested user_settings block with just:
#   execution_role = var.execution_role_arn
resource "aws_sagemaker_user_profile" "this" {
  domain_id         = aws_sagemaker_domain.this.id
  user_profile_name = "MLEngineer"
  user_settings {
    execution_role = var.execution_role_arn
  }
}
# TODO: implement the two resources above.
