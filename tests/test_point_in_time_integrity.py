"""Phase 3 exit gate 4: "100% of feature rows have max_input_known_at
<= as_of (proven by test AND query)." The query half lives in
docs/phase-3/evidence/point-in-time-proof.log; this is the test half --
it must keep passing on every real build of feature_snapshots, not just
the one time the query was run by hand."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_every_feature_snapshot_respects_point_in_time_integrity(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT feature_set_version, count(*) AS total,
                   count(*) FILTER (WHERE max_input_known_at IS NOT NULL) AS with_known_at,
                   count(*) FILTER (
                       WHERE max_input_known_at IS NOT NULL
                       AND max_input_known_at::date > as_of
                   ) AS violating
            FROM feature_snapshots
            GROUP BY feature_set_version
            """
        )
    ).all()

    if not rows:
        pytest.skip("no feature_snapshots rows exist yet in this database")

    for feature_set_version, total, with_known_at, violating in rows:
        assert violating == 0, (
            f"{feature_set_version}: {violating}/{with_known_at} rows "
            f"(of {total} total) have max_input_known_at > as_of -- leakage"
        )
