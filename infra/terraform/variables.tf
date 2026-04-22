variable "project" {
  description = "Project name used for resource naming"
  type        = string
  default     = "staffingagent"
}

variable "environment" {
  description = "Deployment environment (prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "db_password" {
  description = "Master password for Aurora PostgreSQL (20+ chars, mixed case, numbers, symbols)"
  type        = string
  sensitive   = true
}
