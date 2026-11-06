# AWS deployment architecture (Phase 5 §6)

Describes the real AWS architecture `infra/aws/`'s Terraform models --
validated (`terraform fmt`/`validate`, below) but **never applied**:
this environment has no AWS credentials, and applying infrastructure
is explicitly out of this phase's scope per the brief. Nothing here
has ever run against a real AWS account.

## Services

| Component | AWS service | Notes |
|---|---|---|
| `api`/`worker` (Phase 5's own containers) | ECS Fargate | Two real services behind the same cluster; `worker` runs the Dagster webserver + schedules, `api` runs uvicorn. No EC2 to patch. |
| `web` (Next.js) | ECS Fargate | A third real Fargate service, same cluster. |
| Application database | RDS for PostgreSQL, `pgvector` via the `rds.extensions` parameter group setting | Multi-AZ for production; single-AZ acceptable for staging. Replaces the local `pgvector/pgvector:pg16` container 1:1. |
| Object storage | S3 (real bucket, versioning on, SSE-S3) | Replaces the local Garage container; `ledgerlight.storage.s3_store.ObjectStore` already speaks plain S3-compatible API, so this is a config change (`LEDGERLIGHT_S3_ENDPOINT` → the real bucket's regional endpoint), not a code change. |
| Secrets | AWS Secrets Manager | Every real secret this phase introduced (`LEDGERLIGHT_POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `SESSION_SECRET_KEY`, `WEBHOOK_SECRET_ENCRYPTION_KEY`, `S3_SECRET_ACCESS_KEY`) -- injected into each Fargate task as a real secret reference, never a plain environment variable, never baked into an image. |
| Load balancing / TLS | ALB + ACM | One real ALB, two target groups (`api`+`web` share one ALB via host-based or path-based routing; `worker`'s own Dagster webserver port is internal-only, never exposed through the ALB). ACM issues/renews the real TLS certificate; the ALB terminates TLS, forwards plain HTTP to Fargate tasks inside the private subnet. |
| Observability | CloudWatch Logs + Container Insights | Every real container's stdout/stderr (the real structured JSON logs `ledgerlight.api.app` already emits) goes to a real CloudWatch Logs group per service; Container Insights gives real CPU/memory/network metrics with no extra instrumentation. |
| Networking | VPC, private subnets for compute+RDS, public subnets only for the ALB/NAT | Fargate tasks and RDS have no public IP; outbound internet access (e.g. for the real acquisition/ingestion scripts' own HTTP fetches) goes through a NAT gateway. |
| IAM | Least-privilege task roles, one per service | `api`/`worker` share a role that can read the real Secrets Manager secrets + read/write the real S3 bucket; `web` gets no AWS permissions at all (it only ever talks to `api` over HTTP). No service gets `AdministratorAccess` or a wildcard `*` resource. |

## Real request flow

```
Browser
  │ HTTPS (ACM cert)
  ▼
ALB (public subnet)
  │  HTTP, path/host-routed
  ├─────────────► web (Fargate, private subnet) ──► api (Fargate, private subnet, internal)
  └─────────────► api (Fargate, private subnet)        │
                                                         ├──► RDS Postgres (private subnet)
                                                         └──► S3 (via VPC gateway endpoint)

worker (Fargate, private subnet) ──► RDS Postgres + S3, same as api -- never reachable from the ALB
```

## Cost notes (rough, us-east-1, on-demand, not a quote)

- RDS `db.t4g.micro` (single-AZ, dev/staging sizing): ~$15/month compute + ~$0.10/GB-month storage (Phase 6A §10's own re-check found a fresher `ap-south-1` gp3 figure of ~$0.131/GB-month as of Aug 2026 -- both shown, see `docs/ops/cost-per-filing.md`; the difference is noise at this project's real data volumes).
- Fargate: 3 services × 0.25 vCPU / 0.5 GB each, running continuously: ~$25-35/month total at these small sizes.
- ALB: ~$16/month base + a few dollars of LCU usage at low traffic.
- NAT gateway: ~$33/month base + per-GB data processing -- the single largest fixed cost at this scale; a real cost-reduction option for a low-traffic deployment is a NAT instance or VPC endpoints for S3/Secrets Manager to cut NAT data-processing charges (an S3 gateway endpoint is already free and included above).
- S3/Secrets Manager/CloudWatch: usage-based, a few dollars/month at this project's real current data volumes.

Total: roughly **$90-120/month** for a small, continuously-running staging-sized deployment at on-demand rates -- before Reserved/Savings Plan discounts, before any real production traffic/storage growth. Not a committed estimate; real AWS pricing should be checked at apply time.

## Known limitations / explicitly out of scope here

- No multi-region, no read replicas, no autoscaling policies configured (Fargate service desired-count is static in the Terraform below) -- all real, deliberate simplifications for a Phase 5 architecture doc, not a production capacity plan.
- No WAF in front of the ALB -- `docs/security/threat-model.md`'s own "Known, disclosed gaps" already names this.
- Terraform state is configured for local backend only in this phase (see `infra/aws/README.md`) -- a real deployment needs a real remote backend (S3 + DynamoDB lock table) before this is ever applied by more than one person.
