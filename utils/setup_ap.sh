#!/bin/bash
#
# setup_ap.sh
# -------------------------------------------------------------------------
# Turn the Pi's Wi-Fi (wlan0) into its own access point so the robot works with
# no router, anywhere.
#
#   SSID:      egorwifi
#   password:  password         (WPA2; also embedded in the join-QR later)
#   band:      2.4 GHz, channel 6   (best range/compatibility)
#   Pi IP:     10.10.10.1        (control page: http://10.10.10.1:8080)
#
# Home Wi-Fi is kept as a LOWER-priority autoconnect fallback: if the AP ever
# fails to start on boot, the Pi rejoins your home network so you're not locked
# out. This does NOT delete your home Wi-Fi connection.
#
# Run:  sudo ./utils/setup_ap.sh      (then: sudo reboot)
# Safe to re-run.
#
# NOTE: activating the AP drops wlan0 off home Wi-Fi, so an SSH session over home
# Wi-Fi will freeze. Reconnect by joining "egorwifi" and: ssh u@10.10.10.1
# -------------------------------------------------------------------------
set -euo pipefail

CON="egor-ap"
IFACE="wlan0"
SSID="egorwifi"
PASS="password"
AP_IP="10.10.10.1/24"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run as root:  sudo $0" >&2
    exit 1
fi

# Idempotent: drop any previous AP profile.
if nmcli -t -f NAME connection show | grep -qx "${CON}"; then
    echo "Removing existing ${CON} ..."
    nmcli connection delete "${CON}" || true
fi

echo "Creating AP profile '${CON}' (SSID ${SSID}, 2.4GHz, ${AP_IP}) ..."
nmcli connection add type wifi ifname "${IFACE}" con-name "${CON}" ssid "${SSID}" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel 6 \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "${PASS}" \
    ipv4.method shared \
    ipv4.addresses "${AP_IP}" \
    ipv6.method disabled

# Keep home Wi-Fi as a fallback, but lower its priority so the AP wins at boot.
while IFS=: read -r name typ; do
    [[ "${typ}" == "802-11-wireless" ]] || continue
    [[ "${name}" == "${CON}" ]] && continue
    echo "Lowering priority of existing Wi-Fi connection: ${name}"
    nmcli connection modify "${name}" connection.autoconnect-priority 0 2>/dev/null || true
done < <(nmcli -t -f NAME,TYPE connection show)

echo
echo "----------------------------------------------------------------------"
echo "AP profile created. Wi-Fi country/reg domain must be set for AP to start"
echo "(yours already is, since wlan0 connects as a client). To activate cleanly:"
echo
echo "    sudo reboot"
echo
echo "After reboot, on your phone/laptop:"
echo "  1. Join Wi-Fi:   ${SSID}   (password: ${PASS})"
echo "  2. Control page: http://10.10.10.1:8080"
echo "  3. SSH:          ssh u@10.10.10.1"
echo
echo "If the AP fails to start, the Pi falls back to home Wi-Fi automatically."
echo "----------------------------------------------------------------------"
