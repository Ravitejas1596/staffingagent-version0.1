resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_rds_cluster_parameter_group" "main" {
  name        = "${local.name}-pg15-params"
  family      = "aurora-postgresql15"
  description = "Aurora PostgreSQL 15 parameter group for ${local.name}"
}

resource "aws_rds_cluster" "main" {
  cluster_identifier = "${local.name}-db"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = "15.10"
  database_name      = "staffingagent"
  master_username    = "postgres"
  master_password    = var.db_password

  db_subnet_group_name            = aws_db_subnet_group.main.name
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.main.name
  vpc_security_group_ids          = [aws_security_group.db.id]

  enable_http_endpoint = true  # RDS Data API — allows aws rds-data execute-statement

  storage_encrypted = true
  deletion_protection = true

  backup_retention_period = 7
  preferred_backup_window = "03:00-04:00"

  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-db-final-snapshot"

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 4
  }
}

resource "aws_rds_cluster_instance" "main" {
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version
}
