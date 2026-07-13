#!/usr/bin/env python3
"""Export raw path geometry for ALL road trips (for the density view).
Uses recorded GPS points (no OSRM snapping — too many requests for 400+ trips);
already road-following and fine for an aggregate density map."""
import json
from datetime import datetime
import extract_road_trips as R
from geo_export import collect_points

segs = R.load_segments("location-history.json")
current_home, _ = R.build_home_lookup(segs)
legs, _ = R.extract_legs(segs)
journeys = R.chain_journeys(legs)
trips_j = R.group_trips(journeys, segs, current_home)

out = []
for tj in trips_j:
    a = R.assess_trip(tj, segs, current_home)
    t0, t1 = datetime.fromisoformat(a["start"]), datetime.fromisoformat(a["end"])
    lines = collect_points(segs, t0, t1)
    if not lines:
        continue
    lines = [[[round(p[0], 4), round(p[1], 4)] for p in ln] for ln in lines]
    out.append({
        "category": a["category"],
        "title": a["origin"] + (f" → {a['farthest']}" if a["farthest"] != a["origin"] else ""),
        "date": a["start"][:10],
        "drive_km": a["drive_km"],
        "lines": lines,
    })

pts = sum(sum(len(l) for l in t["lines"]) for t in out)
lns = sum(len(t["lines"]) for t in out)
json.dump(out, open("all_trips_geo.json", "w"))
print(f"{len(out)} trips · {lns} polylines · {pts} points")
import os
print(f"file size: {os.path.getsize('all_trips_geo.json')//1024} KB")
