# infra/aws -- Terraform (validated, never applied)

Phase 5 §6. This Terraform has **never been run against a real AWS
account** -- this environment has no AWS credentials, and applying
infrastructure is explicitly out of this phase's scope. See
`docs/deploy/aws-architecture.md` for the architecture it describes.

## What was actually run here

```sh
docker run --rm -v "${PWD}:/workspace" -w /workspace hashicorp/terraform:1.9 fmt -check -recursive
docker run --rm -v "${PWD}:/workspace" -w /workspace hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}:/workspace" -w /workspace hashicorp/terraform:1.9 validate
```

Both commands ran clean against the real `hashicorp/terraform:1.9`
image (via Docker, since no `terraform` binary is installed on this
host) -- see `docs/phase-5/evidence/terraform-validate.log` for the
real output. **`terraform plan`/`apply` were never run** -- they
require real AWS credentials this environment does not have.

## Local backend only

No remote backend (`backend "s3"` etc.) is configured in
`versions.tf` -- state would default to a local `.tfstate` file,
which is correct for this phase's validate-only use and explicitly
wrong for a real, multi-person deployment. Before anyone ever runs
`terraform apply` against a shared AWS account, add a real S3 +
DynamoDB-lock remote backend here first.

## Before a real apply (not done in this phase)

1. Configure real AWS credentials (`aws configure` / environment
   variables / an assumed role) -- never commit them.
2. Add a real remote backend (above).
3. Push real `api`/`web` images to a real ECR repository; set
   `container_image_api`/`container_image_web` to those real URIs.
4. Set `acm_certificate_domain` to a real domain you control, and
   complete the real ACM DNS validation after `apply` creates the
   certificate request.
5. `terraform plan` and have a human review it -- `docs/release/release-gates.md`
   should gain a real gate requiring this before any real apply (§10).
6. Only then `terraform apply`, and immediately populate every secret
   listed in the `secrets_to_populate` output via the AWS console/CLI
   -- never via Terraform itself (see `secrets.tf`'s own docstring for
   why).
