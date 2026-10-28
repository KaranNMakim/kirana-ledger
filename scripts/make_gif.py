"""Stitch phone-size app screenshots into a captioned walkthrough GIF.

    py scripts/make_gif.py <screenshots_dir> docs/demo.gif

Screenshots are matched by filename suffix (the keys in FRAMES), captured at 390x844 from `make demo`.
Needs Pillow (not a project dependency); fonts default to Windows Segoe UI, any TTF works.
"""
import glob
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC, OUT = sys.argv[1], sys.argv[2]
FRAMES = [
    ("zsly89", "Speak or type an udhaar entry", "Hinglish · Hindi · Gujarati, voice or text"),
    ("y9n9sv", "“Ramesh bhai ko 2 kilo chawal udhaar”", "2 kg rice on credit for Ramesh"),
    ("bl9ac6", "Two customers called Ramesh", "so the app asks instead of guessing"),
    ("hfb3iq", "One tap picks the right person", "items and price already understood"),
    ("q5fdce", "Saved, priced from the catalogue", "provenance: confirmed by you · one-tap undo"),
    ("5f9suh", "Customers: balance + payment pattern", "sorted by who owes most"),
    ("214bkj", "A late payer's profile", "avg days to pay, oldest unpaid, partial pays"),
    ("yx2jsd", "“Why?” shows every deduction", "explainable demo heuristic, not a credit score"),
    ("8zebkf", "Polite reminder draft in Hinglish", "balance, since-when, thanks for last payment"),
    ("1cup6l", "…or in Gujarati", "draft only: nothing is ever auto-sent"),
    ("j2his9", "Insights: who owes most, who pays late", "graph queries over owes / paid edges"),
    ("vaykef", "Seasonal patterns", "Diwali and wedding-season credit spikes"),
    ("y7yr13", "The udhaar knowledge graph", "customer → owes → shop · bought → product"),
]
W, H, BAND = 390, 844, 92
title_font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 19)
sub_font = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 14)
step_font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 13)

frames = []
for n, (key, title, sub) in enumerate(FRAMES, 1):
    path = glob.glob(str(Path(SRC) / f"*{key}.jpg"))[0]
    shot = Image.open(path).convert("RGB")
    shot = shot.resize((W, round(shot.height * W / shot.width)), Image.LANCZOS).crop((0, 0, W, H))
    canvas = Image.new("RGB", (W, H + BAND), "#1c1917")
    canvas.paste(shot, (0, BAND))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, W, 4), fill="#b45309")
    d.rectangle((0, 4, round(W * n / len(FRAMES)), 8), fill="#fbbf24")  # progress bar
    d.text((16, 18), f"{n}/{len(FRAMES)}", font=step_font, fill="#fbbf24")
    d.text((16, 34), title, font=title_font, fill="#fffaf3")
    d.text((16, 62), sub, font=sub_font, fill="#d6d3d1")
    frames.append(canvas)

pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
durations = [2600] * len(pal)
durations[0], durations[-1] = 2400, 3600
pal[0].save(OUT, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)
print(OUT, len(pal), "frames")
