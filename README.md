# EgorRobot — Setup Guide

Setup notes for flashing and configuring the Raspberry Pi 5 that controls
EgorRobot's two CyberGear motors over a Waveshare 2-CH CAN HAT.

> **Important naming note (read once):** On this hat, the header physically
> labeled **"CAN1"** shows up in Linux as the **`can0`** interface. The motors
> are wired to that header, so **all motor commands use `can0`.** The `can1`
> interface exists but is unused (no cable). Don't trust the silkscreen label.

---

## 1. Flash the OS

1. Flash **Raspberry Pi OS 64-bit Lite**.
2. Add the following to the **end** of `/boot/firmware/config.txt` (edit as sudo):
   ```
   dtparam=spi=on
   dtoverlay=spi1-3cs
   dtoverlay=mcp2515,spi1-1,oscillator=16000000,interrupt=22
   dtoverlay=mcp2515,spi1-2,oscillator=16000000,interrupt=13
   ```
3. Save and reboot.
4. After reboot, confirm both interfaces exist:
   ```
   ls /sys/class/net
   ```
   You should see `can0` and `can1` in the output.

> If you re-flash and CAN won't communicate, note that the running system
> reports its CAN clock as 8 MHz; verify the `oscillator=` value matches your
> hat's actual crystal.

## 2. Install CAN tooling

```
sudo apt update && sudo apt install -y can-utils python3-can python3-pip
```
(The saved image `egor_9_7_with_powerdown.img` already has these installed.)

## 3. Bring up the motor bus (`can0`)

The motors are on `can0` at **1 Mbit/s**.

**Recommended — install the auto-start service (one time).** So `can0` comes up
at the right bitrate on every boot and you never type the manual command again:
```
sudo ./utils/setup_can_service.sh
```
This installs and starts a systemd service (`egor-can.service`). Manage it with:
```
sudo systemctl status  egor-can.service
sudo systemctl restart egor-can.service
```

**Manual alternative (one-off, not persistent).** Bring it up just for this session:
```
sudo ip link set can0 up type can bitrate 1000000
```
Confirm it is healthy:
```
ip -details link show can0
```
Look for `state UP` and `can state ERROR-ACTIVE`. (`ERROR-PASSIVE` or `BUS-OFF`
means nothing is acknowledging on the bus — check motor power and wiring.)

## 4. Loopback self-test (optional, no motor needed)

Verifies the hat's CAN controller by looping frames back internally.

Enable loopback:
```
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000 loopback on
sudo ip link set can0 up
```
In terminal 1:
```
candump can0
```
In terminal 2:
```
cansend can0 0300007F#0000000000000000
```
You should see the frame appear in terminal 1.

Turn loopback back off when done:
```
# Ctrl-C the candump in terminal 1 first
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000 loopback off
sudo ip link set can0 up
```

## 5. Failsafe power-down button (optional but recommended)

A momentary button that triggers a clean shutdown, protecting the SD card from
corruption on an accidental power bump.

1. Connect a momentary switch between **GPIO26 (BCM) / physical pin 37** and GND.
2. Copy `utils/shutdown_button.py` to `/home/u/`.
3. Create the service file `/etc/systemd/system/shutdown-button.service`:
   ```
   [Unit]
   Description=GPIO Emergency Shutdown Button
   After=multi-user.target

   [Service]
   Type=simple
   # Run as root so GPIO access works correctly.
   User=root
   WorkingDirectory=/home/u
   ExecStart=/usr/bin/python3 /home/u/shutdown_button.py
   # Restart the program if it unexpectedly stops.
   Restart=on-failure
   RestartSec=2

   [Install]
   WantedBy=multi-user.target
   ```
4. Register, enable, and start it:
   ```
   sudo systemctl daemon-reload
   sudo systemctl enable shutdown-button.service
   sudo systemctl start shutdown-button.service
   sudo systemctl status shutdown-button.service
   ```
   View its log with: `sudo journalctl -u shutdown-button.service`

## 6. Test the motors

With `can0` up (step 3) and the **wheels off the ground**:

```
sudo ./utils/setup_can_service.sh   # one time: auto-bring-up can0 on every boot
python3 utils/scan_motors.py    # discover motor CAN IDs (finds 0x7E and 0x7F)
python3 utils/motor_test.py     # enable/read/disable one motor (is it alive?)
python3 utils/spin_test.py      # gently spin one motor in speed mode
python3 utils/dance_test.py     # full demo: both wheels, forward/back, N turns
```

Every script disables the motors on exit. Ctrl-C is safe; a bump switch cuts the
motor rail (Pi stays up) for a hard stop.

## 7. Drive it from a web page (HTTP control)

A Flask server (`utils/robot_server.py`) exposes a REST API and serves a joystick
web page (`utils/robot_ui.html`). Both files must sit together in `utils/`.

Install Flask once:
```
sudo apt install -y python3-flask
```

**Recommended — run it as an auto-start service (one time):**
```
sudo ./utils/setup_robot_service.sh
```
This installs `egor-robot.service`, which starts on every boot after
`egor-can.service`. Then open the control page from any device on the same LAN:
```
http://egor:8080/          (or http://<pi-ip>:8080/)
```
Hold a direction to move, release to stop; arrow keys / WASD also work; there's a
big EMERGENCY STOP. **Wheels off the ground until you're sure.**

**Development loop:**
```
./utils/stop_robot_service.sh              # stop the service (also disables motors)
python3 utils/robot_server.py              # run manually to iterate
sudo systemctl start egor-robot.service    # hand back to the service when done
```

**REST API** (all POST unless noted):

| Endpoint | Action |
|---|---|
| `/api/move/<DIR>` | DIR = FWD, REV, FWD_L, FWD_R, REV_L, REV_R, SPIN_L, SPIN_R, STOP |
| `/api/drive` | JSON `{"left":-1..1,"right":-1..1}` (raw per-wheel) |
| `/api/stop` | soft stop (wheels to 0, motors stay enabled) |
| `/api/estop` | hard stop (disable motors) |
| `/api/enable` | clear an e-stop / re-arm |
| `/api/shutdown` | power the Pi off cleanly (needs `setup_shutdown_api.sh`) |
| `/api/reboot` | reboot the Pi cleanly (same permission as shutdown) |
| `/api/status` (GET) | JSON telemetry + `can_error` flag |
| `/api/netinfo` (GET) | interfaces + IPs (eth0 = maintenance SSH target) |
| `/api/sysinfo` (GET) | power/under-voltage, CPU temp, service + CAN health |
| `/admin` (GET) | admin / health web page |

**Safety:** a watchdog stops the wheels if no command arrives within 0.5 s, so a
dropped connection or closed tab fails safe. The server has **no authentication**
— use it only on a trusted network.

**Shut down from the page:** the control page has a **⏻ Shut down Pi** button
(with an "Are you sure?" confirm) that calls `POST /api/shutdown`, which stops the
motors and powers the Pi off cleanly. Because the server runs as a normal user,
grant it permission once:
```
sudo ./utils/setup_shutdown_api.sh
```
This adds a narrow password-less-sudo rule for **only** the `shutdown` command
(validated before install). Until you run it, the button safely reports
"Shutdown not available".

**Admin / health page:** open **`/admin`** (or the "admin / network info" link at
the bottom of the control page) for a live panel, refreshed every few seconds:
each network interface's IP — including a copy-ready `ssh u@<eth0-ip>` for
maintenance — plus power/under-voltage status, CPU temperature, the three
services' health, the CAN bus state, and a **Reboot** button. It answers "is the
robot healthy, and how do I SSH in?" at a glance. (Reboot uses the same
`setup_shutdown_api.sh` permission as shutdown.)

**Low-level API tests** (server running; wheels up):
```
python3 utils/run_status.py       # print status
python3 utils/run_fwd_test.py     # forward 2 s
python3 utils/run_left_test.py    # spin left 2 s
python3 utils/run_right_test.py   # spin right 2 s
python3 utils/run_stop_test.py    # single stop
./utils/estop.sh                  # emergency: kill control procs + disable motors
```

## 8. Add the webcam video (live view in the control page)

A USB webcam is streamed as MJPEG by **µStreamer** on port 8081, and the control
page (`robot_ui.html`) embeds that stream so the driver sees live video above the
joystick. The camera runs as its **own** service on its **own** port, so a video
hiccup can never stall motor control.

1. Plug in the USB webcam and confirm the Pi sees it (note its capture node,
   usually `/dev/video0`):
   ```
   sudo apt install -y v4l-utils
   lsusb                         # your camera should be listed
   v4l2-ctl --list-devices       # find its /dev/videoN node
   ```
2. Install µStreamer:
   ```
   sudo apt install -y ustreamer
   ```
3. Test it in the foreground, then view in a browser:
   ```
   ustreamer -d /dev/video0 -r 640x480 -m MJPEG -f 15 -s 0.0.0.0 -p 8081
   # then open http://egor:8081/stream  — you should see live video
   ```
   (The G910 outputs MJPG in hardware, so the Pi barely works. A harmless startup
   warning about "HW encoding quality parameters" can be ignored.)
4. Ctrl-C the test, then install it as an auto-start service:
   ```
   sudo ./utils/setup_camera_service.sh
   ```
   This installs `egor-camera.service` (640×480 @ 15 fps, port 8081; starts on
   boot). Tune resolution/fps at the top of that script. Stop it for development
   with `sudo systemctl stop egor-camera.service`.
5. With the control server running (Section 7), open `http://egor:8080/` — the
   video panel appears at the top. If the camera is down you'll see a
   "Camera offline — retrying…" panel that recovers on its own.

Sizing: the video panel is capped by `max-width` on `.cam` in `robot_ui.html`
(currently 320 px); button sizes are tuned nearby for small phones.

## 9. Troubleshooting & maintenance tools

A few utilities exist purely to make this (or any) Pi easier to look after:

- **Admin / health page** — `/admin` in the browser (Section 7): interface IPs, the
  `ssh u@<eth0-ip>` maintenance line, power/temp/service/CAN health, and reboot.
- **`check_can.sh`** — quick post-boot check that `can0` is up and healthy:
  ```
  ./utils/check_can.sh
  ```
- **`bootcrumbs.sh`** — find out how far a boot got when a Pi won't boot or isn't
  reachable, *without* HDMI or a serial cable. It stamps the boot stage (plus IP and
  board model) onto the card; read it back on any machine, even a Windows card
  reader:
  ```
  sudo ./utils/bootcrumbs.sh install    # add the breadcrumb services
       ./utils/bootcrumbs.sh show        # read how far the last boot got
  sudo ./utils/bootcrumbs.sh remove      # take them out when done
  ```
- **`setup_eth_direct.sh`** — router-free wired SSH: makes eth0 hand out an address
  so a laptop plugged straight in (via a USB-Ethernet dongle) can `ssh u@10.0.0.1`.
  Don't plug that port into a home router (it runs its own DHCP).
  ```
  sudo ./utils/setup_eth_direct.sh
  ```

These are reusable on other Raspberry Pi projects, not just this robot.

## 10. Portable access — egorwifi AP + QR

So the robot works **anywhere with no router** and no IP to remember, the Pi hosts
its own Wi-Fi and you reach it at a fixed address.

**Access point (`setup_ap.sh`)** — turns wlan0 into the AP:

- SSID **`egorwifi`**, password **`password`** (WPA2), 2.4 GHz.
- Pi fixed at **`10.10.10.1`** → control page **`http://10.10.10.1:8080`**.
- Home Wi-Fi is kept as a lower-priority autoconnect **fallback** (if the AP fails
  to start on boot, the Pi rejoins home Wi-Fi so you're not locked out).

```
sudo ./utils/setup_ap.sh      # then: sudo reboot
```

Activating the AP drops wlan0 off home Wi-Fi. Reconnect by joining egorwifi
(`ssh u@10.10.10.1`), or over eth0-to-router (`ssh u@192.168.0.xx`, IP from `/admin`).

**Clean URL (`setup_captive.sh`)** — adds wildcard DNS + a tiny root service on
port 80 that redirects to the control page, so `http://10.10.10.1` (no `:8080`)
works. Verify with `curl -I http://10.10.10.1` (expect `302`).

**QR sticker (`make_qr.py`)** — makes a printable card with two QR codes: one
**joins egorwifi** (password embedded, no typing), one **opens the controls**.
Scan to join, scan to drive. Edit the constants + re-run if the SSID/password/URL
change.

```
pip install "qrcode[pil]" && python3 utils/make_qr.py    # writes egor_qr_card.png
```

> **Captive-portal auto-open: attempted, not reliable — don't re-chase it.** The
> port-80 redirect works (`curl` returns 302), but modern iPhones/Androids bypass
> the network's DNS (Private DNS / DoH) and/or use HTTPS for their "is there
> internet?" check, so the page won't auto-pop on most phones — a phone-side
> limitation the robot can't influence. The **two-QR sticker is the intended access
> method** and works on every phone (which is why commercial gadgets do the same).

---

## Quick reference

| Task                          | Command                                             |
|-------------------------------|-----------------------------------------------------|
| List network interfaces       | `ip link show`                                      |
| Install auto-start service    | `sudo ./utils/setup_can_service.sh` (one time)      |
| Bring up motor bus (one-off)  | `sudo ip link set can0 up type can bitrate 1000000` |
| Check bus health              | `ip -details -statistics link show can0`            |
| Watch live CAN traffic        | `candump can0`                                      |
| Manually enable motor 0x7F    | `cansend can0 0300007F#0000000000000000`            |
| Manually stop motor 0x7F      | `cansend can0 0400007F#0000000000000000`            |
| Install control server (boot) | `sudo ./utils/setup_robot_service.sh` (one time)    |
| Stop control server (dev)     | `./utils/stop_robot_service.sh`                     |
| Open the control page         | `http://egor:8080/`                                 |
| Emergency stop everything     | `./utils/estop.sh`                                  |
| Install camera service (boot) | `sudo ./utils/setup_camera_service.sh` (one time)   |
| View raw camera stream        | `http://egor:8081/stream`                           |
| Enable web shutdown button    | `sudo ./utils/setup_shutdown_api.sh` (one time)     |
| Open the admin / health page  | `http://egor:8080/admin`                            |
| Diagnose a Pi that won't boot | `sudo ./utils/bootcrumbs.sh install` (read elsewhere) |
| Direct-cable SSH (no router)  | `sudo ./utils/setup_eth_direct.sh` -> `ssh u@10.0.0.1` |
| Set up egorwifi AP (portable) | `sudo ./utils/setup_ap.sh` (then reboot)            |
| Clean URL / captive attempt   | `sudo ./utils/setup_captive.sh`                     |
| Make the access QR sticker    | `python3 utils/make_qr.py`                          |
| Control page on the AP        | `http://10.10.10.1:8080`  (or `http://10.10.10.1`)  |

Motor IDs: **driver `0x7F`**, **passenger `0x7E`** (daisy-chained on `can0`).
See `CLAUDE.md` for the full protocol reference and troubleshooting playbook.
