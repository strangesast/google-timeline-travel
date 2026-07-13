#!/usr/bin/env python3
"""Emit the two data tiers Vite consumes:
  src/data/<name>.dev.json     full fidelity (exact dates) — gitignored, local
  src/data/<name>.public.json  redacted (season only) — leak-gated
Run after the extraction pipeline (geo_export.py / export_all.py / osrm_match.py).
"""
import json, os, sys
from redact import redact_trip, scan_for_leaks

os.makedirs("src/data", exist_ok=True)

def emit(src, name):
    if not os.path.exists(src):
        sys.exit(f"missing {src} — run the extraction pipeline first")
    trips = json.load(open(src))
    json.dump(trips, open(f"src/data/{name}.dev.json", "w"))
    public = [redact_trip(t) for t in trips]
    txt = json.dumps(public)
    leaks = scan_for_leaks(txt)
    if leaks:
        sys.exit(f"PII leak gate FAILED for {name}: {leaks}")
    open(f"src/data/{name}.public.json", "w").write(txt)
    print(f"{name}: dev + public written ({len(trips)} trips) · leak-gate OK")

emit("trips_geo_matched.json", "trips")
emit("all_trips_geo.json", "alltrips")
