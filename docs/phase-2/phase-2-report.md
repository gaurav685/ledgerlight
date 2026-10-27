# Phase 2 Report: Knowledge Store, Classification, Extraction and Entity Resolution

Branch: `phase-2/knowledge-extraction-entity-resolution`, from `53d4ba7` (Phase 1 final).
Git policy honoured throughout: every commit is local-only, no remote configured, nothing pushed.

## 1. Summary

Phase 2 adds, over the real Phase 0/1 corpus (not synthetic data):

- A knowledge schema (18 new tables) sharing the Phase 1 database/Alembic history (ADR 0005).
- Taxonomy v1.0: 10 event types, machine-readable YAML, boundary-tested rule thresholds for
  PLEDGE_UP, RESULT_DELAY (citing real SEBI LODR Regulation 33 deadlines), RPT_GROWTH and
  AUDIT_QUAL; GUIDANCE_MISS defined but its detection is explicitly deferred to Phase 3.
- Company/filing bootstrap from real bhavcopy history (5,675 companies, 12,198 identifiers,
  22 filings linked; 12 documents unresolved and documented as a real limitation).
- Page-aware chunking (2,591 chunks over 536 pages).
- Three event classifiers compared honestly on a real silver-labelled split: a rules/keyword
  baseline, TF-IDF+logistic regression, and DeBERTa-v3 zero-shot NLI (CPU) -- no fine-tuning
  attempted (documented threshold not met).
- One real worked structured extractor (AUD_RESIGN) with span-verified evidence; the other
  8 Pydantic schemas exist and are tested but have no real extractor yet (documented, not
  stubbed with invented logic). An optional LLM extractor exists, correctly gated to
  `status="not_run"` since no `LLM_PROVIDER` key is configured here.
- Entity resolution (deterministic identifier -> normalized name -> fuzzy, with conflict
  detection and reversible merges), bootstrapped for real companies and the one real audit
  firm found in extracted events.
- Hybrid retrieval: true BM25 (`rank_bm25`, never conflated with Postgres `ts_rank`), a local
  CPU embedding model (`BAAI/bge-small-en-v1.5`), reciprocal rank fusion, and a point-in-time
  filter applied before ranking -- evaluated on all three methods over a 30-query silver set.
- A Dagster `knowledge_pipeline_job` wiring chunk -> embed -> extract -> resolve-entities in
  the required order, idempotent, run for real.
- A review queue, a label-review CLI (human-only), and a company+time split (dev/validation/test).

**Everything scored above is against SILVER labels** (`label_source=ai_assisted_unreviewed`).
No gold labels exist: 241 items are pending human review. See §13.

**A real bug was found and fixed during this phase's own evaluation run**: the DeBERTa
zero-shot classifier, with `TOKENIZERS_PARALLELISM` unset, triggered a multiprocessing spawn
that resolved to an unrelated Python 3.11 interpreter on this machine, turning a ~20-minute
CPU workload into a 13+ hour stall. Fixed in `ledgerlight/knowledge/classifier.py` (see §10).

Out of scope, per the brief, and not started: GUIDANCE_MISS detection, features/risk
models/scores, the investigation agent, API endpoints, frontend.

## 2. Files changed

108 files changed since `53d4ba7` (Phase 1 final): 7,620 insertions, 28 deletions, across
20 commits (`22c41bb`..`ac4dfad`, see §14 for the full log).

New: `data/taxonomy/taxonomy-v1.0.yaml`; `docs/adr/0005-...md`, `docs/evaluation/phase-2-evaluation.md`,
`docs/knowledge/{schema,taxonomy,extraction,entity-resolution,retrieval}.md`; 38 evidence logs
under `docs/phase-2/evidence/`; `ledgerlight/db/migrations/versions/59ce66e91705_...py`;
`ledgerlight/knowledge/{__init__,chunking,classifier,classifier_eval,embedding,entity_bootstrap,
entity_resolution,evidence,extraction,extraction_pipeline,extraction_schemas,filings,
label_review,label_split,labeling,llm_extraction,models,retrieval,retrieval_eval,review_queue,
taxonomy}.py`; `scripts/{bootstrap_companies,build_bm25_index,chunk_corpus,embed_chunks,
evaluate,extract,label_review,labels_propose,labels_split,link_filings,resolve_entities,
retrieval_eval,review_queue,taxonomy_load,train_classifier}.py`; `tests/{test_chunking,
test_entity_resolution,test_evidence,test_extraction_adversarial,test_extraction_schemas,
test_knowledge_pipeline_integration,test_label_review,test_labeling,test_llm_extraction,
test_retrieval,test_review_queue,test_taxonomy_thresholds}.py`.

Modified: `.gitignore`, `ledgerlight/db/migrations/env.py`, `ledgerlight/ingestion/content_identity.py`,
`ledgerlight/orchestration/definitions.py`, `Makefile`, `pyproject.toml`, `README.md`,
`tests/test_content_identity.py`, `tests/test_upsert_content_identity.py`.

## 3. Commands run, in order

```
git checkout -b phase-2/knowledge-extraction-entity-resolution 53d4ba7
uv run ruff check . && uv run ruff format --check .      # baseline
uv run mypy
uv run pytest
preflight-pdf-page-integrity check (real PyMuPDF vs stored page counts)
# HTML churn fix, then:
git commit -m "phase-1: suppress version churn from volatile HTML markup"
alembic revision --autogenerate -m "phase 2 knowledge schema"   # + manual pgvector-extension fix
alembic upgrade head        # from empty, and against the real db
python scripts/taxonomy_load.py data/taxonomy/taxonomy-v1.0.yaml   # x2 (idempotent)
python scripts/bootstrap_companies.py        # x2 (idempotent)
python scripts/link_filings.py               # x2 (idempotent)
python scripts/chunk_corpus.py               # x2 (idempotent)
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install transformers sentence-transformers scikit-learn rapidfuzz pgvector rank_bm25
python scripts/embed_chunks.py
python scripts/build_bm25_index.py
python scripts/labels_propose.py             # x2 (idempotent)
python scripts/labels_split.py               # x2 (stable)
python scripts/retrieval_eval.py
python scripts/train_classifier.py
python scripts/extract.py                    # x2 (idempotent)
python scripts/resolve_entities.py           # x2 (idempotent)
python scripts/review_queue.py summary
python scripts/review_queue.py list
dagster job list -m ledgerlight.orchestration.definitions
# knowledge_pipeline_job executed via Dagster's Python API, run_id ae693c22-...
python scripts/evaluate.py                   # 1st attempt killed (low memory)
                                              # 2nd attempt stalled 13h+ (TOKENIZERS_PARALLELISM bug)
                                              # fixed in classifier.py, re-run: completed
pytest -m integration                        # 48 passed after fixing 1 pre-existing test-isolation bug
pytest -m corpus
pre-commit run --all-files
gitleaks detect --source . --log-opts="--all"
alembic check                                # 0 drift
git bundle create ../ledgerlight-backups/ledgerlight-phase-2.bundle --all
git bundle verify ../ledgerlight-backups/ledgerlight-phase-2.bundle
```

## 4. Preflight (raw output)

### 4a. PDF page-integrity re-check (stop condition: none triggered)

```
source_id       doc_type                    bytes  pymupdf_pages  stored_pages  match
thermax_ir      annual_report            13358993            217           217     OK
dmart_ir        investor_presentation     3564259             13            13     OK
mastek_ir       shareholding_pattern      2259252              5             5     OK
brightcom_ir    annual_report             1932129            122           122     OK
sebi            sebi_interim_order        1247907             29            29     OK
sebi            sebi_confirmatory_order     978834             33            33     OK
sebi            sebi_related_document      907087             32            32     OK
spicejet_ir     shareholding_pattern       848284              4             4     OK
vakrangee_ir    auditor_resignation_company_update     512753              2             2     OK
jetairways_ir   shareholding_pattern       503265              7             7     OK
care            rating_rationale           495362             17            17     OK
lichousing_ir   shareholding_pattern       492014              8             8     OK
vakrangee_ir    auditor_resignation_letter     250640              1             1     OK
vakrangee_ir    reg30_intimation           237412              1             1     OK
ibbi            nclt_order                 178066             22            22     OK

mismatches: 0
```

No PDF's stored page count is lower than PyMuPDF's -- stop condition not triggered.

### 4b. Dynamic-HTML version-churn fix

Fixed in commit `22c41bb` ("phase-1: suppress version churn from volatile HTML markup"),
before any Phase 2 schema work. `content_identity_bytes()` now hashes normalized main-body
text (script/style stripped, title-duplicate lines excluded) for `text/html` documents. All
4 real churning documents (2 IBBI NCLT pages, pnbhousing_ir, suzlon_ir) collapse to exactly
1 distinct normalized hash each (previously 4-5 distinct hashes per document from CSRF
tokens/randomized DOM ids). `content_sha256` was re-backfilled for all 18 existing
`text/html` `document_versions` rows.

### 4c. Baseline checks before Phase 2 schema work

```
........................................................................ [ 80%]
.................                                                        [100%]
89 passed, 10 deselected in 23.56s
........                                                                 [100%]
8 passed, 91 deselected in 8.85s
..                                                                       [100%]
2 passed, 97 deselected in 16.55s
```

89 unit + 8 integration + 2 corpus = 99 passing. Green baseline confirmed before any
Phase 2 schema work started.

## 5. Test and check results (final, after all Phase 2 work)

Unit tests (`pytest`, non-network, non-integration, non-corpus):
```
183 passed, 49 deselected in 18.99s
```

Integration tests (`pytest -m integration`) -- includes one pre-existing test fixed in this
session (see §10 and §1's summary):
```
...............................................                          [100%]
47 passed, 185 deselected in 9.92s
```

Corpus tests (`pytest -m corpus`):
```
..                                                                       [100%]
2 passed, 230 deselected in 14.14s
```

Total: 183 + 47 + 2 = **232 passing, 0 failing**.

Lint and typecheck:
```
ruff check .                -> All checks passed!
ruff format --check .       -> 134 files already formatted
mypy                         -> Success: no issues found in 73 source files
```

`pre-commit run --all-files`:
```
ruff...................................................................................Passed
ruff-format.............................................................................Passed
Detect hardcoded secrets.................................................................Passed
check for added large files..............................................................Passed
reject staged files under data/raw, data/interim, data/processed........................Passed
mypy (project venv -- avoids a second, heavy isolated env)...............................Passed
```

Full-history secret scan (`gitleaks detect --source . --log-opts="--all"`, using
pre-commit's own managed gitleaks binary since no `gitleaks` is on `PATH` in this
environment), re-run at the end after all commits:
```
27 commits scanned.
scan completed in 1.92s
no leaks found
```

Migration drift check (`alembic check` against the real database, at `HEAD`):
```
No new upgrade operations detected.
```

## 6. Corpus knowledge statistics (real database, this branch's HEAD)

| table | rows |
|---|---|
| companies | 5,675 |
| company_identifiers | 12,198 |
| filings | 22 |
| documents | 443 |
| document_versions | 468 |
| document_pages | 536 |
| chunks | 2,591 |
| entities | 13 (12 company, 1 audit_firm) |
| mentions | 3 |
| entity_links | 3 (2 normalized_name, 1 manual) |
| label_items | 241 (all `ai_assisted_unreviewed`, 0 `human_reviewed`) |
| model_registry | 1 (tfidf-logreg-event-classifier) |
| review_queue | 0 (open or otherwise -- nothing has failed verification or needed review yet) |

Events by type/status:

| event_type | status | count |
|---|---|---|
| AUD_RESIGN | candidate | 4 |

Event fields by validation_status:

| validation_status | count |
|---|---|
| validated | 7 |

Label items by proposed event type (silver):

| event_type | count |
|---|---|
| none | 154 |
| PLEDGE_UP | 28 |
| RPT_GROWTH | 22 |
| AUDIT_QUAL | 8 |
| FORENSIC | 7 |
| ID_EXIT | 6 |
| AUD_RESIGN | 6 |
| RESULT_DELAY | 4 |
| RATING_ACT | 4 |
| KMP_EXIT | 2 |

Label split (company + time, 13 groups): dev 115 / validation 112 / test 14. One company's
217-page annual report dominates the validation group (112 of 112+14 non-dev items) --
reported honestly, not forced to look even (see `docs/evaluation/phase-2-evaluation.md`).

## 7. Evaluation

All metrics below are against SILVER labels. See `docs/evaluation/phase-2-evaluation.md` for
the summary version and limitations.

### 7a. Fine-tuning decision

```
positives per class (dev+validation+test combined): {'RPT_GROWTH': 22, 'FORENSIC': 7,
'PLEDGE_UP': 28, 'ID_EXIT': 6, 'none': 154, 'RESULT_DELAY': 4, 'KMP_EXIT': 2, 'AUDIT_QUAL': 8,
'RATING_ACT': 4, 'AUD_RESIGN': 6}
fine-tune threshold: >= 50 positives/class
max positives in any non-'none' class: 28 -- does NOT meet the threshold. Decision:
zero-shot only, no fine-tuning attempted.
```

### 7b. Classification -- validation (n=112)

```
-- rules_baseline (n=112) --
label             precision   recall       f1  support
AUD_RESIGN            1.000    1.000    1.000        2
KMP_EXIT              1.000    1.000    1.000        1
ID_EXIT               1.000    1.000    1.000        4
RESULT_DELAY          1.000    1.000    1.000        1
AUDIT_QUAL            1.000    1.000    1.000        5
RPT_GROWTH            1.000    1.000    1.000        9
none                  1.000    1.000    1.000       90
macro_f1: 1.000
confusion_matrix (rows=true, cols=pred, order=['AUD_RESIGN', 'KMP_EXIT', 'ID_EXIT', 'RESULT_DELAY', 'AUDIT_QUAL', 'RPT_GROWTH', 'none']):
     2    0    0    0    0    0    0
     0    1    0    0    0    0    0
     0    0    4    0    0    0    0
     0    0    0    1    0    0    0
     0    0    0    0    5    0    0
     0    0    0    0    0    9    0
     0    0    0    0    0    0   90

-- tfidf_lr (n=112) --
label             precision   recall       f1  support
AUD_RESIGN            0.000    0.000    0.000        2
PLEDGE_UP             0.000    0.000    0.000        0
KMP_EXIT              0.000    0.000    0.000        1
ID_EXIT               0.500    0.250    0.333        4
RESULT_DELAY          0.000    0.000    0.000        1
AUDIT_QUAL            1.000    0.200    0.333        5
RPT_GROWTH            0.294    0.556    0.385        9
none                  0.889    0.889    0.889       90
macro_f1: 0.243
confusion_matrix (rows=true, cols=pred, order=['AUD_RESIGN', 'PLEDGE_UP', 'KMP_EXIT', 'ID_EXIT', 'RESULT_DELAY', 'AUDIT_QUAL', 'RPT_GROWTH', 'none']):
     0    0    0    0    0    0    1    1
     0    0    0    0    0    0    0    0
     0    0    0    1    0    0    0    0
     0    0    0    1    0    0    3    0
     0    0    0    0    0    0    0    1
     0    0    0    0    0    1    0    4
     0    0    0    0    0    0    5    4
     0    1    1    0    0    0    8   80

-- deberta_zero_shot (n=112) --
label             precision   recall       f1  support
AUD_RESIGN            0.000    0.000    0.000        2
KMP_EXIT              0.000    0.000    0.000        1
ID_EXIT               0.000    0.000    0.000        4
RESULT_DELAY          0.000    0.000    0.000        1
AUDIT_QUAL            0.286    0.400    0.333        5
RPT_GROWTH            0.000    0.000    0.000        9
none                  0.842    0.944    0.890       90
macro_f1: 0.175
confusion_matrix (rows=true, cols=pred, order=['AUD_RESIGN', 'KMP_EXIT', 'ID_EXIT', 'RESULT_DELAY', 'AUDIT_QUAL', 'RPT_GROWTH', 'none']):
     0    1    0    0    0    0    1
     0    0    1    0    0    0    0
     0    2    0    0    0    0    2
     0    0    0    0    0    0    1
     0    0    0    0    2    0    3
     0    0    0    0    0    0    9
     0    0    0    0    5    0   85

-- DeBERTa confidence distribution (validation) --
  min=0.159 max=0.874 mean=0.343
  (sample sizes per class are too small, 2-28 positives, for a reliable calibration curve --
  not computed; reporting the raw confidence range instead)
```

### 7c. Production classifier selection and test (n=14, reported once)

```
=== Selected production classifier (by validation macro_f1): rules_baseline (macro_f1=1.000) ===

-- rules_baseline_TEST (n=14) --
label             precision   recall       f1  support
AUD_RESIGN            1.000    1.000    1.000        4
PLEDGE_UP             1.000    1.000    1.000        2
ID_EXIT               1.000    1.000    1.000        1
none                  1.000    1.000    1.000        7
macro_f1: 1.000
confusion_matrix (rows=true, cols=pred, order=['AUD_RESIGN', 'PLEDGE_UP', 'ID_EXIT', 'none']):
     4    0    0    0
     0    2    0    0
     0    0    1    0
     0    0    0    7
```

The selected classifier (`rules_baseline`) wins only because it is the same function that
generated the silver labels in the first place -- a known circularity, disclosed explicitly,
not a genuine accuracy claim. `tfidf_lr` (trained independently on `dev`, macro_f1=0.243) and
`deberta_zero_shot` (zero-shot, no fine-tuning, macro_f1=0.175) are the two methods that give
an actually independent read on this corpus, and both are far from 1.0 -- consistent with a
small, imbalanced corpus (6 of 9 non-"none" classes have under 10 validation examples).
All three methods reproduced byte-identical metrics on a second run -- `rules_baseline`/
`tfidf_lr` individually (`docs/phase-2/evidence/evaluate-reproducibility-check.log`), and all
three together via a full second `evaluate.py` run including `deberta_zero_shot`
(`docs/phase-2/evidence/evaluate-full-rerun-diff.log`, see §17.4).

### 7d. Extraction (AUD_RESIGN)

4 events, 7 fields, 0 failed verifications, against the real corpus. Exact/normalized-match
and coverage metrics against gold fields: not computed -- no gold-labelled fields exist yet.

### 7e. Entity resolution

Real bootstrap run: 12 company entities, 1 audit_firm entity ("Price Waterhouse & Co
Chartered Accountants LLP", the real firm named in the real Vakrangee AUD_RESIGN extraction
-- see `docs/knowledge/entity-resolution.md`), 3 mentions all correctly resolved
(2 `normalized_name`, 1 `manual` first-seen bootstrap). Pairwise P/R/F1
against exact-match-only: **not run** -- no labelled mention-pairs exist and the real
corpus's entity surface is too thin (effectively one audit firm, 12 companies with no
observed real name variants) to build a meaningful pair set without inventing cases.

### 7f. Retrieval (30-query silver set)

```
method             n   recall@5  recall@10      mrr
lexical_bm25      30      0.567      0.667    0.330
vector            30      0.333      0.467    0.210
hybrid_rrf        30      0.533      0.633    0.258
```

Lexical BM25 wins outright; reported honestly even though hybrid isn't best (see
`docs/knowledge/retrieval.md` for the discussion of why).

## 8. Model choices, licences, fine-tuning decision

| model | version/checkpoint | licence | role |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | sentence-transformers, 384-dim | MIT | local CPU embeddings |
| `rank_bm25.BM25Okapi` | rank_bm25 0.2.2 | Apache-2.0 | true lexical BM25 (not `ts_rank`) |
| `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` | transformers zero-shot pipeline | MIT | zero-shot NLI classifier |
| `tfidf-logreg-event-classifier` v1 | scikit-learn, trained on this corpus | n/a (locally trained) | second classifier, in `model_registry` with a training-data snapshot hash |
| `rapidfuzz.fuzz.token_sort_ratio` | rapidfuzz 3.14.6 | MIT | entity-name fuzzy scoring |

Fine-tuning: **not attempted**, see §7a. Rationale recorded in
`docs/adr/0005-knowledge-schema-and-models.md`.

## 9. LLM extractor status

`ledgerlight/knowledge/llm_extraction.py`: gated on `LLM_PROVIDER` + a matching
`<PROVIDER>_API_KEY` in the environment. No `LLM_PROVIDER` is configured in this environment,
so every real call in this phase reports `status="not_run"`, cost `$0.00` -- never faked. The
real-provider call path is schema-validated (`extraction_schemas`, `extra="forbid"`), has no
tool access, and intentionally raises `NotImplementedError` rather than being exercised
without a provider actually wired up and tested for real.

## 10. Security and adversarial test results

- `tests/test_extraction_adversarial.py` (6 tests, all passing): injected instructions inside
  document text produce no extra fields and do not bypass evidence verification; invented
  values not present in the cited span are rejected (name/date/number); `<script>` tags are
  never executed.
- Evidence verification is three-way (`validated`/`failed`/`unverifiable`), never binary --
  a field with no checkable text in its span is `unverifiable`, distinct from `failed`
  (actively contradicts the span). A field that fails is still stored
  (`validation_status=failed`), never silently dropped, and queues a review item.
- Real bug found and fixed in `ledgerlight/knowledge/evidence.py`: date verification stripped
  commas from candidate strings but only had comma-requiring month-name patterns, so
  "April 28, 2018" never verified. Fixed by adding comma-less date formats.
- Real bug found and fixed in `ledgerlight/knowledge/entity_resolution.py`: the legal-suffix
  regex `r"\b& co\.?\b"` could never match (`\b` requires a word/non-word transition, and
  neither side of `&` provides one), so "... & Co ..." was never stripped. Fixed to
  `r"&\s*co\.?\b"`.
- Real bug found and fixed in `ledgerlight/knowledge/labeling.py`: a strict-proximity regex
  for AUD_RESIGN missed real matches where a firm name separates subject and verb by more
  than the hardcoded character gap; switched to chunk-wide co-occurrence matching. A second
  bug made 'none' sampling non-idempotent (sampling by unordered query position); fixed by
  ordering the query and sampling deterministically from the chunk's own id.
- Real bug found and fixed in `ledgerlight/knowledge/classifier.py` (this run): see §1's
  summary and the commit "phase-2: fix catastrophic DeBERTa zero-shot slowdown".
- No secrets found in a full git-history scan (`gitleaks detect --source . --log-opts="--all"`,
  27 commits scanned) -- see §5.

## 11. Limitations and known defects

- All classification/extraction/entity-resolution/retrieval metrics are against SILVER labels
  only. No gold review has happened (§13).
- Only AUD_RESIGN has a real structured extractor; the other 8 event types' schemas exist and
  are tested but are not backed by real extraction logic in this phase (would need
  table/layout extraction this phase didn't build) -- documented, not stubbed.
- Entity-resolution pairwise P/R/F1 and extraction exact/normalized-match-vs-gold metrics are
  not run (no labelled pairs/gold fields exist).
- The corpus is small (443 documents, 468 versions, 2,591 chunks); 6 of 9 non-deferred event
  types have under 10 silver-labelled examples -- too small for calibration curves or
  confidence intervals.
- 12 documents (DHFL/Reliance Capital/Future Retail, IBBI/CARE sources) could not be linked to
  a company via NSE/BSE symbol -- no external BSE-code mapping was available (BLOCKED per the
  Phase 0 source inventory), not a code defect.
- `uv.lock` was not regenerated to include the new ML dependencies (`torch`,
  `sentence-transformers`, `transformers`, `scikit-learn`, `rapidfuzz`, `pgvector`,
  `rank_bm25`): `uv` is not on `PATH` in this environment (same gap disclosed in the Phase 1
  report). Dependencies were installed with `pip` directly into the existing `.venv` (bootstrapped
  via `python -m ensurepip`, since the venv had no `pip` either) and added to `pyproject.toml`'s
  dependency list by hand. Anyone re-running `uv sync` on this branch will not get these
  packages until `uv.lock` is regenerated with a working `uv` install.
- The DeBERTa zero-shot evaluation initially stalled for over 13 hours due to the
  `TOKENIZERS_PARALLELISM` bug (§10); fixed, re-run, and completed in this session -- flagged
  here as a real defect that was found and fixed, not hidden.

## 12. Decisions needing user approval

1. Whether to invest in a generic HTML-token-normalization approach for future sources beyond
   the 4 documents already fixed in §4b, versus continuing to fix churn sources case-by-case.
2. Whether entity-resolution pairwise evaluation should stay deferred (not enough real pairs)
   or whether a small set of synthetic/constructed pairs should be built to at least sanity-check
   the thresholds, with that construction clearly labelled as synthetic, not real.
3. The `uv.lock` gap above: regenerate it once a working `uv` binary is available in this
   environment, or treat the `pyproject.toml` dependency list + this report as sufficient
   provenance for now.

## 13. Human gold-review checkpoint

**No gold labels exist.** All 241 silver label items have `label_source=ai_assisted_unreviewed`
and `review_status=pending`; 0 have `review_status` other than `pending`, 0 have
`label_source=human_reviewed`. Every classification/extraction/entity-resolution/retrieval
metric in this report is silver-only and is NOT claimed as ground truth.

To review them yourself:

```sh
make label-review REVIEWER="your name"
# or directly:
uv run python scripts/label_review.py --reviewer "your name" --limit 20
```

241 items are pending review across: PLEDGE_UP (28), RPT_GROWTH (22), AUDIT_QUAL (8),
FORENSIC (7), AUD_RESIGN (6), ID_EXIT (6), RATING_ACT (4), RESULT_DELAY (4), KMP_EXIT (2),
none (154). This tool does not self-review or mark its own labels as gold at any point.

Gold-dependent exit gates (9 and part of 15) are marked **PENDING_HUMAN_REVIEW** below.

## 14. Commit, identity and backup

20 commits, `22c41bb`..`ac4dfad`, all authored by `gaurav685 <gaurav685@gmail.com>`:

```
git log -n 20 --format='%H %an <%ae>' 53d4ba7..HEAD
```

All 20 commit hashes returned `gaurav685 <gaurav685@gmail.com>` -- no other author/committer
identity appears anywhere in this range.

```
git log 53d4ba7..HEAD --format='%B' | grep -i -E "co-authored-by|claude|anthropic|generated with"
-> NONE FOUND
```

No `Co-Authored-By` trailer, no "Generated with" line, no mention of Claude/Anthropic/any AI
agent anywhere in any of the 20 commit messages. No remote is configured on this repository;
nothing has been pushed.

The backup bundle (`../ledgerlight-backups/ledgerlight-phase-2.bundle`) is created and verified
after this report's own commit, so its output necessarily isn't inside this file -- it is
pasted in full in the session's final message (§16) and in `git bundle verify`'s own output.

## 15. Exit gates

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Preflight (branch, baseline checks, PDF integrity, HTML churn fix) | PASS | §4 |
| 2 | Migrations apply from empty and match models with 0 drift | PASS | §5, `alembic check` |
| 3 | Taxonomy v1.0 loaded from file, never hand-inserted, boundary-tested | PASS | §1, 23 threshold tests, `taxonomy-load` idempotent |
| 4 | 3 classifiers compared on validation, once on test, with support counts and fine-tuning justification | PASS | §7a, §7b, §7c |
| 5 | Span-cited extraction with verified evidence, failures queued not promoted | PASS | §7d, §10 |
| 6 | Entity resolution: conflicts queued, merges reversible, evaluated (or honestly not run) | PASS (with documented pairwise-eval gap) | §7e |
| 7 | Point-in-time-correct hybrid retrieval, evaluated on all 3 methods | PASS | §7f |
| 8 | Idempotent/reproducible pipeline, model_registry populated | PASS | §6, Dagster job run, model_registry row |
| 9 | Gold metrics OR PENDING_HUMAN_REVIEW | **PENDING_HUMAN_REVIEW** | §13 |
| 10 | All tests/checks/adversarial tests passing, clean secret scan | PASS | §5, §10 |
| 11 | Committed locally, no AI attribution, bundle verified, nothing pushed | PASS | §14 |

## 16. Final report

This document. Also printed in full in the session's final message.

## 17. Phase 2 Completion Pass (gold evaluation attempt, evidence, reproducibility)

### 17.1 Label status (re-verified against the real database)

```sql
SELECT label_source, COUNT(*) FROM label_items GROUP BY label_source;
 -> ('ai_assisted_unreviewed', 241)
SELECT review_status, COUNT(*) FROM label_items GROUP BY review_status;
 -> ('pending', 241)
SELECT COUNT(*) FROM label_items WHERE reviewer IS NOT NULL OR reviewed_at IS NOT NULL;
 -> 0
```

0 `human_reviewed`, 0 `rejected`, 0 rows with any reviewer/review timestamp set. Per-class gold
counts: **every one of the 9 non-"none" event classes has 0 gold positives** (241/241 silver,
0/241 gold). Field-level gold labels: 0 (`label_item_fields` is empty). Entity-pair gold
labels: 0 (no labelled mention-pair table has ever been populated). Retrieval-query gold
labels: 0 (the 30-query set is `ai_constructed_unreviewed` silver, see §7f).

**A request to run `scripts/label_review.py` on the model's own behalf was declined.** That
script's own docstring and §4/§13 of this report are explicit: only a human running it may set
`label_source=human_reviewed`; "Claude/any automated process must never run this on your
behalf." Having the model review its own AI-generated silver labels would be exactly the
self-review the brief forbids, and would defeat the entire purpose of the silver/gold
distinction. The user agreed to proceed with every part of this completion pass that does not
require gold labels; gold evaluation (§17.2 below) stays honestly unresolved.

### 17.2 Gold evaluation

**Not run.** 0 gold labels of any kind exist (§17.1), so there is no held-out gold split to
evaluate classification, extraction, entity resolution, or retrieval against. No table below
is fabricated or estimated from silver data relabelled as gold. All existing silver-vs-silver
numbers (classification, extraction, entity resolution, retrieval) are unchanged from §6/§7 of
this report and `docs/evaluation/phase-2-evaluation.md` — re-run once more for reproducibility
only (§17.4), not re-evaluated against anything new. Gate 9 stays
**PENDING_HUMAN_REVIEW**, not PARTIAL: PARTIAL would imply partial gold coverage exists to
report a number against, and none does.

### 17.3 Evidence not yet shown

**PDF pages per version, 15 largest PDFs (PyMuPDF vs stored, real query against this branch's
database):**
```
source_id       doc_type                              bytes  stored_pages
thermax_ir      annual_report                       13358993           217
dmart_ir        investor_presentation                3564259            13
mastek_ir       shareholding_pattern                 2259252             5
brightcom_ir    annual_report                         1932129           122
sebi            sebi_interim_order                    1247907            29
sebi            sebi_confirmatory_order                978834            33
sebi            sebi_related_document                  907087            32
spicejet_ir     shareholding_pattern                   848284             4
vakrangee_ir    auditor_resignation_company_update     512753             2
jetairways_ir   shareholding_pattern                   503265             7
care            rating_rationale                       495362            17
lichousing_ir   shareholding_pattern                   492014             8
vakrangee_ir    auditor_resignation_letter              250640             1
vakrangee_ir    reg30_intimation                        237412             1
ibbi            nclt_order                              178066            22
```
Identical to the PyMuPDF-vs-stored preflight check already run in §4a (0 mismatches) — these
are the same 15 PDFs, re-confirmed by direct SQL this session.

**Zero-page versions by mime type:**
```sql
SELECT dv.mime_type, COUNT(*) FROM document_versions dv
LEFT JOIN document_pages dp ON dp.version_id = dv.id WHERE dp.id IS NULL
GROUP BY dv.mime_type;
 -> ('application/zip', 434)
```
Expected, not a defect: bhavcopy ZIP content is parsed into `price_bars`, never
`document_pages` (documented in the Phase 1 report, lines 336/564). No other mime type has any
zero-page version.

**Version-churn fix test results (raw, re-printed from `docs/phase-2/evidence/`):**
```
tests/test_content_identity.py::test_same_inner_content_different_zip_timestamp_has_same_identity_hash PASSED
tests/test_content_identity.py::test_genuinely_different_inner_content_has_different_identity_hash PASSED
tests/test_content_identity.py::test_non_zip_non_html_content_identity_is_the_raw_bytes PASSED
tests/test_content_identity.py::test_multi_entry_zip_falls_back_to_raw_bytes PASSED
tests/test_content_identity.py::test_malformed_zip_falls_back_to_raw_bytes PASSED
tests/test_content_identity.py::test_csrf_token_and_randomized_dom_id_do_not_change_identity_hash PASSED
tests/test_content_identity.py::test_duplicated_title_text_in_body_does_not_change_identity_hash PASSED
tests/test_content_identity.py::test_genuinely_different_html_text_has_different_identity_hash PASSED
tests/test_content_identity.py::test_script_and_style_tags_are_fully_excluded_from_html_identity PASSED
9 passed in 0.58s

tests/test_upsert_content_identity.py::test_jittered_zip_timestamp_does_not_create_a_second_version PASSED
tests/test_upsert_content_identity.py::test_churning_html_csrf_token_does_not_create_a_second_version PASSED
2 passed in 3.91s
```

**Phase 1 §18 items and current status:**

| # | Phase 1 §18 item | Current status |
|---|---|---|
| 1 | 11 spurious ZIP-jitter `DocumentVersion` rows left in place, not merged/cleaned up | **Unchanged** — still not merged; still a pending decision, not made unilaterally, since it has FK implications |
| 2 | 4 dynamic-HTML-token duplicate versions, not fixed, "unlikely to be fixable generically" | **RESOLVED in Phase 2 preflight** — fixed in commit `22c41bb` (§4b); all 4 real documents now collapse to 1 distinct hash each |
| 3 | Retry/dead-letter attempt-tracking proven correct but not wired per-item into live ingestion jobs | **Unchanged** — Phase 2 did not touch ingestion jobs; still deferred |
| 4 | pre-commit `mypy`/`pytest-fast` hooks hardcode the Windows venv path | **Unchanged** — same caveat stands; this environment is still Windows-only |

**Knowledge statistics (events by type/status, fields by validation_status, entities by type,
auto-links vs review items — re-queried this session):**
```
events:        AUD_RESIGN / candidate: 4
event_fields:  validated: 7
entities:      company: 12, audit_firm: 1
entity_links:  normalized_name/active: 2, manual/active: 1   (3 auto-links, 0 in review)
review_queue:  0 open items of any reason_code
```

**Model choices, checkpoints, licences, fine-tuning decision:** unchanged from §8 — repeated
here for completeness: `BAAI/bge-small-en-v1.5` (MIT, embeddings), `rank_bm25.BM25Okapi`
(Apache-2.0, lexical), `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` (MIT, zero-shot),
`tfidf-logreg-event-classifier` v1 (locally trained, in `model_registry`),
`rapidfuzz.fuzz.token_sort_ratio` (MIT, entity fuzzy scoring). Fine-tuning: not attempted,
28 max positives/class vs a 50 threshold (§7a).

**LLM extractor status:** not run. `status="not_run"`, 0 calls, $0.00 cost -- no `LLM_PROVIDER`
key configured in this environment (§9, unchanged).

**Adversarial test names and results (re-run this session):**
```
tests/test_extraction_adversarial.py::test_injected_instructions_yield_no_extra_fields PASSED
tests/test_extraction_adversarial.py::test_injected_instructions_do_not_bypass_evidence_verification PASSED
tests/test_extraction_adversarial.py::test_invented_value_not_present_in_span_is_rejected_name PASSED
tests/test_extraction_adversarial.py::test_invented_value_not_present_in_span_is_rejected_date PASSED
tests/test_extraction_adversarial.py::test_invented_value_not_present_in_span_is_rejected_number PASSED
tests/test_extraction_adversarial.py::test_extractor_never_executes_html_or_script_content_as_instructions PASSED
6 passed in 0.30s
```

**Open review_queue count by reason_code:** 0 open items of any reason_code (table re-queried
directly this session; empty result set).

### 17.4 Reproducibility: re-running `evaluate.py` on the same snapshot

`scripts/evaluate.py` re-run in full (rules_baseline, tfidf_lr, DeBERTa zero-shot, production
selection, test report) against the identical validation/test split and the identical
`tfidf_lr` model (`data/models/tfidf_lr_v1.pkl`, unchanged). Diffed against the prior full run
(`docs/phase-2/evidence/evaluate-run-final.log` vs
`docs/phase-2/evidence/evaluate-run-rerun-for-reproducibility.log`):

```
$ diff docs/phase-2/evidence/evaluate-run-final.log docs/phase-2/evidence/evaluate-run-rerun-for-reproducibility.log
52c52
< Loading weights:   0%|          | 0/202 [00:00<?, ?it/s]Loading weights:  19%|#9        | 39/202 [00:00<00:00, 364.92it/s]Loading weights:  38%|###8      | 77/202 [00:00<00:00, 371.23it/s]Loading weights: 100%|##########| 202/202 [00:00<00:00, 915.10it/s]
---
> Loading weights:   0%|          | 0/202 [00:00<?, ?it/s]Loading weights:  29%|##9       | 59/202 [00:00<00:00, 576.72it/s]Loading weights:  58%|#####7    | 117/202 [00:00<00:00, 438.19it/s]Loading weights: 100%|##########| 202/202 [00:00<00:00, 769.96it/s]
```

The only diff line is the weight-loading progress bar's own throughput readout (`it/s`, a
timing artifact of that one run, not a metric) -- every substantive line (fine-tuning
decision, all three methods' per-class precision/recall/F1/support, all three confusion
matrices, the DeBERTa confidence range, the selected production classifier, and the test-set
report) is byte-identical across both runs, confirming full reproducibility including
`deberta_zero_shot` (frozen weights, non-stochastic greedy decoding), not just the two
already-deterministic methods checked in the prior session
(`docs/phase-2/evidence/evaluate-reproducibility-check.log`).

### 17.5 Final checks (this completion pass)

```
ruff check .           -> All checks passed!
ruff format --check .  -> 137 files already formatted
mypy                    -> Success: no issues found in 73 source files
pytest -q               -> 183 passed, 49 deselected
pytest -q -m integration -> 47 passed, 185 deselected
pytest -q -m corpus      -> 2 passed, 230 deselected
```
Total: 232 passing, 0 failing.

```
pre-commit run --all-files:
ruff...................................................................................Passed
ruff-format.............................................................................Passed
Detect hardcoded secrets.................................................................Passed
check for added large files..............................................................Passed
reject staged files under data/raw, data/interim, data/processed........................Passed
mypy (project venv -- avoids a second, heavy isolated env)...............................Passed
```

```
gitleaks detect --source . --log-opts="--all":
28 commits scanned.
scan completed in 1.43s
no leaks found
```

```
alembic check:
No new upgrade operations detected.
```

### 17.6 Exit gates, re-marked (completion pass)

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Preflight (branch, baseline checks, PDF integrity, HTML churn fix) | PASS | §4, §17.3 |
| 2 | Migrations apply from empty and match models with 0 drift | PASS | §17.5 |
| 3 | Taxonomy v1.0 loaded from file, never hand-inserted, boundary-tested | PASS | §1, 23 threshold tests |
| 4 | 3 classifiers compared on validation, once on test, support counts + fine-tuning justification | PASS (silver only) | §7a-c, §17.4 |
| 5 | Span-cited extraction with verified evidence, failures queued not promoted | PASS (silver only) | §7d, §17.3 |
| 6 | Entity resolution: conflicts queued, merges reversible, evaluated (or honestly not run) | PASS, pairwise eval honestly not run | §7e, §17.3 |
| 7 | Point-in-time-correct hybrid retrieval, evaluated on all 3 methods | PASS (silver only) | §7f |
| 8 | Idempotent/reproducible pipeline, model_registry populated | PASS | §17.1 model_registry row, §17.4 |
| 9 | Gold metrics OR PENDING_HUMAN_REVIEW | **PENDING_HUMAN_REVIEW** -- 0 gold items exist, every class 0 positives; not PARTIAL (no partial gold coverage to report) | §17.1, §17.2 |
| 10 | All tests/checks/adversarial tests passing, clean secret scan | PASS -- 232 tests, 6 adversarial tests, clean gitleaks | §17.3, §17.5 |
| 11 | Committed locally, no AI attribution, bundle verified, nothing pushed | PASS | §14, this section's own commit |

No gate regressed. Gate 9 is unchanged from the original report (`PENDING_HUMAN_REVIEW`) --
this completion pass could not move it to PASS or PARTIAL because the one and only thing that
would have moved it (a real human running `label_review.py`) did not happen in this session,
and the model correctly declined to perform that step itself.

## 18. 80-item review sample (filling per-class gold-coverage gaps)

Gaurav reviewed 38 event-level label items (real counts, re-verified against the database:
26 accepted, 10 corrected, 2 rejected; 0 in the `test` split -- 21 `dev`, 17 `validation`).
Four classes had 0 gold-counted items at all (`ID_EXIT`, `RATING_ACT`, `RESULT_DELAY`,
`AUDIT_QUAL`), and `KMP_EXIT`/`FORENSIC`/`RPT_GROWTH`/`AUD_RESIGN`/`PLEDGE_UP` were all below
the 4-per-class target.

`ledgerlight/knowledge/label_sample.py` builds a deterministic 80-item sample (seed 42): the
38 already-reviewed items unchanged, plus up to 42 new pending items selected to fill each
class's gap -- `test` split preferred, `validation` as fallback, `dev` never used for new
items (reviewing more training-split items wouldn't grow gold *evaluation* coverage). When a
class's per-class minimum is satisfied before the 42-item budget is used up, the remaining
budget is filled by round-robining the same class order/split preference until the budget or
the eligible pool is exhausted -- in this corpus that overflow lands mostly on `none`, the
only class with a large remaining pool; disclosed here, not hidden.

Real composition (`scripts/build_label_sample.py`,
`docs/phase-2/evidence/build-label-sample-run1.log`):

```
class         already   new  total  new_test  new_val
-----------------------------------------------------
AUD_RESIGN          1     5      6         4        1
PLEDGE_UP           2     2      4         2        0
KMP_EXIT            1     1      2         0        1
ID_EXIT             0     5      5         1        4
RATING_ACT          0     0      0         0        0
RESULT_DELAY        0     1      1         0        1
AUDIT_QUAL          0     5      5         0        5
FORENSIC            1     0      1         0        0
RPT_GROWTH          1     8      9         0        8
none               32    15     47         7        8
```

`RATING_ACT` and `FORENSIC` stay under the 4-item minimum: both have **zero** items in the
`test`+`validation` splits combined (all their silver items landed in `dev` when the original
company+time split was built in Phase 2) -- there is nothing eligible to add for them without
reaching into `dev`, which this design deliberately does not do. `KMP_EXIT` (2 of 4) and
`RESULT_DELAY` (1 of 4) are also short, for the same reason (thin test+validation pools).
These four classes are flagged `under_minimum_classes`, not silently padded.

Manifest: `data/manifests/label-review-sample-42.jsonl` (80 lines, `{label_item_id, split}`
only -- no document text, no proposed/corrected codes, nothing that could let a reviewer or
this report infer the "right answer" from the manifest itself).

### 18.1 Sample-mode review CLI

`scripts/label_review.py --reviewer "Gaurav" --sample-size 80` (auto-discovers the one
manifest under `data/manifests/` with exactly 80 lines) or
`--sample-manifest data/manifests/label-review-sample-42.jsonl` explicitly. Presents only the
pending items from the manifest (the 42 new ones, shrinking as they're decided), and prints
progress as `done/total` (`38/80` before the first new decision, counting up to `80/80`).
Smoke-tested this session with an immediate `q` (quit) on the very first prompt -- confirmed
it shows `38/80 done, 42 pending item(s) to show` and made zero database writes (verified: the
reviewed-item count stayed at 38 before and after). No item was reviewed, decided, or altered
by this session.

### 18.2 Skip persistence

`review_status` gains a `skipped` value (migration `61708ede1bba_add_review_note_to_label_items`
also adds a nullable `review_note` text column). `apply_review_decision(..., "skip", ...,
note=...)` persists `review_status='skipped'`, `reviewer`, `reviewed_at`, and the optional
note -- but deliberately does **not** set `label_source='human_reviewed'`, since a skip is a
non-decision, not a judgement about correctness, and must never promote a label to GOLD.
Skipped items are excluded from `pending_label_items`'s result (same as accepted/corrected/
rejected), which is what makes a second run of the sample CLI resume with whatever's still
actually pending.

### 18.3 Coverage gap: field/entity-pair/retrieval-query review types don't exist

`label_item_fields` has 0 rows (schema exists, never populated); there is no entity-pair
review table and no retrieval-query review table in this schema at all. Gold evaluation for
extraction (field-level accuracy), entity resolution (pairwise P/R/F1), and retrieval
(Recall@k/MRR against a human-reviewed query set) therefore has no review mechanism to build
on yet, even once event-level gold coverage grows. **This is a real, disclosed gap, not built
in this change** (explicitly out of scope per this task's own instructions) -- deferred to
Phase 6. See `docs/release/release-gates.md` for the release-blocking framing of this gap.

### 18.4 Tests added

`tests/test_label_sample.py` (6 tests): deterministic sampling given the same seed, different
seeds can select differently, the 38-equivalent already-reviewed items are included with
decisions untouched, a class already at its minimum gets 0 new items, `test` split is
exhausted before `validation` is touched, `dev` is never used for new items (and the class is
flagged `under_minimum`).

`tests/test_label_review.py` (+5 tests, 1 pre-existing test fixed): skip persists as
`skipped` without promoting to gold; skip without a note is allowed; a skipped item is
excluded from a subsequent pending query (distinguishing it from an untouched item); a second
`pending_label_items` call excludes an item decided since the first call (resume). The
pre-existing `test_gold_label_counts_...` test was failing against the real database (the same
class of test-isolation bug fixed earlier in this branch: `gold_label_counts` queried the
whole table, which now includes Gaurav's real 38 reviews) -- fixed by adding the same
`only_label_item_ids` scoping parameter already used elsewhere in this codebase, not by
changing the production logic.

### 18.5 Checks

```
ruff check .            -> All checks passed!
ruff format --check .   -> 141 files already formatted
mypy                     -> Success: no issues found in 75 source files
pytest -q                -> 183 passed, 59 deselected in 15.52s
pytest -q -m integration -> 57 passed, 185 deselected in 11.78s
pytest -q -m corpus      -> 2 passed, 240 deselected in 11.75s
```
Total: 242 passing (up from 232; +10 new tests, 0 regressions).

```
pre-commit run --all-files:
ruff...................................................................................Passed
ruff-format.............................................................................Passed
Detect hardcoded secrets.................................................................Passed
check for added large files..............................................................Passed
reject staged files under data/raw, data/interim, data/processed........................Passed
mypy (project venv -- avoids a second, heavy isolated env)...............................Passed
```

```
gitleaks detect --source . --log-opts="--all":
29 commits scanned.
scan completed in 1.82s
no leaks found
```

```
alembic check:
No new upgrade operations detected.
```

Gate 9 is still `PENDING_HUMAN_REVIEW` -- this change only builds the sample and the tooling;
it does not review anything. 42 new items are now queued for Gaurav in the manifest, in
addition to whatever of the original 203 he chooses to review outside the sample.

## 19. Gold evaluation executed (80-item review complete)

Gaurav completed all 80 sample items (verified against the database, not taken on claim):
50 accepted, 25 corrected, 2 rejected, 3 skipped.

### 19.1 Label status

By decision:
```
SQL: SELECT review_status, COUNT(*) FROM label_items WHERE reviewer ILIKE 'gaurav' GROUP BY review_status;
corrected: 25   skipped: 3   rejected: 2   accepted: 50
```

By split (all 80, including skipped):
```
SQL: SELECT split, COUNT(*) FROM label_items WHERE reviewer ILIKE 'gaurav' GROUP BY split;
validation: 45   dev: 21   test: 14
```
45 validation = 42 decided + 3 skipped (all 3 skips are validation-split `AUDIT_QUAL` items).

By final event class (decided, non-rejected, non-skipped -- corrected items count under their
corrected code; n=75):
```
SQL: SELECT COALESCE(corrected_event_type_code, proposed_event_type_code) AS final_class, COUNT(*)
     FROM label_items WHERE reviewer ILIKE 'gaurav' AND review_status NOT IN ('rejected','skipped')
     GROUP BY final_class ORDER BY 2 DESC;
none: 58   AUD_RESIGN: 5   RPT_GROWTH: 4   KMP_EXIT: 4   PLEDGE_UP: 3   ID_EXIT: 1
```

Skipped items (3, all excluded from every metric below): all `AUDIT_QUAL`-proposed,
validation split. Notes: `"s"`, `"s"`, and one with no note. These are not informative review
content -- quoted here in full since they're each under 15 words (one character), not
truncated.

### 19.2 Silver-label error rate

Overall, all 77 decided items (any split): **error rate = (corrected + rejected) / decided =
27 / 77 = 0.351**, bootstrap 95% CI [0.247, 0.455] (10,000 resamples, seed 42).

Per proposed event type (decided count, errors, rate, CI; `n<5` flagged insufficient support):
```
class          decided errors   rate  ci_low ci_high  flag
OVERALL             77     27  0.351   0.247   0.455
none                41      4  0.098   0.024   0.195
RPT_GROWTH          12      8  0.667   0.417   0.917
PLEDGE_UP            7      4  0.571   0.143   0.857
ID_EXIT              6      5  0.833   0.500   1.000
AUD_RESIGN           6      2  0.333   0.000   0.667
AUDIT_QUAL           2      2  1.000   1.000   1.000  insufficient support (n<5)
FORENSIC             1      1  1.000   1.000   1.000  insufficient support (n<5)
KMP_EXIT             1      0  0.000   0.000   0.000  insufficient support (n<5)
RESULT_DELAY         1      1  1.000   1.000   1.000  insufficient support (n<5)
RATING_ACT           0      0    n/a     n/a     n/a  insufficient support (n=0, never reviewed)
```

Confusion table, proposed -> final (accepted + corrected only; rejected shown separately since
a rejection has no valid final class):
```
proposed       -> final class (count)
AUD_RESIGN     -> AUD_RESIGN:4  KMP_EXIT:1  none:1                    (decided: 6)
PLEDGE_UP      -> PLEDGE_UP:3  none:4                                 (decided: 7)
KMP_EXIT       -> KMP_EXIT:1                                          (decided: 1)
ID_EXIT        -> ID_EXIT:1  KMP_EXIT:1  none:4                       (decided: 6)
RATING_ACT     -> (never reviewed)                                    (decided: 0)
RESULT_DELAY   -> none:1                                              (decided: 1)
AUDIT_QUAL     -> none:2                                               (decided: 2)
FORENSIC       -> REJECTED:1                                          (decided: 1)
RPT_GROWTH     -> RPT_GROWTH:4  none:8                                (decided: 12)
none           -> none:38  KMP_EXIT:1  AUD_RESIGN:1  REJECTED:1      (decided: 41)
```

**Most common error patterns** (no notes exist on corrected/rejected items -- the CLI only
ever prompts for a note on `skip`, so there is nothing informative to quote beyond the 3 skip
notes already shown in §19.1):
- The keyword-rule proposer's dominant failure mode is **false positives on positive classes**:
  `ID_EXIT` (83.3% error), `RPT_GROWTH` (66.7%), `PLEDGE_UP` (57.1%), and `AUDIT_QUAL` (2/2,
  insufficient support) are all majority-wrong, and in every one of those corrections the
  reviewer's final class was `none` -- the proposer is firing on keyword co-occurrence in
  boilerplate/unrelated text (e.g. routine audit-report language for `AUDIT_QUAL`, generic
  director-related text for `ID_EXIT`) without the real event actually being present.
- `none` itself is comparatively well-calibrated (9.8% error, tight CI [2.4%, 19.5%], n=41) --
  the proposer is good at recognizing when nothing is happening, just unreliable at naming
  *which* positive event type when something keyword-matches.
- 2 false negatives exist (proposer said `none`, reviewer found a real event: one corrected to
  `AUD_RESIGN`, one to `KMP_EXIT`) -- rarer than false positives, but real, meaning the
  proposer also misses genuine events, not just over-fires.
- `AUD_RESIGN` (the one event type with a real extractor) sits at 33.3% error across dev+
  validation -- better than the other positive classes, but far from clean; see §19.3 for how
  this differs sharply from `AUD_RESIGN`'s performance on the frozen test split specifically.

### 19.3 Classifier gold metrics -- frozen TEST split only (n=14)

Never used for tuning; reported once. Gold final classes in test: `none` (9), `AUD_RESIGN`
(4), `PLEDGE_UP` (1) -- every other class has 0 gold positives in test.

```
-- rules (n=14) --
label        precision recall    f1 support  F1_95%CI
AUD_RESIGN       1.000  1.000 1.000       4  [1.000, 1.000]
PLEDGE_UP        0.500  1.000 0.667       1  [0.000, 1.000]  insufficient support (n<3)
none             1.000  0.778 0.875       9  [0.625, 1.000]
macro_f1: 0.635   macro_f1 95% CI: [0.432, 1.000]

-- tfidf_lr (n=14) --
label        precision recall    f1 support  F1_95%CI
AUD_RESIGN       0.000  0.000 0.000       4  [0.000, 0.000]
PLEDGE_UP        0.333  1.000 0.500       1  [0.000, 1.000]  insufficient support (n<3)
none             0.600  0.667 0.632       9  [0.308, 0.833]
macro_f1: 0.283   macro_f1 95% CI: [0.111, 0.544]

-- deberta_zero_shot (n=14) --
label        precision recall    f1 support  F1_95%CI
AUD_RESIGN       1.000  1.000 1.000       4  [1.000, 1.000]
PLEDGE_UP        0.000  0.000 0.000       1  [0.000, 0.000]  insufficient support (n<3)
none             0.889  0.889 0.889       9  [0.700, 1.000]
macro_f1: 0.472   macro_f1 95% CI: [0.417, 1.000]
```
(Bootstrap 95% CIs: 2000 resamples, seed 42, resampling the 14 paired gold/prediction tuples.
Raw predictions: `docs/phase-2/evidence/gold-test-predictions.json`; full command output and
confusion matrices: `docs/phase-2/evidence/gold-validation-metrics.log`'s sibling test-side
computation and this section.)

`ID_EXIT`, `KMP_EXIT`, `RATING_ACT`, `RESULT_DELAY`, `AUDIT_QUAL`, `FORENSIC`, `RPT_GROWTH`
all have **0 gold positives in test** -- not evaluated, not estimated.

**Validation-split gold, reported separately and clearly labelled (n=41 -- the subset Gaurav
actually reviewed, NOT the full 111-item mixed silver+gold validation split used by the
standard `evaluate` pipeline in §19.4):**
```
-- rules (n=41) --   macro_f1: 0.312
-- tfidf_lr (n=41) -- macro_f1: 0.195
-- deberta_zero_shot (n=41) -- macro_f1: 0.399
```
Full per-class tables: `docs/phase-2/evidence/gold-validation-metrics.log`.

**Does this change classifier selection?** On this n=41 gold-only validation subset,
`deberta_zero_shot` (0.399) edges out `rules_baseline` (0.312) -- a different winner than the
standard pipeline's selection. **Selection is NOT changed.** Reasoning: the production
selection mechanism (`scripts/evaluate.py`, §19.4) uses the full 111-item validation split,
which is the authoritative, reproducible, already-documented selection criterion; the n=41
gold-only slice is thin, has a different class mix (no `AUD_RESIGN` or `PLEDGE_UP` positives
at all), and switching the selection mechanism on a small favorable subset would itself be a
form of tuning-on-a-subset this report is trying to avoid. The gold-only result is reported as
a signal to watch as more gold accumulates, not acted on now. This is documented, not silent.

### 19.4 Silver correction impact

**19.4.1 Estimated false positives among currently stored events.** Only `AUD_RESIGN` has any
stored events (4, all `status=candidate`, per §6/§17.3). Applying `AUD_RESIGN`'s §19.2 error
rate (0.333, CI [0.000, 0.667]) to those 4 events: **expected false positives ~= 1.3, 95% CI
[0.0, 2.7]**. No other event type has any stored events to apply a rate to.

**19.4.2 Recommendation (not implemented):** none of the 9 positive event types currently
clear a bar I'd call "reliable enough to feed Phase 3 features as ground truth":
- `ID_EXIT` (83.3% error), `RPT_GROWTH` (66.7%), `PLEDGE_UP` (57.1%) are all majority-wrong by
  measured rate with real support (n>=6) -- **need stricter detection before Phase 3 use.**
- `AUDIT_QUAL`, `FORENSIC`, `KMP_EXIT`, `RESULT_DELAY`, `RATING_ACT` have **insufficient
  support** (n<5, three of them n<=1) -- not yet judgable either way.
- `AUD_RESIGN` is the most promising (33.3% error, the one type with a real extractor, and a
  clean 100% precision/recall on the frozen test split specifically) -- but its broader dev+
  validation error rate (33%, CI up to 67%) shows the *silver proposal* stage still produces
  real errors outside the small test sample. Recommend: AUD_RESIGN output sourced from
  test-split-equivalent evidence can be trusted with lighter review; AUD_RESIGN output from
  elsewhere in the corpus should still get a human spot-check before Phase 3 consumption,
  not be treated as clean ground truth yet.
- `none` is the one well-supported, low-error class (9.8%, CI [2.4%, 19.5%]) -- useful as a
  negative filter, not as a source of positive-event ground truth (it has none to contribute).

**19.4.3 Retraining on dev-split gold corrections.** `scripts/train_classifier.py` already
supports this with no new code: `classifier_eval.load_split` has always used
`corrected_event_type_code` when set and excluded `rejected` items, for whichever split it
loads -- so simply re-running the existing retrain command on the `dev` split now picks up
Gaurav's 21 real dev-split reviews automatically. Retrained:
```
$ python scripts/train_classifier.py
dev examples: 114   (was 115 -- one dev item, originally silver, is now reviewer-rejected
                      and correctly excluded by load_split)
training_data_snapshot_hash: 2c69d820f0e1ba0a460703abbefabaaf3177001240db6ed83402ae5415ceba8a
                      (differs from the pre-review hash 303c959d..., confirming the training
                      set genuinely changed)
```
Old model backed up before retraining; `model_registry` row updated in place (same
`model_name`/`model_version`, new `artifact_hash`/`training_data_snapshot_hash`) --
`docs/phase-2/evidence/train-classifier-after-gold-dev-corrections.log`.

**Before/after on validation -- two comparisons, because this is actually two different
changes that happened at once, and conflating them would be misleading:**

*(a) The "official" before/after* (what running `evaluate` literally shows, old vs new): old
run used the pre-retrain model against the then-pure-silver 112-item validation split
(`tfidf_lr` macro_f1 = 0.243, `docs/phase-2/evidence/evaluate-run-final.log`); the new run uses
the retrained model against the now-partially-gold-corrected 111-item validation split (1
fewer item: one validation `none` proposal is now reviewer-rejected and excluded) --
`tfidf_lr` macro_f1 = 0.202 (`docs/phase-2/evidence/evaluate-run-after-gold-corrections.log`).
**This -0.041 move is NOT purely a retraining effect** -- see (b).

*(b) Isolated model-only comparison* (same current, gold-corrected validation labels for
both, varying only the model -- raw output:
`docs/phase-2/evidence/tfidf-before-after-retrain-isolated.log`):
```
tfidf_OLD_MODEL (pre-gold-dev-retrain) vs CURRENT validation labels: macro_f1 = 0.199
tfidf_NEW_MODEL (post-gold-dev-retrain) vs CURRENT validation labels: macro_f1 = 0.202
```
Retraining on 21 dev-split gold corrections moved validation macro_f1 by **+0.003** -- a
negligible, likely-noise-level change, not a regression and not a meaningful improvement.
**Most of the (a) drop (0.243 -> ~0.199-0.202) is explained by the validation *labels*
themselves changing** (silver mislabels corrected by review, one item excluded as rejected),
not by the retrained model performing worse.

A second, more striking silver-correction impact shows up in the *same* before/after: the
rules-baseline's macro_f1 **collapsed from 1.000 (pure silver, perfectly circular -- it IS the
labelling function) to 0.441** the moment real gold corrections entered the validation split
(§19.3/§19.4.1's confusion matrices and the full-validation run in
`evaluate-run-after-gold-corrections.log`). This is the clearest, most concrete demonstration
in this report of why the brief insisted silver metrics never be reported as real accuracy.

**Test stays untouched:** the test-split report in both the before and after `evaluate` runs
is byte-identical (`AUD_RESIGN`/`PLEDGE_UP`/`none`, macro_f1 0.635 both times) -- test
composition and gold labels didn't change between these runs, and nothing here was tuned
against it.

### 19.5 Gaps and evidence not yet shown (re-printed, still current)

**Field/entity-pair/retrieval review gap** (verbatim from §18.3 / `docs/release/release-gates.md`):
unchanged -- `label_item_fields` still has 0 rows; no entity-pair or retrieval-query review
table exists. Still deferred to Phase 6; not built in this change either.

**Preflight raw output** (unchanged since §4; re-verified this session):
- 15 largest PDFs, PyMuPDF vs stored pages: 0 mismatches (§4a, re-confirmed by direct SQL in
  §17.3).
- Zero-page versions by mime type: `application/zip: 434` (expected -- bhavcopy content goes
  to `price_bars`, never `document_pages`; Phase 1 report lines 336/564). No other mime type
  has zero-page versions.
- Version-churn fix test result (re-run this session):
  ```
  tests/test_content_identity.py -- 9 passed
  tests/test_upsert_content_identity.py -- 2 passed
  ```

**Knowledge statistics** (re-queried this session, unchanged from §6/§17.3 -- review activity
touches only `label_items`, not events/fields/entities):
```
events:        AUD_RESIGN / candidate: 4
event_fields:  validated: 7
entities:      company: 12, audit_firm: 1
entity_links:  normalized_name/active: 2, manual/active: 1   (3 auto-links, 0 in review)
review_queue:  0 open items of any reason_code
```

**Model checkpoints, versions, licences, fine-tuning decision** (unchanged from §8, restated):
`BAAI/bge-small-en-v1.5` (MIT), `rank_bm25.BM25Okapi` (Apache-2.0),
`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` (MIT), `tfidf-logreg-event-classifier` v1
(locally trained, `model_registry` updated this session with a new training-data snapshot
hash), `rapidfuzz.fuzz.token_sort_ratio` (MIT). Fine-tuning: still not attempted -- even after
adding the dev-split gold corrections, the max positives in any non-`none` class across
dev+validation+test combined is 24 (`PLEDGE_UP`), still under the 50-positive threshold.

**Adversarial test results** (re-run this session): 6/6 passing, same tests as §10/§17.3.

**Open review_queue count by reason_code:** 0 (re-queried this session; empty result set).

### 19.6 Reproducibility

`scripts/evaluate.py` re-run on the exact same snapshot (same `model_registry` row, same
label_items state) and diffed:

```
$ diff docs/phase-2/evidence/evaluate-run-after-gold-corrections.log docs/phase-2/evidence/evaluate-run-after-gold-repro-check.log
48c48
< Loading weights: ... 364.92it/s ... 371.23it/s ... 915.10it/s
---
> Loading weights: ... 514.83it/s ... 433.56it/s ... 822.08it/s
```

The only diff line is the weight-loading progress bar's own throughput readout (a timing
artifact of that one run) -- every metric, confusion matrix, the fine-tuning decision, the
production-classifier selection, and the test report are byte-identical between the two runs.
Full diff: `docs/phase-2/evidence/evaluate-after-gold-rerun-diff.log`.

### 19.7 Checks (this session, after all gold-evaluation work)

```
ruff check .            -> All checks passed!
ruff format --check .   -> 141 files already formatted
mypy                     -> Success: no issues found in 75 source files
pytest -q                -> 183 passed, 59 deselected in 19.10s
pytest -q -m integration -> 57 passed, 185 deselected in 20.41s
pytest -q -m corpus      -> 2 passed, 240 deselected in 14.20s
```
Total: 242 passing, 0 failing (unchanged from §18.5 -- no code changed this session, only
real retraining/evaluation runs and documentation).

```
pre-commit run --all-files:
ruff...................................................................................Passed
ruff-format.............................................................................Passed
Detect hardcoded secrets.................................................................Passed
check for added large files..............................................................Passed
reject staged files under data/raw, data/interim, data/processed........................Passed
mypy (project venv -- avoids a second, heavy isolated env)...............................Passed
```

```
gitleaks detect --source . --log-opts="--all":
30 commits scanned.
scan completed in 1.71s
no leaks found
```

```
alembic check:
No new upgrade operations detected.
```

### 19.8 Exit gates, re-marked (gold evaluation executed)

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Preflight (branch, baseline checks, PDF integrity, HTML churn fix) | PASS | §4, §19.5 |
| 2 | Migrations apply from empty and match models with 0 drift | PASS | §19.7 |
| 3 | Taxonomy v1.0 loaded from file, never hand-inserted, boundary-tested | PASS | §1, 23 threshold tests |
| 4 | 3 classifiers compared on validation, once on test, support counts + fine-tuning justification | PASS -- now with real gold-test and gold-validation metrics, not just silver | §19.3, §19.4.3 |
| 5 | Span-cited extraction with verified evidence, failures queued not promoted | PASS (still silver-only; field-level gold deferred, §19.5) | §7d, §19.5 |
| 6 | Entity resolution: conflicts queued, merges reversible, evaluated (or honestly not run) | PASS, pairwise eval honestly not run (deferred, §19.5) | §7e, §19.5 |
| 7 | Point-in-time-correct hybrid retrieval, evaluated on all 3 methods | PASS (still silver-only; gold query review deferred, §19.5) | §7f |
| 8 | Idempotent/reproducible pipeline, model_registry populated | PASS -- model_registry updated with the real gold-dev retrain, reproducibility re-confirmed after the update | §19.4.3, §19.6 |
| 9 | Gold metrics OR PENDING_HUMAN_REVIEW | **PASS for event classification gold** (test n=14, validation n=41, both real and reported with support/CIs); **PARTIAL overall** -- extraction/entity-resolution/retrieval gold are **DEFERRED_TO_PHASE_6** (§19.5, no review infrastructure exists for them yet) | §19.2, §19.3, §19.5 |
| 10 | All tests/checks/adversarial tests passing, clean secret scan | PASS -- 242 tests, 6 adversarial tests, clean gitleaks (30 commits) | §19.5, §19.7 |
| 11 | Committed locally, no AI attribution, bundle verified, nothing pushed | PASS | §14, this session's own commit |

Gate 9 moves from `PENDING_HUMAN_REVIEW` to **PASS (event classification) / PARTIAL
(overall)** -- real human review happened (80 items), real gold metrics exist with real
support counts and confidence intervals for event classification specifically, and the
classifier-selection mechanism was checked against gold validation (and not changed, with
reasoning documented, §19.3). Extraction/entity-resolution/retrieval gold remain
`DEFERRED_TO_PHASE_6` per `docs/release/release-gates.md` -- there is no review mechanism for
them to evaluate against yet, gold or otherwise.
