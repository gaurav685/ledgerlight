# Phase 0 Data-Source Inventory

Full machine-readable detail: `data/manifests/sources.yaml`. This document is
the human-readable narrative of the same findings. Every claim below was
checked by an actual HTTP request (robots.txt fetch, reachability probe, or
real document download) on **2026-10-23**, unless marked UNVERIFIED/gap. No
URL, robots.txt line, or terms-of-use paraphrase here was assumed — each was
opened (the exact URLs are listed under each source in `sources.yaml`).

## Summary table

| Source | Access method | Terms / redistribution | Verified coverage | Verdict |
|---|---|---|---|---|
| BSE | HTML + static PDF paths | Not reached (blocked) | Not verified (blocked) | **BLOCKED** |
| NSE | HTML + `nsearchives.nseindia.com` archives | Not reached (blocked) | Not verified (blocked) | **BLOCKED** |
| SEBI | HTML + PDF | Reproduction needs permission; not an open licence | 2025-04 to 2025-07 (seed sample) | **AVAILABLE** |
| IBBI | HTML + PDF | Generic copyright notice; full terms not read (gap) | 2019-07 to 2024-08 (seed sample) | **AVAILABLE** |
| CRISIL Ratings | HTML | Not reviewed — see note below | Not fetched (declined) | **BLOCKED** (judgment call) |
| ICRA | HTML | Not reached (bot-mitigation challenge) | Not verified (blocked) | **BLOCKED** |
| CARE Ratings (CareEdge) | HTML + PDF | Copyrighted, all rights reserved | 2019-06-05 (seed sample) | **AVAILABLE** |
| India Ratings | HTML | Not reviewed (gap) | Not verified | **AVAILABLE_WITH_LIMITS** |
| Acuité | HTML | Not reviewed (gap) | Not verified | **AVAILABLE_WITH_LIMITS** |
| Infomerics | HTML | Not reviewed (gap) | Not verified | **UNCLEAR** |
| Brickwork Ratings | HTML | Not reviewed (gap); regulatory status disrupted 2022-2024 | Not verified | **UNCLEAR** |
| MCA (mca.gov.in) | HTML portal; data.gov.in bulk mirror | Not reached (blocked) | Not verified | **BLOCKED** (mca.gov.in); data.gov.in mirror unverified |
| Price-data alternatives | n/a | Not reviewed | n/a | **UNCLEAR** |
| Commercial datasets (CMIE, Capitaline, ACE, LSEG, Bloomberg) | Paid subscription | n/a (not attempted) | n/a | **REQUIRES_PAYMENT_OR_LICENCE** |
| Academic datasets | n/a | n/a | n/a | **UNCLEAR** (gap — not identified) |

## Headline finding: exchange bot-mitigation, not robots.txt, is the real gate

Both BSE and NSE present permissive-looking or absent robots.txt files, but
their edge infrastructure (Akamai) rejects requests whose User-Agent is not a
recognised browser string:

- **BSE**: our honestly-identified User-Agent got HTTP 403 on *every* path
  tested, including the homepage, `robots.txt` itself, and static PDF asset
  paths (`xml-data/corpfiling/...`, `bseplus/AnnualReport/...`). A plain
  browser User-Agent reached the homepage (HTTP 200).
- **NSE**: the main site (`www.nseindia.com`) returned HTTP 403 for *both*
  our identifying UA and a browser UA (a broader block). Its bulk-archive
  subdomain (`nsearchives.nseindia.com`) served a bhavcopy ZIP to a browser
  UA (HTTP 200) but the identical request with our identifying UA stalled
  mid-TLS-handshake and timed out.

Per the ground rules, we do not send a fake browser identity to get past
this — that is exactly the "stealth / fingerprint-spoofing" technique the
task explicitly rules out, and it also conflicts with our own policy
(§6/ADR-0002) of always sending an honest, identifying User-Agent. **Both
exchanges are therefore marked BLOCKED for this project's acquisition tool**,
even though a human using an ordinary browser can read the same pages. This
is the single biggest constraint on the Phase 0 seed dataset (see
`docs/data/seed-universe.md`) and on the backfill feasibility estimate (see
`docs/data/feasibility-assessment.md`).

## MCA

`mca.gov.in` itself returned an Akamai "Access Denied" page for every
request tried (both UAs), so it is marked BLOCKED. Secondary sources
describe MCA21 company/director master data as free with no login, filed
documents (incorporation papers, annual returns, financials) costing roughly
Rs 25-100 each via a free account, and a free bulk "Company Master Data" ZIP
(28M+ companies) published on `data.gov.in`. **This pricing/bulk-mirror
claim was not independently verified against a live MCA page in Phase 0** —
record it as a promising Phase 1 lead, not a confirmed fact.

## A judgment call: CRISIL Ratings

CRISIL's `robots.txt` is permissive for a generic `*` User-Agent on most
paths, but it explicitly lists `Disallow: /` for a long roster of named
crawlers — including `anthropic-ai`, `claudebot`, `Claude-Web`, `cohere-ai`,
`GPTBot`, `ChatGPT-User`, `PerplexityBot`, `CCBot`, and `bingbot` among
others. This acquisition tool's own User-Agent string is a custom one, not a
literal match for any of those names, so a strict robots.txt parser would
permit the fetch. **We chose not to fetch from CRISIL anyway.** This project
is being built by an AI agent (Claude Code) on the user's behalf, and the
site's robots.txt shows a clear, repeated intent to exclude AI-operated
crawling specifically. Following the letter of the rule while clearly
working against its evident spirit did not seem like the right call. This is
flagged explicitly as a judgment call the user may want to revisit, not a
technical limitation — see "Decisions needing approval" in
`docs/data/acquisition-strategy.md`.

## ICRA

The very first request — fetching `robots.txt` — returned a JavaScript
bot-fingerprinting challenge page (obfuscated script referencing
`cdn.infisecure.com/barracuda.js`, an Imperva-style challenge), not an actual
robots.txt file. This is active anti-automation at the first touchpoint;
marked BLOCKED, no further requests attempted.

## Rating agencies that were reachable but not used

India Ratings, Acuité, Infomerics and Brickwork Ratings all had permissive
or absent `robots.txt` files and reachable homepages, but Phase 0's time
budget did not stretch to locating and verifying a specific company
rationale URL for any of them, nor to reading their terms-of-use pages.
These are credible candidates for Phase 1 and are marked
`AVAILABLE_WITH_LIMITS` / `UNCLEAR` rather than `AVAILABLE`, specifically
because nothing was actually downloaded from them. Brickwork's SEBI
registration was also disrupted 2022-2024 (cancelled, ordered to wind down,
later allowed to resume) — worth knowing before relying on it as a
rating-rationale source; see `sources.yaml` for citations.

## Commercial and academic datasets

Per instructions, commercial datasets (CMIE Prowess, Capitaline, ACE Equity,
LSEG, Bloomberg) are recorded as licensing alternatives only — no access was
attempted. No open academic dataset on Indian corporate governance,
fraud, or default with an **explicit** licence was identified within the
Phase 0 research budget; this is a gap (nothing was found to include), not a
confirmed absence.
