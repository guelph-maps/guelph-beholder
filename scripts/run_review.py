"""One review run: fetch OSM -> conflate City points -> append status events.

    python scripts/run_review.py                  # full Guelph bbox
    python scripts/run_review.py --bbox 43.538,-80.256,43.550,-80.244
    python scripts/run_review.py --force --note "weekly review"
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from beholder import config as _config
from beholder import db as _db
from beholder import osm as _osm
from beholder.city import iter_active_points
from beholder.conflate import conflate_points
from beholder.history import record_review


def _parse_bbox(s: str) -> tuple[float, float, float, float]:
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be 'south,west,north,east'")
    return (parts[0], parts[1], parts[2], parts[3])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run a Beholder review.")
    p.add_argument("--bbox", type=_parse_bbox, default=None,
                   help="south,west,north,east (default: full Guelph bbox)")
    p.add_argument("--cache", action="store_true",
                   help="reuse the cached Overpass extract instead of fetching fresh")
    p.add_argument("--note", default=None, help="optional note for this run")
    p.add_argument("--no-snapshot", action="store_true", help="skip snapshot materialization")
    args = p.parse_args(argv)

    cfg = _config.load()
    bbox = args.bbox or cfg.city_bbox

    print(f"Reading City points in bbox {bbox} ...")
    points = list(iter_active_points(cfg.city_sqlite_path, bbox=bbox,
                                     active_status_values=cfg.active_status_values))
    units = sum(1 for p in points if p.kind == "unit")
    print(f"  {len(points)} active address points ({len(points) - units} civic, {units} unit)")

    if cfg.osm_source == "file":
        print(f"Loading OSM addr elements from {cfg.osm_file_path} ...")
        elements = _osm.load_osm_file(cfg.osm_file_path)
    else:
        print(f"Fetching OSM addr elements (Overpass{', cached' if args.cache else ', fresh'}) ...")
        elements = _osm.fetch_addr_elements(cfg.overpass_url, cfg.cache_dir, bbox,
                                            force=not args.cache)
    print(f"  {len(elements)} OSM elements")

    print("Conflating ...")
    results = conflate_points(points, elements, cfg.match_radius_m)

    _db.init_db(cfg.db_path)
    conn = _db.connect(cfg.db_path)
    try:
        summary = record_review(
            conn, results, bbox=bbox, osm_element_count=len(elements), note=args.note,
        )
    finally:
        conn.close()

    forms = Counter(r.match_form for r in results if r.match_form)
    print(
        f"Review #{summary['run_id']}: {summary['present']} present, "
        f"{summary['missing']} missing, {summary['changes']} change events"
        f"{' (initial seed)' if summary['seeded'] else ''}."
    )
    workaround = forms["combined"] + forms["semicolon"]
    if workaround:
        print(f"  {workaround} of the present matches only work through the "
              f"housenumber workaround ({forms['combined']} combined, "
              f"{forms['semicolon']} ;-list).")

    if not args.no_snapshot:
        try:
            from beholder.snapshot import build_snapshot
        except ImportError:
            print("(snapshot module not available yet; skipping)")
        else:
            paths = build_snapshot(cfg, points)
            print(f"Snapshot written: {', '.join(str(p) for p in paths)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
