# Phase 5 §6: real security groups -- each one scoped to exactly the
# real traffic its own resource needs, never a blanket allow.

resource "aws_security_group" "alb" {
  name_prefix = "${local.name_prefix}-alb-"
  description = "Real ALB SG -- public HTTPS in, nothing else."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from the real internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "To the real api/web Fargate tasks only"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = { Name = "${local.name_prefix}-alb-sg" }
}

resource "aws_security_group" "api" {
  name_prefix = "${local.name_prefix}-api-"
  description = "Real api/worker Fargate tasks -- inbound only from the real ALB."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From the real ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Outbound -- RDS, S3 (via gateway endpoint), Secrets Manager, real external acquisition sources"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-api-sg" }
}

resource "aws_security_group" "web" {
  name_prefix = "${local.name_prefix}-web-"
  description = "Real web Fargate task -- inbound only from the real ALB."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From the real ALB"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description     = "To the real api Fargate task only (the real /api/* proxy's own real destination)"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  tags = { Name = "${local.name_prefix}-web-sg" }
}

resource "aws_security_group" "rds" {
  name_prefix = "${local.name_prefix}-rds-"
  description = "Real RDS -- inbound only from the real api/worker Fargate tasks."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from api/worker"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  tags = { Name = "${local.name_prefix}-rds-sg" }
}
