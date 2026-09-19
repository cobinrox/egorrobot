#!/bin/bash
#
# bootcrumbs.sh - drop "how far did the boot get" breadcrumbs onto the card.
#
# Installs tiny systemd services that append a timestamped line + the board
# MODEL to  /boot/firmware/bootcrumbs.txt  at three boot stages, each followed
# by sync. Move the card between machines, then read the file back (on a Pi, or
# even by popping the card into a Windows reader - it's on the FAT boot
# partition) to see how far each board got.
#
#   sudo ./utils/bootcrumbs.sh install   # add + enable the breadcrumb services
#        ./utils/bootcrumbs.sh show      # print the breadcrumbs file
#   sudo ./utils/bootcrumbs.sh remove    # remove the services (keeps the file)
#
# Stages:
#   EARLY       - filesystems mounted, very early userspace
#   MULTIUSER   - reached multi-user (most services started)
#   NET-ONLINE  - the network came up
#
# Reading the ladder for a given board's newest lines:
#   (none)                         -> never reached Linux (firmware/HW/bootloader)
#   EARLY only                     -> kernel boots, hangs before services finish
#   EARLY + MULTIUSER, no NET      -> boots but network never came up (SSH fails)
#   EARLY + MULTIUSER + NET-ONLINE -> fully boots AND networks (Pi is fine)

set -euo pipefail

HELPER="/usr/local/sbin/bootcrumb.sh"
DIR="/boot/firmware"; [ -d "$DIR" ] || DIR="/boot"
CRUMB="${DIR}/bootcrumbs.txt"
UNITS=(bootcrumb-early bootcrumb-multiuser bootcrumb-net)

need_root(){ [[ "${EUID}" -eq 0 ]] || { echo "run as root: sudo $0 $1" >&2; exit 1; }; }

case "${1:-}" in
  show)
    [[ -f "$CRUMB" ]] && cat "$CRUMB" || echo "no breadcrumbs file at $CRUMB yet"
    ;;
  install)
    need_root install
    echo "Writing helper -> $HELPER"
    cat > "$HELPER" << 'HLP'
#!/bin/bash
STAGE="${1:-?}"
DIR="/boot/firmware"; [ -d "$DIR" ] || DIR="/boot"
CRUMB="${DIR}/bootcrumbs.txt"
MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown)"
IPS="$(hostname -I 2>/dev/null | sed 's/ *$//')"
printf '%s | %-11s | %-30s | IP: %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "$STAGE" "$MODEL" "$IPS" >> "$CRUMB" 2>/dev/null || true
sync
HLP
    chmod 755 "$HELPER"

    cat > /etc/systemd/system/bootcrumb-early.service << 'U1'
[Unit]
Description=Boot breadcrumb (early)
DefaultDependencies=no
After=local-fs.target
Before=sysinit.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/bootcrumb.sh EARLY
RemainAfterExit=yes
[Install]
WantedBy=sysinit.target
U1

    cat > /etc/systemd/system/bootcrumb-multiuser.service << 'U2'
[Unit]
Description=Boot breadcrumb (multi-user)
After=multi-user.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/bootcrumb.sh MULTIUSER
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
U2

    cat > /etc/systemd/system/bootcrumb-net.service << 'U3'
[Unit]
Description=Boot breadcrumb (network online)
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/bootcrumb.sh NET-ONLINE
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
U3

    systemctl daemon-reload
    for u in "${UNITS[@]}"; do systemctl enable "${u}.service" >/dev/null; done
    printf '%s | %-11s | %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "INSTALLED" "$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)" >> "$CRUMB"; sync
    echo "Installed. Breadcrumbs -> $CRUMB"
    echo "Reboot this Pi once to confirm it writes EARLY/MULTIUSER/NET-ONLINE,"
    echo "then card -> Pi5 (~90s) -> back here, and run:  $0 show"
    ;;
  remove)
    need_root remove
    for u in "${UNITS[@]}"; do
      systemctl disable "${u}.service" 2>/dev/null || true
      rm -f "/etc/systemd/system/${u}.service"
    done
    rm -f "$HELPER"; systemctl daemon-reload
    echo "Removed services + helper. Kept $CRUMB."
    ;;
  *)
    echo "usage: $0 {install|show|remove}   (install/remove need sudo)"; exit 1 ;;
esac
