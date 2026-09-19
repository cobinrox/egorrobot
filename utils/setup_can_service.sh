#!/bin/bash
#
# setup_can_service.sh
# -------------------------------------------------------------------------
# One-time installer. Makes the CyberGear CAN bus (can0) come up automatically
# at 1 Mbit/s on EVERY boot, by installing a small helper + a systemd service.
#
# Usage (on the Pi, from the repo root):
#     sudo ./utils/setup_can_service.sh
#
# Safe to re-run: it overwrites its files and re-enables the service.
#
# NOTE: On this Waveshare hat the header labeled "CAN1" is the Linux `can0`
#       interface, and the motors live on it - so this service targets can0.
# -------------------------------------------------------------------------

set -euo pipefail

IFACE="can0"
BITRATE="1000000"
HELPER="/usr/local/sbin/egor-can-up.sh"
UNIT="/etc/systemd/system/egor-can.service"
SERVICE="egor-can.service"

# --- must run as root ----------------------------------------------------
if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: this must be run as root.  Try:  sudo $0" >&2
    exit 1
fi

echo "[1/5] Installing CAN bring-up helper -> ${HELPER}"
install -d -m 755 "$(dirname "${HELPER}")"
cat > "${HELPER}" << 'HELPEREOF'
#!/bin/bash
# Bring up the CyberGear CAN bus (can0) at 1 Mbit/s.
# Installed by setup_can_service.sh; run at boot by egor-can.service.
IFACE="can0"
BITRATE="1000000"

# Wait up to ~10s for the interface to appear (the MCP2515 driver can init late).
for _ in $(seq 1 20); do
    ip link show "${IFACE}" >/dev/null 2>&1 && break
    sleep 0.5
done

if ! ip link show "${IFACE}" >/dev/null 2>&1; then
    echo "egor-can-up: interface ${IFACE} never appeared" >&2
    exit 1
fi

# The bitrate can't be changed while the link is up, so lower it first if needed.
if ip -details link show "${IFACE}" 2>/dev/null | grep -q "state UP"; then
    ip link set "${IFACE}" down
fi

ip link set "${IFACE}" type can bitrate "${BITRATE}"
ip link set "${IFACE}" up
HELPEREOF
chmod 755 "${HELPER}"

echo "[2/5] Installing systemd unit -> ${UNIT}"
cat > "${UNIT}" << 'UNITEOF'
[Unit]
Description=Bring up CyberGear CAN bus (can0) at 1 Mbit/s
After=network-pre.target
Wants=network-pre.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/egor-can-up.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNITEOF

echo "[3/5] Reloading systemd"
systemctl daemon-reload

echo "[4/5] Enabling ${SERVICE} (so it runs on every boot)"
systemctl enable "${SERVICE}"

echo "[5/5] Starting ${SERVICE} now"
systemctl start "${SERVICE}"

echo
echo "----------------------------------------------------------------------"
echo "Done. Service status:"
systemctl --no-pager --full status "${SERVICE}" || true
echo
echo "Interface state (expect: state UP, ERROR-ACTIVE, bitrate 1000000):"
ip -details link show "${IFACE}" || true
echo "----------------------------------------------------------------------"
echo "can0 will now come up automatically at 1 Mbit/s on every boot."
