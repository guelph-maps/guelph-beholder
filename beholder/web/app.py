"""Flask app factory + routes."""
from __future__ import annotations

import sqlite3

from flask import (Flask, abort, g, render_template, request,
                   send_from_directory)

from .. import auth as _auth
from .. import config as _config
from .. import notes as _notes
from .. import osm, queries


def create_app() -> Flask:
    cfg = _config.load()
    app = Flask(__name__)
    app.secret_key = cfg.flask_secret
    app.config["BEHOLDER"] = cfg

    import json as _json
    app.add_template_filter(lambda s: _json.loads(s or "[]"), "fromjson")

    _auth.init_auth(app, cfg)

    def get_conn() -> sqlite3.Connection:
        if "conn" not in g:
            conn = sqlite3.connect(cfg.db_path)
            conn.row_factory = sqlite3.Row
            g.conn = conn
        return g.conn

    @app.teardown_appcontext
    def _close(_exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    def _filters() -> dict:
        return {
            "status": request.args.get("status", ""),
            "transition": request.args.get("transition", ""),
            "kind": request.args.get("kind", ""),
            "match_form": request.args.get("match_form", ""),
            "municipality": request.args.get("municipality", ""),
            "q": request.args.get("q", ""),
        }

    @app.get("/")
    def index():
        conn = get_conn()
        ready = queries.has_snapshot(conn)
        fac = queries.facets(conn) if ready else {"municipalities": []}
        cov = queries.coverage(conn) if ready else {}
        return render_template("index.html", cfg=cfg, ready=ready, facets=fac,
                               coverage=cov)

    @app.get("/api/addresses")
    def api_addresses():
        conn = get_conn()
        if not queries.has_snapshot(conn):
            return render_template("_table.html", rows=[], total=0, page=1,
                                   page_size=queries.PAGE_SIZE, filters=_filters())
        try:
            page = int(request.args.get("page", 1))
        except ValueError:
            page = 1
        filters = _filters()
        rows, total = queries.list_addresses(conn, filters, page=page)
        return render_template("_table.html", rows=rows, total=total, page=page,
                               page_size=queries.PAGE_SIZE, filters=filters)

    @app.get("/address/<int:apid>")
    def address_detail(apid):
        conn = get_conn()
        pt = queries.get_point(conn, apid)
        if pt is None:
            abort(404)
        history = queries.point_history(conn, apid)
        notes = queries.notes_for(conn, apid)
        live = None
        if pt["osm_ref"]:
            otype, oid = pt["osm_ref"].split("/")
            try:
                live = osm.fetch_element(cfg.osm_api_base, otype, int(oid))
            except Exception:
                live = None
        return render_template("_detail.html", pt=pt, history=history,
                               notes=notes, live=live, cfg=cfg,
                               apid=apid, preset_tags=cfg.preset_tags,
                               is_missing=(pt["status"] == "MISSING"))

    @app.post("/address/<int:apid>/notes")
    def add_note(apid):
        if not _auth.can_post(cfg):
            abort(403)
        conn = get_conn()
        pt = queries.get_point(conn, apid)
        if pt is None:
            abort(404)
        try:
            _notes.add_note(
                conn, address_point_id=apid, lat=pt["lat"], lon=pt["lon"],
                tags=request.form.getlist("tags"), text=request.form.get("text", ""),
                author=_auth.current_user(), preset_tags=cfg.preset_tags,
            )
        except ValueError:
            pass
        notes = queries.notes_for(conn, apid)
        return render_template("_notes.html", notes=notes, apid=apid,
                               preset_tags=cfg.preset_tags,
                               is_missing=(pt["status"] == "MISSING"))

    @app.get("/api/points.geojson")
    def api_points():
        gz = cfg.snapshot_dir / "points.geojson.gz"
        if gz.exists():
            resp = send_from_directory(cfg.snapshot_dir, "points.geojson.gz",
                                       mimetype="application/geo+json")
            resp.headers["Content-Encoding"] = "gzip"
            return resp
        path = cfg.snapshot_dir / "points.geojson"
        if not path.exists():
            return {"type": "FeatureCollection", "features": []}
        return send_from_directory(cfg.snapshot_dir, "points.geojson",
                                   mimetype="application/geo+json")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


app = create_app()
