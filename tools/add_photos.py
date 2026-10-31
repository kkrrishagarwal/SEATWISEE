"""Copy real photographs into the public-website photo slots (resized for the web).

Usage:
    .venv/bin/python tools/add_photos.py hero=/path/to/campus.jpg venue="/path/to/rd college.jpeg" gallery_1=~/Pictures/block.png
    .venv/bin/python tools/add_photos.py --list          # show every slot and whether it is filled

Each argument is  <slot>=<source file>.  The image is auto-rotated (EXIF), converted to JPEG, resized to at most
1920 px wide and saved as static/images/photos/<slot>.jpg, which the website picks up immediately (no code change).
Slot names: see ui/public/images.py (hero, about, venue, gallery_1..6, facility_*, head_*, admissions, program_<code>).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.public import images as im  # noqa: E402

MAX_W = 1600


def add(slot: str, src: Path) -> Path:
    src = src.expanduser()
    if not src.exists():
        raise SystemExit(f"{src} does not exist")
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if img.width > MAX_W:
        img = img.resize((MAX_W, round(img.height * MAX_W / img.width)), Image.LANCZOS)
    im.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    for old in im.PHOTO_DIR.glob(f"{slot}.*"):
        old.unlink()
    out = im.PHOTO_DIR / f"{slot}.jpg"
    img.save(out, "JPEG", quality=80, optimize=True)
    return out


def main(argv: list[str]) -> None:
    if not argv or argv == ["--list"]:
        for slot, label in im.SLOTS.items():
            print(f"{'FILLED ' if im.photo(slot) else 'empty  '} {slot:<22} {label}")
        if not argv:
            print("\nUsage: tools/add_photos.py <slot>=<file> [...]")
        return
    for arg in argv:
        if "=" not in arg:
            raise SystemExit(f"expected slot=file, got {arg}")
        slot, src = arg.split("=", 1)
        if slot not in im.SLOTS and not slot.startswith("program_"):
            raise SystemExit(f"unknown slot {slot}; run with --list")
        out = add(slot, Path(src))
        print(f"{slot}: saved {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1:])
