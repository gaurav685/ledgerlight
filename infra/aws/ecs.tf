# Phase 5 §6: real ECS Fargate -- api/worker/web, one real cluster.
# Static, real desired-count per service (var.fargate_desired_count)
# -- no autoscaling policy configured in this phase, per the
# architecture doc's own disclosed limitation.

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name_prefix       = "/ecs/${local.name_prefix}-api-"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name_prefix       = "/ecs/${local.name_prefix}-worker-"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "web" {
  name_prefix       = "/ecs/${local.name_prefix}-web-"
  retention_in_days = 30
}

locals {
  # Every real secret every api/worker task needs, injected via
  # Secrets Manager -- never a plain environment variable.
  api_worker_secrets = [
    { name = "LEDGERLIGHT_POSTGRES_PASSWORD", valueFrom = aws_secretsmanager_secret.postgres_password.arn },
    { name = "LEDGERLIGHT_APP_DB_PASSWORD", valueFrom = aws_secretsmanager_secret.app_db_password.arn },
    { name = "LEDGERLIGHT_S3_SECRET_ACCESS_KEY", valueFrom = aws_secretsmanager_secret.s3_secret_access_key.arn },
  ]

  common_env = [
    { name = "LEDGERLIGHT_ENVIRONMENT", value = var.environment },
    { name = "LEDGERLIGHT_POSTGRES_HOST", value = aws_db_instance.main.address },
    { name = "LEDGERLIGHT_POSTGRES_PORT", value = "5432" },
    { name = "LEDGERLIGHT_POSTGRES_USER", value = var.db_master_username },
    { name = "LEDGERLIGHT_POSTGRES_DB", value = var.db_name },
    { name = "LEDGERLIGHT_APP_DB_USER", value = "ledgerlight_app" },
    { name = "LEDGERLIGHT_S3_ENDPOINT", value = aws_s3_bucket.raw.bucket_regional_domain_name },
    { name = "LEDGERLIGHT_S3_BUCKET", value = aws_s3_bucket.raw.id },
    { name = "LEDGERLIGHT_S3_REGION", value = var.aws_region },
    { name = "LEDGERLIGHT_COOKIE_SECURE", value = "true" },
  ]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  container_definitions = jsonencode([
    {
      name         = "api"
      image        = var.container_image_api
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = concat(local.common_env, [
        { name = "LEDGERLIGHT_SESSION_SECRET_KEY_FROM", value = "secrets-manager" },
      ])
      secrets = concat(local.api_worker_secrets, [
        { name = "LEDGERLIGHT_SESSION_SECRET_KEY", valueFrom = aws_secretsmanager_secret.session_secret_key.arn },
        { name = "LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY", valueFrom = aws_secretsmanager_secret.webhook_secret_encryption_key.arn },
      ])
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
    }
  ])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.container_image_api
      essential = true
      command   = ["dagster", "dev", "-m", "ledgerlight.orchestration.definitions", "-h", "0.0.0.0", "-p", "3001"]
      environment = concat(local.common_env, [
        { name = "LEDGERLIGHT_POSTGRES_DAGSTER_DB", value = "ledgerlight_dagster" },
      ])
      secrets = local.api_worker_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name_prefix}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.web_task.arn

  container_definitions = jsonencode([
    {
      name         = "web"
      image        = var.container_image_web
      essential    = true
      portMappings = [{ containerPort = 3000, protocol = "tcp" }]
      environment = [
        { name = "LEDGERLIGHT_API_ORIGIN", value = "http://${aws_lb.main.dns_name}" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.web.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "web"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.fargate_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.api.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.fargate_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.api.id]
  }
  # Deliberately no load_balancer block -- worker's own Dagster
  # webserver is internal-only, never exposed through the real ALB
  # (see docs/deploy/aws-architecture.md's own real request flow).
}

resource "aws_ecs_service" "web" {
  name            = "${local.name_prefix}-web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.fargate_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.web.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }

  depends_on = [aws_lb_listener.https]
}
