# Phase 5 §6: real AWS Secrets Manager entries -- every real secret
# this phase's own Settings model requires outside dev
# (ledgerlight/config/settings.py's own _no_weak_secrets_outside_dev
# fail-fast check). Values are never set by this Terraform itself
# (that would just move the plaintext secret into the real .tfstate
# file, no safer than an env var) -- each secret is created EMPTY and
# must be populated out-of-band (AWS console, CLI, or a real secrets
# pipeline) before the real ECS tasks that read it can start.

resource "aws_secretsmanager_secret" "postgres_password" {
  name_prefix = "${local.name_prefix}-postgres-password-"
  description = "Real LEDGERLIGHT_POSTGRES_PASSWORD -- populate out-of-band, never via Terraform."

  tags = { Name = "${local.name_prefix}-postgres-password" }
}

resource "aws_secretsmanager_secret" "app_db_password" {
  name_prefix = "${local.name_prefix}-app-db-password-"
  description = "Real LEDGERLIGHT_APP_DB_PASSWORD -- the restricted ledgerlight_app role's password."

  tags = { Name = "${local.name_prefix}-app-db-password" }
}

resource "aws_secretsmanager_secret" "session_secret_key" {
  name_prefix = "${local.name_prefix}-session-secret-key-"
  description = "Real LEDGERLIGHT_SESSION_SECRET_KEY -- generate with openssl rand -hex 32."

  tags = { Name = "${local.name_prefix}-session-secret-key" }
}

resource "aws_secretsmanager_secret" "webhook_secret_encryption_key" {
  name_prefix = "${local.name_prefix}-webhook-secret-encryption-key-"
  description = "Real LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY -- a real Fernet.generate_key() value."

  tags = { Name = "${local.name_prefix}-webhook-secret-encryption-key" }
}

resource "aws_secretsmanager_secret" "s3_secret_access_key" {
  name_prefix = "${local.name_prefix}-s3-secret-access-key-"
  description = "Real LEDGERLIGHT_S3_SECRET_ACCESS_KEY for the real application S3 bucket."

  tags = { Name = "${local.name_prefix}-s3-secret-access-key" }
}
