"""Load config.toml + .env into one settings object."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    # city
    city_name: str
    city_sqlite_path: Path
    active_status_values: tuple[str, ...]
    # osm
    osm_source: str
    osm_file_path: Path
    overpass_url: str
    osm_api_base: str
    city_bbox: tuple[float, float, float, float]
    # conflation
    match_radius_m: float
    # audit
    far_match_m: float
    deprecated_tags: tuple[str, ...]
    # beholder paths
    db_path: Path
    snapshot_dir: Path
    cache_dir: Path
    # notes
    preset_tags: list[str]
    # auth
    allowlist: list[str]
    oauth_authorize_url: str
    oauth_token_url: str
    oauth_userinfo_url: str
    oauth_scope: str
    redirect_uri: str
    # secrets / env
    flask_secret: str
    osm_client_id: str
    osm_client_secret: str
    dev_mode: bool
    dev_admin_user: str = ""

    @property
    def can_dev_login(self) -> bool:
        return self.dev_mode and bool(self.dev_admin_user)


def _abs(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else (ROOT / p)


def load(path: str | Path | None = None) -> Config:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else (ROOT / "config.toml")
    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)

    bbox = raw["osm"]["city_bbox"]
    return Config(
        city_name=raw["city"].get("name", "City"),
        city_sqlite_path=_abs(raw["city"]["sqlite_path"]),
        active_status_values=tuple(raw["city"].get("active_status_values", [])),
        osm_source=raw["osm"].get("source", "overpass"),
        osm_file_path=_abs(raw["osm"].get("file_path", "")),
        overpass_url=raw["osm"]["overpass_url"],
        osm_api_base=raw["osm"]["api_base"],
        city_bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
        match_radius_m=float(raw["conflation"]["match_radius_m"]),
        far_match_m=float(raw["audit"]["far_match_m"]),
        deprecated_tags=tuple(raw["audit"]["deprecated_tags"]),
        db_path=_abs(raw["beholder"]["db_path"]),
        snapshot_dir=_abs(raw["beholder"]["snapshot_dir"]),
        cache_dir=_abs(raw["beholder"]["cache_dir"]),
        preset_tags=list(raw["notes"]["preset_tags"]),
        allowlist=list(raw["auth"]["allowlist"]),
        oauth_authorize_url=raw["auth"]["oauth_authorize_url"],
        oauth_token_url=raw["auth"]["oauth_token_url"],
        oauth_userinfo_url=raw["auth"]["oauth_userinfo_url"],
        oauth_scope=raw["auth"]["oauth_scope"],
        redirect_uri=raw["auth"]["redirect_uri"],
        flask_secret=os.environ.get("FLASK_SECRET", "dev-insecure-secret"),
        osm_client_id=os.environ.get("OSM_CLIENT_ID", ""),
        osm_client_secret=os.environ.get("OSM_CLIENT_SECRET", ""),
        dev_mode=os.environ.get("BEHOLDER_DEV", "") == "1",
        dev_admin_user=os.environ.get("DEV_ADMIN_USER", ""),
    )
