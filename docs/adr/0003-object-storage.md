# ADR 0003: Object Storage (Garage replaces MinIO)

## Status
Accepted (Phase 0 correction 1).

## Context
Phase 0 originally pinned `bitnamilegacy/minio:2025.7.23-debian-12-r5` for
local object storage, because MinIO's community edition was removed from
both Docker Hub and quay.io in 2025-2026 and Bitnami's legacy mirror was
the only image confirmed pullable at the time. That image carries
**CVE-2026-40344** (GHSA-9c4q-hq6p-c237, CVSS 8.2-8.8): an authentication
bypass in MinIO's Snowball auto-extract handler (`PutObjectExtractHandler`)
affecting every release from `RELEASE.2023-05-18T00-05-36Z` up to (not
including) `RELEASE.2026-04-11T03-20-12Z`, allowing any user who knows a
valid access key to write arbitrary objects to any bucket without a valid
signature.

The fixed version (`RELEASE.2026-04-11T03-20-12Z`) **was never released as
open-source** — per public reporting (GitHub issues tracking the gap;
no vendor OSS patch commit exists), the fix shipped only in MinIO AIStor,
the commercial closed-source successor. There is no community-edition
release, old or new, to build from source that contains the fix. **Option
1 from the correction brief (build from a pinned upstream release tag with
the fix) is therefore not feasible** — confirmed by search, not assumed.

## Decision
Replace MinIO with **Garage** (`dxflrs/garage:v2.4.1`), an actively
maintained, S3-native object store published by Deuxfleurs with an
official Docker image on Docker Hub. No public CVE advisory was found for
Garage as of this writing (searched GitHub Security Advisories / CISA
bulletins for "Garage" + "deuxfleurs" — nothing specific came back).

SeaweedFS (Option 2's other candidate) was considered but not chosen:
its S3 API is one of several bolted-on protocols (filer/volume/master
architecture) and needs more moving parts to expose a simple S3 endpoint
locally, versus Garage's single S3-native binary.

### What changed technically
- `infra/docker-compose.yml`: `minio` service replaced by `garage`, backed
  by a committed `infra/garage/garage.toml` (single-node, replication
  factor 1, sqlite metadata backend).
- `ledgerlight/config/settings.py`: `minio_endpoint` /
  `minio_root_user` / `minio_root_password` replaced by `s3_endpoint` /
  `s3_region`. **Garage has no static root user/password** (unlike
  MinIO) — access keys are minted per-use via Garage's admin CLI.
- `scripts/infra_check.py`: the object-storage check now (a) runs
  `docker exec <garage> /garage layout assign/apply` once per fresh volume
  (idempotent — skipped if a role is already assigned), (b) provisions a
  throwaway bucket + access key via the Garage CLI, then (c) does the
  actual round-trip — put object, get object, delete object, delete
  bucket — **entirely through a generic boto3 S3 client**, so swapping the
  backend again later would not require touching the round-trip logic,
  only the provisioning step. `DeleteBucket` via the S3 API was verified
  to work against Garage even though `CreateBucket` via the S3 API is
  deliberately not permitted for ordinary keys (bucket creation is a
  deliberate administrative action in Garage's security model).

## Vulnerability scan
`trivy` (v0.76.1, installed user-locally, no sudo, no account) was run
against `dxflrs/garage:v2.4.1` with `--severity CRITICAL,HIGH`:

```
Number of language-specific files   num=0
[report] Supported files for scanner(s) not found.   scanners=[vuln]
[report] No issues detected with scanner(s).          scanners=[secret]
```

`docker history` confirms why: the image is a single `COPY result/bin/garage /`
layer (71.3 MB) with no OS package manager and no embedded dependency
manifest trivy can read — i.e. a scratch image containing only the
statically-linked Rust binary. **This means trivy found zero OS/package
vulnerabilities to report because there is no OS layer to scan, not
because every dependency was checked and found clean** — a true
binary-level SBOM scan of Garage's compiled Rust dependencies was not
performed (no tool for that was available in this environment). Treat
"no CRITICAL/HIGH findings" as accurate for what trivy can see (OS
packages, embedded manifests, secrets), not as a blanket vulnerability-free
certification of the binary itself.

## Consequences
- No known unpatched CVE in the chosen image, versus a confirmed CVSS
  ~8+ auth bypass in the previous one.
- Slightly more setup complexity (Garage's key/bucket provisioning via
  CLI vs. MinIO's static root env vars), isolated entirely inside
  `scripts/infra_check.py` — no change needed elsewhere.
- Phase 1+ is still free to choose a different S3-compatible backend
  (managed cloud storage, SeaweedFS, etc.); this ADR only resolves the
  Phase 0 local-dev choice, consistent with the generic-S3-client design.
