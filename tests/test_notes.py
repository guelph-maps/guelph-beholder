import json

import pytest
from flask import Flask, session

from beholder import auth as _auth
from beholder import config as _config
from beholder import db as _db
from beholder.notes import add_note


@pytest.fixture
def conn(tmp_path):
    dbp = tmp_path / "b.db"
    _db.init_db(dbp)
    c = _db.connect(dbp)
    yield c
    c.close()


PRESET = ["Merged into building", "Wrong location / bad data"]


def test_add_note_filters_tags_and_trims_text(conn):
    add_note(conn, address_point_id=1, lat=1.0, lon=2.0,
             tags=["Merged into building", "NOT A PRESET"], text="  hello    world ",
             author="skfd", preset_tags=PRESET)
    row = conn.execute("SELECT tags_json, text, author FROM notes").fetchone()
    assert json.loads(row["tags_json"]) == ["Merged into building"]
    assert row["text"] == "hello world"
    assert row["author"] == "skfd"


def test_add_note_text_only_ok(conn):
    add_note(conn, address_point_id=1, lat=None, lon=None, tags=[], text="just text",
             author="skfd", preset_tags=PRESET)
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1


def test_add_note_empty_raises(conn):
    with pytest.raises(ValueError):
        add_note(conn, address_point_id=1, lat=None, lon=None,
                 tags=["bogus"], text="   ", author="skfd", preset_tags=PRESET)


def test_can_post_allowlist():
    cfg = _config.load()  # allowlist includes 'skfd'
    app = Flask(__name__)
    app.secret_key = "test"

    with app.test_request_context("/"):
        assert _auth.can_post(cfg) is False  # anonymous

    with app.test_request_context("/"):
        session["user"] = "skfd"
        assert _auth.can_post(cfg) is True

    with app.test_request_context("/"):
        session["user"] = "some_random_mapper"
        assert _auth.can_post(cfg) is False
