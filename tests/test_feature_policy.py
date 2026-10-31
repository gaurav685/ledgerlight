"""Tests for ledgerlight.modelling.feature_policy against the real
feature_definitions rows already built in this project's database --
not synthetic tier names, the real ones from Sec4.1-4.3."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ledgerlight.modelling.feature_policy import (
    FeaturePolicyViolation,
    assert_primary_model_feature_policy,
)

pytestmark = pytest.mark.integration


def test_structured_and_rule_verified_pass(db_session: Session) -> None:
    """Real tiers from Sec4.1/4.2 -- must be allowed for the PRIMARY model."""
    assert_primary_model_feature_policy(["price-liquidity-1.0", "rule-verified-1.0"], db_session)


def test_seed_governance_tier_is_rejected(db_session: Session) -> None:
    """Real EVENT_CANDIDATE tier from Sec4.3 -- must be rejected for the
    PRIMARY model; this is exactly the ablation-only arm (c)."""
    with pytest.raises(FeaturePolicyViolation, match="seed-governance-1.0"):
        assert_primary_model_feature_policy(["seed-governance-1.0"], db_session)


def test_mixing_an_allowed_and_a_rejected_tier_still_raises(db_session: Session) -> None:
    with pytest.raises(FeaturePolicyViolation, match="EVENT_CANDIDATE"):
        assert_primary_model_feature_policy(
            ["price-liquidity-1.0", "seed-governance-1.0"], db_session
        )
