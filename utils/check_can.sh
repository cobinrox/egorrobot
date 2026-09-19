#!/bin/bash
#
# check_can.sh - quick post-boot sanity check that the CyberGear CAN bus (can0)
# is up and healthy at 1 Mbit/s. Read-only; no sudo needed.
#
# Usage (from the repo root):
#     ./utils/check_can.sh
#
# Reminder: on this Waveshare hat the header labeled "CAN1" is the can0 interface.

IFACE="can0"
EXPECT_BITRATE="1000000"
FAILED=0

ok()   { echo "  [ OK ] $1"; }
bad()  { echo "  [FAIL] $1"; FAILED=1; }
info() { echo "  [info] $1"; }

echo "Checking ${IFACE} ..."

# 1) Does the interface exist at all?
if ! ip link show "${IFACE}" >/dev/null 2>&1; then
    bad "${IFACE} does not exist (CAN hat overlay missing from config.txt, or driver not loaded)"
    echo
    echo "RESULT: CAN interface NOT ready."
    exit 1
fi
ok "${IFACE} exists"

DETAILS="$(ip -details link show "${IFACE}" 2>/dev/null)"

# 2) Is it UP?
if echo "${DETAILS}" | grep -qw "state UP"; then
    ok "${IFACE} is UP"
else
    bad "${IFACE} is DOWN  -> sudo ./utils/setup_can_service.sh   (or bring it up manually)"
fi

# 3) Controller health
if   echo "${DETAILS}" | grep -q "ERROR-ACTIVE";  then ok  "controller ERROR-ACTIVE (healthy)"
elif echo "${DETAILS}" | grep -q "ERROR-PASSIVE"; then bad "controller ERROR-PASSIVE (frames unacknowledged - check motor power/wiring)"
elif echo "${DETAILS}" | grep -q "BUS-OFF";       then bad "controller BUS-OFF (serious bus fault - check wiring/termination)"
else info "controller state unknown (interface likely down)"
fi

# 4) Bitrate
if echo "${DETAILS}" | grep -q "bitrate ${EXPECT_BITRATE}"; then
    ok "bitrate ${EXPECT_BITRATE} (1 Mbit/s)"
else
    ACT="$(echo "${DETAILS}" | grep -o 'bitrate [0-9]*' | head -1)"
    bad "bitrate is not ${EXPECT_BITRATE} (${ACT:-none set})"
fi

# 5) Auto-start service (informational)
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-enabled egor-can.service >/dev/null 2>&1; then
        ok "egor-can.service enabled (auto-starts on boot)"
    else
        info "egor-can.service not enabled -> sudo ./utils/setup_can_service.sh"
    fi
fi

echo
if [[ "${FAILED}" -eq 0 ]]; then
    echo "RESULT: yea verily, ${IFACE} is up and healthy."
    echo "(To also confirm the motors answer: python3 utils/scan_motors.py)"
    exit 0
else
    echo "RESULT: ${IFACE} has problems - see the [FAIL] line(s) above."
    exit 1
fi
