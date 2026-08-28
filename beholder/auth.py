"""OSM OAuth2 login, a dev-login bypass, and the post-rights allowlist.

Session state is a signed Flask cookie: session['user'] is the OSM display
name. Posting notes is gated by can_post(); reading is open to everyone.
"""
from __future__ import annotations

from authlib.integrations.flask_client import OAuth
from flask import Flask, redirect, session, url_for

from .config import Config


def current_user() -> str | None:
    return session.get("user")


def can_post(cfg: Config) -> bool:
    user = current_user()
    if not user:
        return False
    if cfg.can_dev_login and user == cfg.dev_admin_user:
        return True
    return user in cfg.allowlist


def init_auth(app: Flask, cfg: Config) -> None:
    oauth = OAuth(app)
    oauth.register(
        name="osm",
        client_id=cfg.osm_client_id,
        client_secret=cfg.osm_client_secret,
        authorize_url=cfg.oauth_authorize_url,
        access_token_url=cfg.oauth_token_url,
        client_kwargs={"scope": cfg.oauth_scope, "token_endpoint_auth_method": "client_secret_post"},
    )

    @app.get("/auth/login")
    def auth_login():
        return oauth.osm.authorize_redirect(cfg.redirect_uri)

    @app.get("/auth/callback")
    def auth_callback():
        oauth.osm.authorize_access_token()
        # OSM has no OIDC userinfo; read the authenticated user's details.
        resp = oauth.osm.get(cfg.oauth_userinfo_url)
        user = resp.json().get("user", {})
        if user.get("display_name"):
            session["user"] = user["display_name"]
            session["uid"] = user.get("id")
        return redirect(url_for("index"))

    @app.get("/auth/logout")
    def auth_logout():
        session.clear()
        return redirect(url_for("index"))

    if cfg.can_dev_login:
        @app.get("/auth/dev-login")
        def auth_dev_login():
            session["user"] = cfg.dev_admin_user
            session["uid"] = 0
            return redirect(url_for("index"))

    @app.context_processor
    def _inject_auth():
        return {"current_user": current_user(), "can_post": can_post(cfg)}
