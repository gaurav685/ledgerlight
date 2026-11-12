# Data-source compliance and licence review (Phase 6A §11)

Consolidates: a dated re-check of robots.txt/terms for every currently
enabled data source since the last check (2026-10-25/10-23), a
third-party licence inventory for Python, npm, the two real model
checkpoints, and the container base images, and an explicit
commercial-use / BLOCKED-sources statement. Full historical detail
lives in `docs/data/source-inventory.md` and its machine-readable
mirror `data/manifests/sources.yaml` -- this file is the Phase 6A
consolidation and re-check, not a replacement for either.

## 1. Source re-check (2026-11-06)

**Scope**: every source this project's own acquisition tool actually
fetches from today (`ledgerlight/orchestration/definitions.py`'s
`_KNOWN_ITEM_SOURCES` plus `archives.nseindia.com` and the manual-
download path) -- 16 real hosts. Sources already marked BLOCKED were
not re-tested (re-testing a block that was itself a deliberate,
disclosed judgment call, not a transient technical failure, would not
change the decision).

**Unchanged since the last check** (robots.txt re-fetched, byte-for-
byte or functionally identical): `nse_archives`, `sebi` (robots.txt
*and* `website-policy.html`'s redistribution terms re-read in full),
`ibbi`, `vakrangee_ir`, `jetairways_ir`, `lichousing_ir`,
`pnbhousing_ir`, `spicejet_ir`, `suzlon_ir`, `mastek_ir`.

**Real changes found** (none alter any verdict except one -- see
below; full detail in `data/manifests/sources.yaml`'s
`retest_2026_11_06` block):

| source | what changed | verdict after |
|---|---|---|
| `care` | robots.txt went from fully-open to a populated WordPress-template ruleset | unchanged -- AVAILABLE (the paths this project fetches aren't in the new disallow list) |
| `india_ratings` | robots.txt disappeared (was present+permissive, now 404) | unchanged -- AVAILABLE_WITH_LIMITS (still allow-by-convention; no document was ever fetched from this source) |
| `acuite` | robots.txt disappeared (was empty, now 404) | unchanged -- AVAILABLE_WITH_LIMITS (same reasoning) |
| `brightcom_ir` | robots.txt gained a `Sitemap:` line | unchanged -- AVAILABLE |
| `dmart_ir` | robots.txt gained a `Sitemap:` line | unchanged -- AVAILABLE |
| `thermax_ir` | **real, significant: robots.txt now carries a Cloudflare "Content-Signal" block naming ~30 AI crawlers by name, including `ClaudeBot`, `anthropic-ai`, `Claude-Web`, each `Disallow: /`** | **downgraded: AVAILABLE -> BLOCKED** |

### The Thermax finding, in full

Thermax's robots.txt previously had no rules at all (a template
comment only, `fetched_at: 2026-10-25`). It now reads, in relevant
part:

```
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /
...
User-agent: ClaudeBot
Disallow: /
...
User-agent: anthropic-ai
Disallow: /
...
User-agent: Claude-Web
Disallow: /
```

This project's real acquisition tool identifies itself as
`LedgerlightAcquisition/0.1 (contact: ...)`
(`ledgerlight/acquisition/fetcher.py`) and matches none of the ~30
named entries -- mechanically, the wildcard `Allow: /` still permits
it, and `ledgerlight.acquisition.robots.RobotsCache.can_fetch()` would
still return `True`.

But this project already has a standing precedent for exactly this
situation, set in Phase 0: `crisil` in `data/manifests/sources.yaml`
is marked **BLOCKED specifically because its robots.txt names AI-
crawler user agents (`anthropic-ai`, `claudebot`, `Claude-Web`) even
though CRISIL's own literal UA string doesn't match either** --
*"out of respect for the site's evident intent toward AI-operated
crawling... not merely the letter of the match."* This session is
operated by Claude Code. Applying that same already-established
judgment for consistency: **`thermax_ir` is downgraded from AVAILABLE
to BLOCKED, effective 2026-11-06**, and removed from the live
scheduled source list in `ledgerlight/orchestration/definitions.py`.

This is a disclosed, deliberate judgment call, not a technical
necessity -- the wildcard rule's `use=reference` signal could
plausibly be read as covering this project's actual use (extracting
specific structured facts from one company's own regulatory filing
for a governance-risk model, not bulk-harvesting content to train a
foundation model's weights). This project chooses not to rely on that
reading given the explicit named-crawler block, consistent with how
it already treated CRISIL. **A human reviewer may reasonably reach a
different conclusion**; this is flagged as a real decision point, not
asserted as the only correct one.

The one Thermax annual-report PDF already downloaded in Phase 5
(2026-10-25, before this robots.txt change existed) is not
retroactively affected.

### Explicit BLOCKED-sources statement

The following real sources are **BLOCKED** and this project does not
fetch from them, for the reasons given (full detail in
`data/manifests/sources.yaml`):

- **BSE** (`bseindia.com`) -- Akamai edge bot-mitigation rejects this
  project's honest, identifying User-Agent on every path tested,
  including `robots.txt` itself. Ground rules forbid spoofing a
  browser identity to get around this.
- **NSE** (`www.nseindia.com`, `nsearchives.nseindia.com`) -- same
  Akamai edge behaviour; `robots.txt` itself is permissive on paper,
  but the actual control is a fingerprint/behavioural block this
  project does not attempt to defeat. (`archives.nseindia.com`, a
  genuinely separate host, *is* usable for specific bhavcopy file
  paths -- see `nse_archives`, unaffected by this statement.)
- **CRISIL** (`crisilratings.com`) -- robots.txt explicitly names AI-
  crawler user agents (`anthropic-ai`, `claudebot`, `Claude-Web`);
  this project is operated by an AI agent and chooses not to fetch
  from this host regardless of its own literal UA string not
  matching.
- **ICRA** (`icra.in`) -- edge bot-mitigation serves a browser-
  fingerprinting challenge (Imperva/`barracuda.js`-style) on the very
  first request; ground rules forbid defeating fingerprinting
  challenges.
- **MCA** (`mca.gov.in`) -- returns Access Denied for every request
  regardless of User-Agent. (`data.gov.in`'s Company Master Data
  mirror is a real, unblocked alternative for CIN lookups, not yet
  independently verified -- a disclosed, carried-forward gap, not a
  new finding this phase.)
- **Thermax IR** (`thermaxglobal.com`) -- newly added this phase; see
  above.

No other source in `data/manifests/sources.yaml` is BLOCKED (several
are UNCLEAR, REQUIRES_REGISTRATION, REQUIRES_PAYMENT_OR_LICENCE, or
AWAITING_KEY -- not fetched today, but not blocked on compliance
grounds either; see the manifest for each one's specific reason).

## 2. Third-party licence inventory

### Python dependencies

Generated via `pip-licenses` (added as a real dev dependency this
phase -- `uv add --dev pip-licenses` -- following the same
methodology fix §9 already made for `pip-audit`: an undeclared tool
run via `uv run` audits its own ephemeral environment, not the real
project venv). Full table:
`docs/phase-6/evidence/sec11-python-licences.md` (195 real packages).

```
uv run pip-licenses --format=markdown --with-urls
```

**All permissive (MIT/BSD/Apache-2.0/ISC/PSF) except one real,
significant finding -- now RESOLVED (Phase 6 Correction 2 §5):**

- **`pymupdf` (2.0) is dual-licensed: GNU AGPL-3.0, or Artifex's
  commercial licence.** This project does not hold an Artifex
  commercial licence. `pymupdf` is a real, direct, load-bearing
  dependency (`pyproject.toml`: `"pymupdf>=2.0,<3"`), imported
  directly in `ledgerlight/processing/pdf.py` for real PDF page
  extraction -- part of the application's own served code, not a
  separate out-of-process tool. AGPL-3.0's network-use clause means
  that offering this combined work's functionality to users over a
  network (exactly this platform's intended SaaS deployment model,
  per `docs/deploy/aws-architecture.md`) would require releasing the
  entire combined work's source under AGPL-3.0, unless an Artifex
  commercial licence is obtained first. **This was never previously
  flagged** (Phase 1/2 only mention `pymupdf` by name in unrelated
  contexts -- install-size and page-count cross-checks, never its
  licence).
  **RESOLVED**: rather than obtaining an Artifex commercial licence or
  replacing the library, the user chose (Phase 6 Correction 2 §5,
  licence decision 2026-11-12) to license this whole project under
  **AGPL-3.0-or-later** -- see `LICENSE` (root), `README.md`'s Licence
  section, and `pyproject.toml`'s `license = "AGPL-3.0-or-later"`.
  Licensing the entire combined work under AGPL-3.0 satisfies
  `pymupdf`'s own AGPL-3.0 branch directly: the network-use clause no
  longer presents a conflict, because this project's own source is
  now required to be made available under the same terms regardless.
  No Artifex commercial licence was obtained, and the library was not
  replaced.
- `psycopg`/`psycopg2-binary` (LGPL-3.0 / LGPL) -- used unmodified, as
  a dynamically-linked driver; LGPL explicitly permits this without
  triggering copyleft on the calling application. No concern.
- `bidict`, `certifi`, `pathspec`, `tqdm` carry MPL-2.0 (file-level
  copyleft only, no network-use clause, routinely used in commercial
  Python applications without issue). No concern.

### npm dependencies (frontend)

Generated via `license-checker-rseidelsohn` (run via `npx`, not added
as a permanent dependency -- a one-off audit tool, not something the
app imports). Full summary:
`docs/phase-6/evidence/sec11-npm-licences-summary.log` (332 real
packages).

```
npx --yes license-checker-rseidelsohn --summary
```

```
MIT: 285, Apache-2.0: 22, ISC: 14, BSD-2-Clause: 7, BSD-3-Clause: 2,
Python-2.0: 1, MPL-2.0: 1, CC-BY-4.0: 1, UNLICENSED: 1, CC0-1.0: 1,
BlueOak-1.0.0: 1, 0BSD: 1
```

**All permissive. The two unusual labels, checked individually:**
`UNLICENSED` is this project's own `frontend@0.1.0` root package
(no `license` field set in `package.json` -- normal for an internal,
unpublished app, not a third-party dependency). `Python-2.0` is
`argparse@2.0.1`, an npm package (a JS port, unrelated to Python's own
stdlib module) -- the Python Software Foundation licence is itself
permissive and commercial-use-friendly.

### Model checkpoints

Two real local model checkpoints, both loaded from Hugging Face and
run entirely on CPU, never a hosted/API model:

| model | used for | licence |
|---|---|---|
| `BAAI/bge-small-en-v1.5` | chunk embeddings (`ledgerlight/knowledge/embedding.py`) | MIT -- model card states explicitly: "can be used for commercial purposes free of charge" |
| `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` | zero-shot event classification + the real NLI/entailment verifier (`ledgerlight/knowledge/classifier.py`, `ledgerlight/agent/nli.py`) | MIT |

Both clean, both explicitly commercial-use-permitted. No finding.

### Container base images

| image | licence family |
|---|---|
| `python:3.12.8-slim-bookworm` (pinned by digest) | Debian (permissive) + PSF Python licence |
| `node:24.14.0-bookworm-slim` (pinned by digest) | Debian + Node.js (MIT) |
| `pgvector/pgvector:pg16` | PostgreSQL Licence (permissive, BSD/MIT-family) + pgvector (PostgreSQL Licence) |
| `dxflrs/garage:v2.4.1` | **AGPL-3.0** -- see below |

**Garage (object storage) is AGPL-3.0, but low-risk as used here**:
it runs unmodified, as a separate networked service this project's
code talks to over the S3 API -- it is never forked, patched, or
linked into the application process the way `pymupdf` is. AGPL's
network-use copyleft clause is triggered by distributing a *modified*
version of the AGPL program over a network; using an unmodified
third-party AGPL *service* as infrastructure (the same pattern as
using an unmodified AGPL database server) does not obligate this
project to release its own source. This is a materially different
risk profile from the `pymupdf` finding above, and is noted for
completeness, not flagged as a blocker.

## 3. Explicit commercial-use statement

- **No real blocker exists today for continuing to run this platform
  as a research/internal tool, or for a commercial/SaaS-style
  launch.** `pymupdf`'s AGPL-3.0/commercial dual licence (above) is
  **RESOLVED**, as of Phase 6 Correction 2 §5: this whole project is
  now licensed AGPL-3.0-or-later (`LICENSE`), which satisfies
  `pymupdf`'s own AGPL-3.0 branch directly, including for a networked
  SaaS deployment that serves this platform's PDF-extraction
  functionality to outside users. This was the single most important
  finding of this review when first made, and is carried here as
  resolved, not re-opened.
- **BSE, NSE (except `nse_archives`), CRISIL, ICRA, MCA, and (newly,
  this phase) Thermax IR are BLOCKED** and this project does not
  fetch from them -- see the explicit statement above for the real
  reason in each case. None of these blocks are a licensing
  restriction on content already lawfully acquired before a block
  took effect (e.g. the pre-existing Thermax PDF); they are forward-
  looking acquisition decisions only.
- Every other enabled source's own redistribution terms (SEBI, CARE,
  etc. -- see `data/manifests/sources.yaml`) require asking permission
  before redistributing the documents themselves, which is why only
  *manifests* (metadata) are committed to this repository, never the
  raw downloaded documents -- unchanged from every prior phase.
