#!/bin/bash
#
# estop.sh - EMERGENCY STOP.
# Kills any robot control process, then sends the CyberGear STOP/disable command
# to both motors so nothing keeps driving (or holding torque) on the bus.
#
# Usage:  ./utils/estop.sh
#
IFACE="can0"

echo "[estop] killing any control processes..."
pkill -f robot_server.py 2>/dev/null
pkill -f dance_test.py   2>/dev/null
pkill -f spin_test.py    2>/dev/null
pkill -f motor_test.py   2>/dev/null
sleep 0.3

echo "[estop] disabling motors on ${IFACE} (CyberGear stop = command 0x04)..."
# extended ID = (0x04 << 24) | (master 0x00 << 8) | motorID
if command -v cansend >/dev/null 2>&1; then
    cansend "${IFACE}" 0400007E#0000000000000000 2>/dev/null && echo "  sent STOP to 0x7E (right)"
    cansend "${IFACE}" 0400007F#0000000000000000 2>/dev/null && echo "  sent STOP to 0x7F (left)"
else
    echo "  WARNING: cansend not found (sudo apt install -y can-utils)"
fi

echo "[estop] done - motors disabled. (If still noisy, hit a bump switch to cut the motor rail.)"
