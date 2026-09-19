#!/usr/bin/env python3
"""
dance_test.py - Two daisy-chained CyberGear motors on one CAN bus (can0),
with direction-corrected "forward"/"backward" (the motors are mounted
mirror-image, so a raw + command spins them opposite physical ways):

   1) driver    forward  3 rotations
   2) driver    backward 3 rotations
   3) passenger forward  3 rotations
   4) passenger backward 3 rotations
   5) both      forward  3 rotations
   6) both      backward 3 rotations
   then stop.

Rotations are counted from each motor's own feedback (load-end / post-gearbox
angle), so a rotation is a wheel turn regardless of the 7.75:1 gearing.
try/finally guarantees every motor is disabled on exit (finish, error, Ctrl-C).
"""

import can
import time
import math
import struct

# ---- Configuration ---------------------------------------------------------
CHANNEL      = 'can0'
MASTER_ID    = 0x00
# forward_sign: the command sign that drives each wheel PHYSICALLY forward.
# Observed: driver spins backward on +, passenger spins forward on +.
DRIVER_ID,    DRIVER_FWD    = 0x7F, -1
PASSENGER_ID, PASSENGER_FWD = 0x7E, +1

TURNS         = 3
CRUISE_SPEED  = 4.0        # rad/s, main travel speed (magnitude)
FINISH_SPEED  = 1.5        # rad/s, speed during the final turn (magnitude)
CURRENT_LIMIT = 3.0        # A, torque budget for the speed loop
PHASE_TIMEOUT = 25.0       # s, safety cap per phase

# ---- CyberGear protocol constants ------------------------------------------
CMD_ENABLE, CMD_STOP, CMD_WRITE = 0x03, 0x04, 0x12
IDX_RUN_MODE, IDX_SPD_REF, IDX_LIMIT_CUR = 0x7005, 0x700A, 0x7018
RUN_MODE_SPEED = 2
TWO_PI, FOUR_PI, EIGHT_PI = 2*math.pi, 4*math.pi, 8*math.pi
TARGET_RAD = TURNS * TWO_PI

def uint_to_float(x, lo, hi):
    return (x / 65535.0) * (hi - lo) + lo

class Motor:
    def __init__(self, bus, motor_id, name, fwd_sign):
        self.bus, self.id, self.name, self.fwd = bus, motor_id, name, fwd_sign
        self.total = 0.0
        self.prev = None
        self.frames = 0

    def _mkid(self, cmd):
        return (cmd << 24) | (MASTER_ID << 8) | self.id

    def _send(self, cmd, data):
        self.bus.send(can.Message(arbitration_id=self._mkid(cmd), data=data, is_extended_id=True))

    def _write_u8(self, idx, val):
        self._send(CMD_WRITE, bytes([idx & 0xFF, (idx >> 8) & 0xFF, 0, 0, val & 0xFF, 0, 0, 0]))

    def _write_f32(self, idx, val):
        self._send(CMD_WRITE, bytes([idx & 0xFF, (idx >> 8) & 0xFF, 0, 0]) + struct.pack('<f', val))

    def enable(self):       self._send(CMD_ENABLE, bytes(8))
    def stop(self):         self._send(CMD_STOP, bytes(8))
    def set_speed(self, s): self._write_f32(IDX_SPD_REF, s)

    def arm_speed_mode(self):
        self.stop(); time.sleep(0.02)
        self._write_u8(IDX_RUN_MODE, RUN_MODE_SPEED)
        self._write_f32(IDX_LIMIT_CUR, CURRENT_LIMIT)
        time.sleep(0.02)
        self.enable()

    def reset_count(self):
        self.total, self.prev, self.frames = 0.0, None, 0

    def feed(self, raw_angle_uint):
        self.frames += 1
        ang = uint_to_float(raw_angle_uint, -FOUR_PI, FOUR_PI)
        if self.prev is not None:
            d = ang - self.prev
            if d >  FOUR_PI: d -= EIGHT_PI     # unwrap the +-4pi rollover
            elif d < -FOUR_PI: d += EIGHT_PI
            self.total += d
        self.prev = ang

    def physical_turns(self):
        # signed turns in the robot frame: + = forward
        return (self.total * self.fwd) / TWO_PI

def drain_and_route(bus, by_id):
    msg = bus.recv(timeout=0.005)
    while msg is not None:
        if ((msg.arbitration_id >> 24) & 0x1F) == 2 and len(msg.data) >= 2:
            src = (msg.arbitration_id >> 8) & 0xFF
            m = by_id.get(src)
            if m:
                m.feed((msg.data[0] << 8) | msg.data[1])
        msg = bus.recv(timeout=0.0)

def run_phase(label, active, by_id, direction):
    # direction: +1 forward, -1 backward
    print(f"\n{label}")
    for m in active:
        m.reset_count()
        m.arm_speed_mode()
        m.set_speed(direction * m.fwd * CRUISE_SPEED)
    start = time.time()
    while True:
        drain_and_route(active[0].bus, by_id)
        done = True
        for m in active:
            sign = direction * m.fwd
            remaining = TARGET_RAD - abs(m.total)
            if remaining <= 0:
                m.set_speed(0.0)
            elif remaining < TWO_PI:
                m.set_speed(sign * FINISH_SPEED); done = False   # slow last turn
            else:
                m.set_speed(sign * CRUISE_SPEED); done = False
        if done:
            break
        if time.time() - start > PHASE_TIMEOUT:
            print("  ! phase timeout - stopping")
            break
        time.sleep(0.01)
    for m in active:
        m.set_speed(0.0)
    time.sleep(0.25)
    for m in active:
        m.stop()
    for m in active:
        note = "" if m.frames else "  (no feedback - check this motor!)"
        print(f"  {m.name}: {m.physical_turns():+.2f} turns{note}")

with can.interface.Bus(channel=CHANNEL, interface='socketcan') as bus:
    driver    = Motor(bus, DRIVER_ID,    "driver   ", DRIVER_FWD)
    passenger = Motor(bus, PASSENGER_ID, "passenger", PASSENGER_FWD)
    by_id = {DRIVER_ID: driver, PASSENGER_ID: passenger}
    try:
        run_phase("Phase 1: driver forward 3",    [driver],    by_id, +1)
        run_phase("Phase 2: driver backward 3",   [driver],    by_id, -1)
        run_phase("Phase 3: passenger forward 3", [passenger], by_id, +1)
        run_phase("Phase 4: passenger backward 3",[passenger], by_id, -1)
        run_phase("Phase 5: both forward 3",      [driver, passenger], by_id, +1)
        run_phase("Phase 6: both backward 3",     [driver, passenger], by_id, -1)
        print("\nDone.")
    finally:
        for m in (driver, passenger):
            m.set_speed(0.0)
            m.stop()
        print("All motors disabled.")
