"""Read queries over the materialized current_state table (+ events/notes)."""
from __future__ import annotations

import sqlite3

PAGE_SIZE = 100

_ALLOWED_STATUS = {"PRESENT", "MISSING"}
_ALLOWED_TRANSITION = {"newly_missing", "newly_present", "format_fixed",
                       "representation_changed"}
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
               lat, lon, status, representation, match_form, osm_ref, transition
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
    return {k: (row[k] or 0) for k in row.keys()}


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
