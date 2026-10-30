"""DO! u want — public college website (multi-page). Pure st.html rendering, local image assets, CMS copy, live DB data.

Pages: home · about · academics · courses (+ ?program=CODE detail) · admissions · campus · contact
Navigation uses ?page=... query params handled by the router in app.py.
"""
from __future__ import annotations

import base64
import html as _html
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st

from database import db_manager as db

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "images"
BRAND = "DO! u want"
TAGLINE_DEFAULT = "Discover Opportunities. Unlock Your Future."
PUBLIC_PAGES = [("home", "Home"), ("about", "About Us"), ("academics", "Academics"), ("courses", "Courses"),
                ("admissions", "Admissions"), ("campus", "Campus Life"), ("contact", "Contact Us")]
ICONS = {"CSE": "💻", "ECE": "⚡", "MECH": "⚙️", "MGMT": "🏛️", "DATA": "📊", "BIO": "🧬", "PHY": "🔭", "FIN": "💹", "MKT": "📣", "DES": "🎨"}


def esc(x) -> str:
    return _html.escape(str(x if x is not None else ""))


@lru_cache(maxsize=64)
def img(name: str) -> str:
    """data: URI for a local asset; falls back to a flat colour if missing (never a broken external URL)."""
    p = ASSETS / name
    if not p.exists():
        return "data:image/svg+xml;utf8," + "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='9'><rect width='16' height='9' fill='%230B1F3A'/></svg>"
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root { --navy:#0B1F3A; --navy2:#122B4F; --ink:#0F172A; --muted:#64748B; --gold:#F5B301; --gold2:#FFD75E; --neon:#38BDF8; --white:#fff; --bg:#F6F8FC; }
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display:none !important; }
.block-container { padding:0 !important; max-width:100% !important; }
[data-testid="stAppViewContainer"] { background:var(--bg); }
html, body, .stApp, [class*="css"] { font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; color:var(--ink); }
[data-testid="stVerticalBlock"] { gap:0 !important; } .element-container { margin:0 !important; }
a { text-decoration:none; }

.topbar { background:#07152A; color:rgba(255,255,255,.75); font-size:.8rem; padding:6px 6vw; display:flex; justify-content:space-between; }
.nav { position:sticky; top:0; z-index:999; display:flex; align-items:center; justify-content:space-between; padding:12px 6vw;
  background:rgba(11,31,58,.95); backdrop-filter:blur(10px); color:var(--white); border-bottom:1px solid rgba(255,255,255,.08); }
.nav .brand { display:flex; align-items:center; gap:12px; }
.nav .brand img { width:44px; height:44px; border-radius:12px; }
.nav .brand b { display:block; font-weight:900; font-size:1.2rem; letter-spacing:-.3px; } .nav .brand small { color:rgba(255,255,255,.7); font-size:.75rem; }
.nav .links { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
.nav .links a { color:rgba(255,255,255,.85); padding:8px 12px; border-radius:8px; font-weight:500; font-size:.92rem; }
.nav .links a:hover, .nav .links a.active { background:rgba(255,255,255,.1); color:var(--gold2); }
.nav .cta { margin-left:10px; padding:10px 18px; border-radius:10px; background:linear-gradient(135deg,var(--gold),#FF9F1C); color:var(--navy) !important; font-weight:800 !important; box-shadow:0 8px 22px rgba(245,179,1,.35); }
.nav .ghost { padding:9px 16px; border-radius:10px; border:1.5px solid rgba(255,255,255,.45); color:var(--white) !important; font-weight:700 !important; margin-left:8px; }

.hero { position:relative; min-height:76vh; display:flex; align-items:center; padding:60px 6vw 90px; color:var(--white);
  background-size:cover; background-position:center; }
.hero::after { content:""; position:absolute; left:0; right:0; bottom:0; height:140px; background:linear-gradient(180deg,rgba(11,31,58,0),var(--navy)); }
.hero > * { position:relative; z-index:1; }
.eyebrow { display:inline-block; padding:6px 14px; border-radius:999px; border:1px solid rgba(255,255,255,.35); background:rgba(255,255,255,.08); font-size:.78rem; letter-spacing:2px; text-transform:uppercase; margin-bottom:20px; }
.hero h1 { font-size:clamp(2.3rem,5.2vw,4.6rem); line-height:1.03; font-weight:900; margin:0 0 18px; max-width:16ch; letter-spacing:-1.5px; }
.hero h1 em { font-style:normal; background:linear-gradient(90deg,var(--gold),var(--gold2)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { font-size:1.12rem; max-width:58ch; color:rgba(255,255,255,.85); line-height:1.6; margin:0; }
.hero .tag { margin-top:22px; display:inline-block; background:rgba(245,179,1,.14); border-left:4px solid var(--gold); padding:10px 14px; border-radius:10px; color:#FFF3C4; font-size:.92rem; max-width:62ch; }
.hero .btns { margin-top:26px; display:flex; gap:12px; flex-wrap:wrap; }
.btn { display:inline-block; padding:13px 26px; border-radius:14px; font-weight:800; }
.btn.gold { background:linear-gradient(135deg,var(--gold),#FF9F1C); color:var(--navy) !important; box-shadow:0 12px 30px rgba(245,179,1,.35); }
.btn.outline { border:1.5px solid rgba(255,255,255,.6); color:var(--white) !important; }
.btn.navy { background:var(--navy); color:var(--white) !important; }

.section { padding:80px 6vw; } .section.alt { background:var(--white); } .section.navy { background:radial-gradient(1200px 500px at 10% 0%,#1B3B6B 0%,var(--navy) 55%); color:var(--white); }
.kicker { color:var(--neon); font-weight:700; letter-spacing:3px; text-transform:uppercase; font-size:.76rem; }
.section h2 { font-size:clamp(1.9rem,3.4vw,2.8rem); font-weight:900; letter-spacing:-1px; margin:8px 0 10px; }
.section .lead { color:var(--muted); font-size:1.08rem; max-width:64ch; margin-bottom:36px; line-height:1.6; } .section.navy .lead { color:rgba(255,255,255,.75); }
.page-head { background:linear-gradient(100deg,rgba(11,31,58,.95),rgba(11,31,58,.6)), var(--img) center/cover; color:#fff; padding:90px 6vw 60px; }
.page-head h1 { font-size:clamp(2rem,4vw,3.4rem); font-weight:900; margin:0 0 8px; letter-spacing:-1px; } .page-head p { color:rgba(255,255,255,.8); max-width:60ch; margin:0; }
.crumb { color:rgba(255,255,255,.6); font-size:.85rem; margin-bottom:14px; } .crumb a { color:var(--gold2); }

.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:22px; }
.grid3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:22px; }
.card { background:var(--white); border:1px solid rgba(15,23,42,.06); border-radius:22px; overflow:hidden; box-shadow:0 10px 30px rgba(11,31,58,.08); transition:transform .2s ease,box-shadow .2s ease; display:flex; flex-direction:column; }
.card:hover { transform:translateY(-8px); box-shadow:0 24px 50px rgba(11,31,58,.16); }
.card img { width:100%; height:170px; object-fit:cover; } .card .body { padding:20px 22px 22px; flex:1; display:flex; flex-direction:column; }
.card h3 { margin:0 0 6px; font-size:1.1rem; font-weight:800; } .card p { color:var(--muted); font-size:.92rem; line-height:1.5; margin:0 0 12px; flex:1; }
.meta { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; } .tag { font-size:.72rem; font-weight:700; padding:5px 10px; border-radius:999px; background:#EEF2FF; color:#3730A3; } .tag.gold { background:#FEF3C7; color:#92400E; } .tag.green { background:#DCFCE7; color:#166534; }
.card .btn { align-self:flex-start; padding:9px 16px; font-size:.85rem; }
.feature { background:var(--white); border-radius:20px; padding:24px; border:1px solid rgba(15,23,42,.06); box-shadow:0 8px 24px rgba(11,31,58,.06); }
.feature .ic { width:48px; height:48px; border-radius:14px; display:grid; place-items:center; font-size:1.4rem; background:linear-gradient(135deg,#E0F2FE,#FEF3C7); margin-bottom:14px; }
.feature h3 { margin:0 0 6px; font-size:1.05rem; font-weight:800; } .feature p { color:var(--muted); font-size:.92rem; line-height:1.55; margin:0; }

.masonry { display:grid; grid-template-columns:2fr 1fr 1fr; grid-template-rows:240px 240px; gap:16px; }
.tile { border-radius:22px; background-size:cover; background-position:center; position:relative; overflow:hidden; box-shadow:0 16px 40px rgba(0,0,0,.25); }
.tile.big { grid-row:span 2; } .tile::after { content:""; position:absolute; inset:0; background:linear-gradient(180deg,rgba(0,0,0,0) 40%,rgba(11,31,58,.85) 100%); }
.tile span { position:absolute; left:18px; bottom:16px; z-index:2; color:var(--white); font-weight:800; font-size:1.02rem; }
.gallery { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; }
.gallery .tile { height:220px; }
.counters { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:16px; margin-top:36px; }
.counter { text-align:center; padding:24px 14px; border-radius:20px; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.14); }
.counter b { display:block; font-size:2.2rem; font-weight:900; background:linear-gradient(90deg,var(--gold2),var(--neon)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.counter small { color:rgba(255,255,255,.78); font-weight:600; letter-spacing:.5px; }
.split { display:grid; grid-template-columns:1.1fr 1fr; gap:40px; align-items:center; } .split img { width:100%; border-radius:22px; box-shadow:0 20px 50px rgba(11,31,58,.2); }
.steps { display:grid; gap:12px; } .step { display:flex; gap:14px; align-items:flex-start; background:var(--white); border-radius:16px; padding:14px 16px; box-shadow:0 8px 24px rgba(11,31,58,.07); }
.step .n { width:32px; height:32px; border-radius:10px; background:var(--navy); color:var(--gold2); font-weight:900; display:grid; place-items:center; flex:none; } .step b { display:block; } .step span { color:var(--muted); font-size:.9rem; }
.faq details { background:var(--white); border-radius:14px; padding:14px 18px; margin-bottom:10px; border:1px solid rgba(15,23,42,.06); } .faq summary { font-weight:700; cursor:pointer; } .faq p { color:var(--muted); margin:8px 0 0; }
.dates { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; } .date { background:var(--white); border-radius:16px; padding:16px; border-left:5px solid var(--gold); box-shadow:0 8px 24px rgba(11,31,58,.06); } .date b { display:block; font-size:1.05rem; } .date span { color:var(--muted); font-size:.88rem; }
.demo-banner { background:#FFF7E0; color:#6B4E00; border-top:1px solid #FDE68A; border-bottom:1px solid #FDE68A; padding:8px 6vw; font-size:.82rem; text-align:center; }
.contact-grid { display:grid; grid-template-columns:1.2fr 1fr; gap:30px; } .contact-card { background:var(--white); border-radius:20px; padding:26px; box-shadow:0 8px 24px rgba(11,31,58,.06); }
.contact-card p { margin:6px 0; color:#334155; }
.footer { background:#07152A; color:rgba(255,255,255,.8); padding:60px 6vw 28px; }
.footer .cols { display:grid; grid-template-columns:2fr 1fr 1fr 1fr 1.3fr; gap:30px; }
.footer h4 { color:var(--white); margin:0 0 12px; font-size:.95rem; letter-spacing:1px; text-transform:uppercase; }
.footer a, .footer .line { color:rgba(255,255,255,.7); display:block; margin-bottom:8px; font-size:.92rem; } .footer a:hover { color:var(--gold2); }
.footer .social a { display:inline-block; margin:0 10px 0 0; padding:8px 12px; border-radius:10px; background:rgba(255,255,255,.08); }
.footer .bottom { border-top:1px solid rgba(255,255,255,.1); margin-top:36px; padding-top:18px; display:flex; justify-content:space-between; font-size:.82rem; color:rgba(255,255,255,.5); flex-wrap:wrap; gap:10px; }
@media (max-width:900px) { .masonry { grid-template-columns:1fr 1fr; grid-template-rows:200px 200px 200px; } .tile.big { grid-column:span 2; grid-row:span 1; }
  .split, .footer .cols, .contact-grid { grid-template-columns:1fr; } .nav .links { display:none; } }
</style>
"""


# ------------------------------------------------------------------ chrome
def nav(content: dict, active: str, settings: dict) -> None:
    name = esc(content.get("institute_name", "Institute"))
    links = "".join(f'<a class="{"active" if k == active else ""}" href="?page={k}" target="_self">{t}</a>' for k, t in PUBLIC_PAGES)
    st.html(f"""
<div class="topbar"><span>Academic session {esc(settings.get('academic_session', ''))} · Admissions open</span><span>{esc(content.get('contact_info', ''))}</span></div>
<div class="nav">
  <a class="brand" href="?page=home" target="_self"><img src="{img('logo.png')}" alt="logo"><div><b style="color:#fff">{BRAND}</b><small>{name}</small></div></a>
  <div class="links">{links}<a class="ghost" href="?page=login" target="_self">Student Login</a><a class="cta" href="?page=login&intent=apply" target="_self">Apply Now</a></div>
</div>""")
    if settings.get("demo_mode", "1") == "1":
        st.html('<div class="demo-banner">Demonstration mode · applicants, statistics and photographs are synthetic sample content for evaluation purposes.</div>')


def page_head(title: str, sub: str, image: str, crumb: str) -> None:
    st.html(f"""<div class="page-head" style="--img:url('{img(image)}')"><div class="crumb"><a href="?page=home" target="_self">Home</a> › {esc(crumb)}</div>
<h1>{esc(title)}</h1><p>{esc(sub)}</p></div>""")


def footer(content: dict) -> None:
    name = esc(content.get("institute_name", "Institute"))
    contact_lines = "".join(f'<span class="line">{esc(x.strip())}</span>' for x in str(content.get("contact_info", "")).split("·") if x.strip())
    st.html(f"""
<footer class="footer" id="contact">
  <div class="cols">
    <div><img src="{img('logo.png')}" style="width:52px;border-radius:14px;margin-bottom:10px"><h4>{BRAND}</h4><p style="max-width:40ch;line-height:1.6;color:rgba(255,255,255,.65)">{name}. {esc(content.get('hero_subtitle', ''))}</p>
      <div class="social"><a href="#">Facebook</a><a href="#">Instagram</a><a href="#">LinkedIn</a><a href="#">YouTube</a></div></div>
    <div><h4>Quick links</h4><a href="?page=home" target="_self">Home</a><a href="?page=about" target="_self">About Us</a><a href="?page=campus" target="_self">Campus Life</a><a href="?page=contact" target="_self">Contact</a></div>
    <div><h4>Academics</h4><a href="?page=academics" target="_self">Schools & departments</a><a href="?page=courses" target="_self">All courses</a><a href="?page=academics" target="_self">Academic calendar</a></div>
    <div><h4>Admissions</h4><a href="?page=admissions" target="_self">How to apply</a><a href="?page=admissions" target="_self">Eligibility</a><a href="?page=admissions" target="_self">Important dates</a><a href="?page=login&intent=apply" target="_self">Apply Now</a><a href="?page=login" target="_self">Student login</a></div>
    <div><h4>Contact</h4>{contact_lines}</div>
  </div>
  <div class="bottom"><span>© 2026 {name}. All rights reserved.</span><span>Admissions powered by SEATWISEE · intelligent seat allocation</span></div>
</footer>""")


# ------------------------------------------------------------------ data helpers
def _programs(c) -> pd.DataFrame:
    return db.load_programs(c)


def _stats(c, programs: pd.DataFrame) -> dict:
    return {
        "programs": len(programs), "seats": int(programs.capacity.sum()) if len(programs) else 0,
        "departments": programs.department.replace("", pd.NA).dropna().nunique() if "department" in programs else 0,
        "applicants": c.execute("SELECT COUNT(*) FROM applicants WHERE application_status='applied'").fetchone()[0],
        "facilities": 8,  # demonstration content: campus facilities listed on Campus Life
    }


def program_card_html(r, detail_link=True) -> str:
    track = r.required_track if isinstance(r.required_track, str) and r.required_track else "Any track"
    open_tag = '<span class="tag green">Open</span>' if int(getattr(r, "is_open", 1) or 0) else '<span class="tag">Closed</span>'
    btn = f'<a class="btn navy" href="?page=courses&program={esc(r.code)}" target="_self">View Details</a>' if detail_link else ""
    return (f'<div class="card"><img src="{img(f"program_{str(r.code).lower()}.jpg")}" alt=""><div class="body">'
            f'<h3>{ICONS.get(r.code, "🎓")} {esc(r.name)}</h3><p>{esc(r.description or "")}</p>'
            f'<div class="meta"><span class="tag">{esc(r.duration or "")}</span><span class="tag gold">{int(r.capacity)} seats</span><span class="tag">{esc(track)} · score ≥ {int(r.min_score)}</span>{open_tag}</div>{btn}</div></div>')


# ------------------------------------------------------------------ pages
def page_home(c, content, settings):
    programs = _programs(c)
    stats = _stats(c, programs)
    title = esc(content.get("hero_title", ""))
    parts = title.rsplit(" ", 1)
    title_html = f"{parts[0]} <em>{parts[1]}</em>" if len(parts) == 2 else title
    ann = esc(content.get("announcements", "")).strip()
    st.html(f"""
<section class="hero" style="background-image:linear-gradient(100deg,rgba(11,31,58,.92) 0%,rgba(11,31,58,.7) 45%,rgba(11,31,58,.3) 100%),url('{img('hero.jpg')}')">
  <div><div class="eyebrow">Admissions {esc(settings.get('academic_session',''))} · Now Open</div>
    <h1>{title_html}</h1><p>{esc(content.get('hero_subtitle',''))}</p>
    {f'<div class="tag"><b>Announcement</b> · {ann}</div>' if ann else ''}
    <div class="btns"><a class="btn gold" href="?page=login&intent=apply" target="_self">Apply Now →</a><a class="btn outline" href="?page=courses" target="_self">Explore Programs</a></div>
  </div>
</section>""")
    cards = "".join(program_card_html(r) for r in programs.head(4).itertuples())
    st.html(f"""
<section class="section alt" id="about"><div class="split">
  <div><div class="kicker">About the institution</div><h2>{esc(settings.get('institute_tagline', TAGLINE_DEFAULT))}</h2>
  <p class="lead">{esc(content.get('about_us',''))}</p>
  <div class="grid"><div class="feature"><div class="ic">🎯</div><h3>Vision</h3><p>To be a learner-centred institution where every admission decision is fair, transparent and explainable.</p></div>
  <div class="feature"><div class="ic">🧭</div><h3>Mission</h3><p>Rigorous academics, hands-on labs and industry partnerships that turn curiosity into careers.</p></div></div></div>
  <img src="{img('campus.jpg')}" alt="campus"></div></section>
<section class="section"><div class="kicker">Academic programs</div><h2>Programs built for the next decade</h2>
  <p class="lead">Seats, eligibility floors and track requirements shown here are the live values the admission engine uses.</p>
  <div class="grid">{cards}</div><p style="margin-top:22px"><a class="btn navy" href="?page=courses" target="_self">See all {len(programs)} programs →</a></p></section>
<section class="section navy" id="campus"><div class="kicker">Campus life</div><h2>Where ideas get built</h2>
  <p class="lead">Modern classrooms, computing labs, a central library, sports facilities and a packed calendar of student events.</p>
  <div class="masonry">
    <div class="tile big" style="background-image:url('{img('campus.jpg')}')"><span>Main Academic Block</span></div>
    <div class="tile" style="background-image:url('{img('lab.jpg')}')"><span>Computer Laboratory</span></div>
    <div class="tile" style="background-image:url('{img('library.jpg')}')"><span>Central Library</span></div>
    <div class="tile" style="background-image:url('{img('sports.jpg')}')"><span>Sports Complex</span></div>
    <div class="tile" style="background-image:url('{img('events.jpg')}')"><span>Cultural Fest</span></div>
  </div>
  <div class="counters"><div class="counter"><b>{stats['programs']}</b><small>PROGRAMS</small></div><div class="counter"><b>{stats['seats']}</b><small>SEATS THIS YEAR</small></div>
  <div class="counter"><b>{stats['departments']}</b><small>ACADEMIC SCHOOLS</small></div><div class="counter"><b>{stats['facilities']}</b><small>CAMPUS FACILITIES</small></div><div class="counter"><b>{stats['applicants']}</b><small>APPLICATIONS RECEIVED</small></div></div>
  <p style="color:rgba(255,255,255,.5);font-size:.8rem;margin-top:10px">Programs, seats, schools and applications are live database values. Facilities count is demonstration content.</p></section>
<section class="section alt" id="why"><div class="kicker">Why choose {BRAND}</div><h2>Fair admissions you can audit</h2>
  <div class="grid3"><div class="feature"><div class="ic">⚖️</div><h3>Transparent allocation</h3><p>Every seat is assigned by a constraint-optimisation engine that respects eligibility, capacity and your ranked choices, and is independently validated.</p></div>
  <div class="feature"><div class="ic">🔄</div><h3>Automatic vacancy filling</h3><p>When a seat is released, the next qualifying applicant is identified automatically and notified.</p></div>
  <div class="feature"><div class="ic">📣</div><h3>Appeals with evidence</h3><p>Request a different program and the admissions office sees exactly who would be affected before deciding.</p></div></div></section>""")
    page_admissions_block(c, settings, compact=True)


def page_about(c, content, settings):
    page_head("About Us", content.get("about_us", ""), "campus.jpg", "About Us")
    st.html(f"""
<section class="section alt"><div class="split"><img src="{img('classroom.jpg')}" alt="">
  <div><div class="kicker">Who we are</div><h2>{esc(content.get('institute_name',''))}</h2>
  <p class="lead">{esc(content.get('about_us',''))}</p>
  <div class="grid"><div class="feature"><div class="ic">🎯</div><h3>Vision</h3><p>A learner-centred institution where admission decisions are fair, transparent and explainable.</p></div>
  <div class="feature"><div class="ic">🧭</div><h3>Mission</h3><p>Rigorous academics, hands-on laboratories and industry partnerships.</p></div>
  <div class="feature"><div class="ic">🏅</div><h3>Academic excellence</h3><p>Outcome-based curricula reviewed every year with industry and alumni input.</p></div>
  <div class="feature"><div class="ic">🌱</div><h3>Learning environment</h3><p>Small cohorts, mentoring, and a campus designed for collaboration.</p></div></div></div></div></section>
<section class="section"><div class="kicker">Why choose {BRAND}</div><h2>{esc(settings.get('institute_tagline', TAGLINE_DEFAULT))}</h2>
  <div class="grid3"><div class="feature"><div class="ic">⚖️</div><h3>Fair seat allocation</h3><p>Powered by SEATWISEE: ranked preferences, eligibility and capacity are respected for every applicant, and results are validated independently.</p></div>
  <div class="feature"><div class="ic">💼</div><h3>Career development</h3><p>A dedicated placement cell, internships from the second year and alumni mentoring.</p></div>
  <div class="feature"><div class="ic">🤝</div><h3>Inclusive community</h3><p>Students from every track and background, with support services and scholarships.</p></div></div></section>""")


def page_academics(c, content, settings):
    programs = _programs(c)
    page_head("Academics", "Schools, departments and the programs they offer.", "library.jpg", "Academics")
    depts = programs.groupby(programs.department.fillna("Academics"))
    blocks = ""
    for dept, grp in depts:
        items = "".join(f'<a href="?page=courses&program={esc(r.code)}" target="_self" class="feature" style="display:block"><h3>{ICONS.get(r.code,"🎓")} {esc(r.name)}</h3><p>{esc(r.duration or "")} · {int(r.capacity)} seats · min score {int(r.min_score)}</p></a>' for r in grp.itertuples())
        blocks += f'<section class="section {"alt" if len(blocks) % 2 else ""}"><div class="kicker">School</div><h2>{esc(dept)}</h2><div class="grid3">{items}</div></section>'
    st.html(blocks + f"""
<section class="section navy"><div class="kicker">Academic calendar</div><h2>Session {esc(settings.get('academic_session',''))}</h2>
  <div class="dates"><div class="date"><b>Applications open</b><span>Rolling, until seats are filled</span></div><div class="date"><b>Allocation rounds</b><span>Published by the admissions office</span></div>
  <div class="date"><b>Offer acceptance</b><span>Within {esc(settings.get('offer_accept_days','7'))} days of a provisional offer</span></div><div class="date"><b>Classes begin</b><span>August (demonstration date)</span></div></div></section>""")


def page_courses(c, content, settings):
    programs = _programs(c)
    code = (st.query_params.get("program") or "").upper()
    if code and (programs.code == code).any():
        r = programs[programs.code == code].iloc[0]
        track = r.required_track if isinstance(r.required_track, str) and r.required_track else "any track"
        used = db.get_current_assignment_map(c)
        allocated = sum(1 for p in used.values() if p == int(r.id))
        page_head(f"{r['name']}", r.description or "", f"program_{code.lower()}.jpg", f"Courses › {code}")
        st.html(f"""
<section class="section alt"><div class="split"><div>
  <div class="kicker">{esc(r.department or 'Academics')} · {esc(r.duration or '')}</div><h2>{ICONS.get(code,'🎓')} {esc(r['name'])}</h2>
  <p class="lead">{esc(r.description or '')}</p>
  <div class="grid"><div class="feature"><h3>Eligibility</h3><p>Entrance score of at least <b>{int(r.min_score)}</b>, open to <b>{esc(track)}</b> students. Rank it among your preferences to be considered.</p></div>
  <div class="feature"><h3>Seats</h3><p><b>{int(r.capacity)}</b> seats this session{f' · {allocated} provisionally allotted so far' if used else ''}.</p></div>
  <div class="feature"><h3>Program ID</h3><p>{esc(code)} · status: {'open for applications' if int(r.is_open or 0) else 'closed'}</p></div>
  <div class="feature"><h3>How seats are assigned</h3><p>By the SEATWISEE engine using your ranked preferences, eligibility and capacity; results are independently validated.</p></div></div>
  <p style="margin-top:22px"><a class="btn gold" href="?page=login&intent=apply" target="_self">Apply for this program →</a> <a class="btn navy" href="?page=courses" target="_self">All courses</a></p></div>
  <img src="{img(f'program_{code.lower()}.jpg')}" alt=""></div></section>""")
        return
    page_head("Courses", f"{len(programs)} programs across {programs.department.replace('', pd.NA).dropna().nunique()} schools. Seats and eligibility are live values.", "lab.jpg", "Courses")
    cards = "".join(program_card_html(r) for r in programs.itertuples())
    st.html(f'<section class="section alt"><div class="grid">{cards}</div></section>')


def page_admissions_block(c, settings, compact=False):
    programs = _programs(c)
    max_prefs = esc(settings.get("max_preferences", "5"))
    faq = "".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in [
        ("How many programs can I rank?", f"Up to {max_prefs}, in order of preference. Your first choice carries the most weight."),
        ("What documents are mandatory?", "Your 12th Board Marksheet and your CUET PG / entrance exam scorecard as PDF, PNG or JPG (max 8 MB each)."),
        ("How is my seat decided?", "The SEATWISEE engine assigns seats using your ranked preferences, each program's eligibility floor and capacity. The allocation policy in force is published to administrators and every result is independently validated."),
        ("What if I am waitlisted?", "Seats released by withdrawals are filled automatically by the next qualifying applicant. You are notified when your status changes."),
        ("Can I appeal my allocation?", "Yes. Request a different program from your portal with a reason; the admissions office evaluates the exact effect on other applicants before deciding."),
        ("Is this a real admission?", "This deployment runs in demonstration mode with synthetic applicants. Real admissions follow the institution's published policy."),
    ])
    rows = "".join(f'<div class="feature"><h3>{ICONS.get(r.code,"🎓")} {esc(r.name)}</h3><p>{esc(r.duration or "")} · {int(r.capacity)} seats · score ≥ {int(r.min_score)} · {esc(r.required_track or "any track")}</p></div>' for r in programs.itertuples())
    st.html(f"""
<section class="section" id="admissions"><div class="kicker">Admissions {esc(settings.get('academic_session',''))}</div><h2>How to apply</h2>
  <p class="lead">Four steps from account to allotment. Everything happens in your student portal.</p>
  <div class="split"><div class="steps">
    <div class="step"><div class="n">1</div><div><b>Create your account</b><span>Name, email, phone, address and a password. You receive a welcome email.</span></div></div>
    <div class="step"><div class="n">2</div><div><b>Submit your application</b><span>Entrance score, track, the college's questions, up to {max_prefs} ranked programs and your two documents. You get an Application ID.</span></div></div>
    <div class="step"><div class="n">3</div><div><b>Eligibility check and allocation</b><span>The admissions office verifies eligibility and publishes the allocation. Track every stage in your portal.</span></div></div>
    <div class="step"><div class="n">4</div><div><b>Accept your offer</b><span>Provisional offers are accepted from the portal within {esc(settings.get('offer_accept_days','7'))} days; your allotment letter is downloadable.</span></div></div>
  </div><div><img src="{img('placement.jpg')}" alt="" style="width:100%;border-radius:22px"></div></div>
  <div style="margin-top:26px"><a class="btn gold" href="?page=login&intent=apply" target="_self">Apply Now →</a></div></section>
{'' if compact else f'''<section class="section alt"><div class="kicker">Important dates</div><h2>Key dates</h2>
  <div class="dates"><div class="date"><b>Applications open</b><span>Now · rolling</span></div><div class="date"><b>Document verification</b><span>Continuous</span></div><div class="date"><b>Allocation rounds</b><span>Published by the admissions office</span></div><div class="date"><b>Offer acceptance</b><span>{esc(settings.get('offer_accept_days','7'))} days from offer</span></div></div>
  <p class="lead" style="margin-top:14px;font-size:.9rem">Dates are demonstration placeholders; the admissions office sets the real schedule in Announcements.</p></section>
<section class="section"><div class="kicker">Eligibility & available programs</div><h2>Programs open this session</h2><div class="grid3">{rows}</div></section>
<section class="section alt faq"><div class="kicker">FAQ</div><h2>Frequently asked questions</h2>{faq}</section>'''}""")


def page_admissions(c, content, settings):
    page_head("Admissions", "Procedure, eligibility, important dates and answers to common questions.", "placement.jpg", "Admissions")
    page_admissions_block(c, settings, compact=False)


def page_campus(c, content, settings):
    page_head("Campus Life", "Classrooms, laboratories, library, sports, activities and placements.", "sports.jpg", "Campus Life")
    tiles = "".join(f'<div class="tile" style="background-image:url(\'{img(f)}\')"><span>{t}</span></div>' for f, t in [
        ("campus.jpg", "College campus"), ("classroom.jpg", "Smart classrooms"), ("lab.jpg", "Computer laboratories"), ("library.jpg", "Central library"),
        ("sports.jpg", "Sports facilities"), ("activities.jpg", "Student activities"), ("events.jpg", "Events & cultural programs"), ("placement.jpg", "Placement & career development"), ("hostel.jpg", "Residences")])
    st.html(f"""<section class="section alt"><div class="gallery">{tiles}</div>
<p class="lead" style="margin-top:18px;font-size:.88rem">Images are locally generated demonstration scenes; replace the files in assets/images with campus photographs to update the site.</p></section>
<section class="section"><div class="grid3">
  <div class="feature"><div class="ic">🏫</div><h3>Classrooms & labs</h3><p>Smart classrooms, computing labs with GPU workstations, electronics and mechanical workshops.</p></div>
  <div class="feature"><div class="ic">📚</div><h3>Library</h3><p>Print and digital collections, quiet study zones and group rooms, open late during examinations.</p></div>
  <div class="feature"><div class="ic">🏅</div><h3>Sports & activities</h3><p>Courts, grounds and a fitness centre; clubs for coding, robotics, drama, music and debate.</p></div>
  <div class="feature"><div class="ic">🎭</div><h3>Events</h3><p>An annual tech fest, cultural fest and hackathons run by students.</p></div>
  <div class="feature"><div class="ic">💼</div><h3>Placements</h3><p>A placement cell that prepares students with mock interviews, resume clinics and recruiter drives.</p></div>
  <div class="feature"><div class="ic">🏠</div><h3>Residences</h3><p>On-campus hostels with dining, Wi-Fi and 24×7 support.</p></div></div></section>""")


def page_contact(c, content, settings):
    page_head("Contact Us", "We are happy to help with admissions and campus queries.", "hero.jpg", "Contact Us")
    lines = "".join(f"<p>{esc(x.strip())}</p>" for x in str(content.get("contact_info", "")).split("·") if x.strip())
    st.html(f"""<section class="section alt"><div class="contact-grid">
  <div class="contact-card"><div class="kicker">Admissions office</div><h2 style="margin-top:6px">{esc(content.get('institute_name',''))}</h2>{lines}
    <p style="margin-top:14px"><a class="btn gold" href="?page=login&intent=apply" target="_self">Apply Now →</a> <a class="btn navy" href="?page=login" target="_self">Student login</a></p></div>
  <div class="contact-card"><div class="kicker">Visit us</div><h3>Campus location</h3><p>Knowledge Park III, Greater Noida, Uttar Pradesh 201310 (demonstration address)</p>
    <img src="{img('campus.jpg')}" alt="" style="width:100%;border-radius:16px;margin-top:10px"></div></div></section>""")


PAGES = {"home": page_home, "about": page_about, "academics": page_academics, "courses": page_courses,
         "admissions": page_admissions, "campus": page_campus, "contact": page_contact}


def render(c, page: str = "home") -> None:
    content = db.get_site_content(c)
    settings = db.get_settings(c)
    st.html(CSS)
    nav(content, page if page in PAGES else "home", settings)
    PAGES.get(page, page_home)(c, content, settings)
    footer(content)
