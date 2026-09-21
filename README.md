# EgorRobot

Reviving and running a Raspberry Pi 5 robot chassis: two Xiaomi CyberGear motors on
a Waveshare 2-CH CAN HAT, driven from a phone-friendly web page with live webcam
video, a rear/front-wheel drive toggle, a sleep/wake motor toggle, portable Wi-Fi
access, and an admin/health page.

## 📖 Everything lives in [`CLAUDE.md`](CLAUDE.md)

To keep one document to maintain, **`CLAUDE.md` is the single source of truth** — it
holds the feature overview, a Quickstart, the full step-by-step setup guide, the web/
camera/access details, the CyberGear protocol reference, wiring gotchas, the
diagnostic playbook, and a command quick-reference.

Where to start in it:

- **Already comfortable with Pi + CAN motor projects?** Jump to **Quickstart** —
  the whole bring-up in five short steps.
- **New to the project (or this kind of build)?** Read it top to bottom; **Features
  at a glance** is right up front, then **First-time setup (full bring-up)**.

## Quick facts

- **Pi:** Raspberry Pi 5, `ssh u@egor`. Repo at `~/gitprojects/egorrobot`.
- **Motors:** two CyberGear on **`can0`** — driver `0x7F`, passenger `0x7E`.
  (Gotcha: the hat header silk-screened **"CAN1" is Linux `can0`**.)
- **Drive it:** `http://egor:8080/`, or `http://10.10.10.1:8080` on the robot's own
  `egorwifi` access point (pw `password`).

See **[`CLAUDE.md`](CLAUDE.md)** for all details.
