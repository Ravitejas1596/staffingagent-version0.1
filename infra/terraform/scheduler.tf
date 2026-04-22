# --- IAM role for EventBridge Scheduler to start ECS tasks ---

resource "aws_iam_role" "eventbridge_scheduler" {
  name = "${local.name}-eventbridge-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge_scheduler" {
  name = "ecs-run-task"
  role = aws_iam_role.eventbridge_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = aws_ecs_task_definition.sync.arn
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = aws_iam_role.ecs_task_execution.arn
      }
    ]
  })
}

# --- ECS task definition for the sync job ---

resource "aws_ecs_task_definition" "sync" {
  family                   = "${local.name}-sync"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name    = "sync"
    image   = "${aws_ecr_repository.api.repository_url}:latest"
    command = ["python", "-m", "src.sync.bullhorn_sync"]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "sync"
      }
    }

    secrets = [
      {
        name      = "DATABASE_URL"
        valueFrom = "${aws_secretsmanager_secret.api_secrets.arn}:DATABASE_URL::"
      },
      {
        name      = "DATABASE_ADMIN_URL"
        valueFrom = "${aws_secretsmanager_secret.api_secrets.arn}:DATABASE_ADMIN_URL::"
      },
      {
        name      = "ANTHROPIC_API_KEY"
        valueFrom = "${aws_secretsmanager_secret.api_secrets.arn}:ANTHROPIC_API_KEY::"
      },
      {
        name      = "BULLHORN_CLIENT_ID"
        valueFrom = "${aws_secretsmanager_secret.api_secrets.arn}:BULLHORN_CLIENT_ID::"
      },
      {
        name      = "BULLHORN_CLIENT_SECRET"
        valueFrom = "${aws_secretsmanager_secret.api_secrets.arn}:BULLHORN_CLIENT_SECRET::"
      },
      {
        name      = "BULLHORN_API_USER"
        valueFrom = "${aws_secretsmanager_secret.api_secrets.arn}:BULLHORN_API_USER::"
      },
      {
        name      = "BULLHORN_API_PASSWORD"
        valueFrom = "${aws_secretsmanager_secret.api_secrets.arn}:BULLHORN_API_PASSWORD::"
      }
    ]

    environment = [
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
      { name = "STAFFINGAGENT_TENANT", value = "default" }
    ]
  }])
}

# --- EventBridge Scheduler: nightly at 2 AM UTC ---

resource "aws_scheduler_schedule" "bullhorn_sync" {
  name                         = "${local.name}-bullhorn-sync"
  description                  = "Nightly Bullhorn pay/bill data sync"
  schedule_expression          = "cron(0 2 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.eventbridge_scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.sync.arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = module.vpc.private_subnets
        security_groups  = [aws_security_group.api.id]
        assign_public_ip = false
      }
    }

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}
