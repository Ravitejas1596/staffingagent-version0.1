output "db_endpoint" {
  description = "Aurora PostgreSQL cluster endpoint"
  value       = aws_rds_cluster.main.endpoint
}

output "alb_dns" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for the API container image"
  value       = aws_ecr_repository.api.repository_url
}

output "uploads_bucket" {
  description = "S3 bucket name for VMS file uploads"
  value       = aws_s3_bucket.uploads.id
}

output "sqs_queue_url" {
  description = "SQS queue URL for async agent jobs"
  value       = aws_sqs_queue.agent_jobs.url
}

output "time_anomaly_sla_timer_queue_url" {
  description = "SQS queue URL for Time Anomaly SLA re-check timers"
  value       = aws_sqs_queue.time_anomaly_sla_timers.url
}

output "time_anomaly_sla_timer_queue_arn" {
  description = "SQS queue ARN for Time Anomaly SLA re-check timers (for IAM policy attachments)"
  value       = aws_sqs_queue.time_anomaly_sla_timers.arn
}

output "vpc_private_subnets" {
  description = "Private subnet IDs for ECS service network configuration"
  value       = module.vpc.private_subnets
}

output "api_security_group_id" {
  description = "Security group ID for API containers"
  value       = aws_security_group.api.id
}

output "api_target_group_arn" {
  description = "Target group ARN for ECS service load balancer configuration"
  value       = aws_lb_target_group.api.arn
}

output "ecs_task_execution_role_arn" {
  description = "ARN of the ECS task execution IAM role"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "account_id" {
  description = "AWS account ID (for task-def.json placeholders)"
  value       = data.aws_caller_identity.current.account_id
}

output "rds_cluster_arn" {
  description = "RDS cluster ARN — used with aws rds-data execute-statement"
  value       = aws_rds_cluster.main.arn
}

output "db_credentials_secret_arn" {
  description = "Secrets Manager ARN for RDS Data API credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}
