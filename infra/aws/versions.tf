terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Phase 5 §6: local backend only -- this Terraform has never been
  # applied (no AWS credentials in this environment) and is validated,
  # not run, by this phase. A real multi-person deployment needs a
  # real remote backend (S3 + DynamoDB lock table) configured here
  # before anyone runs `terraform apply` against a shared account --
  # see docs/deploy/aws-architecture.md's own "Known limitations".
}

provider "aws" {
  region = var.aws_region
}
