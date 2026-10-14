# modules/vpc - network for the platform.
#   Public subnet:  IGW route; holds the NAT Gateway.
#   Private subnet: SageMaker domain + Glue workers; outbound only, via the NAT.
# NAT, its EIP, and the private default route are skipped when
# enable_nat_gateway = false (LocalStack).

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "${var.project}-${var.environment}-vpc" }
}

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

resource "aws_eip" "this" {
  domain     = "vpc"
  count      = var.enable_nat_gateway ? 1 : 0
  tags       = { Name = "${var.project}-${var.environment}-eip" }
  depends_on = [aws_internet_gateway.this]
}

# Public route table: 0.0.0.0/0 -> IGW.
resource "aws_route_table" "this" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${var.project}-${var.environment}-public-rt" }
}

# Without an explicit association the subnet falls back to the VPC's main table.
resource "aws_route_table_association" "this" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.this.id
}

# Private route table. Its 0.0.0.0/0 -> NAT route is a separate aws_route
# with the NAT's count, so it disappears when NAT is disabled.
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

# Shared by the SageMaker domain and the Glue connection. Glue refuses to run
# unless an attached SG allows all ingress from itself (self = true); a
# VPC-CIDR rule does not satisfy that check.
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
