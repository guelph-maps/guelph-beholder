# Guelph Address Beholder

Audits the completeness of Guelph address coverage in OpenStreetMap **over
time**. The unit of tracking is the **City address point**, not an OSM node: for
every active City of Guelph address point, is it present in OSM today or
missing? Because reviews run periodically, the beholder keeps its own
append-only history of how each point's status changes between runs. Approved
mappers can leave notes (preset tags + a one-liner) explaining why an address is
missing.

Guelph's import is **finished** — a community import completed in October 2025 —
so this is not a backlog tracker. It watches a near-complete city for residue,
for regressions, and for the tag cleanups that are still outstanding.

Same tool as `toronto-import-beholder`, retargeted. It is **standalone**: it
reads the City scraper DB and live OSM, and reimplements the small helpers it
needs (street normalization etc.) rather than importing the address-import
tool's code.

## Data flow

```
City scraper DB (guelph.db, read-only)  --+
                                          +-> conflate (number+street[+unit], 100 m) -> status events -> current_state -> table (all) + map (missing)
OSM addresses (Overpass, whole city)    --+                                             (append-on-change)   (snapshot)
```

- **PRESENT** — an OSM element with a matching `addr:housenumber` + normalized
  `addr:street` sits within 100 m (representation: node / building / way /
  relation / interpolation).
- **MISSING** — no such match.

### Units

Guelph's source publishes 13,162 unit rows alongside 40,684 civic ones, and
`guelph-address-import` collapses them to civic for upload. The beholder does
**not**: a unit is a real door and is expected to be its own node in OSM, so it
is tracked as its own point. A civic point matches any element carrying its
civic number; a unit point additionally requires the element's `addr:unit`.

Because ~7.5k units have no OSM node at all, the table and map default to
**civic addresses only** — the `kind` filter switches to units or to both.

### The double-encoded-housenumber workaround

Guelph's 2025 import wrote units into the housenumber:
`addr:housenumber=714-30` **and** `addr:unit=30`, so nothing carries the bare
civic `714`. Splitting that back out is a pending mechanical edit (see
`guelph-address-import/IMPORT_PROPOSAL.mediawiki`, "Mechanical edits"). Until it
lands, those elements are **accepted as found** — indexed under the bare civic
number as well — and the match is recorded as `match_form = combined` so the
residue is countable. `;`-lists (`52A;52B;52`) are split likewise and recorded
as `semicolon`.

Three things keep this honest:

- the split is believed **only when `addr:unit` backs it**, which is what keeps
  real ranges (`380-400 Waterloo Avenue`) and interpolation ways from being read
  as units;
- a **clean match always beats a workaround match**, even a nearer one;
- when an address's form is fixed the point gets a `format_fixed` transition, so
  the campaign's progress is visible in the history rather than invisible.

Nothing has to be unwound when the cleanup lands: a point matched via `combined`
today matches the split node tomorrow, still PRESENT.

## Layout

| Path | Role |
|---|---|
| `beholder/city.py` | read active City address points (read-only), civic + unit |
| `beholder/streets.py` | street normalizer + name overrides |
| `beholder/osm.py` | Overpass fetch (cached) + live single-element lookup |
| `beholder/conflate.py` | present/missing, representation, and the housenumber workaround |
| `beholder/history.py` | review runs + append-on-change status events |
| `beholder/snapshot.py` | materialize `current_state` table + `points.geojson` |
| `beholder/queries.py` | read queries for the web layer |
| `beholder/auth.py` | OSM OAuth2 + dev-login + allowlist |
| `beholder/notes.py` | note creation |
| `beholder/web/` | Flask app, templates, static (MapLibre + HTMX) |
| `scripts/run_review.py` | one review: fetch -> conflate -> events -> snapshot |

## Setup

```sh
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env        # then edit
```

`.env` keys: `FLASK_SECRET`, `OSM_CLIENT_ID`/`OSM_CLIENT_SECRET`, and for local
work `BEHOLDER_DEV=1` + `DEV_ADMIN_USER=...`. With `BEHOLDER_DEV=1` the
`/auth/dev-login` bypass is enabled (and is never registered otherwise).

This beholder **shares the Toronto beholder's registered OSM OAuth2 app** — same
credentials, same `http://127.0.0.1:5000/auth/callback` redirect — so only one of
the two can run at a time. To run both, register a second app at
https://www.openstreetmap.org/oauth2/applications (scope `read_prefs`), point
`[auth] redirect_uri` at the new port, and serve with `--port`.

`config.toml` holds non-secret settings: City DB path, Overpass URL, Guelph
bbox, match radius, preset note tags, and the post allowlist.

## Run a review, then serve

```sh
# Small area first (downtown, around St. George's Square):
.\.venv\Scripts\python.exe scripts\run_review.py --bbox 43.538,-80.256,43.550,-80.244
# Full city (~10 s end to end):
.\.venv\Scripts\python.exe scripts\run_review.py

.\.venv\Scripts\python.exe -m flask --app beholder.web.app run
# http://127.0.0.1:5000
```

`--cache` reuses the previous Overpass extract instead of refetching.

## Tests

```sh
.\.venv\Scripts\python.exe -m pytest
```

## Where it stood at the first seed (2026-08-27)

53,846 City points against 48,344 OSM address elements, full run in ~10 s.

| | tracked | missing |
|---|---|---|
| civic | 40,684 | 927 (2.3%) |
| unit | 13,162 | 7,522 (57%) |

Of the present matches, **5,563** work only through a unit-in-housenumber and
**1,653** through a `;`-list — both awaiting the tag cleanup. Three streets read
missing end to end (Sora Lane, Poppy Drive West, Crawley Road); all three are
genuine gaps, not normalization failures — Sora Lane does not exist in OSM at
all.

## Scale / known limits

- The **map renders MISSING points only**, filtered to civic by default. The
  GeoJSON is minified + pre-gzipped (`points.geojson.gz`, ~70 KB on the wire) and
  served with `Content-Encoding: gzip`. The table lists all points server-side.
- `STREET_NAME_OVERRIDES` is empty: Guelph's source street is already OSM long
  form and no systematic mismatch has surfaced. A street where *every* point
  reads MISSING is the tell that one belongs there.
- OSM addresses with `addr:housenumber` but no `addr:street` won't match and will
  read as MISSING — expected.
- The bbox is a rectangle around a city that is wholly inside Wellington County,
  so it catches township addresses in the corners. The 75 `Guelph/Eramosa Twp`
  source rows are tracked like any other point; `municipality` tells them apart.
