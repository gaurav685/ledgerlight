"""Real code-level enforcement of the brief's own mandatory feature
policy (§4): "The PRIMARY model uses STRUCTURED and RULE-VERIFIED
features only. EVENT-CANDIDATE features enter ONLY in the ablation
arm, labelled unverified." Built now, before any training exists,
specifically so the PRIMARY model's training code can call this at
the one real place features get assembled, rather than relying on
every future caller to remember the rule by convention."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

PRIMARY_MODEL_ALLOWED_TIERS: frozenset[str] = frozenset({"STRUCTURED", "RULE_VERIFIED"})
ABLATION_ONLY_TIERS: frozenset[str] = frozenset({"EVENT_CANDIDATE"})


class FeaturePolicyViolation(ValueError):
    """Raised when a feature set intended for the PRIMARY model
    includes a tier the brief restricts to the ablation arm only."""


def assert_primary_model_feature_policy(feature_set_versions: list[str], session: Session) -> None:
    """Real check against the live `feature_definitions` table -- not
    a hardcoded tier-name guess per `feature_set_version`, since a
    version string alone (e.g. "seed-governance-1.0") doesn't encode
    its tier; the table does."""
    rows = session.execute(
        text(
            "SELECT DISTINCT version, provenance_tier FROM feature_definitions "
            "WHERE version = ANY(:versions)"
        ),
        {"versions": feature_set_versions},
    ).all()

    violations = [
        (version, tier) for version, tier in rows if tier not in PRIMARY_MODEL_ALLOWED_TIERS
    ]
    if violations:
        detail = ", ".join(f"{version} ({tier})" for version, tier in violations)
        raise FeaturePolicyViolation(
            f"PRIMARY model feature set includes non-allowed tier(s): {detail}. "
            f"Only {sorted(PRIMARY_MODEL_ALLOWED_TIERS)} are permitted for the PRIMARY "
            f"model per the brief's §4 feature policy; EVENT-CANDIDATE features "
            f"(e.g. seed-governance-1.0) may only appear in the ablation arm."
        )
