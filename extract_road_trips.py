#!/usr/bin/env python3
"""
extract_road_trips.py  (v2)

Extract *car travel* from a Google Timeline "location-history.json" and assess
each trip. "Road trip" is treated loosely: any travel reliably identifiable as
driving counts -- including one-way intercity / interstate / international
drives, not just multi-day round trips.

BUILD-UP FROM A RELIABLE PRIMITIVE
----------------------------------
Rather than segmenting the timeline by "home" (fragile: home moves over the
12-year span, and a missed home makes whole epochs collapse into one bogus
"trip"), v2 builds up from the most trustworthy unit in the data:

  LEG  -> a single validated driving activity.
          activity.type in {in passenger vehicle, motorcycling}, using
          distanceMeters (a reliable road odometer; haversine fallback when 0).
          A leg is ACCEPTED only if it is physically plausible for a car:
              0 < km <= MAX_LEG_KM,  0 < hours <= MAX_LEG_HOURS,
              implied speed <= MAX_DRIVE_SPEED.
          This gate removes flights mislabeled "in passenger vehicle"
          (e.g. 12,362 km @ 6,794 km/h) -- 0.8% of legs, all absurd.

  JOURNEY -> a maximal chain of legs separated by < CHAIN_GAP_H of non-driving.
          One continuous travel span: a driving day, gas/meal/photo stops
          included; it breaks at an overnight sleep or a long dwell.

  TRIP  -> consecutive journeys not separated by a night spent AT HOME and
          within MAX_TRIP_GAP_DAYS. A single big day-drive is a 1-journey trip;
          a multi-day tour is many journeys. Home is used only to decide trip
          boundaries and to annotate distance-from-home -- never to fabricate
          trips -- so a home miss can only merge, never create a monster.

QUALIFICATION (loose, per request): a journey is kept as car travel if
  drive_km >= MIN_JOURNEY_KM  OR  net displacement >= MIN_DISPLACEMENT_KM.
A trip is reported if it contains >=1 qualifying journey.

Each trip is assessed: dates, duration, driving distance, #legs, moving time,
average moving speed, longest leg, farthest point from home, endpoints and
en-route stops (with dwell + overnight detection), and nearest-city labels
(approximate, from a small built-in North-American gazetteer).

Outputs a console report + road_trips.json + road_trips.csv.
Usage:  python3 extract_road_trips.py [location-history.json]
"""

import json
import re
import sys
import csv
import math
import bisect
from datetime import datetime, timedelta
from collections import Counter, defaultdict

# ---- reliability gates (a "leg" must be physically car-plausible) ----------
MAX_DRIVE_SPEED = 140.0   # km/h: p99 real driving = 115; flights >> this
MAX_LEG_KM = 1200.0       # km: single continuous car leg ceiling
MAX_LEG_HOURS = 18.0      # h:  single leg duration ceiling
DRIVE_TYPES = {"in passenger vehicle", "motorcycling"}

# ---- chaining / grouping ---------------------------------------------------
CHAIN_GAP_H = 8.0         # h: gap that still keeps two legs in one journey
MAX_TRIP_GAP_DAYS = 14.0  # days: hard cap between journeys in one trip

# ---- qualification (loose) -------------------------------------------------
MIN_JOURNEY_KM = 120.0    # km driven, OR ...
MIN_DISPLACEMENT_KM = 80.0  # km net A->B (captures one-way intercity travel)

# ---- home (annotation + trip boundaries only) ------------------------------
R_HOME = 30.0             # km: within this of adaptive home == "at home"
HOME_WINDOW = 120         # days: window for adaptive home estimate

# ---- stops -----------------------------------------------------------------
STOP_MIN_HOURS = 0.4
OVERNIGHT_MIN_HOURS = 5.0

_geo = re.compile(r"geo:(-?\d+\.?\d*),(-?\d+\.?\d*)")

# Small approximate gazetteer (lat, lng, label) for readable endpoints/stops.
# Nearest match within GAZ_RADIUS km wins; otherwise raw coordinates are shown.
GAZ_RADIUS = 60.0
GAZ = [
    (42.89, -78.88, "Buffalo NY"), (42.98, -78.80, "Amherst NY"),
    (43.16, -77.61, "Rochester NY"), (43.05, -76.15, "Syracuse NY"),
    (42.10, -75.91, "Binghamton NY"), (42.65, -73.76, "Albany NY"),
    (44.93, -74.89, "Potsdam/Massena NY"), (43.10, -79.06, "Niagara Falls"),
    (42.09, -76.81, "Elmira NY"), (40.71, -74.01, "New York City"),
    (45.42, -75.70, "Ottawa ON"), (43.65, -79.38, "Toronto ON"),
    (45.50, -73.57, "Montreal QC"), (42.13, -80.09, "Erie PA"),
    (41.50, -81.69, "Cleveland OH"), (40.44, -79.996, "Pittsburgh PA"),
    (42.36, -71.06, "Boston MA"), (39.95, -75.16, "Philadelphia PA"),
    (38.90, -77.04, "Washington DC"), (39.29, -76.61, "Baltimore MD"),
    (36.85, -75.98, "Virginia Beach VA"), (33.69, -78.89, "Myrtle Beach SC"),
    (35.23, -80.84, "Charlotte NC"), (35.60, -82.55, "Asheville NC"),
    (28.54, -81.38, "Orlando FL"), (26.12, -80.14, "Fort Lauderdale FL"),
    (25.76, -80.19, "Miami FL"), (27.95, -82.46, "Tampa FL"),
    (30.33, -81.66, "Jacksonville FL"), (30.42, -87.22, "Pensacola FL"),
    (33.75, -84.39, "Atlanta GA"), (36.16, -86.78, "Nashville TN"),
    (41.88, -87.63, "Chicago IL"), (42.33, -83.05, "Detroit MI"),
    (44.76, -85.62, "Traverse City MI"), (46.55, -87.40, "Marquette MI"),
    (32.78, -96.80, "Dallas TX"), (29.76, -95.37, "Houston TX"),
    (34.05, -118.24, "Los Angeles CA"), (32.72, -117.16, "San Diego CA"),
    (33.68, -117.83, "Irvine CA"), (47.61, -122.33, "Seattle WA"),
    (48.75, -122.48, "Bellingham WA"), (49.28, -123.12, "Vancouver BC"),
    (45.52, -122.68, "Portland OR"), (44.39, -68.20, "Bar Harbor ME"),
    (43.66, -70.26, "Portland ME"), (40.09, -75.39, "Norristown PA"),
]


def parse_geo(s):
    m = _geo.match(str(s))
    return (float(m.group(1)), float(m.group(2))) if m else None


def haversine(a, b):
    R = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def label(coord):
    if not coord:
        return "?"
    best, bestd = None, GAZ_RADIUS
    for la, lo, name in GAZ:
        d = haversine(coord, (la, lo))
        if d < bestd:
            best, bestd = name, d
    return best if best else f"{coord[0]:.2f},{coord[1]:.2f}"


def seg_kind(d):
    for k in d:
        if k not in ("startTime", "endTime"):
            return k
    return None


# ---------------------------------------------------------------------------
def load_segments(path):
    data = json.load(open(path))
    segs = []
    for d in data:
        if "startTime" not in d or "endTime" not in d:
            continue
        try:
            st = datetime.fromisoformat(d["startTime"])
            et = datetime.fromisoformat(d["endTime"])
        except ValueError:
            continue
        segs.append({"raw": d, "kind": seg_kind(d), "start": st, "end": et})
    segs.sort(key=lambda s: s["start"])
    return segs


def build_home_lookup(segs):
    """adaptive home = dominant OVERNIGHT location in a rolling +/-HOME_WINDOW
    window, weighted by dwell hours. Uses ALL visits (not just those labeled
    'Home'), which is robust to sparse/missing semantic labels."""
    nights = []  # (time, lat, lng, dwell_hours)
    for s in segs:
        if s["kind"] != "visit":
            continue
        dwell = (s["end"] - s["start"]).total_seconds() / 3600.0
        if dwell < 6.0:
            continue
        p = parse_geo(s["raw"]["visit"].get("topCandidate", {}).get("placeLocation"))
        if p:
            nights.append((s["start"], p[0], p[1], dwell))
    nights.sort(key=lambda x: x[0])
    ntimes = [n[0] for n in nights]
    win = timedelta(days=HOME_WINDOW)
    cache = {}

    def current_homes(t):
        """up to 3 residence centroids for time t (handles dual-home /
        residence-transition periods). Any cluster with >=25% of the top
        cluster's dwell qualifies as 'a home'."""
        if not nights:
            return []
        key = t.date()
        if key in cache:
            return cache[key]
        lo = bisect.bisect_left(ntimes, t - win)
        hi = bisect.bisect_right(ntimes, t + win)
        w = nights[lo:hi]
        if not w:
            i = min(range(len(nights)), key=lambda j: abs((nights[j][0] - t).total_seconds()))
            res = [(nights[i][1], nights[i][2])]
        else:
            cell = defaultdict(float)
            for _, la, ln, dw in w:
                cell[(round(la, 1), round(ln, 1))] += dw
            top = max(cell.values())
            keep = [c for c, v in sorted(cell.items(), key=lambda x: -x[1])
                    if v >= 0.25 * top][:3]
            res = []
            for c in keep:
                pts = [(la, ln) for _, la, ln, _ in w
                       if (round(la, 1), round(ln, 1)) == c]
                res.append((sum(p[0] for p in pts) / len(pts),
                            sum(p[1] for p in pts) / len(pts)))
        cache[key] = res
        return res

    def current_home(t):
        homes = current_homes(t)
        return homes[0] if homes else None

    current_home.multi = current_homes
    return current_home, len(nights)


def extract_legs(segs):
    """validated driving legs only"""
    legs = []
    rejected = 0
    for s in segs:
        if s["kind"] != "activity":
            continue
        a = s["raw"]["activity"]
        if a.get("topCandidate", {}).get("type") not in DRIVE_TYPES:
            continue
        km = float(a.get("distanceMeters", 0) or 0) / 1000.0
        sp, ep = parse_geo(a.get("start")), parse_geo(a.get("end"))
        if km <= 0 and sp and ep:
            km = haversine(sp, ep)
        hours = (s["end"] - s["start"]).total_seconds() / 3600.0
        if km <= 0 or hours <= 0:
            continue
        speed = km / hours
        if km > MAX_LEG_KM or hours > MAX_LEG_HOURS or speed > MAX_DRIVE_SPEED:
            rejected += 1
            continue
        legs.append({"start": s["start"], "end": s["end"], "km": km,
                     "hours": hours, "from": sp, "to": ep})
    return legs, rejected


def chain_journeys(legs):
    legs.sort(key=lambda l: l["start"])
    journeys, cur = [], []
    gap = timedelta(hours=CHAIN_GAP_H)
    for leg in legs:
        if cur and leg["start"] - cur[-1]["end"] > gap:
            journeys.append(cur)
            cur = []
        cur.append(leg)
    if cur:
        journeys.append(cur)
    return journeys


def stops_between(segs, t0, t1, home):
    """visits within [t0,t1] used as en-route stops"""
    out = []
    for s in segs:
        if s["kind"] != "visit" or s["start"] < t0 or s["end"] > t1:
            continue
        dwell = (s["end"] - s["start"]).total_seconds() / 3600.0
        if dwell < STOP_MIN_HOURS:
            continue
        v = s["raw"]["visit"].get("topCandidate", {})
        coord = parse_geo(v.get("placeLocation"))
        overnight = dwell >= OVERNIGHT_MIN_HOURS and s["start"].date() != s["end"].date()
        out.append({"dwell": dwell, "coord": coord,
                    "type": v.get("semanticType", "Unknown"),
                    "overnight": overnight,
                    "from_home": haversine(coord, home) if (coord and home) else None})
    return out


def assess_journey(j):
    drive_km = sum(l["km"] for l in j)
    hours = sum(l["hours"] for l in j)
    start, end = j[0]["start"], j[-1]["end"]
    a = j[0]["from"] or j[0]["to"]
    b = j[-1]["to"] or j[-1]["from"]
    disp = haversine(a, b) if (a and b) else 0.0
    return {"start": start, "end": end, "drive_km": drive_km,
            "hours": hours, "n_legs": len(j),
            "from": a, "to": b, "displacement": disp,
            "longest_leg": max(l["km"] for l in j),
            "qualifies": drive_km >= MIN_JOURNEY_KM or disp >= MIN_DISPLACEMENT_KM}


def group_trips(journeys, segs, current_home):
    """group qualifying journeys into trips. A trip breaks when (a) the
    previous journey RETURNED HOME (its endpoint is within R_HOME of the
    adaptive home), (b) a FLIGHT occurred between the two journeys, or
    (c) the gap exceeds MAX_TRIP_GAP_DAYS."""
    flight_times = sorted(
        s["start"] for s in segs
        if s["kind"] == "activity"
        and s["raw"]["activity"].get("topCandidate", {}).get("type") == "flying")

    def flight_between(t0, t1):
        i = bisect.bisect_left(flight_times, t0)
        return i < len(flight_times) and flight_times[i] <= t1

    def ended_home(jn):
        if not jn["to"]:
            return False
        return any(haversine(jn["to"], h) <= R_HOME
                   for h in current_home.multi(jn["end"]))

    js = [assess_journey(j) for j in journeys]
    js = [x for x in js if x["qualifies"]]
    js.sort(key=lambda x: x["start"])

    trips, cur, prev_home = [], [], False
    for jn in js:
        if cur:
            prev = cur[-1]
            gap_days = (jn["start"] - prev["end"]).total_seconds() / 86400.0
            if prev_home or gap_days > MAX_TRIP_GAP_DAYS or flight_between(prev["end"], jn["start"]):
                trips.append(cur)
                cur = []
        cur.append(jn)
        prev_home = ended_home(jn)
    if cur:
        trips.append(cur)
    return trips


def assess_trip(trip_journeys, segs, current_home):
    start = trip_journeys[0]["start"]
    end = trip_journeys[-1]["end"]
    home = current_home(start) or current_home(end)
    drive_km = sum(j["drive_km"] for j in trip_journeys)
    hours = sum(j["hours"] for j in trip_journeys)
    n_legs = sum(j["n_legs"] for j in trip_journeys)
    longest = max(j["longest_leg"] for j in trip_journeys)

    stops = stops_between(segs, start, end, home)
    # cluster stops to ~0.1deg to dedupe repeated dwells
    clustered = defaultdict(lambda: [0.0, None, Counter(), False])
    max_from_home = 0.0
    for st in stops:
        if st["from_home"] is not None:
            max_from_home = max(max_from_home, st["from_home"])
        key = (round(st["coord"][0], 1), round(st["coord"][1], 1)) if st["coord"] else (None, None)
        c = clustered[key]
        c[0] += st["dwell"]
        c[1] = c[1] or st["coord"]
        c[2][st["type"]] += 1
        c[3] = c[3] or st["overnight"]
    # also consider journey endpoints for farthest-point
    for j in trip_journeys:
        for pt in (j["from"], j["to"]):
            if pt and home:
                max_from_home = max(max_from_home, haversine(pt, home))

    stop_list = sorted(
        ([h, coord, sem.most_common(1)[0][0], ov] for h, coord, sem, ov in clustered.values()),
        key=lambda x: -x[0])
    overnight_n = sum(1 for _, _, _, ov in clustered.values() if ov)

    origin = trip_journeys[0]["from"]
    dest = max(((j["to"], haversine(j["to"], home) if (j["to"] and home) else 0)
                for j in trip_journeys), key=lambda x: x[1])[0]

    if max_from_home >= 300:
        category = "long-haul"
    elif max_from_home >= 75:
        category = "regional"
    else:
        category = "local"

    return {
        "category": category,
        "start": start.isoformat(), "end": end.isoformat(),
        "duration_days": round((end - start).total_seconds() / 86400.0, 2),
        "n_journeys": len(trip_journeys), "n_legs": n_legs,
        "drive_km": round(drive_km, 1),
        "drive_hours": round(hours, 2),
        "avg_moving_speed_kmh": round(drive_km / hours, 1) if hours else 0.0,
        "longest_leg_km": round(longest, 1),
        "max_dist_from_home_km": round(max_from_home, 1),
        "home_anchor": [round(home[0], 4), round(home[1], 4)] if home else None,
        "origin": label(origin), "origin_coord": origin,
        "farthest": label(dest), "farthest_coord": dest,
        "n_stops": len(clustered), "n_overnight_stops": overnight_n,
        "top_stops": [
            {"label": label(coord), "dwell_hours": round(h, 1),
             "coord": [round(coord[0], 4), round(coord[1], 4)] if coord else None,
             "type": sem, "overnight": ov}
            for h, coord, sem, ov in stop_list[:15]
        ],
    }


def fmt_dur(days):
    d = int(days)
    h = int(round((days - d) * 24))
    return f"{d}d {h}h" if d else f"{h}h"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "location-history.json"
    print(f"Loading {path} ...")
    segs = load_segments(path)
    current_home, n_home = build_home_lookup(segs)

    legs, rejected = extract_legs(segs)
    print(f"  {len(legs)} validated driving legs "
          f"({rejected} implausible legs rejected by speed/distance gate)")
    journeys = chain_journeys(legs)
    print(f"  {len(journeys)} driving journeys (continuous travel spans)")
    trips_j = group_trips(journeys, segs, current_home)
    trips = [assess_trip(tj, segs, current_home) for tj in trips_j]
    trips.sort(key=lambda t: -t["drive_km"])

    total = sum(t["drive_km"] for t in trips)
    cat = Counter(t["category"] for t in trips)
    multiday = [t for t in trips if t["duration_days"] >= 1]
    print(f"  {len(trips)} car trips (>=1 qualifying journey); "
          f"{len(multiday)} span multiple days")
    print(f"  by reach from home:  long-haul (>=300km) {cat['long-haul']}  |  "
          f"regional (75-300km) {cat['regional']}  |  local (<75km) {cat['local']}")
    print(f"  total driven across all trips: {total:,.0f} km "
          f"({total/1.609:,.0f} mi)\n")

    # Lead with the substantial trips (long-haul + regional); locals go to files.
    headline = [t for t in trips if t["category"] in ("long-haul", "regional")]
    print("=" * 78)
    print(f"{len(headline)} INTERCITY / ROAD TRIPS (>=75 km from home)  "
          f"— {cat['local']} local day-drives omitted here (see CSV)")
    print("=" * 78)

    for i, t in enumerate(headline, 1):
        d0, d1 = t["start"][:10], t["end"][:10]
        span = d0 if d0 == d1 else f"{d0} → {d1}"
        route = t["origin"]
        if t["farthest"] != t["origin"]:
            route += f" → {t['farthest']}"
        print(f"\n{i:3}. [{t['category']:9}] {span}  ({fmt_dur(t['duration_days'])})   {route}")
        print(f"     {t['drive_km']:,.0f} km / {t['drive_km']/1.609:,.0f} mi "
              f"in {t['n_legs']} legs ({t['n_journeys']} driving day(s)) | "
              f"avg {t['avg_moving_speed_kmh']:.0f} km/h | "
              f"longest leg {t['longest_leg_km']:,.0f} km")
        print(f"     farthest {t['max_dist_from_home_km']:,.0f} km from home | "
              f"{t['n_stops']} stops, {t['n_overnight_stops']} overnight")
        heads = [s for s in t["top_stops"] if s["overnight"]][:5] or t["top_stops"][:4]
        for s in heads:
            tag = "overnight" if s["overnight"] else f"{s['dwell_hours']:.0f}h"
            print(f"         • {s['label']:22} {s['type']:16} ({tag})")

    json.dump({"config": {k: v for k, v in globals().items()
                          if k.isupper() and isinstance(v, (int, float))},
               "trips": trips}, open("road_trips.json", "w"), indent=2, default=str)
    with open("road_trips.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "start", "end", "duration_days", "origin", "farthest",
                    "drive_km", "drive_mi", "n_journeys", "n_legs", "drive_hours",
                    "avg_moving_speed_kmh", "longest_leg_km",
                    "max_dist_from_home_km", "n_stops", "n_overnight_stops"])
        for t in trips:
            w.writerow([t["category"], t["start"], t["end"], t["duration_days"],
                        t["origin"], t["farthest"], t["drive_km"],
                        round(t["drive_km"]/1.609, 1),
                        t["n_journeys"], t["n_legs"], t["drive_hours"],
                        t["avg_moving_speed_kmh"], t["longest_leg_km"],
                        t["max_dist_from_home_km"], t["n_stops"],
                        t["n_overnight_stops"]])
    print("\n" + "=" * 78)
    print(f"Wrote road_trips.json ({len(trips)} trips) and road_trips.csv")


def run_pipeline(path="location-history.json"):
    """Full extraction bootstrap shared by the export/sample scripts.
    Returns (segments, current_home lookup, list-of-trip-journeys)."""
    segs = load_segments(path)
    current_home, _ = build_home_lookup(segs)
    legs, _ = extract_legs(segs)
    journeys = chain_journeys(legs)
    trips_j = group_trips(journeys, segs, current_home)
    return segs, current_home, trips_j


if __name__ == "__main__":
    main()
