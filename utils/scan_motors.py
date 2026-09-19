#!/usr/bin/env python3
"""
scan_motors.py - Discover CyberGear motors on a single CAN bus (non-invasive).

Sends a read-parameter request to each candidate CAN ID (0..127) and records
which IDs reply. It only READS a parameter - it never enables or moves a motor.

Bus: can0  (the Waveshare header silkscreened "CAN1").
"""

import can
import time

CHANNEL      = 'can0'
MASTER_ID    = 0x00
CMD_READ     = 0x11      # read single parameter
IDX_RUN_MODE = 0x7005    # any valid, harmless parameter to read

def make_id(cmd, mid):
    return (cmd << 24) | (MASTER_ID << 8) | mid

with can.interface.Bus(channel=CHANNEL, interface='socketcan') as bus:
    print(f"Scanning {CHANNEL} for CyberGear motors (IDs 0-127)...")
    found = []
    req = bytes([IDX_RUN_MODE & 0xFF, (IDX_RUN_MODE >> 8) & 0xFF, 0, 0, 0, 0, 0, 0])
    for mid in range(128):
        # flush anything pending
        while bus.recv(timeout=0.0) is not None:
            pass
        bus.send(can.Message(arbitration_id=make_id(CMD_READ, mid),
                             data=req, is_extended_id=True))
        deadline = time.time() + 0.03
        while time.time() < deadline:
            msg = bus.recv(timeout=0.03)
            if msg is None:
                continue
            cmd = (msg.arbitration_id >> 24) & 0x1F
            if cmd in (0x11, 0x02):        # read-reply or feedback = a live motor
                found.append(mid)
                print(f"  -> motor responding at CAN ID 0x{mid:02X} ({mid})")
                break
    print()
    if found:
        print("Motors found at IDs:", ", ".join(f"0x{m:02X} ({m})" for m in found))
    else:
        print("No motors responded. Is can0 up? Is the motor rail powered?")
