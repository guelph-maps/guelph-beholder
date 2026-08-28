"""Fetch OSM address-bearing elements via Overpass (cached), plus a live
single-element lookup for the detail panel."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

USER_AGENT = "guelph-beholder/0.1 (OSM address coverage audit)"
_HEADERS = {"User-Agent": USER_AGENT}


@dataclass(frozen=True)
class OsmElement:
    type: str          # node | way | relation
    id: int
    lat: float
    lon: float
    tags: dict[str, str]

    @property
    def ref(self) -> str:
        return f"{self.type}/{self.id}"


def _bbox_key(bbox: tuple[float, float, float, float]) -> str:
    s = ",".join(f"{v:.5f}" for v in bbox)
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def _overpass_query(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    b = f"{south},{west},{north},{east}"
    return (
        "[out:json][timeout:180];"
        "("
        f'node["addr:housenumber"]({b});'
        f'way["addr:housenumber"]({b});'
        f'relation["addr:housenumber"]({b});'
        ");"
        "out tags center;"
    )


def _parse_elements(raw: dict) -> list[OsmElement]:
    out: list[OsmElement] = []
    for el in raw.get("elements", []):
        if "lat" in el and "lon" in el:
            lat, lon = el["lat"], el["lon"]
        elif "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue
        out.append(OsmElement(
            type=el["type"], id=int(el["id"]),
            lat=float(lat), lon=float(lon),
            tags=el.get("tags", {}) or {},
        ))
    return out


def fetch_addr_elements(
    overpass_url: str,
    cache_dir: Path,
    bbox: tuple[float, float, float, float],
    *,
    force: bool = False,
    session: requests.Session | None = None,
) -> list[OsmElement]:
    """All OSM elements carrying addr:housenumber within bbox. Cached to disk
    by bbox; pass force=True to refetch."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"overpass_{_bbox_key(bbox)}.json"
    if cache_file.exists() and not force:
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        return _parse_elements(raw)

    sess = session or requests
    resp = sess.post(overpass_url, data={"data": _overpass_query(bbox)},
                     headers=_HEADERS, timeout=300)
    resp.raise_for_status()
    raw = resp.json()
    raw["_fetched_at"] = time.time()
    raw["_bbox"] = list(bbox)
    cache_file.write_text(json.dumps(raw), encoding="utf-8")
    return _parse_elements(raw)


def load_osm_file(path: Path) -> list[OsmElement]:
    """Load OSM address elements from a prebuilt JSON file (e.g. a saved
    Overpass response, for offline reruns). Accepts either a bare list of
    elements or the Overpass `{"elements": [...]}` wrapper."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    elements = data if isinstance(data, list) else data.get("elements", [])
    return _parse_elements({"elements": elements})


def fetch_element(osm_api_base: str, osm_type: str, osm_id: int) -> dict | None:
    """Live fetch of a single element's current state from the OSM API.
    Returns the element dict (with tags, visible, version, ...) or None if
    deleted/absent. Used by the detail panel (secondary enrichment)."""
    url = f"{osm_api_base}/{osm_type}/{osm_id}.json"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    if resp.status_code in (404, 410):
        return None
    resp.raise_for_status()
    els = resp.json().get("elements", [])
    return els[0] if els else None
