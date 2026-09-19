#!/bin/bash
#
# setup_camera_service.sh
# -------------------------------------------------------------------------
# One-time installer. Registers the USB webcam MJPEG stream (ustreamer) as a
# systemd service that starts automatically on boot, serving on port 8081.
#
# Usage (on the Pi, from the repo):
#     sudo ./utils/setup_camera_service.sh
#
# Stream URLs once running:  http://egor:8081/         (viewer)
#                            http://egor:8081/stream   (raw MJPEG for <img>)
# Safe to re-run.
# -------------------------------------------------------------------------
set -euo pipefail

# --- tunables (match what we tested) ---
DEVICE="/dev/video0"
RESOLUTION="640x480"
FPS="15"
PORT="8081"

SERVICE="egor-camera.service"
UNIT="/etc/systemd/system/${SERVICE}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run as root:  sudo $0" >&2
    exit 1
fi

UST="$(command -v ustreamer || true)"
RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"

if [[ -z "${UST}" ]]; then
    echo "ERROR: ustreamer not found. Install it first:  sudo apt install -y ustreamer" >&2
    exit 1
fi

echo "[1/4] Writing ${UNIT}"
echo "      ustreamer=${UST}  user=${RUN_USER}  ${DEVICE} ${RESOLUTION}@${FPS}fps port ${PORT}"
cat > "${UNIT}" << EOF
[Unit]
Description=Egor webcam MJPEG stream (ustreamer)
After=network.target
# keep retrying even if the camera is unplugged / not yet present
StartLimitIntervalSec=0

[Service]
Type=simple
User=${RUN_USER}
ExecStart=${UST} -d ${DEVICE} -r ${RESOLUTION} -m MJPEG -f ${FPS} -s 0.0.0.0 -p ${PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "[2/4] daemon-reload"
systemctl daemon-reload
echo "[3/4] enabling ${SERVICE}"
systemctl enable "${SERVICE}"
echo "[4/4] (re)starting ${SERVICE}"
systemctl restart "${SERVICE}"

echo
systemctl --no-pager --full status "${SERVICE}" | head -n 8 || true
echo
echo "Stream:  http://egor:8081/stream   (viewer at http://egor:8081/)"
echo "Stop for dev:  sudo systemctl stop ${SERVICE}"
