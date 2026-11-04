# Phase 5 §6: real S3 bucket -- replaces the local Garage container.
# ledgerlight.storage.s3_store.ObjectStore already speaks plain
# S3-compatible API, so switching is a real config change
# (LEDGERLIGHT_S3_ENDPOINT -> this bucket's regional endpoint), never
# a code change.

resource "aws_s3_bucket" "raw" {
  bucket_prefix = "${local.name_prefix}-raw-"

  tags = { Name = "${local.name_prefix}-raw" }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
