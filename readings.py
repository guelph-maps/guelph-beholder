"""Guelph's workaround readings of OSM address tags. Deletable.

The 2025 community import wrote units into the housenumber:
`addr:housenumber=714-30` *and* `addr:unit=30` (5,538 objects on 2026-08-27), so
nothing in Guelph carries the bare civic `714`. Roughly 830 more objects carry
`;`-separated housenumbers (`52A;52B;52`). Splitting both back out is a pending
mechanical edit — see IMPORT_PROPOSAL.mediawiki in guelph-address-import,
"Mechanical edits".

Until that lands, those elements are accepted as found: they are indexed under
the address they *mean* as well as the one they say, and the match is recorded
under this reading's name so the residue stays countable and visibly shrinks.

**Delete this file and the `[conflation] readings` line together when the
cleanup finishes.** Nothing has to be unwound: a point matched under `combined`
today matches the split element tomorrow under `literal`, still PRESENT, and the
change is recorded as a `format_fixed` transition.

The engine deliberately contains none of this. It reads addresses literally,
which is what correct tagging is; this file is a fact about one city's data on
one set of dates.
"""
from __future__ import annotations

from typing import Iterable

from beholder.readings import Reading


def split_combined(housenumber: str, unit: str) -> str | None:
    """The bare civic number of a double-encoded housenumber, or None.

    Only splits when `unit` actually backs the trailing part. That guard is what
    distinguishes `714-30` + addr:unit=30 (a unit) from `380-400 Waterloo
    Avenue` (a range, 17 of them) and from interpolation ways (81). Suffixed
    civics survive: `645A-2` + unit 2 -> `645A`.
    """
    if not housenumber or not unit:
        return None
    tail = "-" + unit
    if housenumber.endswith(tail) and len(housenumber) > len(tail):
        return housenumber[: -len(tail)]
    return None


def combined_unit(housenumber: str, unit: str) -> Iterable[tuple[str, str]]:
    """`714-30` + `addr:unit=30` also answers to civic `714`."""
    civic = split_combined(housenumber, unit)
    return ((civic, unit),) if civic else ()


def semicolon_list(housenumber: str, unit: str) -> Iterable[tuple[str, str]]:
    """`52A;52B;52` answers to each part. Whitespace around the separators is
    real in the data (`38A; 38B`)."""
    if ";" not in housenumber:
        return ()
    return tuple((part.strip(), unit) for part in housenumber.split(";") if part.strip())


#: Both rank below the engine's literal reading (0), so a correctly tagged
#: element always wins the match and the `combined` count never inflates.
READINGS = (
    # A `;`-list beside a plain node is one address written twice, so it counts
    # toward duplicate_osm; the unit nodes behind a combined housenumber are
    # separate doors and do not.
    Reading("semicolon", 1, semicolon_list, counts_as_duplicate=True),
    Reading("combined", 2, combined_unit, counts_as_duplicate=False),
)
