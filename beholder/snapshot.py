"""Materialize current state (City point attributes + latest status) into a
queryable `current_state` table plus a GeoJSON layer for the map.

The table is what the web data-grid filters/paginates; the GeoJSON feeds the
MapLibre layer. Guelph is ~54k points and the MISSING set is a residue on top of
a completed 2025 import, so the map layer stays small.
"""
from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .city import AddressPoint
from .audit import is_campaign_only
from .conflate import CLEAN
from .config import Config
from . import db as _db

CURRENT_STATE_SCHEMA = """
DROP TABLE IF EXISTS current_state;
CREATE TABLE current_state (
    address_point_id INTEGER PRIMARY KEY,
    address_full     TEXT,
    address_number   TEXT,
    street_full      TEXT,
    unit             TEXT,
    kind             TEXT,        -- civic | unit
    municipality     TEXT,
    ward             TEXT,
    postcode         TEXT,
    lat              REAL,
    lon              REAL,
    status           TEXT,
    representation   TEXT,
    match_form       TEXT,        -- clean | combined | semicolon
    issues           TEXT,        -- sorted, comma-joined audit codes ('' when clean)
    distance_m       REAL,
    match_count      INTEGER,
    osm_ref          TEXT,
    prev_status      TEXT,
    changed_in_run   INTEGER,     -- review_run_id of the latest status event
    transition       TEXT         -- '', 'newly_missing', 'newly_present', 'format_fixed', 'issues_changed', 'representation_changed'
);
CREATE INDEX idx_cs_status ON current_state(status);
CREATE INDEX idx_cs_kind ON current_state(kind);
CREATE INDEX idx_cs_street ON current_state(street_full);
CREATE INDEX idx_cs_muni ON current_state(municipality);
CREATE INDEX idx_cs_form ON current_state(match_form);
CREATE INDEX idx_cs_issues ON current_state(issues);
"""


def _latest_events(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT address_point_id, status, representation, match_form, issues,
               distance_m, osm_ref, prev_status, prev_match_form, prev_issues,
               review_run_id
        FROM status_events
        WHERE id IN (SELECT MAX(id) FROM status_events GROUP BY address_point_id)
        """
    ).fetchall()
    return {r["address_point_id"]: r for r in rows}


def _latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MAX(id) FROM review_runs").fetchone()
    return row[0]


def _transition(ev: sqlite3.Row, latest_run_id: int | None) -> str:
    if ev["review_run_id"] != latest_run_id or ev["prev_status"] is None:
        return ""
    if ev["prev_status"] != ev["status"]:
        return "newly_missing" if ev["status"] == "MISSING" else "newly_present"
    # Same status, so something else moved. Precedence is fixed so a run always
    # labels the same change the same way: a workaround match turning clean is
    # the double-encoding cleanup landing here; otherwise an audit issue
    # appeared or was fixed; otherwise the geometry changed.
    if ev["prev_match_form"] != ev["match_form"] and ev["match_form"] == CLEAN:
        return "format_fixed"
    if (ev["prev_issues"] or "") != (ev["issues"] or ""):
        return "issues_changed"
    return "representation_changed"


def build_snapshot(cfg: Config, points: Iterable[AddressPoint],
                   match_counts: dict[int, int] | None = None) -> list[Path]:
    conn = _db.connect(cfg.db_path)
    try:
        events = _latest_events(conn)
        latest_run = _latest_run_id(conn)
        conn.executescript(CURRENT_STATE_SCHEMA)

        rows = []
        for p in points:
            ev = events.get(p.address_point_id)
            rows.append((
                p.address_point_id, p.address_full, p.address_number, p.street_full,
                p.unit, p.kind, p.municipality, p.ward, p.postcode, p.lat, p.lon,
                ev["status"] if ev else None,
                ev["representation"] if ev else None,
                ev["match_form"] if ev else None,
                ev["issues"] if ev else None,
                ev["distance_m"] if ev else None,
                (match_counts or {}).get(p.address_point_id),
                ev["osm_ref"] if ev else None,
                ev["prev_status"] if ev else None,
                ev["review_run_id"] if ev else None,
                _transition(ev, latest_run) if ev else "",
            ))
        conn.executemany(
            """
            INSERT INTO current_state
                (address_point_id, address_full, address_number, street_full,
                 unit, kind, municipality, ward, postcode, lat, lon, status,
                 representation, match_form, issues, distance_m, match_count,
                 osm_ref, prev_status, changed_in_run, transition)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        conn.commit()
        geojson_path = _write_geojson(conn, cfg.snapshot_dir)
    finally:
        conn.close()
    return [cfg.db_path, geojson_path]


def _write_geojson(conn: sqlite3.Connection, snapshot_dir: Path) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    features = []
    # The map draws what needs a mapper's attention: MISSING points, and PRESENT
    # points carrying an audit issue. Points whose only issues are whole-city tag
    # campaigns are left off — addr:province alone would paint every address in
    # Guelph. `kind` rides along so the map can filter civic/unit in step with
    # the table.
    for r in conn.execute(
        "SELECT address_point_id, lon, lat, kind, status, issues, transition "
        "FROM current_state WHERE status = 'MISSING' OR issues != ''"
    ):
        issues = [i for i in (r["issues"] or "").split(",") if i]
        if r["status"] != "MISSING" and is_campaign_only(issues):
            continue
        props = {"id": r["address_point_id"], "kind": r["kind"],
                 "state": "missing" if r["status"] == "MISSING" else "flagged"}
        if r["transition"]:
            props["transition"] = r["transition"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(r["lon"], 5), round(r["lat"], 5)]},
            "properties": props,
        })
    blob = json.dumps({"type": "FeatureCollection", "features": features},
                      separators=(",", ":")).encode("utf-8")
    path = snapshot_dir / "points.geojson"
    path.write_bytes(blob)
    # Pre-gzip so the web layer can serve it with Content-Encoding: gzip.
    with gzip.open(snapshot_dir / "points.geojson.gz", "wb", compresslevel=6) as f:
        f.write(blob)
    return path
