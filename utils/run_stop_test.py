#!/usr/bin/env python3
"""run_stop_test.py - low-level API test: send a single STOP."""
import os, json, urllib.request

BASE = os.environ.get("EGOR_API", "http://localhost:8080")

def post(path):
    req = urllib.request.Request(BASE + path, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read())

print("STOP ->", post("/api/move/STOP"))
