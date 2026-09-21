#!/usr/bin/env python3
"""
robot_server.py - REST backend that drives Egor's two CyberGear wheels over CAN.

Design:
  * One background control thread owns the CAN bus. It streams speed commands to
    both motors at CONTROL_HZ and reads their feedback for telemetry.
  * A watchdog stops the wheels if no fresh command arrives within
    WATCHDOG_TIMEOUT seconds - so a dropped connection or closed browser tab
    fails safe. The web UI must repeat the command while a button is held
    (or send STOP on release).
  * All movement is built on one primitive: set_velocity(left, right) with each
    value in -1..1 (physical forward). Named buttons are thin wrappers over it.

Wheels:  driver (0x7F) = LEFT,  passenger (0x7E) = RIGHT.
Bus:     can0 (must already be up at 1 Mbit/s - see setup_can_service.sh).

Run:     python3 utils/robot_server.py     (needs: sudo apt install -y python3-flask)
         Serves on http://0.0.0.0:8080  (reachable on the LAN as http://egor:8080)

NOTE: no authentication - anyone on the network can drive the robot. Fine for a
      trusted home LAN; don't expose it to the open internet.
"""

import time
import math
import struct
import threading
import atexit
import signal
import sys
import os
import shutil
import subprocess
import json
import socket

import can
from flask import Flask, jsonify, request, Response, redirect

# ---- Configuration ---------------------------------------------------------
CHANNEL          = 'can0'
MASTER_ID        = 0x00
DRIVER_ID,    DRIVER_FWD    = 0x7F, -1     # LEFT wheel  (spins backward on raw +)
PASSENGER_ID, PASSENGER_FWD = 0x7E, +1     # RIGHT wheel (spins forward on raw +)

BASE_SPEED       = 4.0     # rad/s at full stick (|fraction| = 1.0)
CURRENT_LIMIT    = 3.0     # A, torque budget for the speed loop
CONTROL_HZ       = 50      # control-loop / command-stream rate
WATCHDOG_TIMEOUT = 0.5     # s, stop the wheels if no command arrives within this
HTTP_PORT        = 8080

# direction -> (left_fraction, right_fraction), physical forward
MOVES = {
    'FWD':    ( 1.0,  1.0),
    'REV':    (-1.0, -1.0),
    'FWD_L':  ( 0.3,  1.0),
    'FWD_R':  ( 1.0,  0.3),
    'REV_L':  (-0.3, -1.0),
    'REV_R':  (-1.0, -0.3),
    'SPIN_L': (-1.0,  1.0),
    'SPIN_R': ( 1.0, -1.0),
    'STOP':   ( 0.0,  0.0),
}

# ---- CyberGear protocol ----------------------------------------------------
CMD_ENABLE, CMD_STOP, CMD_WRITE = 0x03, 0x04, 0x12
IDX_RUN_MODE, IDX_SPD_REF, IDX_LIMIT_CUR = 0x7005, 0x700A, 0x7018
RUN_MODE_SPEED = 2

def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))

def uint_to_float(x, lo, hi):
    return (x / 65535.0) * (hi - lo) + lo

def read_iface_state():
    try:
        with open(f"/sys/class/net/{CHANNEL}/operstate") as f:
            return f.read().strip()
    except Exception:
        return "unknown"

def _run(cmd, timeout=3):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""

class Motor:
    def __init__(self, bus, motor_id, name, fwd_sign):
        self.bus, self.id, self.name, self.fwd = bus, motor_id, name, fwd_sign
        self.vel = 0.0        # physical rad/s (+ = forward)
        self.temp = 0.0       # deg C
        self.last_fb = 0.0    # time of last feedback frame

    def _mkid(self, cmd):
        return (cmd << 24) | (MASTER_ID << 8) | self.id

    def _send(self, cmd, data):
        if self.bus is None:
            raise OSError("CAN bus not available")
        self.bus.send(can.Message(arbitration_id=self._mkid(cmd), data=data, is_extended_id=True))

    def _wu8(self, idx, val):
        self._send(CMD_WRITE, bytes([idx & 0xFF, (idx >> 8) & 0xFF, 0, 0, val & 0xFF, 0, 0, 0]))

    def _wf32(self, idx, val):
        self._send(CMD_WRITE, bytes([idx & 0xFF, (idx >> 8) & 0xFF, 0, 0]) + struct.pack('<f', val))

    def enable(self): self._send(CMD_ENABLE, bytes(8))
    def stop(self):   self._send(CMD_STOP, bytes(8))

    def arm(self):
        self.stop(); time.sleep(0.02)
        self._wu8(IDX_RUN_MODE, RUN_MODE_SPEED)
        self._wf32(IDX_LIMIT_CUR, CURRENT_LIMIT)
        time.sleep(0.02)
        self.enable()

    def command_fraction(self, frac):
        # frac in -1..1 physical forward -> raw rad/s with the wheel's sign
        self._wf32(IDX_SPD_REF, clamp(frac) * self.fwd * BASE_SPEED)

    def feed(self, data):
        if len(data) < 8:
            return
        self.vel = uint_to_float((data[2] << 8) | data[3], -30.0, 30.0) * self.fwd
        self.temp = ((data[6] << 8) | data[7]) * 0.1
        self.last_fb = time.time()

class Controller:
    def __init__(self):
        try:
            self.bus = can.interface.Bus(channel=CHANNEL, interface='socketcan')
            bus_err = ""
        except Exception as e:
            self.bus = None
            bus_err = f"CAN bus '{CHANNEL}' unavailable: {e}"
            print(bus_err, file=sys.stderr)
        self.left  = Motor(self.bus, DRIVER_ID,    "left",  DRIVER_FWD)
        self.right = Motor(self.bus, PASSENGER_ID, "right", PASSENGER_FWD)
        self.by_id = {DRIVER_ID: self.left, PASSENGER_ID: self.right}
        self.lock = threading.Lock()
        self.tl = self.tr = 0.0
        self.last_cmd = 0.0
        self.estopped = False
        self.estop_req = False
        self.enable_req = False
        self.can_error = bool(bus_err)   # True while CAN is unavailable / failing
        self.last_error = bus_err
        self.armed = False           # motors configured into speed mode + enabled
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        # All bus I/O happens in the control thread (which arms the motors on
        # its first pass), so a powered-off bus can't crash startup.
        self.thread.start()

    # --- called from Flask threads: only touch shared state, never the bus ---
    def set_velocity(self, l, r):
        with self.lock:
            if self.estopped:
                return False
            self.tl, self.tr = clamp(l), clamp(r)
            self.last_cmd = time.time()
            return True

    def soft_stop(self):
        with self.lock:
            self.tl = self.tr = 0.0
            self.last_cmd = time.time()

    def estop(self):
        with self.lock:
            self.estop_req = True
            self.tl = self.tr = 0.0

    def reenable(self):
        with self.lock:
            self.enable_req = True

    def status(self):
        with self.lock:
            now = time.time()
            return {
                "estopped": self.estopped,
                "watchdog_ok": (now - self.last_cmd) <= WATCHDOG_TIMEOUT,
                "targets": {"left": self.tl, "right": self.tr},
                "wheels": {
                    "left":  {"id": DRIVER_ID,    "vel_rad_s": round(self.left.vel, 2),
                              "temp_c": round(self.left.temp, 1),
                              "online": (now - self.left.last_fb) < 1.0},
                    "right": {"id": PASSENGER_ID, "vel_rad_s": round(self.right.vel, 2),
                              "temp_c": round(self.right.temp, 1),
                              "online": (now - self.right.last_fb) < 1.0},
                },
                "can0": read_iface_state(),
                "can_error": self.can_error,
                "last_error": self.last_error,
            }

    def _safe(self, fn):
        """Run a bus operation; track CAN error state; never raise."""
        try:
            fn()
            if self.can_error:
                self.can_error = False
                self.last_error = ""
                print("CAN: sends recovered")
            return True
        except (can.CanError, OSError) as e:
            if not self.can_error:
                self.can_error = True
                self.last_error = str(e)
                print(f"CAN: send error, will keep retrying: {e}", file=sys.stderr)
            return False

    def _loop(self):
        period = 1.0 / CONTROL_HZ
        next_retry = 0.0
        while self.running:
            # 1) drain feedback (a read error must not kill the thread)
            if self.bus is not None:
                try:
                    msg = self.bus.recv(timeout=0.0)
                    while msg is not None:
                        if ((msg.arbitration_id >> 24) & 0x1F) == 2:
                            m = self.by_id.get((msg.arbitration_id >> 8) & 0xFF)
                            if m:
                                m.feed(msg.data)
                        msg = self.bus.recv(timeout=0.0)
                except (can.CanError, OSError):
                    pass

            now = time.time()

            # 2) one-time arm (retried automatically if the bus is down at start)
            if not self.armed:
                if self._safe(lambda: (self.left.arm(), self.right.arm())):
                    self.armed = True

            # 3) snapshot shared state
            with self.lock:
                er, self.estop_req = self.estop_req, False
                nr, self.enable_req = self.enable_req, False
                fresh = (now - self.last_cmd) <= WATCHDOG_TIMEOUT
                tl, tr = (self.tl, self.tr) if fresh else (0.0, 0.0)
                estopped = self.estopped

            # 4) e-stop / re-enable transitions
            if er:
                self._safe(lambda: (self.left.stop(), self.right.stop()))
                with self.lock:
                    self.estopped = True
                estopped = True
            elif nr:
                if self._safe(lambda: (self.left.arm(), self.right.arm())):
                    self.armed = True
                with self.lock:
                    self.estopped = False
                    self.tl = self.tr = 0.0
                    self.last_cmd = time.time()
                estopped = False

            # 5) stream speeds; throttle attempts while the bus is erroring
            if not estopped and (not self.can_error or now >= next_retry):
                if not self._safe(lambda: (self.left.command_fraction(tl),
                                           self.right.command_fraction(tr))):
                    next_retry = now + 0.5

            time.sleep(period)

    def shutdown(self):
        self.running = False
        time.sleep(2.0 / CONTROL_HZ)                      # let the loop exit
        try:
            self.left.stop(); self.right.stop()
        except Exception:
            pass
        try:
            self.bus.shutdown()
        except Exception:
            pass

# ---- Flask app -------------------------------------------------------------
app = Flask(__name__)
ctrl = None

UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "robot_ui.html")
ADMIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin.html")

@app.route('/', methods=['GET'])
def index():
    try:
        with open(UI_PATH, encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html")
    except FileNotFoundError:
        return jsonify(error="robot_ui.html not found next to robot_server.py"), 404

@app.route('/api', methods=['GET'])
def api_info():
    return jsonify(service="egor robot control",
                   moves=list(MOVES.keys()),
                   endpoints=["GET /  (control UI)", "POST /api/move/<DIR>",
                              "POST /api/drive {left,right}", "POST /api/stop",
                              "POST /api/estop", "POST /api/enable",
                              "POST /api/shutdown", "GET /api/status"])

@app.route('/api/move/<direction>', methods=['POST'])
def move(direction):
    d = direction.upper()
    if d not in MOVES:
        return jsonify(error=f"unknown direction '{d}'", valid=list(MOVES.keys())), 400
    l, r = MOVES[d]
    if d == 'STOP':
        ctrl.soft_stop()
        return jsonify(ok=True, command=d)
    if not ctrl.set_velocity(l, r):
        return jsonify(error="estopped - POST /api/enable to resume"), 409
    return jsonify(ok=True, command=d, left=l, right=r)

@app.route('/api/drive', methods=['POST'])
def drive():
    body = request.get_json(force=True, silent=True) or {}
    try:
        l = float(body['left']); r = float(body['right'])
    except (KeyError, TypeError, ValueError):
        return jsonify(error='body must be JSON {"left": -1..1, "right": -1..1}'), 400
    if not ctrl.set_velocity(l, r):
        return jsonify(error="estopped - POST /api/enable to resume"), 409
    return jsonify(ok=True, left=clamp(l), right=clamp(r))

@app.route('/api/stop', methods=['POST'])
def stop():
    ctrl.soft_stop()
    return jsonify(ok=True, command="STOP")

@app.route('/api/estop', methods=['POST'])
def estop():
    ctrl.estop()
    return jsonify(ok=True, command="ESTOP", note="motors disabled; POST /api/enable to resume")

@app.route('/api/enable', methods=['POST'])
def enable():
    ctrl.reenable()
    return jsonify(ok=True, command="ENABLE")

@app.route('/api/shutdown', methods=['POST'])
def shutdown_pi():
    # stop the motors first, then power the Pi down cleanly
    ctrl.estop()
    sh = shutil.which("shutdown") or "/sbin/shutdown"
    # confirm this (non-root) server is allowed to run shutdown without a password
    allowed = subprocess.run(["sudo", "-n", "-l", sh],
                             capture_output=True).returncode == 0
    if not allowed:
        return jsonify(ok=False,
                       error="server not permitted to shut down - run "
                             "'sudo ./utils/setup_shutdown_api.sh' once"), 500
    def go():
        time.sleep(1.0)                     # let the HTTP response flush first
        try:
            subprocess.Popen(["sudo", "-n", sh, "-h", "now"])
        except Exception as e:
            print(f"shutdown failed: {e}", file=sys.stderr)
    threading.Thread(target=go, daemon=True).start()
    return jsonify(ok=True, command="SHUTDOWN", note="Pi is shutting down")

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify(ctrl.status())

@app.route('/api/netinfo', methods=['GET'])
def netinfo():
    info = {"hostname": socket.gethostname(), "interfaces": {}}
    try:
        out = subprocess.run(["ip", "-j", "-4", "addr"],
                             capture_output=True, text=True, timeout=3).stdout
        for iface in json.loads(out or "[]"):
            name = iface.get("ifname", "?")
            if name == "lo":
                continue
            addrs = [a.get("local") for a in iface.get("addr_info", [])
                     if a.get("family") == "inet" and a.get("local")]
            if name in ("eth0", "wlan0") or addrs:
                info["interfaces"][name] = {
                    "ipv4": addrs,
                    "state": iface.get("operstate", "?"),
                    "mac": iface.get("address", ""),
                }
    except Exception as e:
        info["error"] = str(e)
    return jsonify(info)

@app.route('/admin', methods=['GET'])
def admin():
    try:
        with open(ADMIN_PATH, encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html")
    except FileNotFoundError:
        return jsonify(error="admin.html not found next to robot_server.py"), 404

@app.route('/api/sysinfo', methods=['GET'])
def sysinfo():
    d = {}
    # CPU temperature
    t = _run(["vcgencmd", "measure_temp"])          # e.g. temp=48.1'C
    if t.startswith("temp="):
        try: d["temp_c"] = float(t.split("=")[1].split("'")[0])
        except Exception: pass
    if "temp_c" not in d:
        z = _run(["cat", "/sys/class/thermal/thermal_zone0/temp"])
        if z.isdigit(): d["temp_c"] = round(int(z) / 1000.0, 1)
    # under-voltage / throttling flags
    th = _run(["vcgencmd", "get_throttled"])        # e.g. throttled=0x0
    val = 0
    if "=" in th:
        try: val = int(th.split("=")[1], 16)
        except Exception: pass
    d["throttled_raw"]     = f"0x{val:x}"
    d["undervoltage_now"]  = bool(val & 0x1)
    d["undervoltage_past"] = bool(val & 0x10000)
    d["throttled_now"]     = bool(val & 0x4)
    d["throttled_past"]    = bool(val & 0x40000)
    # service health
    d["services"] = {}
    for svc in ("egor-can", "egor-robot", "egor-camera"):
        d["services"][svc] = _run(["systemctl", "is-active", svc + ".service"]) or "unknown"
    # CAN bus
    can = _run(["ip", "-details", "link", "show", "can0"])
    if not can:
        d["can0"] = {"present": False}
    else:
        link = "UP" if "state UP" in can else ("DOWN" if "state DOWN" in can else "?")
        cst  = ("ERROR-ACTIVE" if "ERROR-ACTIVE" in can else
                "ERROR-PASSIVE" if "ERROR-PASSIVE" in can else
                "BUS-OFF" if "BUS-OFF" in can else "?")
        d["can0"] = {"present": True, "link": link, "can_state": cst}
    return jsonify(d)

@app.route('/api/reboot', methods=['POST'])
def reboot_pi():
    ctrl.estop()
    sh = shutil.which("shutdown") or "/sbin/shutdown"
    allowed = subprocess.run(["sudo", "-n", "-l", sh], capture_output=True).returncode == 0
    if not allowed:
        return jsonify(ok=False,
                       error="server not permitted to reboot - run "
                             "'sudo ./utils/setup_shutdown_api.sh' once"), 500
    def go():
        time.sleep(1.0)
        try:
            subprocess.Popen(["sudo", "-n", sh, "-r", "now"])
        except Exception as e:
            print(f"reboot failed: {e}", file=sys.stderr)
    threading.Thread(target=go, daemon=True).start()
    return jsonify(ok=True, command="REBOOT", note="Pi is rebooting")

@app.errorhandler(404)
def _captive_redirect(_e):
    # Captive-portal + convenience: any unknown path (incl. OS connectivity
    # checks like /generate_204, /hotspot-detect.html) bounces to the control
    # page, so joining egorwifi auto-surfaces the controls.
    return redirect("/", code=302)

def main():
    global ctrl
    ctrl = Controller()
    ctrl.start()

    def cleanup(*_):
        ctrl.shutdown()

    atexit.register(cleanup)
    signal.signal(signal.SIGINT,  lambda *_: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(0)))

    print(f"Egor control server on http://0.0.0.0:{HTTP_PORT}  (Ctrl-C to stop)")
    app.run(host='0.0.0.0', port=HTTP_PORT, threaded=True)

if __name__ == '__main__':
    main()
