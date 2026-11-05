# ZAP baseline triage (Phase 6A §2.4)

Real scan: `docker run zaproxy/zap-stable zap-baseline.py -t http://web:3000`
against the real e2e-lite stack, joined to its own real Docker network
(`ledgerlight-phase0_default`). Two runs: before and after the two fixes
below.

**Before** (`docs/phase-6/evidence/sec02-zap-baseline.log`): `FAIL-NEW: 0
WARN-NEW: 6 PASS: 62`

**After** (`docs/phase-6/evidence/sec02-zap-baseline-final.log`):
`FAIL-NEW: 0 WARN-NEW: 4 PASS: 64`

Zero real FAIL findings in either run.

## Fixed

| Finding | Fix |
|---|---|
| `Server Leaks Information via "X-Powered-By" HTTP Response Header Field(s)` [10037] | `poweredByHeader: false` in `next.config.ts` -- Next.js's own default `X-Powered-By: Next.js` header disabled. |
| `Permissions Policy Header Not Set` [10063] | Added a real `Permissions-Policy` header denying every browser feature this app uses none of (camera/microphone/geolocation/payment/usb/interest-cohort). |

Rebuilt the `web` image, redeployed, re-scanned -- both findings confirmed
gone in the second run.

## Accepted (real, low-priority or already-disclosed)

| Finding | Disposition |
|---|---|
| `CSP: script-src unsafe-inline` [10055] | Already fully disclosed with its own real investigation -- `docs/phase-6/evidence/sec02-csp-hydration-bug.md`, `docs/security/threat-model.md`'s own residual-risk entry, `docs/release/release-gates.md`'s own open gap. ZAP independently flagging this confirms the finding, doesn't add anything new. |
| `Non-Storable Content` [10049] | Informational -- ZAP noting pages lack caching headers. For an authenticated analyst app showing per-tenant data, NOT caching is the safer default, not a defect. Accepted, no action. |
| `Modern Web Application` [10109] | Purely informational (ZAP identifying this as an SPA) -- not a finding at all. No action. |
| `Cross-Origin-Embedder-Policy Header Missing or Invalid` [90004] | Real, but low-risk and low-value here: this app embeds no cross-origin resources and is never itself embedded (`frame-ancestors 'none'` already set), so COEP's real purpose (enabling `SharedArrayBuffer`/cross-origin isolation, mitigating Spectre-class attacks on embedded content) doesn't apply. Setting it incorrectly can also break legitimate same-origin resource loading without matching `Cross-Origin-Resource-Policy` headers on every response. Accepted as a real, disclosed gap rather than risk a further rebuild cycle under this session's own real, repeated host memory-pressure kills to chase a low-value header. |

## Real reports

Full HTML/JSON reports: `docs/phase-6/evidence/zap/zap-baseline-report.html`,
`zap-baseline-report.json` (from the final, post-fix run).
