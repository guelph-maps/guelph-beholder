"""Create notes on address points. Preset tags are validated against config;
free text is a trimmed one-liner."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

TEXT_MAX = 200


def add_note(
    conn: sqlite3.Connection,
    *,
    address_point_id: int,
    lat: float | None,
    lon: float | None,
    tags: list[str],
    text: str | None,
    author: str,
    preset_tags: list[str],
) -> None:
    """Insert a note. Raises ValueError if neither a valid preset tag nor text
    is supplied (an empty note is meaningless)."""
    tags = [t for t in tags if t in preset_tags]
    text = " ".join((text or "").split())[:TEXT_MAX]
    if not tags and not text:
        raise ValueError("note must have at least one preset tag or some text")
    conn.execute(
        """
        INSERT INTO notes (address_point_id, lat, lon, tags_json, text, author, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (address_point_id, lat, lon, json.dumps(tags), text, author,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
