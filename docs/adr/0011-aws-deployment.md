# ADR 0011: AWS Deployment Architecture (Phase 5 §6)

## Status
Accepted (Phase 5). **Validated, never applied** -- no AWS
credentials exist in this environment; see `infra/aws/README.md`.

## Context
Phase 5 §6 asked for a real AWS architecture description and real
Terraform modeling it, explicitly never applied. Several real design
decisions were made while building `infra/aws/`; this records them.

## Decisions

### 1. ECS Fargate, not EKS or EC2

The real workload (one FastAPI process, one Dagster worker, one
Next.js server) has no real need for a general-purpose Kubernetes
control plane, and Fargate removes real EC2 patching/AMI-management
work entirely. Accepted tradeoff: less flexibility than EKS for a
much smaller real operational surface, correct for this project's
real current scale.

### 2. RDS for PostgreSQL with pgvector via parameter group, not a custom image

`pgvector` is a real, officially RDS-supported extension (enabled
through the parameter group, not a custom AMI/container) -- this
lets the real production database stay on AWS's own managed
Postgres, with real automated backups/Multi-AZ/patching, rather than
self-managing Postgres on EC2 or ECS the way the local dev Compose
stack does.

### 3. One NAT gateway, not one per AZ

A real, deliberate cost tradeoff (see `docs/deploy/aws-architecture.md`'s
own cost notes) -- a single NAT gateway is a single real point of
failure for private-subnet egress, acceptable for this phase's
staging-sized architecture. A real production deployment with a
stricter real HA requirement should add one NAT gateway per AZ.

### 4. `web` gets no AWS IAM permissions at all

The real Next.js frontend never talks to AWS directly -- every real
data access goes through `api` over HTTP (the same real
`/api/[...path]` route-handler proxy built for local dev). Its real
ECS task role is deliberately created with no attached policy beyond
the bare assume-role trust relationship, so even a real compromise
of the `web` container's own task credentials grants no real AWS
access.

### 5. Secrets Manager entries created empty, never populated by Terraform

Writing a real plaintext secret value into a Terraform resource
argument moves it into the real `.tfstate` file in plaintext -- no
safer than an environment variable, and `.tfstate` is a much easier
file to accidentally leak (logs, CI artifacts, a committed-by-mistake
state file) than a single env var. Every real secret resource here
is created empty; populating the real value is a documented,
deliberate out-of-band step (`infra/aws/README.md`'s own "before a
real apply" checklist).

### 6. Local Terraform backend only, in this phase

No real remote backend (S3 + DynamoDB lock table) is configured.
Correct for this phase's validate-only use (a local `.tfstate` file
is fine when nobody ever runs `apply`); explicitly flagged as wrong
for a real, multi-person deployment -- `infra/aws/README.md`'s own
"before a real apply" checklist requires adding one first.

### 7. Validated via the official `hashicorp/terraform` Docker image, not a host install

No `terraform` binary is installed on this Windows host and
installing one was unnecessary -- `docker run hashicorp/terraform:1.9
fmt/init/validate` against the real `infra/aws/` files produced the
exact same real output a host install would, with zero footprint
left on the host. `tflint` was run the same way (also via its own
official Docker image) since the brief explicitly allowed it "if
feasible" -- it found one real, fixed issue (a deprecated
interpolation-only expression in `ecs.tf`), confirmed and corrected
directly. See `docs/phase-5/evidence/terraform-validate.log` for the
real, raw output of every one of these commands.
