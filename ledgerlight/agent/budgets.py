"""Phase 4 §4: real, enforced investigation budgets. Every investigation
carries a real `BudgetConfig` (persisted as `Investigation.budget_config`)
and accumulates real `Usage` (persisted as `Investigation.usage`) as the
state machine runs. Exceeding ANY limit stops the investigation with
`NEEDS_REVIEW`, reason `budget_exceeded`, keeping whatever real partial
work (claims, a draft dossier) already exists -- never discarded."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

DEFAULT_MAX_STEPS = 20
DEFAULT_MAX_WALL_SECONDS = 300.0
DEFAULT_MAX_TOOL_CALLS = 50
DEFAULT_MAX_LLM_TOKENS = 0
DEFAULT_MAX_COST_USD = 0.0
DEFAULT_MAX_REPAIR_ROUNDS = 2


class BudgetExceeded(Exception):
    """Raised the moment any real budget is exceeded. Caught only by the
    state machine's own top-level loop, which converts it into a real
    NEEDS_REVIEW outcome -- never silently swallowed, never retried past
    the limit."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class BudgetConfig:
    max_steps: int = DEFAULT_MAX_STEPS
    max_wall_seconds: float = DEFAULT_MAX_WALL_SECONDS
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    max_llm_tokens: int = DEFAULT_MAX_LLM_TOKENS
    max_cost_usd: float = DEFAULT_MAX_COST_USD
    max_repair_rounds: int = DEFAULT_MAX_REPAIR_ROUNDS

    def to_json(self) -> dict[str, object]:
        return {
            "max_steps": self.max_steps,
            "max_wall_seconds": self.max_wall_seconds,
            "max_tool_calls": self.max_tool_calls,
            "max_llm_tokens": self.max_llm_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_repair_rounds": self.max_repair_rounds,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> BudgetConfig:
        return cls(
            max_steps=int(cast(float, data.get("max_steps", DEFAULT_MAX_STEPS))),
            max_wall_seconds=float(
                cast(float, data.get("max_wall_seconds", DEFAULT_MAX_WALL_SECONDS))
            ),
            max_tool_calls=int(cast(float, data.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS))),
            max_llm_tokens=int(cast(float, data.get("max_llm_tokens", DEFAULT_MAX_LLM_TOKENS))),
            max_cost_usd=float(cast(float, data.get("max_cost_usd", DEFAULT_MAX_COST_USD))),
            max_repair_rounds=int(
                cast(float, data.get("max_repair_rounds", DEFAULT_MAX_REPAIR_ROUNDS))
            ),
        )


@dataclass
class Usage:
    steps: int = 0
    wall_seconds: float = 0.0
    tool_calls: int = 0
    llm_tokens: int = 0
    cost_usd: float = 0.0

    def to_json(self) -> dict[str, object]:
        return {
            "steps": self.steps,
            "wall_seconds": self.wall_seconds,
            "tool_calls": self.tool_calls,
            "llm_tokens": self.llm_tokens,
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> Usage:
        return cls(
            steps=int(cast(float, data.get("steps", 0))),
            wall_seconds=float(cast(float, data.get("wall_seconds", 0.0))),
            tool_calls=int(cast(float, data.get("tool_calls", 0))),
            llm_tokens=int(cast(float, data.get("llm_tokens", 0))),
            cost_usd=float(cast(float, data.get("cost_usd", 0.0))),
        )


def check_budgets(usage: Usage, budget: BudgetConfig) -> None:
    """Raises `BudgetExceeded` with the real reason the instant any real
    limit is crossed. Called before each step starts (so a step that
    would exceed the budget never runs at all) and after each tool call
    (so a step already in progress stops as soon as it goes over)."""
    if usage.steps >= budget.max_steps:
        raise BudgetExceeded(
            f"budget_exceeded: steps {usage.steps} >= max_steps {budget.max_steps}"
        )
    if usage.wall_seconds >= budget.max_wall_seconds:
        raise BudgetExceeded(
            f"budget_exceeded: wall_seconds {usage.wall_seconds:.1f} >= "
            f"max_wall_seconds {budget.max_wall_seconds}"
        )
    if usage.tool_calls >= budget.max_tool_calls:
        raise BudgetExceeded(
            f"budget_exceeded: tool_calls {usage.tool_calls} >= "
            f"max_tool_calls {budget.max_tool_calls}"
        )
    if usage.llm_tokens > budget.max_llm_tokens:
        raise BudgetExceeded(
            f"budget_exceeded: llm_tokens {usage.llm_tokens} > "
            f"max_llm_tokens {budget.max_llm_tokens}"
        )
    if usage.cost_usd > budget.max_cost_usd:
        raise BudgetExceeded(
            f"budget_exceeded: cost_usd {usage.cost_usd:.4f} > max_cost_usd {budget.max_cost_usd}"
        )
