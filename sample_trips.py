#!/usr/bin/env python3
"""Randomly sample 3 trips from each category and deep-assess them,
including data-quality metrics. Reuses extract_road_trips.py."""
import random
from datetime import datetime
import extract_road_trips as R

SEED = 20260713  # fixed for reproducibility

def parse(t): return datetime.fromisoformat(t)

def season(m):
    return {12:"winter",1:"winter",2:"winter",3:"spring",4:"spring",5:"spring",
            6:"summer",7:"summer",8:"summer",9:"fall",10:"fall",11:"fall"}[m]

def window_segments(segs, t0, t1):
    return [s for s in segs if s["end"] > t0 and s["start"] < t1]

def coverage_and_gap(segs, t0, t1):
    """temporal coverage fraction and largest uncovered gap (hours)."""
    ivals = sorted((max(s["start"], t0), min(s["end"], t1))
                   for s in window_segments(segs, t0, t1))
    if not ivals:
        return 0.0, (t1 - t0).total_seconds() / 3600.0
    merged = [list(ivals[0])]
    for a, b in ivals[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    covered = sum((b - a).total_seconds() for a, b in merged)
    total = (t1 - t0).total_seconds()
    # largest gap = biggest uncovered stretch between merged intervals (+edges)
    gaps = [(merged[0][0] - t0).total_seconds()]
    for (a1, b1), (a2, b2) in zip(merged, merged[1:]):
        gaps.append((a2 - b1).total_seconds())
    gaps.append((t1 - merged[-1][1]).total_seconds())
    return covered / total, max(gaps) / 3600.0

def leg_quality(trip_journeys):
    """count of driving legs using true odometer vs haversine fallback."""
    real = fallback = 0
    for jn in trip_journeys:
        pass  # journeys don't carry leg detail; recomputed below
    return real, fallback

def main():
    path = "location-history.json"
    segs = R.load_segments(path)
    current_home, _ = R.build_home_lookup(path and segs)
    legs, _ = R.extract_legs(segs)
    journeys = R.chain_journeys(legs)
    trips_j = R.group_trips(journeys, segs, current_home)
    # pair each assessed trip with its underlying journeys+legs
    enriched = []
    for tj in trips_j:
        a = R.assess_trip(tj, segs, current_home)
        a["_journeys"] = tj
        enriched.append(a)

    by_cat = {"long-haul": [], "regional": [], "local": []}
    for t in enriched:
        by_cat[t["category"]].append(t)

    rng = random.Random(SEED)
    print(f"Random sample (seed={SEED}) — 3 trips per category\n" + "=" * 74)
    for cat in ("long-haul", "regional", "local"):
        pool = by_cat[cat]
        picks = rng.sample(pool, min(3, len(pool)))
        print(f"\n########  {cat.upper()}  ({len(pool)} trips in category)  ########")
        for t in picks:
            t0, t1 = parse(t["start"]), parse(t["end"])
            cov, gap = coverage_and_gap(segs, t0, t1)
            # recompute leg-level odometer vs fallback for this trip's window
            real = fb = 0
            for s in window_segments(segs, t0, t1):
                if s["kind"] != "activity":
                    continue
                a = s["raw"]["activity"]
                if a.get("topCandidate", {}).get("type") not in R.DRIVE_TYPES:
                    continue
                km = float(a.get("distanceMeters", 0) or 0)
                (real := real + 1) if km > 0 else (fb := fb + 1)
            route = t["origin"] + (f" → {t['farthest']}" if t["farthest"] != t["origin"] else "")
            d0, d1 = t["start"][:10], t["end"][:10]
            span = d0 if d0 == d1 else f"{d0} → {d1}"
            disp_note = ""
            # data-quality flag: recorded driving vs straight-line reach
            if t["drive_km"] < t["max_dist_from_home_km"]:
                disp_note = "  ⚠ recorded driving < straight-line reach (missing legs)"
            print(f"\n  {span}   {route}")
            print(f"    duration     : {t['duration_days']:.2f} days "
                  f"({t['n_journeys']} driving day(s), {t['n_legs']} legs)")
            print(f"    time of year : {t0.strftime('%b %d')} – {t1.strftime('%b %d %Y')} "
                  f"({season(t0.month)})")
            print(f"    driving      : {t['drive_km']:.0f} km / {t['drive_km']/1.609:.0f} mi | "
                  f"longest leg {t['longest_leg_km']:.0f} km | "
                  f"farthest {t['max_dist_from_home_km']:.0f} km from home")
            print(f"    avg speed    : {t['avg_moving_speed_kmh']:.0f} km/h moving "
                  f"({t['drive_hours']:.1f} h driving)")
            print(f"    stops        : {t['n_stops']} ({t['n_overnight_stops']} overnight)")
            print(f"    DATA QUALITY : coverage {cov*100:.0f}% of trip timeline | "
                  f"largest gap {gap:.1f} h | "
                  f"odometer legs {real}/{real+fb}{disp_note}")

if __name__ == "__main__":
    main()
