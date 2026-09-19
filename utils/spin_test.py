#!/usr/bin/env python3
"""
spin_test.py - Gently spin a Xiaomi CyberGear motor in SPEED mode, then stop.

Bus: can0  (on this Waveshare hat, the header silkscreened "CAN1" enumerates
            as the can0 interface).

Safety: the motion is wrapped in try/finally, so the motor is ALWAYS sent a
        stop command on exit - normal finish, an error, or Ctrl-C.
"""

import can
import time
import struct

# ---- Configuration (tweak these) -------------------------------------------
CHANNEL       = 'can0'
MOTOR_ID      = 0x7F     # CyberGear default CAN ID (127)
MASTER_ID     = 0x00     # our host ID
TARGET_SPEED  = 1.5      # rad/s  (sign = direction; valid range -30..30)
CURRENT_LIMIT = 3.0      # A      (torque budget for the speed loop; range 0..23)
RUN_SECONDS   = 3.0      # how long to hold the speed
LOOP_HZ       = 50       # command refresh / feedback poll rate

# ---- CyberGear protocol constants ------------------------------------------
CMD_ENABLE       = 0x03
CMD_STOP         = 0x04
CMD_WRITE_PARAM  = 0x12

IDX_RUN_MODE   = 0x7005  # 0=operation, 1=position, 2=SPEED, 3=current
IDX_SPD_REF    = 0x700A  # float, rad/s
IDX_LIMIT_CUR  = 0x7018  # float, A
RUN_MODE_SPEED = 2

def make_id(cmd_type):
    # Bits 28-24: command type | 23-8: master id | 7-0: target motor id
    return (cmd_type << 24) | (MASTER_ID << 8) | MOTOR_ID

def send(bus, cmd_type, data):
    bus.send(can.Message(arbitration_id=make_id(cmd_type), data=data, is_extended_id=True))

def write_param_u8(bus, index, value):
    data = bytes([index & 0xFF, (index >> 8) & 0xFF, 0, 0, value & 0xFF, 0, 0, 0])
    send(bus, CMD_WRITE_PARAM, data)

def write_param_f32(bus, index, value):
    data = bytes([index & 0xFF, (index >> 8) & 0xFF, 0, 0]) + struct.pack('<f', value)
    send(bus, CMD_WRITE_PARAM, data)

def uint_to_float(x, xmin, xmax):
    return (x / 65535.0) * (xmax - xmin) + xmin

def decode_feedback(msg):
    # Only type-2 (feedback) frames carry the angle/vel/torque/temp layout
    if msg is None or ((msg.arbitration_id >> 24) & 0x1F) != 2 or len(msg.data) < 8:
        return None
    d = msg.data
    vel  = uint_to_float((d[2] << 8) | d[3], -30.0, 30.0)   # rad/s
    torq = uint_to_float((d[4] << 8) | d[5], -12.0, 12.0)   # Nm
    temp = ((d[6] << 8) | d[7]) * 0.1                        # deg C
    return vel, torq, temp

with can.interface.Bus(channel=CHANNEL, interface='socketcan') as bus:
    try:
        print("Configuring speed mode...")
        send(bus, CMD_STOP, bytes(8))                 # ensure disabled before mode change
        time.sleep(0.05)
        write_param_u8(bus, IDX_RUN_MODE, RUN_MODE_SPEED)
        write_param_f32(bus, IDX_LIMIT_CUR, CURRENT_LIMIT)
        time.sleep(0.05)

        print(f"Enabling and spinning at {TARGET_SPEED} rad/s for {RUN_SECONDS:.0f}s...")
        send(bus, CMD_ENABLE, bytes(8))
        write_param_f32(bus, IDX_SPD_REF, TARGET_SPEED)

        t_end  = time.time() + RUN_SECONDS
        period = 1.0 / LOOP_HZ
        i = 0
        while time.time() < t_end:
            write_param_f32(bus, IDX_SPD_REF, TARGET_SPEED)
            fb = decode_feedback(bus.recv(timeout=period))
            if fb and i % 10 == 0:                    # print ~5x/sec, not 50x
                print(f"  vel={fb[0]:6.2f} rad/s   torque={fb[1]:5.2f} Nm   temp={fb[2]:4.1f} C")
            i += 1

        print("Ramping to zero...")
        write_param_f32(bus, IDX_SPD_REF, 0.0)
        time.sleep(0.3)
    finally:
        send(bus, CMD_STOP, bytes(8))                 # always disable on exit
        print("Motor disabled.")
