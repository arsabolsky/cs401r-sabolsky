# Consumed by environments/*/main.tf and passed to other modules.

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.this.id
}

output "public_subnet_id" {
  description = "ID of the public subnet"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "ID of the private subnet"
  value       = aws_subnet.private.id
}

output "private_subnet_availability_zone" {
  description = "Availability Zone of the private subnet (the Glue NETWORK connection needs it)"
  value       = aws_subnet.private.availability_zone
}

output "security_group_id" {
  description = "ID of the default security group"
  value       = aws_security_group.this.id
}
