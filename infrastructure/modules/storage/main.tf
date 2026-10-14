# ── modules/storage ──────────────────────────────────────────────────────────
# Required resources (Task B1). Only these belong in this module:
#
#   aws_s3_bucket
#   aws_s3_bucket_public_access_block
#   aws_s3_bucket_versioning
#   aws_s3_bucket_server_side_encryption_configuration
#   aws_s3_object  x4                 the raw/ processed/ features/ artifacts/ prefixes
#
# ONE bucket with four prefixes, not four buckets. Later labs derive the name
# as ${project}-${environment}-data-${account_id}, so keep that shape.
#
# The four aws_s3_object resources create the prefixes. S3 has no real
# directories; an empty object with a trailing slash is how a prefix is made
# to exist before anything is written to it.

# STEP 1 — you need the account ID for the bucket name, and it isn't a
# variable anywhere in this module. Terraform gets "facts about the account
# you're authenticated as" via a *data source*, not a resource:
#
#   data "aws_caller_identity" "current" {}
#
# Docs: registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity
# Once declared, its account id is available as:
#   data.aws_caller_identity.current.account_id
data "aws_caller_identity" "current" {}

# STEP 2 — aws_s3_bucket
# Docs: .../resources/s3_bucket
# Required argument: bucket (the name — build it from var.project,
# var.environment, "data", and the account id from Step 1)
# Everything else (versioning, encryption, public-access-block) is now a
# SEPARATE resource in modern AWS provider versions — do not look for those
# as arguments on aws_s3_bucket itself.
resource "aws_s3_bucket" "data" {
  bucket        = "${var.project}-${var.environment}-data-${data.aws_caller_identity.current.account_id}"
  tags          = { Name = "${var.project}-${var.environment}-data" }
  force_destroy = var.force_destroy # allows terraform destroy to succeed even if the bucket isn't empty
}

# STEP 3 — aws_s3_bucket_public_access_block
# Docs: .../resources/s3_bucket_public_access_block
# Required: bucket = aws_s3_bucket.this.id
# Then four booleans, all true: block_public_acls, block_public_policy,
# ignore_public_acls, restrict_public_buckets
resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# STEP 4 — aws_s3_bucket_versioning
# Docs: .../resources/s3_bucket_versioning
# Required: bucket = aws_s3_bucket.this.id
# Then a NESTED block (not a flat argument):
#   versioning_configuration {
#     status = "Enabled"
#   }
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

# STEP 5 — aws_s3_bucket_server_side_encryption_configuration
# Docs: .../resources/s3_bucket_server_side_encryption_configuration
# Required: bucket = aws_s3_bucket.this.id
# Then TWO levels of nested block:
#   rule {
#     apply_server_side_encryption_by_default {
#       sse_algorithm = "AES256"
#     }
#   }
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# STEP 6 — aws_s3_object x4, but as ONE resource block using for_each
# Docs: .../resources/s3_object
# var.prefixes is already a list(string) — see variables.tf. Turn it into a
# set with for_each = toset(var.prefixes), then inside the block:
#   bucket = aws_s3_bucket.this.id
#   key    = each.value
# for_each makes Terraform create one object per list entry from a single
# resource block — you do NOT write four separate resource blocks.
resource "aws_s3_object" "prefixes" {
  for_each = toset(var.prefixes)
  bucket   = aws_s3_bucket.data.id
  key      = each.value
}

# Lab 2 — lifecycle rules (the five from the Architecture Reference).
# Skipped when enable_lifecycle_rules = false (LocalStack). depends_on
# versioning because the noncurrent-version rules only apply to a versioned
# bucket. datacapture/ has no writer until Lab 5; the rule exists first.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  count      = var.enable_lifecycle_rules ? 1 : 0
  bucket     = aws_s3_bucket.data.id
  depends_on = [aws_s3_bucket_versioning.this]

  rule {
    id     = "expire-raw-data"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    expiration {
      days = 90
    }
  }

  rule {
    id     = "expire-raw-versions"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "expire-processed-versions"
    status = "Enabled"
    filter {
      prefix = "processed/"
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "expire-feature-versions"
    status = "Enabled"
    filter {
      prefix = "features/"
    }
    noncurrent_version_expiration {
      noncurrent_days = 60
    }
  }

  rule {
    id     = "expire-datacapture"
    status = "Enabled"
    filter {
      prefix = "datacapture/"
    }
    expiration {
      days = 7
    }
  }
}
