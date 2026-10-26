"""review-queue list|resolve|dismiss|summary -- a human-facing CLI over
ledgerlight.knowledge.review_queue."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.review_queue import (  # noqa: E402
    dismiss_item,
    list_open_items,
    resolve_item,
    summarize_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--item-type", default=None)
    list_parser.add_argument("--limit", type=int, default=None)

    resolve_parser = sub.add_parser("resolve")
    resolve_parser.add_argument("--id", required=True)
    resolve_parser.add_argument("--resolution", required=True)
    resolve_parser.add_argument("--reviewer", required=True)

    dismiss_parser = sub.add_parser("dismiss")
    dismiss_parser.add_argument("--id", required=True)
    dismiss_parser.add_argument("--reason", required=True)
    dismiss_parser.add_argument("--reviewer", required=True)

    sub.add_parser("summary")

    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        if args.command == "list":
            items = list_open_items(session, item_type=args.item_type, limit=args.limit)
            print(f"{len(items)} open item(s)")
            for item in items:
                print(
                    f"  id={item.id} type={item.item_type} reason={item.reason_code} "
                    f"priority={item.priority} ref={item.reference_id}"
                )
        elif args.command == "resolve":
            item = resolve_item(session, uuid.UUID(args.id), args.resolution, args.reviewer)
            print(f"resolved: {item.id}")
        elif args.command == "dismiss":
            item = dismiss_item(session, uuid.UUID(args.id), args.reason, args.reviewer)
            print(f"dismissed: {item.id}")
        elif args.command == "summary":
            summary = summarize_queue(session)
            for item_type, statuses in sorted(summary.items()):
                print(f"{item_type}: {statuses}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
