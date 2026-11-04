# Key / session / user revocation

Phase 5 §8. What "revoke" actually does for each real credential type
in this codebase -- not aspirational, grounded in the real code paths.

## API keys

```
DELETE /v1/api-keys/{key_id}
```
(`tenant_admin` only, CSRF-protected). `ledgerlight.api.api_keys.revoke_api_key`
sets `revoked_at` on the real row. `ledgerlight.api.deps._resolve_identity`
checks this on every single request that authenticates with a bearer
API key -- a revoked key is rejected on its very next use, not just at
its next expiry check. There is no separate "key still valid for N
seconds after revocation" grace window.

## User accounts / sessions

```
DELETE /v1/admin/users/{user_id}
```
(`MANAGE_USERS` permission only, CSRF-protected). This sets the real
`memberships.status = 'revoked'` row for that (tenant, user) pair --
it does **not** delete or otherwise touch any already-issued
`sessions` row.

This is still effectively immediate: `ledgerlight.api.deps._resolve_identity`
looks up the caller's membership and requires `status = 'active'` on
**every** request, cookie-authenticated or not. A user whose
membership was just revoked gets a real 401 ("the session's own user
has no active membership") on their very next request, even though
their session row is technically still sitting in the `sessions`
table unexpired. The row itself is cleaned up naturally when it
expires (`DEFAULT_SESSION_LIFETIME`, 12 hours) or when the user next
logs out.

**Known gap, not yet built**: there is no single admin action to
force-expire every one of a specific user's `sessions` rows
immediately. For an urgent case (compromised account, not just an
offboarding), the real, direct remediation today is a manual delete
against the real database:

```sql
DELETE FROM sessions WHERE user_id = '<the real user_id>';
```
Run as the owner role (`ledgerlight`), inside `tenant_scope` for that
user's real tenant_id if running it through the app-role connection
instead. Combine with revoking the membership above so the user also
cannot log back in.

## Session self-revocation (logout)

```
POST /v1/auth/logout
```
(requires the real `X-CSRF-Token` header). `ledgerlight.api.auth.revoke_session`
deletes the caller's own real `sessions` row. This is the only
self-service revocation path -- there is no "log out all my other
sessions" endpoint; a user with multiple active sessions must repeat
this from each one, or an admin must use the manual-delete path above
on their behalf.

## Webhooks

```
DELETE /v1/webhooks/{webhook_id}
```
(`tenant_admin` only, CSRF-protected) -- deletes the real row outright
(no soft-revoke state exists for webhooks, unlike API keys/users).
Any in-flight delivery already past `ledgerlight.api.webhooks.deliver_webhook`'s
own `validate_webhook_url` re-check for that attempt still completes;
nothing cancels an attempt already in progress.
