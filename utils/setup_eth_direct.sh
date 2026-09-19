#!/bin/bash
#
# setup_eth_direct.sh
# -------------------------------------------------------------------------
# Configure the Pi's wired port (eth0) as a self-contained DIRECT link, so a
# laptop plugged straight into it (via a USB-Ethernet dongle, no router) gets an
# address automatically and can SSH to the Pi - anywhere, no network required.
#
#   Pi (eth0):  10.10.10.1
#   laptop:     10.10.10.x   (handed out by the Pi automatically)
#   SSH:        ssh u@10.10.10.1
#
# The 10.10.10.0/24 range is deliberately unlike a home Wi-Fi's 192.168.x, so
# it's obvious at a glance you're on the direct link, not the wireless network.
#
# Run:  sudo ./utils/setup_eth_direct.sh
# Safe to re-run (it recreates the connection cleanly).
#
# WARNING: do NOT plug this port into a home router - it runs its own DHCP
# server and would collide with the router's.
# -------------------------------------------------------------------------
set -euo pipefail

CON="egor-eth-direct"
IFACE="eth0"
PI_IP="10.10.10.1/24"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run as root:  sudo $0" >&2
    exit 1
fi

# Clean out any previous version so re-runs are idempotent.
if nmcli -t -f NAME connection show | grep -qx "${CON}"; then
    echo "Removing existing ${CON} ..."
    nmcli connection delete "${CON}" || true
fi

echo "Creating ${CON}: ${IFACE} -> ${PI_IP} (shared / hands out addresses) ..."
nmcli connection add type ethernet ifname "${IFACE}" con-name "${CON}" \
    ipv4.method shared \
    ipv4.addresses "${PI_IP}" \
    ipv6.method disabled \
    connection.autoconnect yes \
    connection.autoconnect-priority 100

echo "Activating ${CON} ..."
nmcli connection up "${CON}"

echo
echo "----------------------------------------------------------------------"
echo "eth0 address (expect: inet 10.10.10.1/24):"
ip addr show "${IFACE}"
echo
echo "Device status (eth0 should be 'connected' via ${CON}):"
nmcli device status
echo "----------------------------------------------------------------------"
echo "Done. Plug a laptop into ${IFACE}; it will get a 10.10.10.x address."
echo "SSH to the Pi with:  ssh u@10.10.10.1"
echo "(Keep this port OFF your home router - it serves its own DHCP.)"
