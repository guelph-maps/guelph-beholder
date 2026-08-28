"""Read active City of Guelph address points from the scraper DB (read-only).

One tracked point per source row, units included: a unit row is a real door and
is expected to be its own node in OSM, so it is tracked as its own point rather
than collapsed into its civic address (which is what guelph-address-import's
`[units] policy = "collapse-to-civic"` does on the upload side — the beholder
audits what OSM has, not what we would upload).

`address_full` is synthesized as number + street. The source's own ADDRESS /
`full` column appends the unit ("44 Regent Street B"), which is not an address
anyone writes; the unit is carried in its own field instead.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from .streets import city_street_norm

CIVIC = "civic"
UNIT = "unit"


@dataclass(frozen=True)
class AddressPoint:
    address_point_id: int
    address_full: str
    address_number: str
    housenumber_norm: str
    street_full: str
    street_norm: str
    unit: str
    unit_norm: str
    kind: str            # civic | unit
    municipality: str
    ward: str
    postcode: str
    lat: float
    lon: float


def norm_housenumber(num: str | None) -> str:
    """Match key for a housenumber: uppercase, whitespace collapsed."""
    if not num:
        return ""
    return " ".join(num.upper().split())


# A unit designator normalizes the same way a housenumber does ("2b" -> "2B").
norm_unit = norm_housenumber


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def active_snapshot_id(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT MAX(id) FROM snapshots WHERE skipped=0").fetchone()[0]


def _props(r: sqlite3.Row) -> dict:
    try:
        return json.loads(r["props"])
    except (TypeError, ValueError):
        return {}


def _row_to_point(r: sqlite3.Row, props: dict) -> AddressPoint:
    street_full = r["street"] or ""
    number = r["number"] or ""
    unit = (r["unit"] or "").strip()
    ward = props.get("WARD")
    return AddressPoint(
        address_point_id=int(r["identity_key"]),
        address_full=" ".join(x for x in (number, street_full) if x),
        address_number=number,
        housenumber_norm=norm_housenumber(number),
        street_full=street_full,
        street_norm=city_street_norm(street_full),
        unit=unit,
        unit_norm=norm_unit(unit),
        kind=UNIT if unit else CIVIC,
        municipality=props.get("PLACE", ""),
        # Guelph's WARD is an integer 1-6, empty on the township rows.
        ward="" if ward is None else str(ward),
        postcode=props.get("POSTCODE", "") or "",
        lat=float(r["latitude"]),
        lon=float(r["longitude"]),
    )


def iter_active_points(
    city_sqlite_path: Path,
    bbox: tuple[float, float, float, float] | None = None,
    active_status_values: Sequence[str] = (),
) -> Iterator[AddressPoint]:
    """Yield every active address point, optionally clipped to bbox
    [south, west, north, east]."""
    conn = _connect_ro(city_sqlite_path)
    statuses = {s.upper() for s in active_status_values}
    try:
        snap = active_snapshot_id(conn)
        sql = "SELECT * FROM addresses WHERE max_snapshot_id = ?"
        params: list = [snap]
        if bbox is not None:
            south, west, north, east = bbox
            sql += (" AND latitude BETWEEN ? AND ?"
                    " AND longitude BETWEEN ? AND ?")
            params += [south, north, west, east]
        for r in conn.execute(sql, params):
            if r["latitude"] is None or r["longitude"] is None:
                continue
            props = _props(r)
            if statuses and str(props.get("STATUS", "")).upper() not in statuses:
                continue
            yield _row_to_point(r, props)
    finally:
        conn.close()
