"""Beholder's own SQLite store: review runs, per-point status events, notes.

Separate from the read-only City scraper DB. Auth/session state lives in
Flask's signed cookie, so there's no sessions table here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    bbox              TEXT,
    osm_element_count INTEGER,
    present_count     INTEGER,
    missing_count     INTEGER,
    change_count      INTEGER,
    note              TEXT
);

-- Append-only: one row only when a point's (status, representation, match_form) changes
-- versus its last known state. Current state = latest row per address_point_id.
CREATE TABLE IF NOT EXISTS status_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    address_point_id INTEGER NOT NULL,
    review_run_id    INTEGER NOT NULL,
    ts               TEXT NOT NULL,
    status           TEXT NOT NULL,          -- PRESENT | MISSING
    representation   TEXT,                    -- node|building|way|relation|interpolation
    match_form       TEXT,                    -- clean|combined|semicolon
    osm_ref          TEXT,
    prev_status      TEXT,
    prev_match_form  TEXT,
    FOREIGN KEY (review_run_id) REFERENCES review_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_status_events_point ON status_events(address_point_id, id);

CREATE TABLE IF NOT EXISTS notes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    address_point_id INTEGER NOT NULL,
    lat              REAL,
    lon              REAL,
    tags_json        TEXT NOT NULL DEFAULT '[]',
    text             TEXT,
    author           TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_point ON notes(address_point_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
