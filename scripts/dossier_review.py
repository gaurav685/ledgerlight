"""Phase 4 §10 `dossier-review` command: the real human review CLI
over `ledgerlight.agent.review` -- list the real open queue, show one
real task's dossier, record a real reviewer decision (appended to the
real, append-only audit), or apply real reviewer feedback to an
`Event`'s status (a new, immutable `EventVersion`, never an in-place
mutation).

Per the brief's §0 ground rule: never review a gold item or a seeded
QC dossier as a real "human" -- `decide`/`feedback` here are for a
real reviewer, run as a real person at a real terminal, not by this
agent itself.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.agent.export import export_dossier_markdown  # noqa: E402
from ledgerlight.agent.models import Investigation, ReviewTask  # noqa: E402
from ledgerlight.agent.review import (  # noqa: E402
    apply_event_feedback,
    get_task_dossier,
    list_open_tasks,
    record_decision,
)
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Company  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="The real human review CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="list the real open review queue")
    list_parser.add_argument("--limit", type=int, default=None)
    list_parser.add_argument(
        "--blind",
        action="store_true",
        help="suppress the seeded_qc column (see the show subcommand's own --blind help)",
    )

    show_parser = sub.add_parser("show", help="show one real task's dossier")
    show_parser.add_argument("--task-id", required=True)
    show_parser.add_argument(
        "--blind",
        action="store_true",
        help=(
            "suppress the seeded_qc warning below -- use this for a genuine human "
            "review session over a mixed real+seeded-QC sample (Phase 6A §7 item 5), "
            "where telling the reviewer up front which items are seeded would defeat "
            "the whole point of measuring their catch rate"
        ),
    )

    decide_parser = sub.add_parser("decide", help="record a real reviewer decision")
    decide_parser.add_argument("--task-id", required=True)
    decide_parser.add_argument(
        "--decision", required=True, choices=["approve", "approve_with_edits", "reject", "escalate"]
    )
    decide_parser.add_argument("--reviewer", required=True)
    decide_parser.add_argument("--notes", default=None)

    feedback_parser = sub.add_parser(
        "feedback", help="apply real reviewer feedback to an event's status"
    )
    feedback_parser.add_argument("--event-id", required=True)
    feedback_parser.add_argument("--status", required=True, choices=["verified", "rejected"])
    feedback_parser.add_argument("--reviewer", required=True)
    feedback_parser.add_argument("--task-id", default=None)
    feedback_parser.add_argument("--notes", default=None)

    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        if args.command == "list":
            tasks = list_open_tasks(session, limit=args.limit)
            print(f"{len(tasks)} open real review task(s)")
            for task in tasks:
                if args.blind:
                    # reason_code is itself "seeded_qc" for a seeded item --
                    # as revealing as the seeded_qc column, so both are
                    # suppressed together under --blind.
                    reason_part = "reason=<hidden --blind>"
                    seeded_part = ""
                else:
                    reason_part = f"reason={task.reason_code}"
                    seeded_part = f"seeded_qc={task.seeded_qc} "
                print(
                    f"  id={task.id} {reason_part} priority={task.priority} "
                    f"{seeded_part}dossier_id={task.dossier_id} claim_id={task.claim_id}"
                )
            return 0

        if args.command == "show":
            task_id = uuid.UUID(args.task_id)
            found_task = session.get(ReviewTask, task_id)
            if found_task is None:
                print(f"no real review task with id {task_id}")
                return 1
            if found_task.seeded_qc and not args.blind:
                print(
                    "WARNING: this is a seeded QC item (a deliberately flawed dossier), "
                    "not a real finding. Pass --blind to suppress this during a genuine "
                    "human review session over a mixed real+seeded-QC sample."
                )
            dossier = get_task_dossier(session, task_id)
            if dossier is None:
                print(f"task {task_id} references claim_id={found_task.claim_id}, not a dossier")
                return 0
            investigation = session.get(Investigation, dossier.investigation_id)
            assert investigation is not None
            company = session.get(Company, investigation.company_id)
            company_name = (
                company.display_name if company is not None else str(investigation.company_id)
            )
            print(export_dossier_markdown(dossier, investigation, company_name))
            return 0

        if args.command == "decide":
            task = record_decision(
                session, uuid.UUID(args.task_id), args.decision, args.reviewer, notes=args.notes
            )
            print(f"decided: task={task.id} decision={task.decision} status={task.status}")
            return 0

        if args.command == "feedback":
            apply_event_feedback(
                session,
                uuid.UUID(args.event_id),
                args.status,
                args.reviewer,
                review_task_id=uuid.UUID(args.task_id) if args.task_id else None,
                notes=args.notes,
            )
            print(f"applied feedback: event={args.event_id} status={args.status}")
            return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
