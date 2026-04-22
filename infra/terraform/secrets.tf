resource "aws_secretsmanager_secret" "api_secrets" {
  name        = "${local.name}/${var.environment}/api-secrets"
  description = "API configuration secrets for ${local.name} (DATABASE_URL, JWT_SECRET, ANTHROPIC_API_KEY, etc.)"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${local.name}/${var.environment}/db-credentials"
  description = "RDS Data API credentials for ${local.name} — used by aws rds-data execute-statement"
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id     = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = "postgres"
    password = var.db_password
    engine   = "postgres"
    host     = aws_rds_cluster.main.endpoint
    port     = 5432
    dbname   = "staffingagent"
  })
}
