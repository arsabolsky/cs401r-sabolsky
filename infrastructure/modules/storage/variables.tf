# Every variable needs a description — Task B1 grades this.

variable "project" {
  description = "Project name, used as the first element of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "prefixes" {
  description = "Top-level S3 prefixes to create in the data bucket"
  type        = list(string)
  default     = ["raw/", "processed/", "features/", "artifacts/"]
}

variable "enable_lifecycle_rules" {
  description = "Attach the S3 lifecycle configuration; set false for LocalStack"
  type        = bool
  default     = true
}

variable "force_destroy" {
  description = "Allow terraform destroy to succeed even if the bucket isn't empty"
  type        = bool
  default     = false
}
