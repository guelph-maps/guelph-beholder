"""Standalone street-name normalization for conflation.

Reimplemented from the import tool's conflation (referenced, not imported).
Both sides are run through normalize_street() (after apply_street_override() on
the City side) so they compare equal. Guelph's source street is already OSM long
form ("Cork Street West"), unlike Toronto's short form, but the normalizer
collapses both to the same key either way.
"""
from __future__ import annotations

STREET_SUFFIXES = {
    "STREET": "ST", "ROAD": "RD", "AVENUE": "AVE", "BOULEVARD": "BLVD",
    "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "PLACE": "PL",
    "TERRACE": "TER", "CRESCENT": "CRES", "SQUARE": "SQ", "GATE": "GTE",
    "CIRCLE": "CIR", "WAY": "WAY", "TRAIL": "TRL", "PARKWAY": "PKWY",
    "HIGHWAY": "HWY", "EXPRESSWAY": "EXPY",
    "CRT": "CT", "CRCL": "CIR", "GT": "GTE",
    "GARDENS": "GDNS", "GROVE": "GRV", "HEIGHTS": "HTS",
    "PATHWAY": "PTWY", "CIRCUIT": "CRCT", "BRIDGE": "BDGE", "LAWN": "LWN",
    "PARK": "PK", "ROADWAY": "RDWY", "CLOSE": "CS", "WOODS": "WDS",
    "GREEN": "GRN",
}

DIRS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}

# Source-name -> OSM-canonical-name overrides for streets where the City source
# and OSM disagree on the actual name (proper-noun spacing the normalizer can't
# bridge, or outright suffix corrections). Values keep the source's short
# suffixes so normalize_street() collapses them the same on both sides.
STREET_NAME_OVERRIDES: dict[str, str] = {
    # Empty on purpose. Toronto needed a dozen of these; Guelph's source and
    # OSM agree so far. Add entries here as real mismatches surface in reviews
    # (a street where every point reads MISSING is the tell).
}

_OVERRIDES_LOOKUP: dict[str, str] = {
    " ".join(k.upper().split()): v for k, v in STREET_NAME_OVERRIDES.items()
}


def apply_street_override(name: str | None) -> str | None:
    """Return the OSM-canonical name for a known City spelling variant, else
    return `name` unchanged. Case- and whitespace-insensitive."""
    if not name:
        return name
    return _OVERRIDES_LOOKUP.get(" ".join(name.upper().split()), name)


def _glue_mc(tokens: list[str]) -> list[str]:
    """Collapse a standalone "MC" onto the following word ("MC CAUL" -> "MCCAUL")
    so the City source's spaced spelling matches OSM's joined one. Mirrors the
    import tool's _glue_mc_prefix: only fires when the next token is a plain word,
    not a suffix or direction."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if (t == "MC" and i + 1 < len(tokens)
                and tokens[i + 1].isalpha()
                and tokens[i + 1] not in STREET_SUFFIXES
                and tokens[i + 1] not in DIRS):
            out.append("MC" + tokens[i + 1])
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def normalize_street(name: str | None) -> str:
    """Uppercase, strip dots, glue Mc-prefixes, and collapse suffix/direction
    tokens to their short forms so City and OSM street names compare equal."""
    if not name:
        return ""
    out = []
    for p in _glue_mc(name.upper().replace(".", "").split()):
        if p in STREET_SUFFIXES:
            out.append(STREET_SUFFIXES[p])
        elif p in DIRS:
            out.append(DIRS[p])
        else:
            out.append(p)
    return " ".join(out)


def city_street_norm(name: str | None) -> str:
    """Full City-side normalization: apply overrides, then normalize."""
    return normalize_street(apply_street_override(name))
