#!/usr/bin/env python3
"""Emit the two data tiers Vite consumes:
  src/data/<name>.dev.json     full fidelity (exact dates) — gitignored, local
  src/data/<name>.public.json  redacted (season only) — leak-gated
Run after the extraction pipeline (geo_export.py / export_all.py / osrm_match.py).

All tiers are loaded, redacted, and leak-gated BEFORE anything is written, so a
gate failure on one tier cannot leave a stale/mismatched public.json for another.
"""
import json, os, sys
from redact import redact_trip, scan_for_leaks

SPECS = [("trips_geo_matched.json", "trips"), ("all_trips_geo.json", "alltrips")]


def prepare(src, name):
    if not os.path.exists(src):
        sys.exit(f"missing {src} — run the extraction pipeline first")
    trips = json.load(open(src))
    public = [redact_trip(t) for t in trips]
    leaks = scan_for_leaks(json.dumps(public))
    if leaks:
        sys.exit(f"PII leak gate FAILED for {name}: {leaks}")
    return name, trips, public


def main():
    os.makedirs("src/data", exist_ok=True)
    prepared = [prepare(src, name) for src, name in SPECS]   # exits before any write on failure
    for name, dev, public in prepared:
        json.dump(dev, open(f"src/data/{name}.dev.json", "w"))
        json.dump(public, open(f"src/data/{name}.public.json", "w"))
        print(f"{name}: dev + public written ({len(dev)} trips) · leak-gate OK")


if __name__ == "__main__":
    main()
