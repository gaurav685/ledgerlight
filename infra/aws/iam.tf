# Phase 5 §6: real, least-privilege IAM -- one real role for
# api/worker (reads the real Secrets Manager secrets above, reads/
# writes the real S3 bucket above), and the standard real ECS
# execution role every Fargate task needs (pull the real image,
# write to the real CloudWatch Logs group). `web` gets NO AWS
# permissions at all -- it only ever talks to `api` over real HTTP,
# never to AWS directly.

data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name_prefix        = "${local.name_prefix}-exec-"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# The execution role also needs to READ the real secrets (to inject
# them into the task at startup) -- the task role below is for what
# the RUNNING application code itself can do, a real, separate
# concern from what ECS needs to launch it.
data "aws_iam_policy_document" "ecs_execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.postgres_password.arn,
      aws_secretsmanager_secret.app_db_password.arn,
      aws_secretsmanager_secret.session_secret_key.arn,
      aws_secretsmanager_secret.webhook_secret_encryption_key.arn,
      aws_secretsmanager_secret.s3_secret_access_key.arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name_prefix = "secrets-read-"
  role        = aws_iam_role.ecs_execution.id
  policy      = data.aws_iam_policy_document.ecs_execution_secrets.json
}

resource "aws_iam_role" "api_task" {
  name_prefix        = "${local.name_prefix}-api-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
}

data "aws_iam_policy_document" "api_task_s3" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.raw.arn, "${aws_s3_bucket.raw.arn}/*"]
  }
}

resource "aws_iam_role_policy" "api_task_s3" {
  name_prefix = "s3-rw-"
  role        = aws_iam_role.api_task.id
  policy      = data.aws_iam_policy_document.api_task_s3.json
}

# `web` gets a real task role that can assume nothing further --
# intentionally empty of any AWS-resource permission.
resource "aws_iam_role" "web_task" {
  name_prefix        = "${local.name_prefix}-web-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
}
