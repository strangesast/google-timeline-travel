#!/usr/bin/env python3
"""Build-time PII gate. Runs as npm `prebuild` so `npm run build` cannot ship a
public data tier that still contains dates/times/residence labels — enforcing
the invariant the README documents. Scans the exact JSON that Vite bundles."""
import glob, sys
from redact import scan_for_leaks

files = glob.glob("src/data/*.public.json")
if not files:
    sys.exit("no src/data/*.public.json — run `python3 prepare_data.py` first")

bad = False
for f in files:
    leaks = scan_for_leaks(open(f).read())
    if leaks:
        print(f"LEAK in {f}: {leaks}")
        bad = True
    else:
        print(f"ok: {f}")
if bad:
    sys.exit("PII leak gate FAILED — refusing to build")
print("PII leak gate passed")
