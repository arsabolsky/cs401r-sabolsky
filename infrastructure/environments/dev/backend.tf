# Remote state. The bucket and lock table are created by
# scripts/bootstrap-state.sh and must exist before `terraform init`.

terraform {
  backend "s3" {
    bucket         = "northstar-tfstate-573693339848"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "northstar-tfstate-lock"
  }
}
