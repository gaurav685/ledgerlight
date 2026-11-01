"""Phase 4 §5/§14.9: NLI entailment threshold calibration.

The labelled set below is **SYNTHETIC** -- hand-written (premise,
hypothesis, entailed) triples, not real extracted claims or real gold
labels. It exists only to pick a real, defensible entailment threshold
and to report this check's own real precision/recall honestly, per
the brief's explicit instruction ("Report its precision and recall
honestly and mark that set SYNTHETIC"). It is never used as training
data, and it is not a substitute for real human review of real claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ledgerlight.agent.nli import entailment_score

SYNTHETIC_ENTAILMENT_EXAMPLES: list[tuple[str, str, bool]] = [
    # True: minor paraphrase of the same real fact.
    ("The statutory auditor resigned on 28 April 2018.", "The auditor resigned.", True),
    (
        "CARE downgraded the long-term rating to BB- on 2020-03-15.",
        "CARE downgraded the rating.",
        True,
    ),
    (
        "The company's board approved a resolution to appoint a forensic auditor.",
        "A forensic auditor was appointed.",
        True,
    ),
    (
        "The NCLT admitted the company into CIRP on 2019-06-04.",
        "The company was admitted into CIRP.",
        True,
    ),
    (
        "SEBI passed an order restraining the company from accessing capital markets.",
        "SEBI passed an order against the company.",
        True,
    ),
    (
        "The independent director tendered her resignation with immediate effect.",
        "An independent director resigned.",
        True,
    ),
    (
        "Total revenue for the quarter was Rs. 500 crore, up 12% year on year.",
        "Revenue grew year on year.",
        True,
    ),
    (
        "The rating agency placed the issuer on negative outlook.",
        "The issuer was placed on negative outlook.",
        True,
    ),
    (
        "The company disclosed a delay in filing its quarterly results with the exchange.",
        "The company delayed a filing.",
        True,
    ),
    (
        "Mr. Sharma, Chief Financial Officer, resigned effective 1 January 2021.",
        "The CFO resigned.",
        True,
    ),
    # False: unrelated or contradicted statements.
    ("The company reported record profits this year.", "The auditor resigned.", False),
    (
        "CARE reaffirmed the long-term rating at AA with a stable outlook.",
        "CARE downgraded the rating.",
        False,
    ),
    (
        "The board approved the annual dividend for shareholders.",
        "A forensic auditor was appointed.",
        False,
    ),
    (
        "The company successfully refinanced its debt ahead of schedule.",
        "The company was admitted into CIRP.",
        False,
    ),
    (
        "SEBI closed the investigation with no adverse findings against the company.",
        "SEBI passed an order against the company.",
        False,
    ),
    (
        "The independent director was re-appointed for another term.",
        "An independent director resigned.",
        False,
    ),
    (
        "Total revenue for the quarter declined by 8% year on year.",
        "Revenue grew year on year.",
        False,
    ),
    (
        "The rating agency upgraded the outlook to positive.",
        "The issuer was placed on negative outlook.",
        False,
    ),
    (
        "The company filed its quarterly results on time.",
        "The company delayed a filing.",
        False,
    ),
    ("Mr. Sharma was promoted to Managing Director.", "The CFO resigned.", False),
]


@dataclass
class ThresholdCandidate:
    threshold: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class CalibrationResult:
    scores: list[tuple[str, str, bool, float]] = field(default_factory=list)
    candidates: list[ThresholdCandidate] = field(default_factory=list)
    best: ThresholdCandidate | None = None


DEFAULT_CANDIDATE_THRESHOLDS: tuple[float, ...] = tuple(i / 20 for i in range(1, 20))


def calibrate_threshold(
    examples: list[tuple[str, str, bool]] = SYNTHETIC_ENTAILMENT_EXAMPLES,
    candidate_thresholds: tuple[float, ...] = DEFAULT_CANDIDATE_THRESHOLDS,
) -> CalibrationResult:
    """Real entailment scores for every real (synthetic) example, then
    real precision/recall/F1 at each real candidate threshold -- the
    best (by F1, ties broken by the higher threshold, which is more
    conservative) becomes the real calibrated threshold."""
    scores = [
        (premise, hypothesis, entailed, entailment_score(premise, hypothesis))
        for premise, hypothesis, entailed in examples
    ]

    candidates: list[ThresholdCandidate] = []
    for threshold in candidate_thresholds:
        tp = fp = tn = fn = 0
        for _premise, _hypothesis, entailed, score in scores:
            predicted = score >= threshold
            if predicted and entailed:
                tp += 1
            elif predicted and not entailed:
                fp += 1
            elif not predicted and not entailed:
                tn += 1
            else:
                fn += 1
        candidates.append(ThresholdCandidate(threshold, tp, fp, tn, fn))

    best = max(candidates, key=lambda c: (c.f1, c.threshold)) if candidates else None
    return CalibrationResult(scores=scores, candidates=candidates, best=best)


def print_calibration_report(result: CalibrationResult) -> None:
    print("SYNTHETIC entailment calibration set -- not real gold labels:")
    for premise, hypothesis, entailed, score in result.scores:
        print(f"  entailed={entailed!s:5} score={score:.3f} | {premise!r} => {hypothesis!r}")
    print("\nThreshold sweep (SYNTHETIC):")
    for candidate in result.candidates:
        print(
            f"  threshold={candidate.threshold:.2f} precision={candidate.precision:.3f} "
            f"recall={candidate.recall:.3f} f1={candidate.f1:.3f} "
            f"(tp={candidate.true_positives} fp={candidate.false_positives} "
            f"tn={candidate.true_negatives} fn={candidate.false_negatives})"
        )
    if result.best is not None:
        print(
            f"\nBest real threshold on this SYNTHETIC set: {result.best.threshold:.2f} "
            f"(precision={result.best.precision:.3f}, recall={result.best.recall:.3f}, "
            f"f1={result.best.f1:.3f})"
        )
