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
FRAMES = [  # (screenshot suffix, chapter, title, subtitle)
    ("04bhr6", "YOUR SHOP", "Set up your own shop", "name, area, speaking language; ledger starts empty"),
    ("3ws1we", "YOUR SHOP", "Add a customer", "bhai / ben helps voice matching and polite reminders"),
    ("x8tta8", "YOUR SHOP", "Add your own product + local names", "Hindi · Gujarati · Marathi names → alias_of facts"),
    ("ecz16x", "YOUR SHOP", "Teach a new local name", "“bhaat” → Rice (Kolam): the parser learns instantly"),
    ("ho1xf5", "YOUR SHOP", "Speak it in Gujarati", "“Kiranben nu 1 dozen keri ane 2 kilo bhaat lakhi do”"),
    ("hpn0fu", "YOUR SHOP", "Understood and saved, zero taps", "new customer + new product + new name · ₹1,020 · undo"),
    ("xyb5mp", "YOUR SHOP", "Your own knowledge graph", "Kiran → owes → shop · bought → Hapus Mango, Rice"),
    ("bl9ac6", "DEMO DATA · 6 MONTHS", "Two customers called Ramesh?", "it asks instead of guessing"),
    ("yx2jsd", "DEMO DATA · 6 MONTHS", "“Why?” shows every deduction", "explainable demo heuristic, not a credit score"),
    ("1cup6l", "DEMO DATA · 6 MONTHS", "Polite reminder in Gujarati", "draft only: nothing is ever auto-sent"),
    ("vaykef", "DEMO DATA · 6 MONTHS", "Seasonal patterns", "Diwali and wedding-season credit spikes"),
    ("y7yr13", "DEMO DATA · 6 MONTHS", "Who owes what, as a graph", "size = balance · colour = payment pattern"),
    ("x2teun", "YOUR SHOP", "Export your graph", "Turtle · JSON-LD · JSON, with provenance for every fact"),
]
W, H, BAND = 390, 844, 92
FONT, FONT_BOLD = r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"  # any TTF works
step_font = ImageFont.truetype(FONT_BOLD, 13)

frames = []
def fit(d: ImageDraw.ImageDraw, text: str, path: str, size: int) -> ImageFont.FreeTypeFont:
    """Shrink the font until the caption fits the frame width."""
    font = ImageFont.truetype(path, size)
    while d.textlength(text, font=font) > W - 32 and size > 10:
        size -= 1
        font = ImageFont.truetype(path, size)
    return font


for n, (key, chapter, title, sub) in enumerate(FRAMES, 1):
    path = glob.glob(str(Path(SRC) / f"*{key}.jpg"))[0]
    shot = Image.open(path).convert("RGB")
    shot = shot.resize((W, round(shot.height * W / shot.width)), Image.LANCZOS).crop((0, 0, W, H))
    canvas = Image.new("RGB", (W, H + BAND), "#1c1917")
    canvas.paste(shot, (0, BAND))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, W, 4), fill="#b45309")
    d.rectangle((0, 4, round(W * n / len(FRAMES)), 8), fill="#fbbf24")  # progress bar
    d.text((16, 18), f"{n}/{len(FRAMES)} · {chapter}", font=step_font, fill="#fbbf24")
    d.text((16, 34), title, font=fit(d, title, FONT_BOLD, 19), fill="#fffaf3")
    d.text((16, 62), sub, font=fit(d, sub, FONT, 14), fill="#d6d3d1")
    frames.append(canvas)

pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
durations = [2600] * len(pal)
durations[0], durations[-1] = 2400, 3600
pal[0].save(OUT, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)
print(OUT, len(pal), "frames")
