"""Central photo-slot registry for the public website.

HOW TO ADD REAL PHOTOGRAPHS LATER
---------------------------------
Drop a file named after the slot into  static/images/photos/  (jpg, jpeg, png or webp), e.g.

    static/images/photos/hero.jpg
    static/images/photos/venue.jpg
    static/images/photos/gallery_1.jpg

No page code needs to change: every slot that has a file shows the photograph, every slot
without one shows an elegant, clearly marked placeholder. To map a slot to a differently named
file, add an entry to OVERRIDES below, e.g.  OVERRIDES["hero"] = "main-building-2026.jpg".
"""
from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHOTO_DIR = ROOT / "static" / "images" / "photos"
LOGO_URL = "app/static/images/logo.png"
_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# slot -> human label shown inside the placeholder (and in the admin instructions)
SLOTS = {
    "hero": "Homepage hero · main campus photograph",
    "about": "About section · campus or classroom photograph",
    "venue": "Competition venue · R.D. Engineering College, Ghaziabad",
    "gallery_1": "Campus gallery 1 · academic block",
    "gallery_2": "Campus gallery 2 · laboratories",
    "gallery_3": "Campus gallery 3 · library",
    "gallery_4": "Campus gallery 4 · sports",
    "gallery_5": "Campus gallery 5 · events and culture",
    "gallery_6": "Campus gallery 6 · student life",
    "facility_classrooms": "Facility · classrooms",
    "facility_labs": "Facility · laboratories",
    "facility_library": "Facility · library",
    "facility_sports": "Facility · sports",
    "facility_events": "Facility · events and auditorium",
    "facility_hostel": "Facility · residences",
    "head_about": "About page header",
    "head_academics": "Academics page header",
    "head_courses": "Courses page header",
    "head_admissions": "Admissions page header",
    "head_campus": "Campus Life page header",
    "head_contact": "Contact page header",
    "admissions": "Admissions section · students on campus",
}
OVERRIDES: dict[str, str] = {}


def photo(slot: str) -> str | None:
    """URL of the photograph for a slot, or None when no file has been added yet."""
    if slot in OVERRIDES:
        p = PHOTO_DIR / OVERRIDES[slot]
        return f"app/static/images/photos/{p.name}" if p.exists() else None
    for ext in _EXTS:
        p = PHOTO_DIR / f"{slot}{ext}"
        if p.exists():
            return f"app/static/images/photos/{p.name}"
    return None


def program_photo(code: str) -> str | None:
    return photo(f"program_{code.lower()}")


def placeholder(slot: str, label: str | None = None, icon: str = "photo_camera", cls: str = "") -> str:
    """Elegant placeholder block. Replace by adding static/images/photos/<slot>.jpg."""
    text = html.escape(label or SLOTS.get(slot, slot).split(" · ")[-1].capitalize())
    return (f"<div class='ph {cls}' data-slot='{html.escape(slot)}'><div class='ph-frame'><span class='msr'>{icon}</span><b>{text}</b>"
            f"<small>Photograph placeholder · add <code>static/images/photos/{html.escape(slot)}.jpg</code></small></div></div>")


def figure(slot: str, label: str | None = None, icon: str = "photo_camera", cls: str = "", alt: str = "") -> str:
    """<img> when the photo exists, otherwise the placeholder. Same box either way, so layouts never change."""
    url = photo(slot)
    if url:
        return f"<div class='ph has-photo {cls}' data-slot='{html.escape(slot)}'><img src='{url}' alt='{html.escape(alt or label or slot)}'></div>"
    return placeholder(slot, label, icon, cls)


def background(slot: str) -> str:
    """CSS background-image value for hero/page headers: the photo, or a branded gradient placeholder."""
    url = photo(slot)
    if url:
        return f"linear-gradient(100deg,rgba(11,31,58,.92) 0%,rgba(11,31,58,.55) 50%,rgba(109,40,217,.35) 100%),url('{url}')"
    return "radial-gradient(900px 500px at 85% 20%,rgba(139,92,246,.45),transparent 60%),radial-gradient(700px 400px at 10% 90%,rgba(245,179,1,.18),transparent 60%),linear-gradient(120deg,#0B1F3A 0%,#122B4F 55%,#3B1F8A 100%)"
