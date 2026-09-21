#!/bin/bash
#
# setup_robot_service.sh
# -------------------------------------------------------------------------
# One-time installer. Registers the robot HTTP control server (robot_server.py)
# as a systemd service that starts automatically on every boot, after the CAN
# bus is up.
#
# Usage (on the Pi, from the repo):
#     sudo ./utils/setup_robot_service.sh
#
# Safe to re-run. Stop it during development with ./utils/stop_robot_service.sh
# -------------------------------------------------------------------------
set -euo pipefail

SERVICE="egor-robot.service"
UNIT="/etc/systemd/system/${SERVICE}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run as root:  sudo $0" >&2
    exit 1
fi

# Resolve absolute paths from THIS script's location (it lives in utils/).
# The main program now lives in the repo ROOT (one level up from utils/),
# alongside robot_ui.html and admin.html.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVER="${ROOT_DIR}/robot_server.py"
RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"
PY="$(command -v python3)"

if [[ ! -f "${SERVER}" ]]; then
    echo "ERROR: ${SERVER} not found (robot_server.py + robot_ui.html + admin.html live in the repo root)" >&2
    exit 1
fi

echo "[1/4] Writing ${UNIT}"
echo "      user=${RUN_USER}  python=${PY}"
echo "      server=${SERVER}"
cat > "${UNIT}" << EOF
[Unit]
Description=Egor robot HTTP control server
After=network.target egor-can.service
Wants=egor-can.service

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${ROOT_DIR}
ExecStart=${PY} ${SERVER}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

echo "[2/4] systemctl daemon-reload"
systemctl daemon-reload
echo "[3/4] enabling ${SERVICE} (auto-start on boot)"
systemctl enable "${SERVICE}"
echo "[4/4] (re)starting ${SERVICE} now"
systemctl restart "${SERVICE}"

echo
echo "----------------------------------------------------------------------"
systemctl --no-pager --full status "${SERVICE}" | head -n 8 || true
echo "----------------------------------------------------------------------"
echo "Control UI:  http://egor:8080/   (or http://<pi-ip>:8080/)"
echo "Stop during dev:  ./utils/stop_robot_service.sh"
echo
echo "NOTE: if a manual 'python3 robot_server.py' is already running, stop it"
echo "      first - two servers can't share port 8080 or the CAN bus."
