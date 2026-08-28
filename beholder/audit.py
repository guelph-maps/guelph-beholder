"""Correctness checks on a matched OSM element.

Present/missing answers "is this address in OSM at all". These answer "is what
OSM says about it right", field by field, for every field the City source can
verify. Each check yields an issue code; a point carries zero or more.

The source is not automatically the authority — `street_spelling` fires when the
two literals differ and one of them is wrong, which in Guelph has been the City
("Mcgee Street" against OSM's "McGee Street"). The codes name the disagreement,
not the culprit; the detail panel shows both literals so a reviewer can judge.

WARD is deliberately not checked: the source's 1-6 integer is modelled as an
admin polygon in OSM, not an address tag.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .city import AddressPoint, CIVIC
from .osm import OsmElement
from .streets import normalize_street

# Postal codes are compared with spacing and case ignored; the canonical
# written form is "A1A 1A1" and anything else is a formatting issue.
_CANONICAL_POSTCODE = re.compile(r"[A-Z]\d[A-Z] \d[A-Z]\d")

POSTCODE_MISSING = "postcode_missing"
POSTCODE_MISMATCH = "postcode_mismatch"
POSTCODE_FORMAT = "postcode_format"
CITY_MISSING = "city_missing"
CITY_MISMATCH = "city_mismatch"
STREET_SPELLING = "street_spelling"
FAR_MATCH = "far_match"
DUPLICATE_OSM = "duplicate_osm"
CIVIC_ON_UNIT_OBJECT = "civic_on_unit_object"


def deprecated_code(tag: str) -> str:
    return "deprecated_" + tag.replace(":", "_").replace("-", "_")


@dataclass(frozen=True)
class AuditPolicy:
    far_match_m: float = 40.0
    deprecated_tags: tuple[str, ...] = field(default_factory=tuple)


def _norm_postcode(value: str | None) -> str:
    return (value or "").replace(" ", "").upper()


def issues_for(
    point: AddressPoint,
    element: OsmElement,
    distance_m: float,
    match_count: int,
    policy: AuditPolicy,
) -> tuple[str, ...]:
    """Every issue code the matched element earns for this point."""
    found: list[str] = []
    tags = element.tags

    src_pc = _norm_postcode(point.postcode)
    osm_pc_raw = (tags.get("addr:postcode") or "").strip()
    if src_pc and not osm_pc_raw:
        found.append(POSTCODE_MISSING)
    elif src_pc and _norm_postcode(osm_pc_raw) != src_pc:
        found.append(POSTCODE_MISMATCH)
    elif osm_pc_raw and not _CANONICAL_POSTCODE.fullmatch(osm_pc_raw):
        found.append(POSTCODE_FORMAT)

    osm_city = (tags.get("addr:city") or "").strip()
    if not osm_city:
        found.append(CITY_MISSING)
    elif point.municipality and osm_city.upper() != point.municipality.upper():
        # Compared against the source's own PLACE, not a constant "Guelph":
        # the township rows legitimately say something else, and comparing to a
        # constant turned 1 real disagreement into 74 false ones.
        found.append(CITY_MISMATCH)

    osm_street = (tags.get("addr:street") or "").strip()
    if (osm_street and osm_street != point.street_full
            and normalize_street(osm_street) == normalize_street(point.street_full)):
        found.append(STREET_SPELLING)

    if distance_m > policy.far_match_m:
        found.append(FAR_MATCH)

    if match_count > 1:
        found.append(DUPLICATE_OSM)

    if point.kind == CIVIC and tags.get("addr:unit"):
        found.append(CIVIC_ON_UNIT_OBJECT)

    for tag in policy.deprecated_tags:
        if tag in tags:
            found.append(deprecated_code(tag))

    return tuple(sorted(found))


def is_campaign_only(issues: tuple[str, ...] | list[str]) -> bool:
    """True when every issue is a whole-city tag campaign (addr:province sits on
    93% of Guelph's address objects). Such points are not drawn on the flagged
    map layer — they would paint the entire city and mean nothing."""
    return bool(issues) and all(i.startswith("deprecated_") for i in issues)
