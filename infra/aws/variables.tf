# Phase 5 §6: every real input this Terraform needs. No defaults for
# anything secret or environment-specific that would silently apply
# against the wrong real account/region if left unset.

variable "aws_region" {
  description = "Real AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used as a prefix on every real resource this creates."
  type        = string
  default     = "ledgerlight"
}

variable "environment" {
  description = "Matches LEDGERLIGHT_ENVIRONMENT ('staging' or 'production') -- never 'dev'."
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be 'staging' or 'production' -- this Terraform is never for local dev."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the real VPC this creates."
  type        = string
  default     = "10.20.0.0/16"
}

variable "availability_zone_count" {
  description = "Number of real AZs to spread subnets across."
  type        = number
  default     = 2
}

variable "container_image_api" {
  description = "Real ECR image URI for the api/worker service (built from the root Dockerfile)."
  type        = string
}

variable "container_image_web" {
  description = "Real ECR image URI for the web service (built from frontend/Dockerfile)."
  type        = string
}

variable "db_instance_class" {
  description = "Real RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "Real RDS allocated storage, in GB."
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Real application database name (matches LEDGERLIGHT_POSTGRES_DB)."
  type        = string
  default     = "ledgerlight"
}

variable "db_master_username" {
  description = "Real RDS master username (matches LEDGERLIGHT_POSTGRES_USER)."
  type        = string
  default     = "ledgerlight"
}

variable "acm_certificate_domain" {
  description = "Real domain name the ACM certificate and ALB listener are issued for."
  type        = string
}

variable "fargate_desired_count" {
  description = "Real, static desired task count per service -- no autoscaling policy configured in this phase."
  type        = number
  default     = 1
}
