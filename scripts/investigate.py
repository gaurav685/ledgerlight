"""Phase 4 §10 `investigate` command: runs one real investigation
against one real company for one real as_of date, via
`ledgerlight.agent.state_machine.run_investigation`, and prints its
real outcome."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.agent.budgets import BudgetConfig  # noqa: E402
from ledgerlight.agent.state_machine import run_investigation  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real investigation.")
    parser.add_argument("--company", required=True, help="real company_id (UUID)")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--requested-by", default="cli")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--max-wall-seconds", type=float, default=None)
    parser.add_argument("--max-tool-calls", type=int, default=None)
    parser.add_argument("--max-repair-rounds", type=int, default=None)
    parser.add_argument("--resume", default=None, help="an existing investigation_id to resume")
    args = parser.parse_args()

    budget_kwargs: dict[str, object] = {}
    if args.max_steps is not None:
        budget_kwargs["max_steps"] = args.max_steps
    if args.max_wall_seconds is not None:
        budget_kwargs["max_wall_seconds"] = args.max_wall_seconds
    if args.max_tool_calls is not None:
        budget_kwargs["max_tool_calls"] = args.max_tool_calls
    if args.max_repair_rounds is not None:
        budget_kwargs["max_repair_rounds"] = args.max_repair_rounds
    budget = BudgetConfig(**budget_kwargs) if budget_kwargs else None  # type: ignore[arg-type]

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        outcome = run_investigation(
            session,
            uuid.UUID(args.company),
            dt.date.fromisoformat(args.as_of),
            args.requested_by,
            budget_config=budget,
            resume_investigation_id=uuid.UUID(args.resume) if args.resume else None,
        )

    print(f"investigation_id: {outcome.investigation.id}")
    print(f"state: {outcome.investigation.state}")
    print(f"final_status: {outcome.investigation.final_status}")
    print(f"failure_reason: {outcome.investigation.failure_reason}")
    if outcome.rendered is not None:
        section_counts = {k: len(v) for k, v in outcome.rendered.sections.items()}
        print(f"section sentence counts: {section_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
