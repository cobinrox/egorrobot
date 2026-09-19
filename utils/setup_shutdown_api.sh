#!/bin/bash
#
# setup_shutdown_api.sh
# -------------------------------------------------------------------------
# Lets the robot control server (running as your normal user) power the Pi off
# via the web "Shut down" button. It grants password-less sudo for ONLY the
# `shutdown` command - nothing else - via a validated /etc/sudoers.d drop-in.
#
# Run once:  sudo ./utils/setup_shutdown_api.sh
# -------------------------------------------------------------------------
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run as root:  sudo $0" >&2
    exit 1
fi

RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || echo u)}"
SHUT="$(command -v shutdown || echo /sbin/shutdown)"
DROPIN="/etc/sudoers.d/egor-shutdown"

echo "Granting ${RUN_USER} password-less sudo for: ${SHUT}"

TMP="$(mktemp)"
echo "${RUN_USER} ALL=(root) NOPASSWD: ${SHUT}" > "${TMP}"

# Validate BEFORE installing so a mistake can never lock you out of sudo.
if ! visudo -cf "${TMP}"; then
    echo "ERROR: generated sudoers rule is invalid - not installing." >&2
    rm -f "${TMP}"
    exit 1
fi

install -m 0440 -o root -g root "${TMP}" "${DROPIN}"
rm -f "${TMP}"

echo "Installed ${DROPIN}."
echo "Verify (as ${RUN_USER}):  sudo -n -l ${SHUT}   # should list the command"
echo "Restart the control server for the web Shut-down button to work."
