"""Decide PRESENT vs MISSING for each City address point against OSM.

A point is PRESENT when an OSM element shares its normalized housenumber +
street and sits within match_radius_m. Matching on number+street (not proximity
alone) is what keeps the same address on two different streets apart.

Units. A civic point matches any element carrying its civic number, whatever
that element's unit says; a unit point additionally requires the element's
`addr:unit` to be its own. So `100 Main St` and `100 Main St #3` are two tracked
points that can resolve to two different nodes.

The double-encoding workaround. Guelph's 2025 import wrote units into the
housenumber — `addr:housenumber=714-30` *and* `addr:unit=30` (5,538 objects as
of 2026-08-27), so nothing carries the bare civic `714`. Those elements are
accepted as found: they are indexed under the bare civic number as well, and the
match is flagged `combined` so the residue is countable and shrinks as the split
campaign lands. The split is only believed when `addr:unit` backs it — that is
what keeps real ranges (`380-400 Waterloo Avenue`, 17 of them) and interpolation
ways from being mistaken for units. `;`-lists (`52A;52B;52`) are split likewise
and flagged `semicolon`.

A clean match always beats a workaround match, even a nearer one, so the
`combined` count stays honest.

Once a point has an element, `audit.issues_for()` checks what OSM says about it
field by field — see beholder/audit.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .audit import AuditPolicy, issues_for
from .city import AddressPoint, CIVIC, norm_housenumber, norm_unit
from .osm import OsmElement
from .streets import normalize_street

PRESENT = "PRESENT"
MISSING = "MISSING"

# How the element's address had to be read for the match to happen.
CLEAN = "clean"          # addr:housenumber is the civic number as written
COMBINED = "combined"    # addr:housenumber=714-30 + addr:unit=30
SEMICOLON = "semicolon"  # addr:housenumber=52A;52B;52

# Preference order: a clean reading wins over any workaround reading.
_FORM_RANK = {CLEAN: 0, SEMICOLON: 1, COMBINED: 2}

_MatchKey = tuple[str, str]  # (housenumber_norm, street_norm)


@dataclass(frozen=True)
class Candidate:
    element: OsmElement
    unit_norm: str
    match_form: str


@dataclass(frozen=True)
class ConflationResult:
    address_point_id: int
    status: str                 # PRESENT | MISSING
    osm_ref: str | None         # "node/123" of the matched element
    representation: str | None  # node | building | way | relation | interpolation
    match_form: str | None      # clean | combined | semicolon
    distance_m: float | None
    issues: tuple[str, ...] = ()
    # Distinct OSM elements carrying this address, ignoring the combined form
    # (the 30 unit nodes of "714-30 Willow Road" are 30 doors, not 30 duplicates).
    match_count: int = 0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _representation(el: OsmElement) -> str:
    if "addr:interpolation" in el.tags:
        return "interpolation"
    if el.type == "node":
        return "node"
    if el.type == "way":
        return "building" if "building" in el.tags else "way"
    return "relation"


def split_combined(housenumber: str, unit: str) -> str | None:
    """Return the bare civic number of a double-encoded housenumber, or None.

    Only splits when `unit` actually backs the trailing part, which is what
    distinguishes `714-30` + addr:unit=30 (a unit) from `380-400` (a range).
    Suffixed civics survive: `645A-2` + unit 2 -> `645A`.
    """
    if not housenumber or not unit:
        return None
    tail = "-" + unit
    if housenumber.endswith(tail) and len(housenumber) > len(tail):
        return housenumber[: -len(tail)]
    return None


def element_candidates(el: OsmElement) -> list[tuple[_MatchKey, Candidate]]:
    """Every (key, candidate) this element answers to. One element can answer to
    several keys: a `;`-list is one key per part, and a double-encoded
    housenumber answers to its bare civic number as well."""
    street = normalize_street(el.tags.get("addr:street"))
    raw = norm_housenumber(el.tags.get("addr:housenumber"))
    unit = norm_unit(el.tags.get("addr:unit"))
    if not raw or not street:
        return []

    out: list[tuple[_MatchKey, Candidate]] = []
    if ";" in raw:
        for part in (p.strip() for p in raw.split(";")):
            if part:
                out.append(((part, street), Candidate(el, unit, SEMICOLON)))
        return out

    out.append(((raw, street), Candidate(el, unit, CLEAN)))
    civic = split_combined(raw, unit)
    if civic:
        out.append(((civic, street), Candidate(el, unit, COMBINED)))
    return out


def build_index(osm_elements: Iterable[OsmElement]) -> dict[_MatchKey, list[Candidate]]:
    idx: dict[_MatchKey, list[Candidate]] = {}
    for el in osm_elements:
        for key, cand in element_candidates(el):
            idx.setdefault(key, []).append(cand)
    return idx


def conflate_points(
    points: Iterable[AddressPoint],
    osm_elements: Iterable[OsmElement],
    radius_m: float,
    policy: AuditPolicy | None = None,
) -> list[ConflationResult]:
    policy = policy or AuditPolicy()
    index = build_index(osm_elements)
    results: list[ConflationResult] = []
    for p in points:
        candidates = index.get((p.housenumber_norm, p.street_norm), ())
        best: tuple[int, float, Candidate] | None = None
        distinct: set[str] = set()
        for cand in candidates:
            # A unit point wants its own door; a civic point takes any element
            # carrying its civic number.
            if p.kind != CIVIC and cand.unit_norm != p.unit_norm:
                continue
            d = _haversine_m(p.lat, p.lon, cand.element.lat, cand.element.lon)
            if d > radius_m:
                continue
            if cand.match_form != COMBINED:
                distinct.add(cand.element.ref)
            score = (_FORM_RANK[cand.match_form], round(d, 1))
            if best is None or score < (best[0], best[1]):
                best = (score[0], score[1], cand)
        if best is None:
            results.append(ConflationResult(
                p.address_point_id, MISSING, None, None, None, None,
            ))
        else:
            _, d, cand = best
            results.append(ConflationResult(
                p.address_point_id, PRESENT, cand.element.ref,
                _representation(cand.element), cand.match_form, d,
                issues_for(p, cand.element, d, len(distinct), policy),
                len(distinct),
            ))
    return results
