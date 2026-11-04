output "alb_dns_name" {
  description = "Real ALB DNS name -- point the real domain's DNS (CNAME/ALIAS) here."
  value       = aws_lb.main.dns_name
}

output "rds_endpoint" {
  description = "Real RDS endpoint address (never publicly reachable -- private subnet only)."
  value       = aws_db_instance.main.address
}

output "s3_bucket_name" {
  description = "Real S3 bucket name -- set as LEDGERLIGHT_S3_BUCKET."
  value       = aws_s3_bucket.raw.id
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "secrets_to_populate" {
  description = "Real Secrets Manager secret ARNs that must be populated out-of-band before any real ECS task can start successfully."
  value = {
    postgres_password             = aws_secretsmanager_secret.postgres_password.arn
    app_db_password               = aws_secretsmanager_secret.app_db_password.arn
    session_secret_key            = aws_secretsmanager_secret.session_secret_key.arn
    webhook_secret_encryption_key = aws_secretsmanager_secret.webhook_secret_encryption_key.arn
    s3_secret_access_key          = aws_secretsmanager_secret.s3_secret_access_key.arn
  }
}
