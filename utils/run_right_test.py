#!/usr/bin/env python3
"""run_right_test.py - low-level API test: spin RIGHT (in place, CW) for 2 seconds, then stop.

Because of the server's watchdog, one POST would stop after ~0.5s, so this
resends the command every 0.2s for the duration - which also proves the
heartbeat works. WHEELS OFF THE GROUND for this test.
"""
import os, json, time, urllib.request

BASE = os.environ.get("EGOR_API", "http://localhost:8080")
DIRECTION = "SPIN_R"
SECONDS   = 2.0

def post(path):
    req = urllib.request.Request(BASE + path, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read())

print(f"{DIRECTION} for {SECONDS}s (resending every 0.2s to feed the watchdog)...")
end = time.time() + SECONDS
while time.time() < end:
    print("  ->", post(f"/api/move/{DIRECTION}"))
    time.sleep(0.2)
print("STOP ->", post("/api/move/STOP"))
