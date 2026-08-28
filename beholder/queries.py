"""Read queries over the materialized current_state table (+ events/notes)."""
from __future__ import annotations

import collections
import sqlite3

from .audit import is_campaign_only

PAGE_SIZE = 100

_ALLOWED_STATUS = {"PRESENT", "MISSING"}
_ALLOWED_TRANSITION = {"newly_missing", "newly_present", "format_fixed",
                       "issues_changed", "representation_changed"}
_ALLOWED_KIND = {"civic", "unit"}
_ALLOWED_FORM = {"clean", "combined", "semicolon"}


def has_snapshot(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='current_state'"
    ).fetchone()
    return row is not None


def _where(filters: dict) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if filters.get("status") in _ALLOWED_STATUS:
        clauses.append("status = ?")
        params.append(filters["status"])
    if filters.get("transition") in _ALLOWED_TRANSITION:
        clauses.append("transition = ?")
        params.append(filters["transition"])
    if filters.get("kind") in _ALLOWED_KIND:
        clauses.append("kind = ?")
        params.append(filters["kind"])
    if filters.get("match_form") in _ALLOWED_FORM:
        clauses.append("match_form = ?")
        params.append(filters["match_form"])
    issue = (filters.get("issue") or "").strip()
    if issue == "any":
        clauses.append("issues != ''")
    elif issue and issue.replace("_", "").isalnum():
        # Anchored on the separators so no code can match another's substring.
        clauses.append("',' || issues || ',' LIKE ?")
        params.append(f"%,{issue},%")
    if filters.get("municipality"):
        clauses.append("municipality = ?")
        params.append(filters["municipality"])
    q = (filters.get("q") or "").strip()
    if q:
        clauses.append("(address_full LIKE ? OR street_full LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def list_addresses(conn, filters: dict, page: int = 1, page_size: int = PAGE_SIZE):
    where, params = _where(filters)
    total = conn.execute(f"SELECT COUNT(*) FROM current_state{where}", params).fetchone()[0]
    page = max(1, page)
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT address_point_id, address_full, street_full, unit, kind, municipality,
               lat, lon, status, representation, match_form, issues, distance_m,
               osm_ref, transition
        FROM current_state{where}
        ORDER BY status DESC, street_full, address_number + 0, address_number, unit
        LIMIT ? OFFSET ?
        """,
        params + [page_size, offset],
    ).fetchall()
    return rows, total


def facets(conn) -> dict:
    munis = [r[0] for r in conn.execute(
        "SELECT DISTINCT municipality FROM current_state WHERE municipality != '' ORDER BY 1"
    )]
    return {"municipalities": munis}


def issue_summary(conn) -> dict:
    """Per-code counts (commonest first) plus how many points are genuinely
    flagged. Read off the stored strings in one pass rather than one LIKE query
    per code.

    `flagged` deliberately excludes points whose only issues are whole-city tag
    campaigns: addr:province sits on 93% of Guelph's address objects, so a
    rollup including it would report "45,369 addresses have a problem" and mean
    nothing. Those are counted separately and kept out of the map layer.
    """
    tally: collections.Counter[str] = collections.Counter()
    flagged = campaign_only = 0
    for issues, n in conn.execute(
        "SELECT issues, COUNT(*) FROM current_state WHERE issues != '' GROUP BY issues"
    ):
        codes = [c for c in issues.split(",") if c]
        for code in codes:
            tally[code] += n
        if is_campaign_only(codes):
            campaign_only += n
        else:
            flagged += n
    return {"counts": tally.most_common(), "flagged": flagged,
            "campaign_only": campaign_only}


def coverage(conn) -> dict:
    """Headline counts for the top bar: how much is missing, and how much of
    what is present is only matched through the double-encoding workaround."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(status = 'MISSING') AS missing,
               SUM(status = 'MISSING' AND kind = 'civic') AS missing_civic,
               SUM(status = 'MISSING' AND kind = 'unit') AS missing_unit,
               SUM(match_form = 'combined') AS combined,
               SUM(match_form = 'semicolon') AS semicolon
        FROM current_state
        """
    ).fetchone()
    out = {k: (row[k] or 0) for k in row.keys()}
    summary = issue_summary(conn)
    out["issues"] = summary["counts"]
    out["flagged"] = summary["flagged"]
    out["campaign_only"] = summary["campaign_only"]
    return out


def get_point(conn, address_point_id: int):
    return conn.execute(
        "SELECT * FROM current_state WHERE address_point_id = ?", (address_point_id,)
    ).fetchone()


def notes_for(conn, address_point_id: int):
    return conn.execute(
        """
        SELECT id, tags_json, text, author, created_at
        FROM notes WHERE address_point_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (address_point_id,),
    ).fetchall()


def point_history(conn, address_point_id: int):
    return conn.execute(
        """
        SELECT e.ts, e.status, e.representation, e.match_form, e.osm_ref,
               e.prev_status, e.review_run_id
        FROM status_events e
        WHERE e.address_point_id = ?
        ORDER BY e.id DESC
        """,
        (address_point_id,),
    ).fetchall()
