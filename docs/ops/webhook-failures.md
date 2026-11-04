# Webhook delivery failures

Phase 5 §8. How real webhook delivery actually behaves
(`ledgerlight.api.webhooks.deliver_webhook`) and how to diagnose a
real reported failure.

## How a real delivery attempt works

- Up to `DEFAULT_MAX_ATTEMPTS = 3` attempts, backing off
  `DEFAULT_BACKOFF_SECONDS = (1.0, 5.0, 30.0)` seconds between them.
- `validate_webhook_url` (real SSRF protection -- blocks
  private/loopback/link-local/multicast/reserved/unspecified
  addresses) re-runs before **every** attempt, not just at
  registration -- a URL that was safe when registered but now
  resolves somewhere unsafe (DNS rebinding, or the target
  infrastructure changed) fails closed on its next attempt, not just
  its first.
- Every attempt signs the real payload fresh
  (`X-Ledgerlight-Signature`, HMAC-SHA256) with a fresh
  `X-Ledgerlight-Timestamp` -- a receiver verifying the signature
  against an old cached timestamp will always fail; this is by
  design (see `docs/security/controls.md`).
- A 2xx response is the only success condition. Any other status, or
  any `httpx.HTTPError` (timeout, connection refused, TLS failure),
  counts as a failed attempt and is retried (if attempts remain).

## Diagnosing a specific tenant's reported failure

```
GET /v1/webhooks/{webhook_id}/deliveries
```
(`tenant_admin` only) lists real `webhook_deliveries` rows -- each
carries the real `status` (`pending`/`success`/`failed`), attempt
count, and whatever error string `deliver_webhook` captured
(HTTP status, or the real exception text from `httpx`).

```
POST /v1/webhooks/{webhook_id}/test
```
Sends one real, immediate test delivery through the exact same
`deliver_webhook` path production events use -- the fastest way to
reproduce a reported failure interactively rather than waiting for
a real event to trigger one.

## Common real causes, in order of likelihood

1. **The receiver's endpoint is actually down or slow** -- the
   `httpx.post(..., timeout=10.0)` will time out; check the delivery
   row's error string for a timeout message specifically.
2. **URL now fails `validate_webhook_url`** -- most often the
   receiver's DNS now points somewhere private/internal (a
   misconfigured internal redirect, a dev/staging hostname
   accidentally reused). The delivery row's error will be the real
   `UnsafeWebhookUrlError` message naming the blocked address --
   this is almost never a bug in this codebase; it is the control
   doing its job. Confirm with the tenant what the URL should
   actually resolve to before assuming otherwise.
3. **Signature verification failing on the receiver's side** -- ask
   the receiver's team to confirm they verify against
   `X-Ledgerlight-Timestamp` + the raw body bytes (not a
   re-serialized/pretty-printed copy of the JSON, which changes the
   bytes and therefore the signature) using HMAC-SHA256 with the
   secret shown to them once at registration.
4. **The webhook secret was rotated or the webhook re-registered**
   and the receiver still has the old secret -- there is no secret
   rotation endpoint for an individual webhook; re-registering
   (`DELETE` then `POST /v1/webhooks`) issues a new one, which the
   receiver must be given out of band.

## What is NOT retried

After `DEFAULT_MAX_ATTEMPTS` real attempts, the delivery is marked
`failed` permanently -- there is no background job that keeps
retrying a failed delivery later, and no dead-letter requeue for
webhooks specifically (contrast `dead_letters`, which exists for the
ingestion pipeline, not for webhook delivery). A delivery that
exhausts its attempts needs either a fix on the receiver's end and a
fresh `POST .../test`, or waiting for the next real triggering event.
