"""Generate licensed-free demonstration imagery locally (no external URLs). Run: python -m assets.generate_images
Produces stylised campus scenes as JPEGs in assets/images/. Replace with real photographs any time; same filenames."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent / "images"

SCENES = {
    # key: (title, sky top, sky bottom, ground, accent)
    "hero":      ("Main Campus", (12, 32, 64), (64, 120, 190), (34, 92, 60), (245, 179, 1)),
    "campus":    ("Academic Block", (18, 40, 80), (120, 170, 220), (52, 110, 70), (245, 179, 1)),
    "classroom": ("Smart Classroom", (40, 50, 70), (180, 190, 210), (90, 80, 70), (56, 189, 248)),
    "lab":       ("Computer Laboratory", (20, 30, 50), (70, 90, 130), (50, 55, 70), (56, 189, 248)),
    "library":   ("Central Library", (60, 40, 30), (190, 150, 110), (120, 80, 50), (245, 179, 1)),
    "sports":    ("Sports Complex", (30, 80, 140), (150, 200, 240), (60, 140, 60), (255, 255, 255)),
    "activities":("Student Activities", (90, 30, 90), (220, 120, 160), (70, 60, 90), (255, 215, 94)),
    "events":    ("Cultural Fest", (20, 10, 40), (120, 60, 140), (40, 30, 60), (255, 215, 94)),
    "placement": ("Placement Cell", (16, 40, 70), (100, 140, 190), (70, 75, 85), (56, 189, 248)),
    "hostel":    ("Residences", (30, 60, 110), (170, 200, 230), (80, 120, 70), (245, 179, 1)),
}
PROGRAMS = {
    "cse": ("Computer Science & AI", (10, 30, 70), (40, 110, 200)), "ece": ("Electronics", (20, 50, 60), (60, 160, 160)),
    "mech": ("Mechanical", (50, 40, 30), (170, 120, 80)), "data": ("Data Science", (30, 20, 70), (120, 80, 220)),
    "bio": ("Biotechnology", (10, 60, 40), (60, 170, 110)), "phy": ("Applied Physics", (20, 20, 60), (90, 90, 200)),
    "fin": ("Finance", (10, 40, 50), (40, 140, 150)), "mkt": ("Marketing", (90, 30, 40), (230, 100, 90)),
    "des": ("Design", (80, 30, 90), (240, 120, 200)), "mgmt": ("Management", (40, 40, 60), (140, 140, 190)),
}


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        c = _lerp(top, bottom, y / max(1, h - 1))
        for x in range(w):
            px[x, y] = c
    return img


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def scene(key, title, top, bottom, ground, accent, w=1600, h=900, seed=1):
    rng = random.Random(seed)
    img = _gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img)
    # sun / glow
    d.ellipse((w * 0.72, h * 0.08, w * 0.72 + 140, h * 0.08 + 140), fill=_lerp(accent, (255, 255, 255), 0.4))
    # distant hills
    for i in range(3):
        pts = [(0, h)] + [(x, h * (0.55 + 0.08 * i) - 40 * math.sin(x / 140 + i)) for x in range(0, w + 1, 40)] + [(w, h)]
        d.polygon(pts, fill=_lerp(ground, bottom, 0.25 + 0.2 * i))
    # buildings silhouette
    x = 40
    while x < w - 60:
        bw = rng.randint(90, 220); bh = rng.randint(int(h * 0.18), int(h * 0.42))
        col = _lerp(top, (255, 255, 255), rng.uniform(0.08, 0.3))
        d.rectangle((x, h * 0.72 - bh, x + bw, h * 0.72), fill=col)
        for wy in range(int(h * 0.72 - bh) + 18, int(h * 0.72) - 12, 26):
            for wx in range(x + 12, x + bw - 12, 24):
                if rng.random() < 0.6:
                    d.rectangle((wx, wy, wx + 12, wy + 14), fill=_lerp(accent, (255, 255, 255), 0.35))
        x += bw + rng.randint(20, 70)
    # ground + path
    d.rectangle((0, h * 0.72, w, h), fill=ground)
    d.polygon([(w * 0.42, h * 0.72), (w * 0.58, h * 0.72), (w * 0.8, h), (w * 0.2, h)], fill=_lerp(ground, (255, 255, 255), 0.35))
    # trees
    for i in range(14):
        tx = rng.randint(0, w); ty = rng.randint(int(h * 0.74), int(h * 0.95)); r = rng.randint(18, 40)
        d.rectangle((tx - 4, ty, tx + 4, ty + r), fill=(70, 45, 30))
        d.ellipse((tx - r, ty - r, tx + r, ty + r), fill=_lerp(ground, (20, 60, 20), rng.uniform(0.2, 0.7)))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    d = ImageDraw.Draw(img)
    d.rectangle((0, h - 120, w, h), fill=(0, 0, 0))
    d.text((40, h - 95), title, font=_font(54), fill=(255, 255, 255))
    d.text((40, h - 38), "Demonstration image · generated locally · replace with campus photographs", font=_font(20), fill=(200, 200, 200))
    return img


def program_card(key, title, top, bottom, w=900, h=560):
    img = _gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img)
    rng = random.Random(key)
    for i in range(18):
        x, y, r = rng.randint(0, w), rng.randint(0, h), rng.randint(20, 120)
        d.ellipse((x - r, y - r, x + r, y + r), outline=_lerp(bottom, (255, 255, 255), 0.5), width=2)
    d.text((40, h - 110), title, font=_font(46), fill=(255, 255, 255))
    d.text((40, h - 52), "Demonstration image", font=_font(20), fill=(220, 220, 220))
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (k, (title, top, bottom, ground, accent)) in enumerate(SCENES.items()):
        scene(k, title, top, bottom, ground, accent, seed=i + 1).save(OUT / f"{k}.jpg", quality=82, optimize=True)
    for k, (title, top, bottom) in PROGRAMS.items():
        program_card(k, title, top, bottom).save(OUT / f"program_{k}.jpg", quality=82, optimize=True)
    # logo
    logo = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.rounded_rectangle((8, 8, 248, 248), radius=56, fill=(11, 31, 58))
    d.rounded_rectangle((40, 40, 216, 216), radius=40, fill=(245, 179, 1))
    d.text((78, 70), "D!", font=_font(96), fill=(11, 31, 58))
    logo.save(OUT / "logo.png")
    print("generated", len(list(OUT.glob("*"))), "files in", OUT)


if __name__ == "__main__":
    main()
