# Guelph Address Beholder

The **Guelph dataset** for [`address-beholder`](../address-beholder): audits how
completely and how correctly the City of Guelph's address points are represented
in OpenStreetMap, over time.

Part of the [guelph-maps](https://github.com/guelph-maps) organisation, which
indexes every Guelph project. Its sibling on the same engine is
[`guelph-pitches-beholder`](https://github.com/guelph-maps/guelph-pitches-beholder)
— courts and sports fields instead of addresses.

This repo holds no engine code. It is a dataset directory — `config.toml`,
`readings.py`, `.env`, and a gitignored `data/` — run by the engine beside it:

```sh
cd ../address-beholder
.\.venv\Scripts\python.exe run.py --dataset-dir ../guelph-beholder review
.\.venv\Scripts\python.exe run.py --dataset-dir ../guelph-beholder serve
# http://127.0.0.1:5000
```

`--cache` reuses the last Overpass extract instead of refetching. A full review
takes about ten seconds.

## What makes Guelph Guelph

Guelph's import is **finished** — a community import completed in October 2025 —
so this is not a backlog tracker. It watches a near-complete city for residue,
for regressions, and for the tag cleanups still outstanding.

**Units are tracked as their own points.** 13,162 of 53,846 source rows carry a
unit. `guelph-address-import` collapses them to civic for upload; the beholder
does not, because a unit is a real door and is expected to be its own node in
OSM. The table and map default to civic addresses, since ~7.5k unmapped units
would otherwise bury the civic residue. The same City address points are
visible inside iD and JOSM as
[`guelph-address-layer`](https://guelph-maps.github.io/guelph-address-layer/)
([source](https://github.com/guelph-maps/guelph-address-layer)).

**`readings.py` is a workaround, and it is meant to be deleted.** The 2025
import wrote units into the housenumber — `addr:housenumber=714-30` *and*
`addr:unit=30` — so nothing in Guelph carries the bare civic number, and ~830
more objects carry `;`-separated housenumbers. Until the split campaign lands
(see `guelph-address-import/IMPORT_PROPOSAL.mediawiki`, "Mechanical edits"),
those elements are accepted as found and the match is recorded under the reading
that rescued it, so the residue stays countable and visibly shrinks. Delete the
file and the `[conflation] readings` line together when the data is fixed;
nothing has to be unwound.

**`addr:province` is a campaign, not a defect.** It sits on 44,891 of 48,344
Guelph address objects, so it is declared in `[audit] deprecated_tags`, kept out
of the headline count, and left off the map's flagged layer.

## Where it stood on 2026-08-28

53,846 source points against 48,344 OSM address elements.

| | tracked | missing |
|---|---|---|
| civic | 40,684 | 927 (2.3%) |
| unit | 13,162 | 7,522 |

7,216 present matches work only under a workaround reading (5,563 combined
housenumber, 1,653 `;`-list). **1,719** present addresses carry a correctness
issue, plus 43,650 carrying only the `addr:province` campaign:

| code | count |
|---|---|
| `duplicate_osm` | 782 |
| `postcode_missing` | 704 |
| `city_missing` | 354 |
| `far_match` | 265 |
| `civic_on_unit_object` | 236 |
| `postcode_mismatch` | 44 |
| `postcode_format` | 28 |
| `street_spelling` | 5 |
| `city_mismatch` | 1 |

Three streets read missing end to end — Sora Lane, Poppy Drive West, Crawley
Road — and all three are genuine gaps, not normalization failures: Sora Lane does
not exist in OSM at all. `[streets] overrides` is empty for that reason; a street
where *every* point reads MISSING is the tell that an entry belongs there.

## Auth

Shares the Toronto dataset's registered OSM OAuth2 app and its
`http://127.0.0.1:5000/auth/callback` redirect, so only one of the two can be
served at a time. `.env` holds the credentials; with `BEHOLDER_DEV=1`,
`/auth/dev-login` signs in as `DEV_ADMIN_USER` without OSM.

## Related

- [`address-beholder`](https://github.com/skfd/address-beholder) — the engine
- [`guelph-address-import`](https://github.com/guelph-maps/guelph-address-import) — the
  upload side, whose `config.toml` this dataset's field mapping mirrors
- [`guelph-address-layer`](https://github.com/guelph-maps/guelph-address-layer) —
  the same points as an editor tile layer
- [`guelph-pitches-beholder`](https://github.com/guelph-maps/guelph-pitches-beholder)
  — courts and sports fields on the same engine
- `ontario-address-changes` — the tracker DB this reads
