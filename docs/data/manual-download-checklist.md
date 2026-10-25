# Manual Download Checklist — BSE/NSE-Only Documents

**Not downloaded by this project.** Per the Phase 0 correction brief, these
items are listed for a human to retrieve via an ordinary browser and drop
into `data/inbox/` (with a `data/inbox/provenance.csv` row each — see
`ledgerlight/acquisition/import_local.py` and `scripts/import_local.py`),
never fetched automatically. Every item below is something we specifically
looked for and could not obtain any other way within Phase 0 — see
`docs/data/source-inventory.md` for why BSE and NSE are BLOCKED for this
project's acquisition tool.

Prioritised: auditor-resignation letters first, then shareholding
patterns around each event date (for `PLEDGE_UP`), then supporting
bhavcopy (only where the automated NSE-archive path, §B1, doesn't cover
the exact date needed).

| # | Company | Document type | Exchange page (starting point) | Flag supported | Why |
|---|---|---|---|---|---|
| 1 | Manpasand Beverages Ltd | Statutory auditor (Deloitte Haskins & Sells) resignation letter, May 2018 | BSE corporate announcements for scrip code 539207 (bseindia.com) | AUD_RESIGN | Company's own site (manpasand.co.in) has no announcements archive page found in Phase 0; the letter is known only via news paraphrase, not a primary PDF |
| 2 | Manpasand Beverages Ltd | Shareholding pattern, quarter ended Mar 2018 (pre-resignation) | BSE/NSE shareholding pattern filing, scrip 539207 | PLEDGE_UP | Needed to establish the pledge baseline just before the AUD_RESIGN event |
| 3 | CG Power and Industrial Solutions Ltd | Original Aug 2019 exchange disclosure of unauthorised transactions / understated liabilities | BSE corporate announcements, scrip 500093 | FORENSIC | cgglobal.com's own site did not surface this specific 2019 disclosure in Phase 0; only a related SEBI document (Sep 2019) was found |
| 4 | CG Power and Industrial Solutions Ltd | Shareholding pattern, quarter ended Jun 2019 (pre-disclosure) | BSE/NSE shareholding pattern filing, scrip 500093 | PLEDGE_UP | Pledge baseline immediately before the forensic-investigation disclosure |
| 5 | Dewan Housing Finance Corp Ltd (DHFL) | Shareholding pattern, quarter ended Sep 2019 (pre-CIRP) | BSE/NSE shareholding pattern filing, scrip 511072 | PLEDGE_UP | dhfl.com's robots.txt disallows all generic crawlers (`Disallow: /`) — see source-inventory.md — so even though the site is reachable, our tool must not fetch from it at all |
| 6 | Jet Airways (India) Ltd | Shareholding pattern, quarter ended Dec 2018 or Mar 2019 (pre-CIRP) | BSE/NSE shareholding pattern filing, scrip 532617 | PLEDGE_UP | Only a Mar-2022 (post-CIRP) shareholding pattern was found on jetairways.com in Phase 0; the pre-event pattern is needed for the pledge trend |
| 7 | Reliance Capital Ltd | Shareholding pattern, quarter ended Sep 2021 (pre-CIRP) | BSE/NSE shareholding pattern filing, scrip 500111 | PLEDGE_UP | reliancecapital.co.in was unreachable in Phase 0 (connection failure); no alternative primary source found for this specific pre-event filing |
| 8 | Reliance Capital Ltd | Original NCLT CIRP admission order, Dec 2021 | IBBI orders/nclt listing (CP (IB) No. 1231/MB/2021) — **not BSE/NSE**, listed here only because it is the one remaining document gap for this company | KMP_EXIT / FORENSIC context | IBBI's own listing is paginated; the specific original admission order was not isolated within the Phase 0 research budget (see docs/data/seed-universe.md) |
| 9 | Future Retail Ltd | Shareholding pattern, quarter ended Mar 2022 (pre-CIRP) | BSE/NSE shareholding pattern filing, scrip 540064 | PLEDGE_UP | futureretail.in's investor pages are JavaScript-rendered; no direct PDF link was isolated in Phase 0 |
| 10 | Future Retail Ltd | Original NCLT CIRP admission order, Jul 2022 | IBBI orders/nclt listing (C.P. (IB)-527(MB)-2022) — **not BSE/NSE** | KMP_EXIT / FORENSIC context | Same pagination gap as Reliance Capital, item 8 |
| 11 | Brightcom Group Ltd | SEBI interim order, 13 Apr 2023 (primary PDF) | sebi.gov.in enforcement orders — **not BSE/NSE** | FORENSIC / RATING_ACT context | The exact `sebi.gov.in` order page/PDF URL was not located within the Phase 0 research budget; only secondary reporting (news coverage) confirms the order number and date |
| 12 | Brightcom Group Ltd | Shareholding pattern, quarter ended Dec 2022 or Mar 2023 (pre-order) | BSE/NSE shareholding pattern filing, scrip 532368 | PLEDGE_UP | Only current annual reports were found on brightcomgroup.com in Phase 0; the specific pre-event shareholding pattern was not isolated |
| 13 | Vakrangee Ltd | Shareholding pattern, quarter ended Mar 2018 (pre-resignation) | BSE/NSE shareholding pattern filing, scrip 511431 | PLEDGE_UP | The auditor-resignation documents (items already obtained from vakrangee.in — see docs/data/seed-universe.md) do not include the shareholding pattern itself |
| 14 | Gensol Engineering Ltd | Shareholding pattern, quarter ended Dec 2024 (pre-order) | BSE/NSE shareholding pattern filing, scrip 542851 | PLEDGE_UP | gel.gensol.in (the company's own investor subdomain) was unreachable (connection failure) in Phase 0; no alternative primary source found |

That is 14 items, well under the 40-item cap — Phase 0's company-IR-site
and SEBI/IBBI research (§B1-B2) closed most of the original gap, so the
genuinely BSE/NSE-only remainder is small. Items 8, 10 and 11 are not
strictly BSE/NSE (they are IBBI/SEBI pagination gaps) but are included
here because they are the same kind of "a human with a browser can find
this, our tool currently cannot" gap, and the brief's own item 8 points at
exactly this case.
