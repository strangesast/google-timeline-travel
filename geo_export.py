#!/usr/bin/env python3
"""Export path geometry + assessment for the 3-per-category random sample,
for the map viewer. Reuses extract_road_trips.py and the sample seed."""
import json, random
from datetime import datetime
import extract_road_trips as R

SEED = 20260713

def parse(t): return datetime.fromisoformat(t)
def season(m):
    return {12:"Winter",1:"Winter",2:"Winter",3:"Spring",4:"Spring",5:"Spring",
            6:"Summer",7:"Summer",8:"Summer",9:"Fall",10:"Fall",11:"Fall"}[m]

def collect_points(segs, t0, t1):
    """ordered (lat,lng) along the trip: timelinePath points + activity
    endpoints, in time order. Splits into sub-polylines at large spatial
    jumps (so parked gaps don't draw straight lines across the map)."""
    rows = []  # (time_key, lat, lng)
    for s in segs:
        if s["end"] <= t0 or s["start"] >= t1:
            continue
        if s["kind"] == "timelinePath":
            base = s["start"]
            for pt in s["raw"]["timelinePath"]:
                p = R.parse_geo(pt.get("point"))
                if not p:
                    continue
                try:
                    off = float(pt.get("durationMinutesOffsetFromStartTime") or 0)
                except (ValueError, TypeError):
                    off = 0
                rows.append((base.timestamp() + off * 60, p[0], p[1]))
        elif s["kind"] == "activity":
            a = s["raw"]["activity"]
            for key, t in (("start", s["start"]), ("end", s["end"])):
                p = R.parse_geo(a.get(key))
                if p:
                    rows.append((t.timestamp(), p[0], p[1]))
    rows.sort(key=lambda r: r[0])
    # dedupe consecutive identical, split polyline on big jumps (>25 km)
    lines, cur, prev = [], [], None
    for _, la, ln in rows:
        d = R.haversine((la, ln), prev) if prev else None
        if d is not None and d > 25:
            if len(cur) > 1:
                lines.append(cur)
            cur = []
            prev = None
        if prev is None or d > 0.02:  # >20 m
            cur.append([round(la, 5), round(ln, 5)])
            prev = (la, ln)
    if len(cur) > 1:
        lines.append(cur)
    return lines

def odometer_ratio(segs, t0, t1):
    real = fb = 0
    for s in segs:
        if s["kind"] != "activity" or s["end"] <= t0 or s["start"] >= t1:
            continue
        a = s["raw"]["activity"]
        if a.get("topCandidate", {}).get("type") not in R.DRIVE_TYPES:
            continue
        if float(a.get("distanceMeters", 0) or 0) > 0:
            real += 1
        else:
            fb += 1
    return real, real + fb

def main():
    segs, current_home, trips_j = R.run_pipeline("location-history.json")
    enriched = [(R.assess_trip(tj, segs, current_home)) for tj in trips_j]

    by_cat = {"long-haul": [], "regional": [], "local": []}
    for t in enriched:
        by_cat[t["category"]].append(t)

    rng = random.Random(SEED)
    out = []
    for cat in ("long-haul", "regional", "local"):
        pool = by_cat[cat]
        for t in rng.sample(pool, min(3, len(pool))):
            t0, t1 = parse(t["start"]), parse(t["end"])
            lines = collect_points(segs, t0, t1)
            npts = sum(len(l) for l in lines)
            real, tot = odometer_ratio(segs, t0, t1)
            stops = [s for s in t["top_stops"] if s["coord"]]
            out.append({
                "category": cat,
                "title": t["origin"] + (f" → {t['farthest']}"
                         if t["farthest"] != t["origin"] else ""),
                "start": t["start"], "end": t["end"],
                "date_label": (t["start"][:10] if t["start"][:10] == t["end"][:10]
                               else f"{t['start'][:10]} → {t['end'][:10]}"),
                "season": season(t0.month),
                "month_label": (t0.strftime("%b %d, %Y") if t["start"][:10] == t["end"][:10]
                                else f"{t0.strftime('%b %d')} – {t1.strftime('%b %d, %Y')}"),
                "duration_days": t["duration_days"],
                "n_driving_days": t["n_journeys"], "n_legs": t["n_legs"],
                "drive_km": t["drive_km"], "drive_mi": round(t["drive_km"] / 1.609, 1),
                "avg_speed_kmh": t["avg_moving_speed_kmh"],
                "avg_speed_mph": round(t["avg_moving_speed_kmh"] / 1.609, 1),
                "drive_hours": t["drive_hours"],
                "longest_leg_km": t["longest_leg_km"],
                "max_dist_from_home_km": t["max_dist_from_home_km"],
                "n_stops": t["n_stops"], "n_overnight": t["n_overnight_stops"],
                "odometer_legs": real, "total_drive_legs": tot,
                "n_points": npts,
                "lines": lines,
                "stops": [{"lat": s["coord"][0], "lng": s["coord"][1],
                           "label": s["label"], "type": s["type"],
                           "overnight": s["overnight"],
                           "dwell_hours": s["dwell_hours"]} for s in stops[:12]],
            })
            print(f"{cat:10} {out[-1]['title']:34} {npts:5} pts in "
                  f"{len(lines)} line(s)")

    json.dump(out, open("trips_geo.json", "w"))
    print(f"\nWrote trips_geo.json ({len(out)} trips)")

if __name__ == "__main__":
    main()
