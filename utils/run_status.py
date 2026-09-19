#!/usr/bin/env python3
"""run_status.py - low-level API test: fetch and print robot status.
Set EGOR_API to point elsewhere, e.g.  EGOR_API=http://egor:8080 python3 run_status.py
"""
import os, json, urllib.request

BASE = os.environ.get("EGOR_API", "http://localhost:8080")

with urllib.request.urlopen(BASE + "/api/status", timeout=2) as r:
    print(json.dumps(json.loads(r.read()), indent=2))
