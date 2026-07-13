#!/usr/bin/env python3
"""PII redaction for published viewer artifacts.

Policy (per project decision):
  * The ONLY indication of *when* a trip happened is its SEASON.
  * No absolute calendar dates, years, months, or clock times ship.
  * Any time that must be shown is expressed PER-TRIP as a relative offset
    from that trip's start, e.g. "+1min", "+1hr 23min", "+2d 4hr".
  * Durations (already elapsed spans, not "when") and season are retained.

Redaction happens at BUILD time so the published payload never contains the
raw fields — hiding them in the front-end would still leak them in the JSON.
Coordinate precision is left to a separate decision; this module only handles
the temporal PII that was specified.
"""

# absolute-time fields that must never reach a public artifact
PII_TIME_KEYS = ["start", "end", "date", "date_label", "month_label"]

# semantic labels that explicitly tag a residence/workplace -> neutralized
RESIDENCE_LABELS = {"Home", "Inferred Home", "Work", "Inferred Work"}


def fmt_offset(minutes):
    """relative, per-trip elapsed offset: +1min / +1hr 23min / +2d 4hr"""
    m = int(round(minutes))
    if m < 60:
        return f"+{m}min"
    h, mm = divmod(m, 60)
    if h < 24:
        return f"+{h}hr {mm}min" if mm else f"+{h}hr"
    d, hh = divmod(h, 24)
    return f"+{d}d {hh}hr" if hh else f"+{d}d"


def redact_trip(t):
    """return a copy of a trip dict with absolute temporal PII removed.
    `season` (and relative fields like duration) are kept."""
    r = dict(t)
    for k in PII_TIME_KEYS:
        r.pop(k, None)
    if "stops" in r:
        stops = []
        for s in r["stops"]:
            s = {k: v for k, v in s.items() if k not in PII_TIME_KEYS}
            if s.get("type") in RESIDENCE_LABELS:
                s["type"] = "Frequent stop"
            stops.append(s)
        r["stops"] = stops
    return r


# fields/patterns a public artifact must NOT contain (build-time leak gate)
import re
_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
LEAK_PATTERNS = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "ISO date (YYYY-MM-DD)"),
    (re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"), "clock time (HH:MM:SS)"),
    # human-formatted absolute date, e.g. "Jul 13, 2026" (month_label format)
    (re.compile(rf"\b(?:{_MONTHS})[a-z]* \d{{1,2}}, \d{{4}}\b"), "formatted date"),
    (re.compile(r'"(start|end|date|date_label|month_label)"\s*:'), "raw date field"),
    # any residence/workplace tag, not just the "Inferred " variants
    (re.compile(r"\b(?:Inferred )?(?:Home|Work)\b"), "residence semantic label"),
]


def scan_for_leaks(text):
    """return list of (pattern_desc, sample) found in a public artifact."""
    hits = []
    for rx, desc in LEAK_PATTERNS:
        m = rx.search(text)
        if m:
            hits.append((desc, m.group(0)))
    return hits
