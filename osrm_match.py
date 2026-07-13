#!/usr/bin/env python3
"""Snap recorded GPS traces onto OSM road segments via OSRM /match.
Reads trips_geo.json, writes trips_geo_matched.json with road-projected
'lines' (falls back to raw points per-chunk on any failure)."""
import json, time, urllib.request, urllib.parse

OSRM = "https://router.project-osrm.org/match/v1/driving/"
CHUNK = 10      # public OSRM /match hard-caps a trace at 10 coordinates
OVERLAP = 1     # stitch chunks by sharing the last point

def match_chunk(pts):
    """pts: list of [lat,lng] -> list of [lat,lng] snapped to roads, or None.
    No `radiuses` (public server rejects large radii); tidy cleans the trace."""
    coords = ";".join(f"{ln:.5f},{la:.5f}" for la, ln in pts)
    q = urllib.parse.urlencode({"geometries": "geojson", "overview": "full",
                                "tidy": "true", "gaps": "split"})
    url = f"{OSRM}{coords}?{q}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.load(r)
            if data.get("code") != "Ok":
                return None
            out = []
            for m in data.get("matchings", []):
                for lon, lat in m["geometry"]["coordinates"]:
                    out.append([round(lat, 5), round(lon, 5)])
            return out or None
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None

def snap_line(line):
    if len(line) < 2:
        return line, 0, 0
    snapped, ok, total = [], 0, 0
    i = 0
    while i < len(line):
        chunk = line[i:i + CHUNK]
        if len(chunk) < 2:
            snapped.extend(chunk)
            break
        total += 1
        res = match_chunk(chunk)
        if res:
            ok += 1
            snapped.extend(res)
        else:
            snapped.extend(chunk)  # fallback: raw points
        i += CHUNK - OVERLAP
        time.sleep(0.6)  # be polite to the public server
    return snapped, ok, total

def main():
    trips = json.load(open("trips_geo.json"))
    for t in trips:
        raw = t["lines"]
        snapped_lines, ok, total = [], 0, 0
        for line in raw:
            s, o, n = snap_line(line)
            snapped_lines.append(s)
            ok += o; total += n
        t["raw_lines"] = raw
        t["lines"] = snapped_lines
        t["match_rate"] = f"{ok}/{total}"
        rawn = sum(len(l) for l in raw)
        snapn = sum(len(l) for l in snapped_lines)
        print(f"{t['category']:10} {t['title']:34} match {ok}/{total} chunks | "
              f"{rawn}->{snapn} pts")
    json.dump(trips, open("trips_geo_matched.json", "w"))
    print("\nWrote trips_geo_matched.json")

if __name__ == "__main__":
    main()
