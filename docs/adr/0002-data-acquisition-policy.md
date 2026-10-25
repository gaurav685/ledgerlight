# ADR 0002: Data Acquisition Policy

## Status
Accepted (Phase 0).

## Context
Ledgerlight depends entirely on legitimately-sourced public disclosures.
Phase 0 had to decide, concretely, how the acquisition tool behaves when a
source is reachable in principle but defended by bot-mitigation, or when a
source's own robots.txt signals something narrower than "allow this
project."

## Decisions

1. **Always send an honest, identifying User-Agent** (project name +
   contact email from config), never a browser-spoofed one — even where a
   browser-identified request would succeed and ours does not (observed
   for both BSE and NSE). This is a hard rule, not a per-source judgment
   call: the acquisition tool (`ledgerlight/acquisition/fetcher.py`) has
   no code path to send any other User-Agent string.
2. **robots.txt is checked before every fetch** and a disallow is always
   honoured (`RobotsDisallowed` is raised, never retried, never bypassed).
   Absence of a robots.txt file is treated as "allow" per standard
   convention, but that is a statement about crawling, not about
   redistribution rights — see the licence/redistribution fields on every
   manifest entry, which are tracked separately.
3. **A site's explicit stance toward AI-operated crawlers is treated as
   meaningful even when our literal User-Agent string doesn't match**.
   CRISIL Ratings' robots.txt names `anthropic-ai`, `claudebot`,
   `Claude-Web` and several other AI-crawler identifiers with
   `Disallow: /`. This project's acquisition tool is operated by an AI
   agent (Claude Code) on the user's behalf; a strict robots.txt parser
   would permit our custom-named UA to crawl, but doing so would work
   against the evident intent of that robots.txt. Phase 0 chose not to
   fetch from CRISIL for this reason, flagged explicitly as a judgment
   call for the user to revisit (see "Decisions needing your approval" in
   `docs/data/acquisition-strategy.md`), not as a technical limitation.
4. **Never work around active anti-automation** (CAPTCHA, browser
   fingerprinting challenges, stealth browser automation). ICRA's
   robots.txt endpoint itself returned a fingerprinting-challenge page; no
   further request was attempted against that host.
5. **Downloaded documents are untrusted data.** The acquisition tool
   never executes, interprets, or follows instructions found inside any
   downloaded file — it only hashes, stores, and records metadata about
   it.
6. **Only manifests are committed, never documents.** None of the sources
   in `docs/data/source-inventory.md` grants an explicit, open
   redistribution licence (SEBI requires "proper permission" to
   reproduce; CARE/CRISIL content is copyrighted/all-rights-reserved).
   `data/raw/` is gitignored; `data/manifests/*.jsonl` (URLs, hashes,
   timestamps, licence notes — never content) is committed, so provenance
   is fully reproducible without redistributing third-party material.
7. **Content-addressed storage + hash-based dedup**: files are stored by
   their sha256 under `data/raw/<source>/<year>/`, and a repeat fetch of
   content already on disk is recorded as a skip, not a re-download.

## Addendum (Correction 1, 2026-10-25): OS trust store for TLS verification

`vakrangee.in` failed real downloads with
`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` — its
server does not send a complete certificate chain. Browsers and `curl`
(via Windows schannel) succeed by fetching the missing intermediate
automatically (AIA chasing); a plain certifi-bundle verifier correctly
refuses an incomplete chain. The fetcher now verifies TLS using
`truststore` (the OS trust store, via `ssl.PROTOCOL_TLS_CLIENT`) instead
of httpx's default certifi bundle. **This is not a weakened check** —
certificates are still fully verified, just against the same trust
anchors and chain-completion behaviour a browser uses on this machine,
rather than a static bundled root list. Disabling verification outright
was considered and rejected as a real security downgrade.

## Consequences
- This policy is strict enough that it meaningfully reduced Phase 0's
  seed dataset (BSE/NSE/ICRA/MCA all BLOCKED; CRISIL avoided by choice).
  That reduction is documented, not hidden, in
  `docs/data/seed-universe.md` and `docs/data/feasibility-assessment.md`.
- Any future change to send a different User-Agent, retry past a robots
  disallow, or solve a bot challenge would be a deliberate, reviewed
  change to this ADR — not something a future contributor should do
  silently inside `fetcher.py`.
