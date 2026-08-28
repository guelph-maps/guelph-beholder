import pytest

from beholder import db as _db
from beholder.conflate import ConflationResult, PRESENT, MISSING
from beholder.history import record_review, latest_statuses


@pytest.fixture
def conn(tmp_path):
    dbp = tmp_path / "b.db"
    _db.init_db(dbp)
    c = _db.connect(dbp)
    yield c
    c.close()


def _r(apid, status, ref=None, rep=None, form=None):
    return ConflationResult(apid, status, ref, rep, form, 0.0 if ref else None)


def test_seed_then_no_change_then_change(conn):
    run1 = [_r(1, PRESENT, "node/10", "node", "clean"), _r(2, MISSING)]
    s1 = record_review(conn, run1, bbox=None, osm_element_count=2)
    assert s1["changes"] == 2 and s1["seeded"] is True

    # identical second run -> no new events
    s2 = record_review(conn, run1, bbox=None, osm_element_count=2)
    assert s2["changes"] == 0 and s2["seeded"] is False

    # point 2 resolves, point 1 changes representation
    run3 = [_r(1, PRESENT, "way/20", "building", "clean"),
            _r(2, PRESENT, "node/99", "node", "clean")]
    s3 = record_review(conn, run3, bbox=None, osm_element_count=2)
    assert s3["changes"] == 2

    ls = latest_statuses(conn)
    assert ls[1].status == PRESENT and ls[1].representation == "building"
    assert ls[2].status == PRESENT


def test_event_count_is_change_only(conn):
    record_review(conn, [_r(1, PRESENT, "node/10", "node", "clean")], bbox=None, osm_element_count=1)
    record_review(conn, [_r(1, PRESENT, "node/10", "node", "clean")], bbox=None, osm_element_count=1)
    n = conn.execute("SELECT COUNT(*) FROM status_events WHERE address_point_id=1").fetchone()[0]
    assert n == 1


def test_prev_status_recorded_on_transition(conn):
    record_review(conn, [_r(1, MISSING)], bbox=None, osm_element_count=0)
    record_review(conn, [_r(1, PRESENT, "node/5", "node", "clean")], bbox=None, osm_element_count=1)
    row = conn.execute(
        "SELECT status, prev_status FROM status_events WHERE address_point_id=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["status"] == PRESENT and row["prev_status"] == MISSING


def test_the_housenumber_split_landing_is_its_own_event(conn):
    # Same node, same status: only the way its housenumber is written changed.
    record_review(conn, [_r(1, PRESENT, "node/10", "node", "combined")],
                  bbox=None, osm_element_count=1)
    s = record_review(conn, [_r(1, PRESENT, "node/10", "node", "clean")],
                      bbox=None, osm_element_count=1)
    assert s["changes"] == 1
    row = conn.execute(
        "SELECT match_form, prev_match_form FROM status_events "
        "WHERE address_point_id=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["match_form"] == "clean" and row["prev_match_form"] == "combined"
    assert latest_statuses(conn)[1].match_form == "clean"
