#!/usr/bin/env python3
"""
make_qr.py - generate egorwifi access QR codes + a printable card.
Two QRs so the user types nothing: one JOINS the Wi-Fi, one OPENS the controls.
Edit the constants and re-run if the SSID / password / URL change.
Needs: pip install "qrcode[pil]"   (run on any machine with Python + Pillow)
"""
import os, qrcode
from PIL import Image, ImageDraw, ImageFont

SSID = "egorwifi"
PASS = "password"
AUTH = "WPA"                       # WPA covers WPA2
URL  = "http://10.10.10.1:8080"    # control page (known-good, no captive needed)
OUT  = os.environ.get("QR_OUT", ".")

def wifi_payload(ssid, pw, auth):
    esc = lambda s: s.replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace(":","\\:")
    return f"WIFI:T:{auth};S:{esc(ssid)};P:{esc(pw)};;"

def make_qr(data):
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    q.add_data(data); q.make(fit=True)
    return q.make_image(fill_color="black", back_color="white").convert("RGB")

wifi_img = make_qr(wifi_payload(SSID, PASS, AUTH))
url_img  = make_qr(URL)
wifi_img.save(os.path.join(OUT, "qr_wifi.png"))
url_img.save(os.path.join(OUT, "qr_url.png"))

def font(sz, bold=False):
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")
    return ImageFont.truetype(p, sz) if os.path.exists(p) else ImageFont.load_default()

W, H = 900, 1180
card = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(card)
def ctext(y, s, f, fill="black"):
    w = d.textbbox((0,0), s, font=f)[2]
    d.text(((W - w)//2, y), s, font=f, fill=fill)

ctext(36, "EGOR ROBOT", font(64, True))
ctext(120, "Scan to drive  —  no typing needed", font(30), fill="#555555")

qsz, y0 = 340, 190
card.paste(wifi_img.resize((qsz, qsz)), ((W - qsz)//2, y0))
ctext(y0 + qsz + 8,  "STEP 1 — Scan to join the Wi-Fi", font(34, True))
ctext(y0 + qsz + 52, "(network “egorwifi”)", font(26), fill="#555555")

y1 = y0 + qsz + 120
card.paste(url_img.resize((qsz, qsz)), ((W - qsz)//2, y1))
ctext(y1 + qsz + 8, "STEP 2 — Scan to open the controls", font(34, True))

fy = y1 + qsz + 70
d.line((70, fy, W - 70, fy), fill="#cccccc", width=2)
ctext(fy + 18, "Manual: join Wi-Fi “egorwifi” (password: password),", font(23), fill="#555555")
ctext(fy + 50, "then open  http://10.10.10.1:8080", font(23), fill="#555555")

card.save(os.path.join(OUT, "egor_qr_card.png"))
print("wrote qr_wifi.png, qr_url.png, egor_qr_card.png to", OUT)
