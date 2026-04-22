# --- ECS task definition for the Bullhorn event subscription poller ---

resource "aws_ecs_task_definition" "poller" {
  family                   = "${local.name}-poller"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name    = "poller"
    image   = "${aws_ecr_repository.api.repository_url}:latest"
    command = ["python", "-m", "src.sync.bullhorn_poller"]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "poller"
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
      { name = "STAFFINGAGENT_TENANT", value = "default" },
      { name = "POLL_INTERVAL_SECONDS", value = "60" },
      { name = "BULLHORN_EVENTS_QUEUE_URL", value = aws_sqs_queue.bullhorn_events.url }
    ]
  }])
}

# --- ECS task definition for the SQS event consumer ---

resource "aws_ecs_task_definition" "consumer" {
  family                   = "${local.name}-consumer"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name    = "consumer"
    image   = "${aws_ecr_repository.api.repository_url}:latest"
    command = ["python", "-m", "src.sync.bullhorn_consumer"]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "consumer"
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
      { name = "STAFFINGAGENT_TENANT", value = "default" },
      { name = "BULLHORN_EVENTS_QUEUE_URL", value = aws_sqs_queue.bullhorn_events.url }
    ]
  }])
}

# --- ECS service: always-on consumer (desired_count=1) ---

resource "aws_ecs_service" "consumer" {
  name            = "${local.name}-consumer"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.consumer.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  lifecycle {
    ignore_changes = [task_definition]
  }
}

# --- ECS service: always-on poller (desired_count=1) ---

resource "aws_ecs_service" "poller" {
  name            = "${local.name}-poller"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.poller.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  # Allow task replacement without waiting for old task to drain
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  # Restart automatically if the task exits
  lifecycle {
    ignore_changes = [task_definition]
  }
}
