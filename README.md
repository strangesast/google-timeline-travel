# Timeline Road Trips

Extracts road trips from a Google Timeline export and renders them as two
Vite-built, self-contained web views:

- **`viewer.html`** — per-trip detail: road-projected GPS on a light basemap,
  political-boundary overview, stats, animated directional flow.
- **`density.html`** — all trips at once; overlapping low-opacity lines make
  more-travelled corridors render darker.

## Privacy model (important)

Published artifacts contain **no absolute dates/times**. Season is the only
indication of *when* a trip happened; any relative time is expressed per-trip
(e.g. `+1hr 23min`). Redaction happens at **build time** (`redact.py`) — the
public payload never contains the raw fields — and a leak gate fails the build
if a date, clock time, or residence label slips through. Exact coordinates are
intentionally retained (the routes are the content).

Two data tiers, selected by Vite mode:

| tier | data | use |
|------|------|-----|
| `public` (default) | redacted, season-only | **the deployable** |
| `dev` (`--mode dev`) | full dates | local work only — gitignored |

## Pipeline

```
# 1. one-time data extraction (needs location-history.json — never committed)
python3 extract_road_trips.py     # trips + road_trips.csv/json
python3 geo_export.py             # sampled-trip geometry  -> trips_geo.json
python3 osrm_match.py             # snap to OSM roads       -> trips_geo_matched.json
python3 export_all.py             # all-trip geometry       -> all_trips_geo.json

# 2. build the two data tiers (redaction + leak gate)
python3 prepare_data.py           # -> src/data/{trips,alltrips}.{dev,public}.json

# 3. dev / build
npm install
npm run dev            # local dev server, FULL dates (mode=dev)
npm run build          # production build, PUBLIC (redacted) -> dist/
npm run preview        # serve dist/
```

## Layout

```
src/            viewer.js/.css  density.js/.css  mapsettings.js/.css   (app source)
src/data/       generated data tiers (gitignored)
viewer.html
density.html    Vite entry points
vite.config.js  multi-page build; @trips/@alltrips aliases resolve by mode
*.py            data pipeline (extraction + redaction)
```

Leaflet is bundled from npm (no CDN runtime dependency). Map **tiles** are still
fetched from CARTO at runtime — the only remaining external request.
