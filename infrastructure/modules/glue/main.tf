# modules/glue - catalog database, raw/ crawler, VPC connection, and the two ETL
# jobs: transform (raw CSV -> processed/ Parquet) and feature-engineer (processed/
# -> features/ Parquet + Feature Store). Everything runs as DataEngineer.

data "aws_region" "current" {}

locals {
  scripts_dir = "${path.module}/../../../glue-scripts"
}

resource "aws_glue_catalog_database" "this" {
  name = "${var.project}_${var.environment}" # Glue names can't contain "-"
}

# Points at the raw/customers/ folder, so the table is named "customers".
resource "aws_glue_crawler" "raw" {
  name          = "${var.project}-${var.environment}-raw-crawler"
  database_name = aws_glue_catalog_database.this.name
  role          = var.data_engineer_role_arn
  s3_target {
    path = "s3://${var.bucket_name}/raw/customers/"
  }
}

# etag = file hash, so editing the script re-uploads it on the next apply.
resource "aws_s3_object" "transform_script" {
  bucket = var.bucket_name
  key    = "artifacts/glue/transform.py"
  source = "${local.scripts_dir}/transform.py"
  etag   = filemd5("${local.scripts_dir}/transform.py")
}

# Places Glue workers in the private subnet; the SG must have the self-referencing rule.
resource "aws_glue_connection" "vpc" {
  name            = "${var.project}-${var.environment}-vpc-connection"
  connection_type = "NETWORK"
  physical_connection_requirements {
    availability_zone      = var.availability_zone
    subnet_id              = var.subnet_id
    security_group_id_list = [var.security_group_id]
  }
}

resource "aws_glue_job" "transform" {
  name              = "${var.project}-${var.environment}-transform"
  role_arn          = var.data_engineer_role_arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  connections       = [aws_glue_connection.vpc.name]
  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.bucket_name}/${aws_s3_object.transform_script.key}"
  }
  # Exactly the arguments transform.py reads with getResolvedOptions.
  default_arguments = {
    "--database_name" = aws_glue_catalog_database.this.name
    "--table_name"    = "customers"
    "--output_path"   = "s3://${var.bucket_name}/processed/customers/"
  }
}

resource "aws_s3_object" "feature_engineer_script" {
  bucket = var.bucket_name
  key    = "artifacts/glue/feature_engineer.py"
  source = "${local.scripts_dir}/feature_engineer.py"
  etag   = filemd5("${local.scripts_dir}/feature_engineer.py")
}

# Same network placement as transform; it reaches the Feature Store API through the NAT.
resource "aws_glue_job" "feature_engineer" {
  name              = "${var.project}-${var.environment}-feature-engineer"
  role_arn          = var.data_engineer_role_arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  connections       = [aws_glue_connection.vpc.name]
  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.bucket_name}/${aws_s3_object.feature_engineer_script.key}"
  }
  # Exactly the arguments feature_engineer.py reads with getResolvedOptions.
  default_arguments = {
    "--input_path"         = "s3://${var.bucket_name}/processed/customers/"
    "--output_path"        = "s3://${var.bucket_name}/features/customers/"
    "--feature_group_name" = var.feature_group_name
    "--region"             = data.aws_region.current.name
  }
}
