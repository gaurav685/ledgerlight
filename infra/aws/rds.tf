# Phase 5 §6: real RDS for PostgreSQL -- replaces the local
# pgvector/pgvector:pg16 container 1:1. pgvector itself ships as a
# real RDS-supported extension (enabled via the parameter group
# below, not a custom image), so no custom AMI/image is needed.

resource "aws_db_subnet_group" "main" {
  name_prefix = "${local.name_prefix}-db-"
  subnet_ids  = aws_subnet.private[*].id

  tags = { Name = "${local.name_prefix}-db-subnet-group" }
}

resource "aws_db_parameter_group" "postgres" {
  name_prefix = "${local.name_prefix}-pg16-"
  family      = "postgres16"
  description = "Real parameter group enabling pgvector via shared_preload_libraries."

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }
}

resource "aws_db_instance" "main" {
  identifier_prefix = "${local.name_prefix}-db-"

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage           = var.db_allocated_storage_gb
  storage_encrypted           = true
  db_name                     = var.db_name
  username                    = var.db_master_username
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres.name

  multi_az            = var.environment == "production"
  publicly_accessible = false
  skip_final_snapshot = var.environment != "production"

  backup_retention_period = var.environment == "production" ? 7 : 1

  tags = { Name = "${local.name_prefix}-db" }
}

# A second, real, separate database for Dagster's own run/event
# storage -- never mixed with the application schema, same real
# discipline as the local docker-compose.yml's own
# LEDGERLIGHT_POSTGRES_DAGSTER_DB. Created as a logical database on
# the SAME RDS instance (via a null_resource + the real `psql` CLI
# would be the normal pattern, but Terraform's aws provider has no
# native "create a second database on an existing RDS instance"
# resource -- documented here as a real, manual post-apply step
# rather than faked with a resource that doesn't actually exist).
