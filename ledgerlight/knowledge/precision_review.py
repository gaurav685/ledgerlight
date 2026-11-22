"""Enhancement `precision-review` (branch `enhancement/precision-review`):
measures per-type PRECISION of the current production detector for
KMP_EXIT, ID_EXIT and RPT_GROWTH on a fresh, untouched sample.

Honest scope, stated plainly: no Event-table row of any of these three
types exists anywhere in this database -- `ledgerlight.knowledge.
extraction_pipeline` only ever wires up a real extractor for AUD_RESIGN
(see `docs/modelling/event-reliability.md`). There is therefore no
"stored event" candidate pool to sample from for these three types.
The real production method per type (Phase 3 §1.3, `data/manifests/
classifier-selection-gold-validation.json`) is a classifier run directly
over chunk text:
  - KMP_EXIT, ID_EXIT -> rules_baseline (`propose_event_type`)
  - RPT_GROWTH        -> tfidf_lr, evidence-filtered
    (`tfidf_lr_predict_rpt_growth_filtered`, `data/models/tfidf_lr_v1.pkl`)
This module runs exactly those frozen classifiers, fresh, over every
real chunk in the corpus, and treats "classifier flags this chunk as
type X" as the candidate pool -- the closest honest analog to "current
stored events of this type produced by the frozen detector" that this
codebase's real state supports. Disclosed here and in the detector-
freeze manifest, never hidden.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.classifier import (
    RPT_GROWTH_EVIDENCE_FILTER_VERSION,
    rules_baseline_predict,
    tfidf_lr_predict_rpt_growth_filtered,
)
from ledgerlight.knowledge.labeling import PROPOSER_NAME, PROPOSER_VERSION
from ledgerlight.knowledge.models import Chunk, EventField, Filing, LabelItem

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SAMPLE_VERSION = "v2"

GOLD_LABELS_PATH = REPO_ROOT / "data" / "manifests" / "gold-labels-phase2.json"
FROZEN_TEST_SPLIT_PATH = REPO_ROOT / "data" / "manifests" / "frozen-test-split-phase2.json"
TFIDF_MODEL_PATH = REPO_ROOT / "data" / "models" / "tfidf_lr_v1.pkl"
LABELING_SOURCE_PATH = REPO_ROOT / "ledgerlight" / "knowledge" / "labeling.py"
EVIDENCE_SOURCE_PATH = REPO_ROOT / "ledgerlight" / "knowledge" / "evidence.py"
CLASSIFIER_SOURCE_PATH = REPO_ROOT / "ledgerlight" / "knowledge" / "classifier.py"

REVIEW_PACK_AUDIT_PATHS = [
    REPO_ROOT / "docs" / "phase-6" / "review-pack" / "field-review-audit.jsonl",
    REPO_ROOT / "docs" / "phase-6" / "review-pack" / "entity-pair-review-audit.jsonl",
    REPO_ROOT / "docs" / "phase-6" / "review-pack" / "retrieval-review-audit.jsonl",
    REPO_ROOT / "docs" / "phase-6" / "review-pack" / "outcome-evidence-review-audit.jsonl",
]

# Label-item ids cited as worked examples while designing/debugging the
# Phase 3 §1.4 / Phase 6 Correction 1 §5 hardening rules
# (docs/modelling/event-reliability.md's "Frozen-TEST-split consultation"
# table). Resolved to full UUIDs by hand against data/manifests/
# gold-labels-phase2.json and data/manifests/frozen-test-split-phase2.json
# (every one of them already lives in one of those two files -- this list
# is a disclosed, explicit record of *why* each is excluded, not a new
# source of ids). `9f8f00a6-...` (the one AUD_RESIGN false-positive EVENT
# id in that table) is excluded: it is an events.id, not a label_items.id,
# and AUD_RESIGN is not one of this sample's three target types.
HARDENING_CITED_LABEL_ITEM_IDS: frozenset[str] = frozenset(
    {
        "94e783d4-3e12-4238-8dbe-fef4fb507db9",
        "ee794ff1-98de-490b-ad33-508b61414ba3",
        "1260ba02-1cac-48ca-9035-9c8ddd846a08",
        "5852c78b-95e4-40bc-b412-c15dc0ec24f2",
        "83d228a8-f82e-4fba-9edd-b0afc63773a9",
        "b570b630-f399-47f9-82d0-5e432f2aa2c7",
        "98690f06-b540-48a3-9754-d6329117cd02",
        "42956032-36d9-46bd-a781-32b6cf355e1e",
        "4b31329b-063a-41cf-b0ac-e34dae569789",
        "15123f33-7c3a-44df-886b-a59df29c920c",
        "01f5e9ce-debf-4379-8ed9-bfd205c717d7",
        "2f37afa5-45db-4ea2-b193-87be20dcffdf",
        "275c72aa-7753-48e4-9819-ad8612d72490",
        "8e051d86-a85f-4658-8252-c2ba26b10525",
        "c9525ab4-686f-434f-a156-36f3918ab458",
        "964b00b8-8cb5-45b1-8a04-b6e64439fc24",
        "09ceeda4-f6ca-4378-9b9d-126c931f3347",
        "7c86b3db-7222-445e-b15d-54d793744e52",
        "fa42725a-71e9-4e57-b268-66c860b8baec",
        "a001d952-e294-44a3-b90f-ebdb4b7b9038",
        "9167a9a1-0349-42dc-ac71-e831ddaf47be",
        "a3ae3450-cecd-477c-b8c1-c53fd891b903",
        "cf935e23-d709-4496-a23d-32b62d681dde",
        "15eef36f-198d-4431-a388-9ae16c5fa926",
        "1aa8ed91-68d2-4eb1-a2c8-099fdbc99e85",
        "f3a5b95c-a843-45fc-b21a-715090e4e9bc",
    }
)

TARGET_EVENT_TYPES = ("KMP_EXIT", "ID_EXIT", "RPT_GROWTH")
RULES_BASELINE_TYPES = ("KMP_EXIT", "ID_EXIT")
TFIDF_LR_TYPES = ("RPT_GROWTH",)
SAMPLE_SEED = 42
SAMPLE_SIZE_PER_TYPE = 20
COMPANY_CAP_FRACTION = 0.30


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_files(paths: list[Path]) -> str:
    """Order-independent combined hash of several source files -- the
    'code hash' for a rule-based detector with no single artifact."""
    digests = sorted(_sha256_file(p) for p in paths)
    return hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()


def current_detector_state() -> dict[str, dict[str, str]]:
    """The real, current state of each target type's production
    detector, computed fresh from the checked-out code/artifact -- never
    hand-typed. Used both to WRITE the freeze manifest and, later, to
    VERIFY the checked-out code still matches it (the freeze guard)."""
    rules_state = {
        "method": "rules_baseline",
        "proposer_name": PROPOSER_NAME,
        "proposer_version": PROPOSER_VERSION,
        "code_hash_sha256": _sha256_files([LABELING_SOURCE_PATH, EVIDENCE_SOURCE_PATH]),
        "code_files": "ledgerlight/knowledge/labeling.py, ledgerlight/knowledge/evidence.py",
    }
    tfidf_state = {
        "method": "tfidf_lr_rpt_growth_filtered",
        "model_name": "tfidf-logreg-event-classifier",
        "model_version": "1",
        "artifact_path": "data/models/tfidf_lr_v1.pkl",
        "artifact_sha256": _sha256_file(TFIDF_MODEL_PATH),
        "filter_version": RPT_GROWTH_EVIDENCE_FILTER_VERSION,
        "filter_code_hash_sha256": _sha256_files([CLASSIFIER_SOURCE_PATH, LABELING_SOURCE_PATH]),
        "filter_code_files": (
            "ledgerlight/knowledge/classifier.py, ledgerlight/knowledge/labeling.py"
        ),
    }
    return {
        "KMP_EXIT": rules_state,
        "ID_EXIT": rules_state,
        "RPT_GROWTH": tfidf_state,
    }


@dataclass
class ExclusionReport:
    excluded_chunk_ids: set[uuid.UUID] = field(default_factory=set)
    by_source: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _label_item_ids_to_chunk_ids(
    session: Session, label_item_ids: set[uuid.UUID]
) -> set[uuid.UUID]:
    if not label_item_ids:
        return set()
    rows = session.execute(
        select(LabelItem.chunk_id).where(
            LabelItem.id.in_(label_item_ids), LabelItem.chunk_id.is_not(None)
        )
    ).all()
    return {r[0] for r in rows if r[0] is not None}


def build_exclusion_set(
    session: Session,
    *,
    gold_labels_path: Path = GOLD_LABELS_PATH,
    frozen_test_split_path: Path = FROZEN_TEST_SPLIT_PATH,
    hardening_cited_ids: frozenset[str] = HARDENING_CITED_LABEL_ITEM_IDS,
    review_pack_audit_paths: list[Path] | None = None,
    prior_round_manifest_paths: list[Path] | None = None,
) -> ExclusionReport:
    """Every chunk that must never appear in the fresh sample, because it
    already informed a human decision, a frozen metric, or this
    project's own rule-design -- the §2.2 exclusion list, built from real
    files, not guessed."""
    report = ExclusionReport()
    review_pack_audit_paths = (
        REVIEW_PACK_AUDIT_PATHS if review_pack_audit_paths is None else review_pack_audit_paths
    )
    if prior_round_manifest_paths is None:
        prior_round_manifest_paths = sorted(
            (REPO_ROOT / "data" / "manifests").glob("precision-review-v*.jsonl")
        )

    # 1. Phase 2 label set, all splits (every id ever reviewed to gold).
    gold_ids: set[uuid.UUID] = set()
    if gold_labels_path.exists():
        with gold_labels_path.open(encoding="utf-8") as f:
            gold_data = json.load(f)
        gold_ids = {uuid.UUID(r["label_item_id"]) for r in gold_data["records"]}
    gold_chunk_ids = _label_item_ids_to_chunk_ids(session, gold_ids)
    report.by_source["phase2_gold_label_set"] = len(gold_chunk_ids)
    report.excluded_chunk_ids |= gold_chunk_ids

    # 2. The frozen TEST split specifically (mostly a subset of (1), kept
    #    as an explicit, independent check per the brief).
    frozen_ids: set[uuid.UUID] = set()
    if frozen_test_split_path.exists():
        with frozen_test_split_path.open(encoding="utf-8") as f:
            frozen_data = json.load(f)
        frozen_ids = {uuid.UUID(i) for i in frozen_data["item_ids"]}
    frozen_chunk_ids = _label_item_ids_to_chunk_ids(session, frozen_ids)
    new_from_frozen = frozen_chunk_ids - report.excluded_chunk_ids
    report.by_source["frozen_test_split"] = len(frozen_chunk_ids)
    report.by_source["frozen_test_split_net_new"] = len(new_from_frozen)
    report.excluded_chunk_ids |= frozen_chunk_ids

    # 3. Items cited as worked examples in the hardening docs.
    hardening_ids = {uuid.UUID(i) for i in hardening_cited_ids}
    hardening_chunk_ids = _label_item_ids_to_chunk_ids(session, hardening_ids)
    new_from_hardening = hardening_chunk_ids - report.excluded_chunk_ids
    report.by_source["hardening_docs_cited"] = len(hardening_chunk_ids)
    report.by_source["hardening_docs_cited_net_new"] = len(new_from_hardening)
    report.excluded_chunk_ids |= hardening_chunk_ids

    # 4. The Phase 6 AI-QA review pack. Only field-review items carry a
    #    (document_version, page) locator that can be mapped back to a
    #    chunk; entity-pair/retrieval/outcome-evidence/dossier review
    #    operate on entities, retrieval pairs, outcomes and investigation
    #    tasks respectively -- none of which is a chunk, so they
    #    contribute 0 by data shape, not by omission. Stated plainly
    #    rather than silently skipped.
    review_pack_chunk_ids: set[uuid.UUID] = set()
    field_audit_path = next(
        (p for p in review_pack_audit_paths if p.name == "field-review-audit.jsonl"), None
    )
    if field_audit_path is not None and field_audit_path.exists():
        event_field_ids: set[uuid.UUID] = set()
        with field_audit_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                try:
                    event_field_ids.add(uuid.UUID(row["item_id"]))
                except (KeyError, ValueError):
                    continue
        if event_field_ids:
            locators = session.execute(
                select(EventField.evidence_version_id, EventField.evidence_page).where(
                    EventField.id.in_(event_field_ids)
                )
            ).all()
            locator_set = {(vid, page) for vid, page in locators}
            if locator_set:
                chunk_rows = session.execute(
                    select(Chunk.id, Chunk.version_id, Chunk.page_number)
                ).all()
                review_pack_chunk_ids = {
                    cid for cid, vid, page in chunk_rows if (vid, page) in locator_set
                }
    other_pack_files = [
        p.name for p in review_pack_audit_paths if p.name != "field-review-audit.jsonl"
    ]
    report.notes.append(
        f"Phase 6 AI-QA review pack: field-review mapped via (version_id, page) -> "
        f"{len(review_pack_chunk_ids)} chunk(s); {other_pack_files} contribute 0 "
        "(entity/retrieval/outcome/dossier granularity, not chunk-level)."
    )
    new_from_pack = review_pack_chunk_ids - report.excluded_chunk_ids
    report.by_source["ai_qa_review_pack"] = len(review_pack_chunk_ids)
    report.by_source["ai_qa_review_pack_net_new"] = len(new_from_pack)
    report.excluded_chunk_ids |= review_pack_chunk_ids

    # 5. Every chunk already sampled in a prior precision-review round
    #    (data/manifests/precision-review-v*.jsonl) -- "fresh" means
    #    never shown to a reviewer before, in this round or any earlier
    #    one, not just never in the Phase 2/6 sets above.
    prior_round_chunk_ids: set[uuid.UUID] = set()
    for manifest_path in prior_round_manifest_paths:
        if not manifest_path.exists():
            continue
        with manifest_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    prior_round_chunk_ids.add(uuid.UUID(json.loads(line)["id"]))
    new_from_prior_rounds = prior_round_chunk_ids - report.excluded_chunk_ids
    report.by_source["prior_precision_review_rounds"] = len(prior_round_chunk_ids)
    report.by_source["prior_precision_review_rounds_net_new"] = len(new_from_prior_rounds)
    report.excluded_chunk_ids |= prior_round_chunk_ids

    return report


@dataclass(frozen=True)
class Candidate:
    chunk_id: uuid.UUID
    event_type: str
    company_id: uuid.UUID | None
    company_name: str | None


def run_frozen_detector(
    session: Session,
    event_type: str,
    *,
    excluded_chunk_ids: set[uuid.UUID],
    tfidf_model: object | None = None,
) -> list[Candidate]:
    """Runs the real, frozen production classifier for `event_type` over
    every real chunk not in `excluded_chunk_ids`, fresh (never reads
    stored LabelItem predictions, which may mix several historical
    proposer versions) -- see this module's own docstring."""
    if event_type in RULES_BASELINE_TYPES:
        predict_one = rules_baseline_predict
    elif event_type in TFIDF_LR_TYPES:
        if tfidf_model is None:
            import pickle

            with TFIDF_MODEL_PATH.open("rb") as f:
                tfidf_model = pickle.load(f)
    else:
        raise ValueError(f"not a supported target type: {event_type!r}")

    rows = session.execute(select(Chunk.id, Chunk.text, Chunk.version_id)).all()
    eligible = [(cid, text, vid) for cid, text, vid in rows if cid not in excluded_chunk_ids]
    if not eligible:
        return []

    if event_type in RULES_BASELINE_TYPES:
        predictions = [predict_one(text) for _, text, _ in eligible]
    else:
        predictions = tfidf_lr_predict_rpt_growth_filtered(
            tfidf_model,  # type: ignore[arg-type]
            [text for _, text, _ in eligible],
        )

    flagged = [
        (cid, vid)
        for (cid, _text, vid), pred in zip(eligible, predictions, strict=True)
        if pred == event_type
    ]
    if not flagged:
        return []

    version_ids = {vid for _, vid in flagged}
    filing_rows = session.execute(
        select(Filing.version_id, Filing.company_id)
        .where(Filing.version_id.in_(version_ids))
        .order_by(Filing.id)
    ).all()
    company_by_version: dict[uuid.UUID, uuid.UUID] = {}
    for vid, company_id in filing_rows:
        company_by_version.setdefault(vid, company_id)

    from ledgerlight.knowledge.models import Company

    company_ids = set(company_by_version.values())
    company_names = (
        {
            cid: name
            for cid, name in session.execute(
                select(Company.id, Company.display_name).where(Company.id.in_(company_ids))
            ).all()
        }
        if company_ids
        else {}
    )

    return [
        Candidate(
            chunk_id=cid,
            event_type=event_type,
            company_id=company_by_version.get(vid),
            company_name=company_names.get(company_by_version.get(vid)),  # type: ignore[arg-type]
        )
        for cid, vid in flagged
    ]


@dataclass
class SampleResult:
    event_type: str
    selected: list[Candidate]
    eligible_total: int
    shortfall: int
    companies: dict[str, int]


def stratified_sample(
    candidates: list[Candidate],
    *,
    seed: int = SAMPLE_SEED,
    limit: int = SAMPLE_SIZE_PER_TYPE,
    company_cap_fraction: float = COMPANY_CAP_FRACTION,
) -> SampleResult:
    """Deterministic given `seed`: a fixed base order (by chunk_id
    string) is shuffled by a seeded RNG, then filled greedily under a
    per-company cap (~`company_cap_fraction` of `limit`, rounded up so a
    cap is never 0), falling back to deferred over-cap items only if the
    cap would otherwise leave the sample short -- 'about 30%, where
    possible', not an unconditional hard limit when too few companies
    exist to honour it."""
    event_type = candidates[0].event_type if candidates else ""
    base_order = sorted(candidates, key=lambda c: str(c.chunk_id))
    rng = random.Random(seed)
    shuffled = base_order[:]
    rng.shuffle(shuffled)

    cap = max(1, math.ceil(limit * company_cap_fraction))
    selected: list[Candidate] = []
    deferred: list[Candidate] = []
    counts: dict[str, int] = {}
    for c in shuffled:
        key = str(c.company_id) if c.company_id else f"__no_company__{c.chunk_id}"
        if len(selected) >= limit:
            break
        if counts.get(key, 0) < cap:
            selected.append(c)
            counts[key] = counts.get(key, 0) + 1
        else:
            deferred.append(c)

    for c in deferred:
        if len(selected) >= limit:
            break
        key = str(c.company_id) if c.company_id else f"__no_company__{c.chunk_id}"
        selected.append(c)
        counts[key] = counts.get(key, 0) + 1

    shortfall = max(0, limit - len(candidates))
    company_breakdown: dict[str, int] = {}
    for c in selected:
        name = c.company_name or "(unknown company)"
        company_breakdown[name] = company_breakdown.get(name, 0) + 1

    return SampleResult(
        event_type=event_type,
        selected=selected,
        eligible_total=len(candidates),
        shortfall=shortfall,
        companies=company_breakdown,
    )
