# environments/dev - wires the modules together. Names come from
# var.project + var.environment; nothing in modules/ hardcodes one.

module "vpc" {
  source              = "../../modules/vpc"
  project             = var.project
  environment         = var.environment
  vpc_cidr            = var.vpc_cidr
  public_subnet_cidr  = var.public_subnet_cidr
  private_subnet_cidr = var.private_subnet_cidr
  availability_zone   = var.availability_zone
}

module "storage" {
  source        = "../../modules/storage"
  project       = var.project
  environment   = var.environment
  force_destroy = true
}

module "iam" {
  source      = "../../modules/iam"
  project     = var.project
  environment = var.environment
  bucket_arn  = module.storage.bucket_arn
}

module "sagemaker" {
  source             = "../../modules/sagemaker"
  project            = var.project
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = [module.vpc.private_subnet_id]
  security_group_ids = [module.vpc.security_group_id]
  execution_role_arn = module.iam.ml_engineer_role_arn
  instance_type      = var.sagemaker_instance_type
}

module "glue" {
  source                 = "../../modules/glue"
  project                = var.project
  environment            = var.environment
  bucket_name            = module.storage.bucket_name
  data_engineer_role_arn = module.iam.data_engineer_role_arn
  subnet_id              = module.vpc.private_subnet_id
  availability_zone      = module.vpc.private_subnet_availability_zone
  security_group_id      = module.vpc.security_group_id
  feature_group_name     = module.feature_store.feature_group_name
}

# depends_on: CreateFeatureGroup validates the role immediately, so the DataEngineer
# policy attachment must exist first rather than racing it.
module "feature_store" {
  source      = "../../modules/feature_store"
  project     = var.project
  environment = var.environment
  bucket_name = module.storage.bucket_name
  role_arn    = module.iam.data_engineer_role_arn
  depends_on  = [module.iam]
}
