"""Record review runs and append per-point status-change events."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .conflate import ConflationResult, MISSING, PRESENT


@dataclass(frozen=True)
class PointState:
    status: str
    representation: str | None
    match_form: str | None
    issues: str | None
    osm_ref: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_statuses(conn: sqlite3.Connection) -> dict[int, PointState]:
    """Current known state per point = the most recent status_event row."""
    rows = conn.execute(
        """
        SELECT address_point_id, status, representation, match_form, issues, osm_ref
        FROM status_events
        WHERE id IN (SELECT MAX(id) FROM status_events GROUP BY address_point_id)
        """
    ).fetchall()
    return {
        r["address_point_id"]: PointState(r["status"], r["representation"],
                                          r["match_form"], r["issues"], r["osm_ref"])
        for r in rows
    }


def record_review(
    conn: sqlite3.Connection,
    results: Iterable[ConflationResult],
    *,
    bbox: tuple[float, float, float, float] | None,
    osm_element_count: int,
    note: str | None = None,
) -> dict:
    """Open a review run, append a status_event for every point whose
    (status, representation, match_form, issues) changed vs its last known state, and close the run
    with summary counts. Returns the summary dict."""
    results = list(results)
    ts = _now()
    bbox_str = ",".join(f"{v:.5f}" for v in bbox) if bbox else None

    cur = conn.execute(
        "INSERT INTO review_runs (started_at, bbox, osm_element_count) VALUES (?, ?, ?)",
        (ts, bbox_str, osm_element_count),
    )
    run_id = cur.lastrowid

    prev = latest_statuses(conn)
    present = missing = changes = 0
    new_events: list[tuple] = []
    for r in results:
        if r.status == PRESENT:
            present += 1
        else:
            missing += 1
        before = prev.get(r.address_point_id)
        issues = ",".join(r.issues)
        changed = (
            before is None
            or before.status != r.status
            or before.representation != r.representation
            or before.match_form != r.match_form
            or (before.issues or "") != issues
        )
        if changed:
            changes += 1
            new_events.append((
                r.address_point_id, run_id, ts, r.status,
                r.representation, r.match_form, issues, r.distance_m, r.osm_ref,
                before.status if before else None,
                before.match_form if before else None,
                before.issues if before else None,
            ))

    conn.executemany(
        """
        INSERT INTO status_events
            (address_point_id, review_run_id, ts, status, representation, match_form,
             issues, distance_m, osm_ref, prev_status, prev_match_form, prev_issues)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        new_events,
    )
    conn.execute(
        """
        UPDATE review_runs
        SET finished_at = ?, present_count = ?, missing_count = ?, change_count = ?, note = ?
        WHERE id = ?
        """,
        (_now(), present, missing, changes, note, run_id),
    )
    conn.commit()
    return {
        "run_id": run_id,
        "points": len(results),
        "present": present,
        "missing": missing,
        "changes": changes,
        "seeded": prev == {},
    }
