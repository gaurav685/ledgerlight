"""Tests for ledgerlight.agent.budgets -- Phase 4 Sec4's enforced budgets."""

from __future__ import annotations

import pytest

from ledgerlight.agent.budgets import BudgetConfig, BudgetExceeded, Usage, check_budgets


def test_check_budgets_passes_when_under_every_limit() -> None:
    check_budgets(Usage(steps=1, tool_calls=1), BudgetConfig(max_steps=5, max_tool_calls=5))


def test_check_budgets_raises_on_steps_exceeded() -> None:
    with pytest.raises(BudgetExceeded, match="steps"):
        check_budgets(Usage(steps=5), BudgetConfig(max_steps=5))


def test_check_budgets_raises_on_wall_seconds_exceeded() -> None:
    with pytest.raises(BudgetExceeded, match="wall_seconds"):
        check_budgets(Usage(wall_seconds=301.0), BudgetConfig(max_wall_seconds=300.0))


def test_check_budgets_raises_on_tool_calls_exceeded() -> None:
    with pytest.raises(BudgetExceeded, match="tool_calls"):
        check_budgets(Usage(tool_calls=10), BudgetConfig(max_tool_calls=10))


def test_check_budgets_raises_on_llm_tokens_exceeded() -> None:
    with pytest.raises(BudgetExceeded, match="llm_tokens"):
        check_budgets(Usage(llm_tokens=101), BudgetConfig(max_llm_tokens=100))


def test_check_budgets_raises_on_cost_exceeded() -> None:
    with pytest.raises(BudgetExceeded, match="cost_usd"):
        check_budgets(Usage(cost_usd=1.01), BudgetConfig(max_cost_usd=1.0))


def test_budget_config_round_trips_through_json() -> None:
    config = BudgetConfig(max_steps=7, max_wall_seconds=12.5, max_repair_rounds=3)
    restored = BudgetConfig.from_json(config.to_json())
    assert restored == config


def test_usage_round_trips_through_json() -> None:
    usage = Usage(steps=2, wall_seconds=1.5, tool_calls=3, llm_tokens=10, cost_usd=0.02)
    restored = Usage.from_json(usage.to_json())
    assert restored == usage


def test_budget_config_from_json_fills_missing_keys_with_defaults() -> None:
    restored = BudgetConfig.from_json({"max_steps": 9})
    assert restored.max_steps == 9
    assert restored.max_tool_calls == BudgetConfig().max_tool_calls
