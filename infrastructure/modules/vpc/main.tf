# ── modules/vpc ──────────────────────────────────────────────────────────────
# Required resources (Task B1). Only these belong in this module:
#
#   aws_vpc
#   aws_subnet                      public (Lab 1) + private (Lab 2)
#   aws_internet_gateway
#   aws_eip, aws_nat_gateway        Lab 2; skipped when enable_nat_gateway = false
#   aws_route_table                 public (Lab 1) + private (Lab 2)
#   aws_route                       Lab 2; private 0.0.0.0/0 -> NAT, same toggle
#   aws_route_table_association     public (Lab 1) + private (Lab 2)
#   aws_security_group              Lab 2 adds vpc_id, VPC-CIDR ingress, Glue self-rule
#
# Name everything from var.project and var.environment. A hardcoded
# project-environment literal anywhere under modules/ fails the rubric grep.
#
# Example of the naming pattern expected:
#
#   resource "aws_vpc" "this" {
#     cidr_block = var.vpc_cidr
#     tags       = { Name = "${var.project}-${var.environment}-vpc" }
#   }

# STEP 1 — aws_vpc (mostly done below — fix the two HCL bugs described inline)
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "${var.project}-${var.environment}-vpc" }
}

# STEP 2 — aws_subnet
# Docs: .../resources/subnet
# Reference the VPC you just made with aws_vpc.this.id — that's how one
# resource points at another inside the same file. Also give it a tags map
# like the VPC has, named "...-public-1".
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.project}-${var.environment}-public-1" }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = var.availability_zone
  tags              = { Name = "${var.project}-${var.environment}-private-1" }
}

# STEP 3 — aws_internet_gateway
# Docs: .../resources/internet_gateway
# Required: vpc_id. Same pattern as Step 2 — point it at aws_vpc.this.id.
# Give it a Name tag ("...-igw").
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project}-${var.environment}-igw" }
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.this[0].id
  subnet_id     = aws_subnet.public.id
  count         = var.enable_nat_gateway ? 1 : 0
  tags          = { Name = "${var.project}-${var.environment}-nat" }
  depends_on    = [aws_internet_gateway.this]
}

# Lab 2 — Elastic IP for the NAT Gateway (skipped when enable_nat_gateway = false)
resource "aws_eip" "this" {
  domain     = "vpc"
  count      = var.enable_nat_gateway ? 1 : 0
  tags       = { Name = "${var.project}-${var.environment}-eip" }
  depends_on = [aws_internet_gateway.this]
}

# STEP 4 — aws_route_table
# Docs: .../resources/route_table
# Required: vpc_id
# Then a NESTED block (not a flat argument) for each route:
#   route {
#     cidr_block = "0.0.0.0/0"
#     gateway_id = aws_internet_gateway.this.id
#   }
# Give it a Name tag ("...-public-rt").
resource "aws_route_table" "this" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${var.project}-${var.environment}-public-rt" }
}

# STEP 5 — aws_route_table_association
# Docs: .../resources/route_table_association
# This is the resource that actually connects the subnet to the route table
# — without it, the subnet silently falls back to the VPC's main route table
# (this is the exact mistake from Task A2 that left the Subnet associations
# tab empty). Required: subnet_id, route_table_id — both are references to
# resources above, not variables.
resource "aws_route_table_association" "this" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.this.id
}

# Lab 2 — private route table. The 0.0.0.0/0 -> NAT route is a separate
# aws_route with the NAT's count, so it disappears when NAT is disabled.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project}-${var.environment}-private-rt" }
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route" "private_nat" {
  count                  = var.enable_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

# STEP 6 — aws_security_group
# Docs: .../resources/security_group
# Required-in-practice: vpc_id, plus ingress/egress rules as nested blocks
# (a security group with none is nearly useless). Recall Task A2's spec:
#   ingress: all protocols/ports, source = var.vpc_cidr (NOT the internet)
#   egress:  all protocols/ports, destination = "0.0.0.0/0"
# "All protocols" in HCL is written as:
#   from_port = 0
#   to_port   = 0
#   protocol  = "-1"
# Each ingress/egress rule is its own nested block:
#   ingress {
#     from_port   = 0
#     to_port     = 0
#     protocol    = "-1"
#     cidr_blocks = [var.vpc_cidr]
#   }
# Give it a Name tag ("...-sagemaker-sg").
resource "aws_security_group" "this" {
  tags   = { Name = "${var.project}-${var.environment}-sagemaker-sg" }
  vpc_id = aws_vpc.this.id
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
