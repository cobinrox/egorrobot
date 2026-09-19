#!/bin/bash
#
# stop_robot_service.sh
# Stop the auto-start robot control service so you can run/iterate manually.
# The server disables the motors cleanly on shutdown; as a belt-and-suspenders
# safety this also sends the CyberGear stop command afterward.
#
# Usage:  ./utils/stop_robot_service.sh
#
SERVICE="egor-robot.service"

echo "Stopping ${SERVICE} ..."
sudo systemctl stop "${SERVICE}" || true

# Belt-and-suspenders: make sure the motors are disabled even if the server
# was killed hard before its own clean-up ran.
if command -v cansend >/dev/null 2>&1; then
    cansend can0 0400007E#0000000000000000 2>/dev/null || true
    cansend can0 0400007F#0000000000000000 2>/dev/null || true
fi

echo
systemctl --no-pager --full status "${SERVICE}" | head -n 5 || true
echo
echo "Stopped. It will start again on next boot."
echo "  Run manually for dev:      python3 utils/robot_server.py"
echo "  Turn OFF auto-start:        sudo systemctl disable ${SERVICE}"
echo "  Turn auto-start back ON:    sudo systemctl enable ${SERVICE}"
