# Secret rotation

Phase 5 §8. Every real secret this project defines, and the real
procedure to rotate each -- grounded in `.env.example` and the code
that actually reads each value.

## `LEDGERLIGHT_SESSION_SECRET_KEY`

Read by `ledgerlight.api.auth` to HMAC real session tokens. Rotating
it invalidates every existing session immediately (every signature
becomes unverifiable) -- every logged-in user is forced to log back
in. There is no dual-key grace period in this codebase; plan a
rotation for a low-traffic window.

```powershell
openssl rand -hex 32   # -> set as the new LEDGERLIGHT_SESSION_SECRET_KEY
```

Update `.env` (or the real deployment's secret store -- AWS Secrets
Manager in `infra/aws/secrets.tf`, never committed), then restart the
`api`/`worker` services.

## `LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY`

A Fernet key (`ledgerlight.api.webhooks.encrypt_secret`/
`decrypt_secret`) encrypting every tenant's own webhook signing
secret at rest in the `webhooks` table. **This one is NOT safe to
rotate with a simple env-var swap**: every already-encrypted
`webhooks.secret_encrypted` value was encrypted under the OLD key and
cannot be decrypted with a new one.

Real rotation procedure:

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

1. Generate the new key above.
2. Write a one-off script that, for every `webhooks` row: decrypt
   `secret_encrypted` with the OLD key (`Fernet(old_key)`), re-encrypt
   with the NEW key (`Fernet(new_key)`), update the row -- inside one
   transaction per tenant, using the real app-role session
   (`ledgerlight.api.tenancy.tenant_scope`) so RLS is respected.
3. Only after every row is confirmed re-encrypted, update
   `LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY` to the new value and
   restart `api`/`worker`.
4. Keep the old key available (e.g. a second env var) until step 2 is
   verified against every tenant -- a row missed in step 2 becomes
   permanently undecryptable the moment the old key is discarded.

## `LEDGERLIGHT_APP_DB_PASSWORD` / `LEDGERLIGHT_POSTGRES_PASSWORD`

Real Postgres role passwords (`ledgerlight_app`, `ledgerlight`).
Rotate via a real `ALTER ROLE ... PASSWORD`, then update `.env`/the
real secret store and restart every service that connects (`api`,
`worker`; migrations run as the owner role, so also anything that
later runs `alembic upgrade head`):

```sql
ALTER ROLE ledgerlight_app WITH PASSWORD 'the-new-real-password';
```

No downtime for already-open connections mid-transaction; new
connections after the rotation need the updated `.env` in place
first, or they will fail to authenticate.

## `LEDGERLIGHT_S3_ACCESS_KEY_ID` / `LEDGERLIGHT_S3_SECRET_ACCESS_KEY`

Garage (or any S3-compatible provider in a real deployment) access
keys, read by `ledgerlight.storage.s3_store.ObjectStore`. Garage only
prints a key's secret once, at creation -- rotation means provisioning
a NEW key, not reading back the old one:

```powershell
uv run python scripts/garage_provision.py   # no-ops if a key is already in .env
```

To force rotation: delete the existing key
(`ledgerlight.storage.garage_admin.deprovision_key`, or the admin CLI
directly: `docker exec ledgerlight-phase0-garage-1 /garage key delete
--yes <key-name>`), remove the two env vars from `.env`, then re-run
`garage_provision.py` to create a fresh key and grant it the same
bucket access.

## General rule

Never commit a real secret value anywhere in this repo (gitleaks runs
in `security.yml` and as a local pre-commit hook). `.env.example`
documents every variable's NAME and a dev-only placeholder/default
value; real values live only in `.env` (gitignored) locally, or the
real deployment's secret store in production -- never both.
