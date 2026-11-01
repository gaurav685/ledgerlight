"""Phase 4 §5: local DeBERTa NLI entailment(premise -> hypothesis).

Reuses the exact same real model
(`ledgerlight.knowledge.classifier.DEBERTA_MODEL_NAME`, MoritzLaurer's
DeBERTa-v3 MNLI/FEVER/ANLI checkpoint) Phase 2's zero-shot event
classifier already runs locally on CPU -- not a second model, not an
API call. Also applies the same real `TOKENIZERS_PARALLELISM` fix
Phase 2 found the hard way (unset, the Rust tokenizer backend spawned a
parallel worker that resolved to an unrelated system Python install on
this machine, turning a ~20-minute CPU workload into a 13+ hour
stall) before constructing the pipeline.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ledgerlight.knowledge.classifier import DEBERTA_MODEL_NAME

if TYPE_CHECKING:
    from transformers import Pipeline

_entailment_pipeline: Pipeline | None = None


def _get_entailment_pipeline() -> Pipeline:
    global _entailment_pipeline
    if _entailment_pipeline is None:
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from transformers import pipeline

        _entailment_pipeline = pipeline(
            "zero-shot-classification", model=DEBERTA_MODEL_NAME, device=-1
        )
    return _entailment_pipeline


def entailment_score(premise: str, hypothesis: str) -> float:
    """Real entailment probability of `hypothesis` given `premise`,
    from the real local DeBERTa-v3 MNLI model -- never a fabricated or
    heuristic score. `hypothesis_template="{}"` passes the real claim
    sentence through unmodified as the NLI hypothesis, rather than the
    zero-shot pipeline's default "This example is {}." template (which
    only suits single-word candidate labels, not a full claim
    sentence). `multi_label=True` makes the pipeline score entailment
    independently (sigmoid), not in competition with other candidates
    -- correct here since there is only ever one real candidate, the
    claim sentence itself."""
    clf = _get_entailment_pipeline()
    result = clf(premise, candidate_labels=[hypothesis], hypothesis_template="{}", multi_label=True)
    return float(result["scores"][0])
