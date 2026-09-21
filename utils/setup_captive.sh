#!/bin/bash
#
# setup_captive.sh
# -------------------------------------------------------------------------
# Captive portal for the egorwifi AP: joining the network auto-opens the robot
# control page. Two parts:
#   1. Wildcard DNS  — every name on egorwifi resolves to the Pi (10.10.10.1),
#      so the phone's "is there internet?" check lands on us.
#   2. A real listener on port 80 (a tiny redirect server, runs as root) that
#      302-redirects everything to the control page. Unlike a firewall rule you
#      can VERIFY it works:  curl -I http://10.10.10.1
#
# Run:  sudo ./utils/setup_captive.sh    (then: sudo reboot)
# Safe to re-run. Affects the AP (wlan0) only.
# -------------------------------------------------------------------------
set -euo pipefail

AP_IP="10.10.10.1"
DNSD="/etc/NetworkManager/dnsmasq-shared.d"
SRV="/usr/local/sbin/egor-captive80.py"
UNIT="/etc/systemd/system/egor-captive80.service"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run as root:  sudo $0" >&2
    exit 1
fi

echo "[1/5] Wildcard DNS -> ${AP_IP}"
install -d "${DNSD}"
cat > "${DNSD}/egor-captive.conf" << DNSEOF
# egorwifi: resolve every DNS name to the Pi so OS captive checks land on us.
address=/#/${AP_IP}
DNSEOF

echo "[2/5] Removing the old (failed) iptables redirect, if present"
systemctl disable --now egor-captive.service 2>/dev/null || true
rm -f /etc/systemd/system/egor-captive.service /usr/local/sbin/egor-captive-nat.sh
iptables -t nat -D PREROUTING -i wlan0 -p tcp --dport 80 -j REDIRECT --to-ports 8080 2>/dev/null || true

echo "[3/5] Installing port-80 redirect server -> ${SRV}"
cat > "${SRV}" << 'PYSRV'
#!/usr/bin/env python3
# Tiny port-80 responder for the egorwifi captive portal: redirect every request
# to the control page so joining the AP auto-pops it. Runs as root (port 80).
from http.server import BaseHTTPRequestHandler, HTTPServer
TARGET = "http://10.10.10.1:8080/"
class H(BaseHTTPRequestHandler):
    def _r(self):
        self.send_response(302)
        self.send_header("Location", TARGET)
        self.send_header("Content-Length", "0")
        self.end_headers()
    do_GET = do_POST = do_HEAD = _r
    def log_message(self, *a):
        pass
if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 80), H).serve_forever()
PYSRV
chmod 755 "${SRV}"

echo "[4/5] Installing service -> ${UNIT}"
cat > "${UNIT}" << UNITEOF
[Unit]
Description=Egor captive port-80 redirect to control page
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 ${SRV}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNITEOF

echo "[5/5] Enable + start"
systemctl daemon-reload
systemctl enable egor-captive80.service >/dev/null
systemctl restart egor-captive80.service
sleep 1

echo
echo "----------------------------------------------------------------------"
systemctl --no-pager --full status egor-captive80.service | head -n 5 || true
echo
echo "VERIFY port 80 now answers (expect: 302 Found, Location http://${AP_IP}:8080/):"
echo "    curl -I http://${AP_IP}"
echo
echo "Then reboot, join egorwifi, and the control page should auto-pop:"
echo "    sudo reboot"
echo "----------------------------------------------------------------------"
