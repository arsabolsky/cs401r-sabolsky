# modules/storage - one data bucket, northstar-<env>-data-<account-id>,
# with prefixes raw/ processed/ features/ artifacts/. Versioned, SSE-S3,
# public access blocked, lifecycle rules (skipped when enable_lifecycle_rules = false).

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "data" {
  bucket        = "${var.project}-${var.environment}-data-${data.aws_caller_identity.current.account_id}"
  tags          = { Name = "${var.project}-${var.environment}-data" }
  force_destroy = var.force_destroy # allows terraform destroy to succeed even if the bucket isn't empty
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 has no real folders; an empty object ending in "/" makes each prefix exist.
resource "aws_s3_object" "prefixes" {
  for_each = toset(var.prefixes)
  bucket   = aws_s3_bucket.data.id
  key      = each.value
}

# The five rules from the Architecture Reference. depends_on versioning because
# the noncurrent-version rules only apply to a versioned bucket. datacapture/
# has no writer until Lab 5; the rule exists first.
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
