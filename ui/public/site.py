"""DO! u want — public university website (7 pages) for SEATWISEE.

Pages: home · about · academics · courses (+ ?program=CODE detail) · admissions · campus · contact
Navigation uses ?page=... query params handled by the router in app.py. Pure st.html rendering,
CMS copy from site_content, policy values from settings, programs/applications live from the DB.
Photographs come from ui/public/images.py slots (placeholders until real photos are added).
"""
from __future__ import annotations

import html as _html
import re

import pandas as pd
import streamlit as st

from database import db_manager as db
from ui.public import images as im

BRAND = "DO! u want"
SYSTEM = "SEATWISEE"
TAGLINE_DEFAULT = "Discover Opportunities. Unlock Your Future."
SUPPORT_LINE = "Smart admissions. Clear decisions. Better futures."
VENUE_NAME = "R.D. Engineering College, Ghaziabad"
VENUE_CITY = "Ghaziabad, Uttar Pradesh, India"
VENUE_EVENT = "Achithon 2026"
VENUE_MAP = "https://www.google.com/maps/search/?api=1&query=R.D.+Engineering+College+Ghaziabad"
PUBLIC_PAGES = [("home", "Home"), ("about", "About"), ("academics", "Academics"), ("courses", "Courses"),
                ("admissions", "Admissions"), ("campus", "Campus Life"), ("contact", "Contact Us")]
ICONS = {"CSE": "memory", "ECE": "bolt", "MECH": "settings", "MGMT": "account_balance", "DATA": "monitoring", "BIO": "biotech",
         "PHY": "science", "FIN": "payments", "MKT": "campaign", "DES": "palette"}


def esc(x) -> str:
    return _html.escape(str(x if x is not None else ""))


def ic(name: str) -> str:
    return f"<span class='msr'>{name}</span>"


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root { --navy:#0B1F3A; --navy2:#122B4F; --purple:#6D28D9; --violet:#8B5CF6; --gold:#F5B301; --gold2:#FFD75E; --lav:#EDE9FE;
        --bg:#F8FAFC; --white:#fff; --ink:#0F172A; --muted:#64748B; --border:#E5E7EB; }
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display:none !important; }
.block-container { padding:0 !important; max-width:100% !important; }
[data-testid="stAppViewContainer"], .stApp { background:var(--bg); }
.stApp, .stApp *:not([data-testid="stIconMaterial"]):not([role="img"]):not(.msr):not(code):not(pre) { font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; }
.stApp { color:var(--ink); }
[data-testid="stVerticalBlock"] { gap:0 !important; } .element-container { margin:0 !important; }
a { text-decoration:none; }
.msr { font-family:'Material Symbols Rounded' !important; font-weight:400; font-style:normal; font-size:24px; line-height:1; display:inline-block; vertical-align:middle; text-transform:none; letter-spacing:0; font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24; }
code { font-size:.78em; background:rgba(255,255,255,.12); padding:1px 6px; border-radius:6px; }

/* ---------- top bar + navigation ---------- */
.topbar { background:#07152A; color:rgba(255,255,255,.72); font-size:.78rem; padding:7px 6vw; display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.topbar .msr { font-size:16px; color:var(--gold2); }
.nav { position:sticky; top:0; z-index:999; display:flex; align-items:center; justify-content:space-between; padding:12px 6vw;
  background:rgba(11,31,58,.94); backdrop-filter:blur(12px); color:var(--white); border-bottom:1px solid rgba(255,255,255,.08); }
.nav .brand { display:flex; align-items:center; gap:12px; }
.nav .brand img { width:44px; height:44px; border-radius:12px; box-shadow:0 6px 18px rgba(245,179,1,.3); }
.nav .brand b { display:block; font-weight:900; font-size:1.2rem; letter-spacing:-.3px; color:#fff; } .nav .brand small { color:rgba(255,255,255,.7); font-size:.74rem; }
.nav .links { display:flex; align-items:center; gap:2px; }
.nav .links a { color:rgba(255,255,255,.85); padding:9px 13px; border-radius:10px; font-weight:600; font-size:.9rem; transition:background .15s,color .15s; }
.nav .links a:hover { background:rgba(255,255,255,.1); color:#fff; } .nav .links a.active { background:rgba(139,92,246,.28); color:#fff; }
.nav .ghost { padding:9px 16px; border-radius:10px; border:1.5px solid rgba(255,255,255,.45); color:#fff !important; font-weight:700 !important; margin-left:10px; }
.nav .cta { margin-left:8px; padding:10px 18px; border-radius:10px; background:linear-gradient(135deg,var(--gold),#FF9F1C); color:var(--navy) !important; font-weight:800 !important; box-shadow:0 8px 22px rgba(245,179,1,.35); }
.nav .navtoggle { display:none; } .nav .burger { display:none; width:44px; height:44px; border-radius:12px; background:rgba(255,255,255,.1); cursor:pointer; place-items:center; color:#fff; }
.demo-banner { background:#FFF7E0; color:#6B4E00; border-bottom:1px solid #FDE68A; padding:8px 6vw; font-size:.8rem; text-align:center; }

/* ---------- hero + page headers ---------- */
.hero { position:relative; min-height:min(82vh,780px); display:flex; align-items:center; padding:70px 6vw 120px; color:#fff; background-size:cover; background-position:center; overflow:hidden; }
.hero::before { content:""; position:absolute; inset:0; background-image:linear-gradient(rgba(255,255,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px); background-size:32px 32px; }
.hero.no-photo .mark { position:absolute; right:6vw; bottom:90px; z-index:1; display:inline-flex; align-items:center; gap:8px; border:1.5px dashed rgba(255,255,255,.45); border-radius:999px; padding:8px 14px; font-size:.74rem; color:rgba(255,255,255,.75); } .hero .mark .msr { font-size:18px; color:var(--gold2); }
.hero .orb { position:absolute; width:520px; height:520px; border-radius:50%; background:radial-gradient(circle,rgba(139,92,246,.35),transparent 65%); right:-120px; top:-140px; }
.hero > div { position:relative; z-index:1; max-width:760px; }
.eyebrow { display:inline-flex; align-items:center; gap:8px; padding:7px 14px; border-radius:999px; border:1px solid rgba(255,255,255,.3); background:rgba(255,255,255,.08); font-size:.76rem; letter-spacing:2px; text-transform:uppercase; margin-bottom:22px; font-weight:700; }
.eyebrow .msr { font-size:18px; color:var(--gold2); }
.hero h1 { font-size:clamp(2.4rem,5.4vw,4.8rem); line-height:1.02; font-weight:900; margin:0 0 16px; letter-spacing:-2px; max-width:15ch; color:#fff; }
.hero h1 em { font-style:normal; background:linear-gradient(90deg,var(--gold),var(--gold2)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero .support { font-size:1.35rem; font-weight:700; color:#DDD6FE; margin:0 0 14px; letter-spacing:-.3px; }
.hero p.lead { font-size:1.08rem; max-width:58ch; color:rgba(255,255,255,.82); line-height:1.65; margin:0; }
.hero .btns { margin-top:30px; display:flex; gap:12px; flex-wrap:wrap; }
.btn { display:inline-flex; align-items:center; gap:8px; padding:13px 26px; border-radius:14px; font-weight:800; transition:transform .15s,box-shadow .15s; }
.btn:hover { transform:translateY(-2px); } .btn .msr { font-size:20px; }
.btn.gold { background:linear-gradient(135deg,var(--gold),#FF9F1C); color:var(--navy) !important; box-shadow:0 12px 30px rgba(245,179,1,.35); }
.btn.outline { border:1.5px solid rgba(255,255,255,.6); color:#fff !important; } .btn.navy { background:var(--navy); color:#fff !important; } .btn.purple { background:linear-gradient(135deg,var(--purple),var(--violet)); color:#fff !important; box-shadow:0 10px 26px rgba(109,40,217,.3); }
.btn.sm { padding:9px 16px; font-size:.85rem; border-radius:11px; }
.statbar { position:relative; z-index:2; margin:-70px 6vw 0; display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; }
.stat { background:#fff; border-radius:18px; padding:20px 22px; box-shadow:0 18px 50px rgba(11,31,58,.14); border-top:4px solid var(--purple); }
.stat b { display:block; font-size:2rem; font-weight:900; color:var(--navy); letter-spacing:-1px; line-height:1; } .stat small { display:block; margin-top:6px; color:var(--muted); font-weight:700; font-size:.74rem; letter-spacing:1.5px; text-transform:uppercase; }
.stat.g { border-top-color:var(--gold); } .stat.v { border-top-color:var(--violet); } .stat.n { border-top-color:var(--navy); }
.page-head { position:relative; color:#fff; padding:100px 6vw 70px; background-size:cover; background-position:center; }
.page-head h1 { font-size:clamp(2rem,4.2vw,3.6rem); font-weight:900; margin:0 0 10px; letter-spacing:-1.5px; color:#fff; } .page-head p { color:rgba(255,255,255,.82); max-width:62ch; margin:0; font-size:1.05rem; line-height:1.6; }
.crumb { color:rgba(255,255,255,.6); font-size:.84rem; margin-bottom:16px; font-weight:600; } .crumb a { color:var(--gold2); }

/* ---------- sections ---------- */
.section { padding:88px 6vw; } .section.alt { background:#fff; } .section.lav { background:linear-gradient(180deg,#F5F3FF,#fff); }
.section.navy { background:radial-gradient(1100px 500px at 15% 0%,#1B3B6B 0%,var(--navy) 55%); color:#fff; }
.kicker { color:var(--purple); font-weight:800; letter-spacing:3px; text-transform:uppercase; font-size:.74rem; } .navy .kicker { color:var(--gold2); }
.section h2 { font-size:clamp(1.9rem,3.6vw,2.9rem); font-weight:900; letter-spacing:-1.2px; margin:8px 0 10px; line-height:1.1; color:var(--ink); } .navy h2 { color:#fff; }
.section .lead { color:var(--muted); font-size:1.08rem; max-width:66ch; margin:0 0 36px; line-height:1.65; } .navy .lead { color:rgba(255,255,255,.78); }
.center { text-align:center; } .center .lead { margin-left:auto; margin-right:auto; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:22px; }
.grid3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:22px; }
.split { display:grid; grid-template-columns:1.05fr 1fr; gap:48px; align-items:center; }
.card { background:#fff; border:1px solid var(--border); border-radius:22px; overflow:hidden; box-shadow:0 10px 30px rgba(11,31,58,.07); transition:transform .2s,box-shadow .2s; display:flex; flex-direction:column; }
.card:hover { transform:translateY(-8px); box-shadow:0 26px 54px rgba(11,31,58,.16); }
.card > .ph, .card > img { height:170px; min-height:170px; border-radius:0; box-shadow:none; } .card > img { width:100%; object-fit:cover; } .card .body { padding:20px 22px 22px; flex:1; display:flex; flex-direction:column; }
.card h3 { margin:0 0 6px; font-size:1.08rem; font-weight:800; display:flex; gap:8px; align-items:center; color:var(--ink); } .card h3 .msr { color:var(--purple); }
.card p { color:var(--muted); font-size:.92rem; line-height:1.55; margin:0 0 12px; flex:1; }
.meta { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; } .tag { font-size:.72rem; font-weight:800; padding:5px 10px; border-radius:999px; background:var(--lav); color:#4C1D95; }
.tag.gold { background:#FEF3C7; color:#92400E; } .tag.green { background:#DCFCE7; color:#166534; } .tag.grey { background:#F1F5F9; color:#475569; }
.feature { background:#fff; border-radius:20px; padding:26px; border:1px solid var(--border); box-shadow:0 8px 24px rgba(11,31,58,.05); transition:transform .2s,box-shadow .2s; }
.feature:hover { transform:translateY(-4px); box-shadow:0 18px 40px rgba(11,31,58,.12); }
.feature .ic { width:50px; height:50px; border-radius:14px; display:grid; place-items:center; background:linear-gradient(135deg,var(--lav),#DDD6FE); color:var(--purple); margin-bottom:16px; }
.feature h3 { margin:0 0 6px; font-size:1.05rem; font-weight:800; color:var(--ink); display:flex; gap:8px; align-items:center; } .feature h3 .msr { color:var(--purple); } .feature p { color:var(--muted); font-size:.92rem; line-height:1.55; margin:0; }
.navy .feature { background:rgba(255,255,255,.07); border-color:rgba(255,255,255,.14); } .navy .feature h3 { color:#fff; } .navy .feature p { color:rgba(255,255,255,.75); } .navy .feature .ic { background:rgba(255,255,255,.14); color:var(--gold2); }
.steps6 { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; }
.step6 { background:#fff; border-radius:18px; padding:22px 20px; border:1px solid var(--border); box-shadow:0 8px 24px rgba(11,31,58,.05); }
.step6 .n { width:38px; height:38px; border-radius:12px; background:linear-gradient(135deg,var(--navy),var(--purple)); color:var(--gold2); font-weight:900; display:grid; place-items:center; margin-bottom:14px; }
.step6 b { display:block; font-size:1rem; margin-bottom:4px; color:var(--ink); } .step6 span { color:var(--muted); font-size:.88rem; line-height:1.5; }
.gallery { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; } .gallery .ph { height:230px; min-height:230px; }
.gallery .ph.tall { grid-row:span 2; height:100%; min-height:478px; }
.ann { background:#fff; border-radius:18px; padding:20px 22px; border:1px solid var(--border); border-left:5px solid var(--gold); box-shadow:0 8px 24px rgba(11,31,58,.05); }
.ann b { display:block; font-size:1.02rem; margin-bottom:4px; color:var(--ink); } .ann p { margin:0; color:#334155; font-size:.92rem; line-height:1.55; } .ann small { color:var(--muted); display:block; margin-top:8px; }
.faq details { background:#fff; border-radius:14px; padding:14px 18px; margin-bottom:10px; border:1px solid var(--border); } .faq summary { font-weight:700; cursor:pointer; color:var(--ink); } .faq p { color:var(--muted); margin:8px 0 0; line-height:1.55; }
.dates { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; } .date { background:#fff; border-radius:16px; padding:18px; border-left:5px solid var(--purple); box-shadow:0 8px 24px rgba(11,31,58,.05); } .date b { display:block; font-size:1.02rem; color:var(--ink); } .date span { color:var(--muted); font-size:.88rem; }
.contact-grid { display:grid; grid-template-columns:1.2fr 1fr; gap:30px; } .ccard { background:#fff; border-radius:22px; padding:28px; border:1px solid var(--border); box-shadow:0 10px 30px rgba(11,31,58,.06); }
.ccard h2, .ccard h3 { color:var(--ink); } .ccard p { margin:8px 0; color:#334155; display:flex; gap:10px; align-items:center; } .ccard p .msr { color:var(--purple); }
.venue { display:grid; grid-template-columns:1fr 1.05fr; gap:40px; align-items:center; } .venue .ph { min-height:360px; }
.vlabel { display:inline-flex; align-items:center; gap:8px; background:rgba(245,179,1,.16); border:1px solid rgba(245,179,1,.45); color:var(--gold2); padding:6px 12px; border-radius:999px; font-size:.76rem; font-weight:800; letter-spacing:1.5px; text-transform:uppercase; margin-bottom:14px; } .vlabel .msr { font-size:16px; }
.vfacts { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:22px; } .vfact { background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.14); border-radius:14px; padding:14px; } .vfact small { display:block; color:rgba(255,255,255,.6); font-size:.72rem; letter-spacing:1.5px; text-transform:uppercase; font-weight:700; } .vfact b { display:block; margin-top:4px; color:#fff; }
.proglist { display:grid; gap:10px; }
.proglist a { display:flex; justify-content:space-between; align-items:center; gap:12px; background:#fff; border:1px solid var(--border); border-radius:16px; padding:16px 18px; color:var(--ink); transition:transform .15s,box-shadow .15s; }
.proglist a:hover { transform:translateX(4px); box-shadow:0 10px 26px rgba(11,31,58,.1); } .proglist b { display:block; color:var(--ink); } .proglist small { color:var(--muted); } .proglist .msr { color:var(--purple); }
.values { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; } .value { padding:20px; border-radius:16px; background:var(--lav); } .value b { display:block; color:#4C1D95; margin-bottom:4px; } .value span { color:#4C1D95; font-size:.9rem; opacity:.85; }

/* ---------- photo placeholders (ui/public/images.py) ---------- */
.ph { position:relative; border-radius:22px; overflow:hidden; min-height:220px; height:100%; display:flex; align-items:center; justify-content:center;
  background:radial-gradient(600px 300px at 80% 10%,rgba(139,92,246,.45),transparent 60%),radial-gradient(500px 300px at 10% 100%,rgba(245,179,1,.2),transparent 60%),linear-gradient(135deg,#0B1F3A,#2E1065);
  box-shadow:0 18px 44px rgba(11,31,58,.18); }
.ph::before { content:""; position:absolute; inset:0; background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px); background-size:28px 28px; }
.ph .ph-frame { position:relative; z-index:1; border:1.5px dashed rgba(255,255,255,.4); border-radius:16px; padding:22px 26px; text-align:center; color:#fff; max-width:88%; }
.ph .ph-frame .msr { font-size:34px; color:var(--gold2); margin-bottom:8px; } .ph .ph-frame b { display:block; font-size:1rem; color:#fff; } .ph .ph-frame small { display:block; color:rgba(255,255,255,.65); font-size:.74rem; margin-top:6px; }
.ph.has-photo::before { display:none; } .ph.has-photo img { width:100%; height:100%; object-fit:cover; display:block; }
.ph.sm .ph-frame { padding:12px 14px; } .ph.sm .ph-frame .msr { font-size:24px; } .ph.sm .ph-frame b { font-size:.85rem; } .ph.sm .ph-frame small { display:none; }

/* ---------- footer ---------- */
.footer { background:#07152A; color:rgba(255,255,255,.8); padding:64px 6vw 28px; }
.footer .cols { display:grid; grid-template-columns:2fr 1fr 1fr 1fr 1.3fr; gap:30px; }
.footer h4 { color:#fff; margin:0 0 12px; font-size:.9rem; letter-spacing:1.5px; text-transform:uppercase; }
.footer a, .footer .line { color:rgba(255,255,255,.7); display:block; margin-bottom:8px; font-size:.92rem; } .footer a:hover { color:var(--gold2); }
.footer .social a { display:inline-flex; margin:0 8px 0 0; padding:8px 12px; border-radius:10px; background:rgba(255,255,255,.08); } .footer .social .msr { font-size:20px; }
.footer .bottom { border-top:1px solid rgba(255,255,255,.1); margin-top:36px; padding-top:18px; display:flex; justify-content:space-between; font-size:.82rem; color:rgba(255,255,255,.5); flex-wrap:wrap; gap:10px; }

/* ---------- course filters (Streamlit widgets) ---------- */
.st-key-course_filters { padding:28px 6vw 0; } .st-key-course_filters [data-testid="stTextInput"] input, .st-key-course_filters [data-baseweb="select"] > div { border-radius:12px; }

/* ---------- responsive ---------- */
@media (max-width:1100px) { .footer .cols { grid-template-columns:1fr 1fr; } }
@media (max-width:960px) {
  .nav .burger { display:grid; }
  .nav .links { display:none; position:absolute; top:100%; left:0; right:0; flex-direction:column; align-items:stretch; background:rgba(11,31,58,.98); padding:10px 6vw 18px; border-bottom:1px solid rgba(255,255,255,.1); }
  .nav .navtoggle:checked ~ .links { display:flex; } .nav .links a { padding:12px 14px; } .nav .ghost, .nav .cta { margin:6px 0 0; text-align:center; justify-content:center; }
  .split, .venue, .contact-grid, .vfacts { grid-template-columns:1fr; } .section { padding:64px 6vw; } .hero { min-height:min(70vh,640px); padding:50px 6vw 110px; } .eyebrow { letter-spacing:1px; font-size:.68rem; } .hero .mark { display:none !important; }
  .gallery .ph.tall { grid-row:auto; min-height:230px; } .topbar span:last-child { display:none; }
}
@media (max-width:600px) { .footer .cols { grid-template-columns:1fr; } .statbar { margin-top:-50px; } .hero h1 { letter-spacing:-1px; } .section h2 { letter-spacing:-.6px; } }
</style>
"""


# ------------------------------------------------------------------ chrome
def nav(content: dict, active: str, settings: dict) -> None:
    name = esc(content.get("institute_name", "Institute"))
    links = "".join(f'<a class="{"active" if k == active else ""}" href="?page={k}" target="_self">{t}</a>' for k, t in PUBLIC_PAGES)
    st.html(f"""
<div class="topbar"><span>{ic('school')} Academic session {esc(settings.get('academic_session', ''))} · Admissions open</span><span>{esc(content.get('contact_info', ''))}</span></div>
<div class="nav">
  <a class="brand" href="?page=home" target="_self"><img src="{im.LOGO_URL}" alt="logo"><div><b>{BRAND}</b><small>{name}</small></div></a>
  <input type="checkbox" id="navtoggle" class="navtoggle"><label for="navtoggle" class="burger">{ic('menu')}</label>
  <div class="links">{links}<a class="ghost" href="?page=login" target="_self">Student Login</a><a class="cta" href="?page=login&intent=apply" target="_self">Apply Now</a></div>
</div>""")
    if settings.get("demo_mode", "1") == "1":
        st.html('<div class="demo-banner">Demonstration mode · applicants and statistics are synthetic sample data; photographs are placeholders until real images are added.</div>')


def page_head(title: str, sub: str, slot: str, crumb: str) -> None:
    st.html(f"""<div class="page-head" style="background-image:{im.background(slot)}"><div class="crumb"><a href="?page=home" target="_self">Home</a> › {esc(crumb)}</div>
<h1>{esc(title)}</h1><p>{esc(sub)}</p></div>""")


def _contact_parts(content: dict) -> list[str]:
    return [x.strip() for x in str(content.get("contact_info", "")).split("·") if x.strip()]


def _email_in(text: str) -> str | None:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text or "")
    return m.group(0) if m else None


def footer(content: dict) -> None:
    name = esc(content.get("institute_name", "Institute"))
    contact_lines = "".join(f'<span class="line">{esc(x)}</span>' for x in _contact_parts(content))
    st.html(f"""
<footer class="footer" id="contact">
  <div class="cols">
    <div><img src="{im.LOGO_URL}" style="width:52px;border-radius:14px;margin-bottom:10px"><h4>{SYSTEM} · {BRAND}</h4><p style="max-width:40ch;line-height:1.6;color:rgba(255,255,255,.65)">{name}. {esc(content.get('hero_subtitle', ''))}</p>
      <div class="social"><a href="?page=contact" target="_self">{ic('mail')}</a><a href="?page=admissions" target="_self">{ic('school')}</a><a href="?page=login" target="_self">{ic('login')}</a></div></div>
    <div><h4>Quick links</h4><a href="?page=home" target="_self">Home</a><a href="?page=about" target="_self">About</a><a href="?page=campus" target="_self">Campus Life</a><a href="?page=contact" target="_self">Contact Us</a></div>
    <div><h4>Academics</h4><a href="?page=academics" target="_self">Departments</a><a href="?page=courses" target="_self">All courses</a><a href="?page=academics" target="_self">Academic calendar</a></div>
    <div><h4>Admissions</h4><a href="?page=admissions" target="_self">Admission process</a><a href="?page=admissions" target="_self">Eligibility</a><a href="?page=admissions" target="_self">Important dates</a><a href="?page=login&intent=apply" target="_self">Apply Now</a><a href="?page=login" target="_self">Student login</a></div>
    <div><h4>Contact</h4>{contact_lines}<span class="line" style="margin-top:10px;color:rgba(255,255,255,.5)">Competition venue: {esc(VENUE_NAME)}</span></div>
  </div>
  <div class="bottom"><span>© 2026 {name} · {BRAND}. All rights reserved.</span><span>Admissions powered by SEATWISEE.</span></div>
</footer>""")


# ------------------------------------------------------------------ data helpers
def _programs(c) -> pd.DataFrame:
    return db.load_programs(c)


def _stats(c, programs: pd.DataFrame) -> dict:
    return {"programs": len(programs), "seats": int(programs.capacity.sum()) if len(programs) else 0,
            "departments": int(programs.department.replace("", pd.NA).dropna().nunique()) if "department" in programs else 0,
            "applicants": c.execute("SELECT COUNT(*) FROM applicants WHERE application_status='applied'").fetchone()[0]}


def _track(r) -> str:
    return r.required_track if isinstance(r.required_track, str) and r.required_track else "Any track"


def _s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def program_card_html(r, detail_link=True) -> str:
    code = str(r.code)
    open_tag = '<span class="tag green">Open</span>' if int(getattr(r, "is_open", 1) or 0) else '<span class="tag grey">Closed</span>'
    btn = f'<a class="btn navy sm" href="?page=courses&program={esc(code)}" target="_self">View details {ic("arrow_forward")}</a>' if detail_link else ""
    url = im.program_photo(code)
    media = f"<img src='{url}' alt=''>" if url else f"<div class='ph sm' data-slot='program_{code.lower()}'><div class='ph-frame'><span class='msr'>{ICONS.get(code, 'school')}</span><b>{esc(code)}</b></div></div>"
    return (f'<div class="card">{media}<div class="body"><h3>{ic(ICONS.get(code, "school"))}{esc(r.name)}</h3><p>{esc(_s(r.description))}</p>'
            f'<div class="meta"><span class="tag grey">{esc(_s(r.duration))}</span><span class="tag gold">{int(r.capacity)} seats</span><span class="tag">{esc(_track(r))} · score ≥ {int(r.min_score)}</span>{open_tag}</div>{btn}</div></div>')


def _announcements_html(c, content: dict, limit: int = 4) -> str:
    items = []
    cms = str(content.get("announcements", "")).strip()
    if cms:
        items.append(f"<div class='ann'><b>Admissions notice</b><p>{esc(cms)}</p></div>")
    for r in db.load_announcements(c, audience="public").head(limit).itertuples():
        items.append(f"<div class='ann'><b>{esc(r.title)}</b><p>{esc(r.body)}</p><small>{esc(str(r.created_at)[:10])}</small></div>")
    return "".join(items) or "<p class='lead'>No announcements at the moment.</p>"


WHY = [("auto_awesome", "Smart Admission Process", "One guided application: score, track, ranked preferences and documents, with instant feedback on what is missing."),
       ("balance", "Transparent Seat Allocation", "A constraint-optimisation engine assigns every seat by eligibility, capacity and ranked choices, then an independent validator re-checks the result."),
       ("person", "Student-Friendly Application", "Clear steps, mobile-ready forms and plain-language explanations of every decision."),
       ("track_changes", "Real-Time Application Tracking", "Follow your application from submission to eligibility, allocation and offer acceptance in your portal."),
       ("verified_user", "Secure Document Management", "Marksheets and scorecards are stored under secure names and visible only to you and the admissions office."),
       ("admin_panel_settings", "Efficient Administration", "Reallocation, withdrawals and appeals are evaluated with evidence, with a complete audit history of every change.")]

STEPS6 = [("Register", "Create your account with name, email, phone and a password."),
          ("Complete Application", "Enter your entrance score, academic track and the institute's questions."),
          ("Select Preferences", "Rank your preferred programmes in order and upload both documents."),
          ("Eligibility Verification", "The admissions office verifies eligibility against each programme's requirements."),
          ("Seat Allocation", "The SEATWISEE engine allocates seats; results are independently validated and published."),
          ("Admission Confirmation", "Accept your provisional offer in the portal and download your allotment letter.")]


def steps_html() -> str:
    return "<div class='steps6'>" + "".join(f"<div class='step6'><div class='n'>{i}</div><b>{t}</b><span>{d}</span></div>" for i, (t, d) in enumerate(STEPS6, 1)) + "</div>"


def venue_html() -> str:
    return f"""
<section class="section navy" id="venue"><div class="venue">
  {im.figure('venue', 'R.D. Engineering College, Ghaziabad', 'location_city')}
  <div><div class="vlabel">{ic('flag')} Competition venue</div><div class="kicker">Where SEATWISEE is presented</div><h2>{esc(VENUE_NAME)}</h2>
  <p class="lead">SEATWISEE is being demonstrated at {VENUE_EVENT}, hosted at {esc(VENUE_NAME)}. R.D. Engineering College is the competition venue; the admissions platform and the DO! u want brand belong to the Syntaxis Institute of Technology demonstration.</p>
  <div class="vfacts"><div class="vfact"><small>Venue</small><b>{esc(VENUE_NAME)}</b></div><div class="vfact"><small>Location</small><b>{esc(VENUE_CITY)}</b></div>
  <div class="vfact"><small>Event</small><b>{VENUE_EVENT} hackathon</b></div><div class="vfact"><small>Problem statement</small><b>PS06 · FAIRSHIFT seat allocation</b></div></div>
  <p style="margin-top:22px"><a class="btn outline" href="{VENUE_MAP}" target="_blank">{ic('map')} Directions</a> <a class="btn gold" href="?page=about" target="_self">About the project</a></p></div>
</div></section>"""


# ------------------------------------------------------------------ pages
def page_home(c, content, settings):
    programs = _programs(c)
    stats = _stats(c, programs)
    tagline = settings.get("institute_tagline") or TAGLINE_DEFAULT
    parts = esc(tagline).rsplit(" ", 1)
    title_html = f"{parts[0]} <em>{parts[1]}</em>" if len(parts) == 2 else esc(tagline)
    st.html(f"""
<section class="hero {'' if im.photo('hero') else 'no-photo'}" style="background-image:{im.background('hero')}"><div class="orb"></div>{'' if im.photo('hero') else f"<span class='mark'>{ic('photo_camera')} Hero photograph placeholder · static/images/photos/hero.jpg</span>"}
  <div><div class="eyebrow">{ic('school')} {esc(content.get('institute_name', ''))} · Admissions {esc(settings.get('academic_session', ''))}</div>
    <h1>{title_html}</h1><p class="support">{SUPPORT_LINE}</p><p class="lead">{esc(content.get('hero_subtitle', ''))}</p>
    <div class="btns"><a class="btn gold" href="?page=admissions" target="_self">Explore Admissions {ic('arrow_forward')}</a><a class="btn outline" href="?page=login" target="_self">{ic('login')} Student Login</a></div>
  </div>
</section>
<div class="statbar"><div class="stat"><b>{stats['programs']}</b><small>Programmes</small></div><div class="stat g"><b>{stats['seats']}</b><small>Seats this session</small></div>
<div class="stat v"><b>{stats['departments']}</b><small>Departments</small></div><div class="stat n"><b>{stats['applicants']}</b><small>Applications received</small></div></div>""")
    cards = "".join(program_card_html(r) for r in programs.head(4).itertuples())
    why = "".join(f"<div class='feature'><div class='ic'>{ic(i)}</div><h3>{t}</h3><p>{d}</p></div>" for i, t, d in WHY)
    gallery = "".join(im.figure(f"gallery_{i}", lbl, "photo_camera", "tall" if i == 1 else "") for i, lbl in
                      [(1, "Academic block"), (2, "Laboratories"), (3, "Library"), (4, "Sports"), (5, "Events and culture")])
    st.html(f"""
<section class="section alt" id="about"><div class="split">
  <div><div class="kicker">About {SYSTEM}</div><h2>Admissions you can trust, decisions you can explain</h2>
  <p class="lead">{esc(content.get('about_us', ''))}</p>
  <p class="lead" style="margin-bottom:20px">{BRAND} is the public face of {esc(content.get('institute_name', ''))} admissions, run on the {SYSTEM} platform: one application, ranked preferences, verified eligibility and a seat allocation that is validated before it is published.</p>
  <a class="btn purple" href="?page=about" target="_self">Learn more {ic('arrow_forward')}</a></div>
  {im.figure('about', 'Campus or classroom photograph')}</div></section>
<section class="section lav" id="why"><div class="center"><div class="kicker">Why choose {SYSTEM}</div><h2>Built for fair, modern admissions</h2>
  <p class="lead">Every feature exists to make the admission journey clear for students and auditable for the institute.</p></div>
  <div class="grid3">{why}</div></section>
<section class="section alt"><div class="kicker">Programmes</div><h2>Programmes open this session</h2>
  <p class="lead">Seats, eligibility floors and track requirements are the live values the admission engine uses.</p>
  <div class="grid">{cards}</div><p style="margin-top:24px"><a class="btn navy" href="?page=courses" target="_self">See all {len(programs)} programmes {ic('arrow_forward')}</a></p></section>
<section class="section"><div class="center"><div class="kicker">Admission process</div><h2>Six steps from account to admission</h2>
  <p class="lead">Everything happens in your student portal, with notifications at every stage.</p></div>{steps_html()}
  <p class="center" style="margin-top:26px"><a class="btn gold" href="?page=login&intent=apply" target="_self">Apply Now {ic('arrow_forward')}</a></p></section>""")
    st.html(venue_html())
    st.html(f"""
<section class="section alt" id="campus"><div class="kicker">Campus life</div><h2>Where ideas get built</h2>
  <p class="lead">Classrooms, laboratories, library, sports and a packed calendar of student events. Photographs will replace the placeholders below.</p>
  <div class="gallery">{gallery}</div><p style="margin-top:22px"><a class="btn navy" href="?page=campus" target="_self">Explore campus life {ic('arrow_forward')}</a></p></section>
<section class="section lav" id="announcements"><div class="kicker">Announcements</div><h2>Latest updates</h2><div class="grid">{_announcements_html(c, content)}</div></section>""")


def page_about(c, content, settings):
    page_head("About", content.get("about_us", ""), "head_about", "About")
    name = esc(content.get("institute_name", ""))
    st.html(f"""
<section class="section alt"><div class="split"><div><div class="kicker">About the institute</div><h2>{name}</h2>
  <p class="lead">{esc(content.get('about_us', ''))}</p><p class="lead">{esc(content.get('hero_subtitle', ''))}</p></div>
  {im.figure('about', 'Institute photograph')}</div></section>
<section class="section"><div class="split"><div class="proglist" style="gap:14px">
  <div class="feature"><div class="ic">{ic('hub')}</div><h3>About {SYSTEM}</h3><p>{SYSTEM} is the admissions platform behind {BRAND}: a constraint-optimisation engine (Google OR-Tools CP-SAT) allocates seats from ranked preferences, eligibility and capacity, an independent validator checks every published allocation, and every change is written to an append-only audit history.</p></div>
  <div class="feature"><div class="ic">{ic('visibility')}</div><h3>Vision</h3><p>A learner-centred institution where every admission decision is fair, transparent and explainable.</p></div>
  <div class="feature"><div class="ic">{ic('explore')}</div><h3>Mission</h3><p>Rigorous academics, hands-on learning and an admissions process that treats every applicant by the same published rules.</p></div></div>
  <div><div class="kicker">Values and objectives</div><h2>What guides every decision</h2>
  <div class="values"><div class="value"><b>Fairness</b><span>Same rules, same engine, for every applicant.</span></div><div class="value"><b>Transparency</b><span>Every allocation is explained and independently validated.</span></div>
  <div class="value"><b>Minimal disruption</b><span>Reallocation moves as few students as possible.</span></div><div class="value"><b>Evidence</b><span>Appeals are decided on their measured effect, not opinion.</span></div>
  <div class="value"><b>Privacy</b><span>Students see only their own records and documents.</span></div><div class="value"><b>Accountability</b><span>An audit trail of every change, kept forever.</span></div></div></div></div></section>""")
    st.html(venue_html())


def page_academics(c, content, settings):
    programs = _programs(c)
    page_head("Academics", "Departments, programmes and the academic approach behind them.", "head_academics", "Academics")
    depts = programs.groupby(programs.department.fillna("Academics"))
    blocks = ""
    for dept, grp in depts:
        items = "".join(f'<a href="?page=courses&program={esc(r.code)}" target="_self">{ic(ICONS.get(r.code, "school"))}<div style="flex:1"><b>{esc(r.name)}</b><small>{esc(_s(r.duration))} · {int(r.capacity)} seats · min score {int(r.min_score)} · {esc(_track(r))}</small></div>{ic("chevron_right")}</a>' for r in grp.itertuples())
        blocks += f'<div><div class="kicker">Department</div><h3 style="font-size:1.4rem;font-weight:900;margin:6px 0 14px">{esc(dept)}</h3><div class="proglist">{items}</div></div>'
    st.html(f"""
<section class="section alt"><div class="center"><div class="kicker">Academic overview</div><h2>{len(programs)} programmes across {_stats(c, programs)['departments']} departments</h2>
  <p class="lead">Every programme below is a live record: its seats, minimum entrance score and track requirement are exactly what the allocation engine enforces.</p></div>
  <div class="grid3">{blocks}</div></section>
<section class="section lav"><div class="kicker">Academic approach</div><h2>How we teach</h2>
  <div class="grid3"><div class="feature"><div class="ic">{ic('menu_book')}</div><h3>Outcome-based curricula</h3><p>Programmes are organised around clear learning outcomes and reviewed each session.</p></div>
  <div class="feature"><div class="ic">{ic('science')}</div><h3>Hands-on learning</h3><p>Laboratory work, projects and studio sessions from the first year.</p></div>
  <div class="feature"><div class="ic">{ic('groups')}</div><h3>Mentoring</h3><p>Small cohorts with faculty mentors and peer learning groups.</p></div>
  <div class="feature"><div class="ic">{ic('work')}</div><h3>Learning opportunities</h3><p>Internships, hackathons, research assistantships and industry talks.</p></div>
  <div class="feature"><div class="ic">{ic('public')}</div><h3>Interdisciplinary tracks</h3><p>Engineering, science, commerce and arts tracks feed into every department.</p></div>
  <div class="feature"><div class="ic">{ic('verified')}</div><h3>Transparent assessment</h3><p>Published eligibility floors and explainable allocation decisions.</p></div></div></section>
<section class="section navy"><div class="kicker">Academic calendar</div><h2>Session {esc(settings.get('academic_session', ''))}</h2>
  <div class="dates"><div class="date"><b>Applications open</b><span>Rolling, until seats are filled</span></div><div class="date"><b>Allocation rounds</b><span>Published by the admissions office</span></div>
  <div class="date"><b>Offer acceptance</b><span>Within {esc(settings.get('offer_accept_days', '7'))} days of a provisional offer</span></div><div class="date"><b>Classes begin</b><span>Announced by the institute</span></div></div></section>""")


def page_courses(c, content, settings):
    programs = _programs(c)
    code = (st.query_params.get("program") or "").upper()
    if code and (programs.code == code).any():
        r = programs[programs.code == code].iloc[0]
        used = db.get_current_assignment_map(c)
        allocated = sum(1 for p in used.values() if p == int(r.id))
        page_head(f"{r['name']}", _s(r.description), f"program_{code.lower()}", f"Courses › {code}")
        st.html(f"""
<section class="section alt"><div class="split"><div>
  <div class="kicker">{esc(_s(r.department) or 'Academics')} · {esc(_s(r.duration))}</div><h2>{esc(r['name'])}</h2>
  <p class="lead">{esc(_s(r.description))}</p>
  <div class="grid"><div class="feature"><div class="ic">{ic('rule')}</div><h3>Eligibility</h3><p>Entrance score of at least <b>{int(r.min_score)}</b>, open to <b>{esc(_track(r))}</b> students. Rank it among your preferences to be considered.</p></div>
  <div class="feature"><div class="ic">{ic('event_seat')}</div><h3>Seats</h3><p><b>{int(r.capacity)}</b> seats this session{f' · {allocated} provisionally allotted so far' if used else ''}.</p></div>
  <div class="feature"><div class="ic">{ic('tag')}</div><h3>Programme code</h3><p>{esc(code)} · {'open for applications' if int(r.is_open or 0) else 'closed'}</p></div>
  <div class="feature"><div class="ic">{ic('balance')}</div><h3>How seats are assigned</h3><p>By the {SYSTEM} engine using your ranked preferences, eligibility and capacity; results are independently validated.</p></div></div>
  <p style="margin-top:24px"><a class="btn gold" href="?page=login&intent=apply&program={esc(code)}" target="_self">Apply for this programme {ic('arrow_forward')}</a> <a class="btn navy" href="?page=courses" target="_self">All courses</a></p></div>
  {im.figure(f'program_{code.lower()}', r['name'], ICONS.get(code, 'school'))}</div></section>""")
        return
    page_head("Courses", f"{len(programs)} programmes across {_stats(c, programs)['departments']} departments. Seats and eligibility are live values.", "head_courses", "Courses")
    with st.container(key="course_filters"):
        f1, f2, f3 = st.columns([2, 1, 1])
        q = f1.text_input("Search programmes", key="course_q", placeholder="name, code or keyword")
        depts = ["All departments"] + sorted(programs.department.replace("", pd.NA).dropna().unique().tolist())
        dept = f2.selectbox("Department", depts, key="course_dept")
        tracks = ["Any track"] + sorted(programs.required_track.replace("", pd.NA).dropna().unique().tolist())
        track = f3.selectbox("Track", tracks, key="course_track")
    v = programs
    if q:
        v = v[v.name.str.contains(q, case=False) | v.code.str.contains(q, case=False) | v.description.fillna("").str.contains(q, case=False)]
    if dept != "All departments":
        v = v[v.department == dept]
    if track != "Any track":
        v = v[(v.required_track == track) | v.required_track.isna() | (v.required_track == "")]
    cards = "".join(program_card_html(r) for r in v.itertuples())
    st.html(f'<section class="section alt" style="padding-top:28px"><p class="lead" style="margin-bottom:18px">{len(v)} programme(s) shown.</p><div class="grid">{cards or "<p class=lead>No programme matches these filters.</p>"}</div>'
            f'<p style="margin-top:26px"><a class="btn gold" href="?page=login&intent=apply" target="_self">Apply Now {ic("arrow_forward")}</a></p></section>')


def faq_html(settings: dict) -> str:
    max_prefs = esc(settings.get("max_preferences", "5"))
    return "".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in [
        ("How many programmes can I rank?", f"Up to {max_prefs}, in order of preference. Your first choice carries the most weight."),
        ("What documents are mandatory?", "Your 12th Board Marksheet and your CUET PG / entrance exam scorecard as PDF, PNG or JPG (max 8 MB each)."),
        ("How is my seat decided?", f"The {SYSTEM} engine assigns seats using your ranked preferences, each programme's eligibility floor and capacity. Every published result is independently validated."),
        ("What if I am waitlisted?", "Seats released by withdrawals are filled automatically by the next qualifying applicant. You are notified when your status changes."),
        ("Can I appeal my allocation?", "Yes. Request a different programme from your portal with a reason; the admissions office evaluates the exact effect on other applicants before deciding."),
        ("Is this a real admission?", "This deployment runs in demonstration mode with synthetic applicants. Real admissions follow the institution's published policy.")])


def page_admissions(c, content, settings):
    programs = _programs(c)
    page_head("Admissions", "Process, eligibility, instructions, important dates and answers to common questions.", "head_admissions", "Admissions")
    rows = "".join(f'<div class="feature"><div class="ic">{ic(ICONS.get(r.code, "school"))}</div><h3>{esc(r.name)}</h3><p>{esc(_s(r.duration))} · {int(r.capacity)} seats · score ≥ {int(r.min_score)} · {esc(_track(r))}</p></div>' for r in programs.itertuples())
    st.html(f"""
<section class="section alt"><div class="center"><div class="kicker">Admission process {esc(settings.get('academic_session', ''))}</div><h2>Six steps from account to admission</h2>
  <p class="lead">Everything happens in your student portal, with notifications at every stage.</p></div>{steps_html()}
  <p class="center" style="margin-top:26px"><a class="btn gold" href="?page=login&intent=apply" target="_self">Apply Now {ic('arrow_forward')}</a> <a class="btn navy" href="?page=login" target="_self">{ic('login')} Student Login</a></p></section>
<section class="section"><div class="split"><div><div class="kicker">Application instructions</div><h2>Before you start</h2>
  <div class="proglist"><div class="feature"><h3>{ic('badge')} Keep your scorecard ready</h3><p>Your entrance score and academic track decide which programmes you are eligible for.</p></div>
  <div class="feature"><h3>{ic('upload_file')} Prepare two documents</h3><p>12th Board Marksheet and entrance scorecard, PDF/PNG/JPG, up to 8 MB each.</p></div>
  <div class="feature"><h3>{ic('format_list_numbered')} Rank up to {esc(settings.get('max_preferences', '5'))} programmes</h3><p>Order matters: the engine tries your first choice first.</p></div>
  <div class="feature"><h3>{ic('schedule')} Accept within {esc(settings.get('offer_accept_days', '7'))} days</h3><p>Provisional offers are accepted in the portal; your allotment letter is downloadable.</p></div></div></div>
  {im.figure('admissions', 'Students on campus')}</div></section>
<section class="section lav"><div class="kicker">Important dates</div><h2>Key dates · session {esc(settings.get('academic_session', ''))}</h2>
  <div class="dates"><div class="date"><b>Applications open</b><span>Now · rolling</span></div><div class="date"><b>Document verification</b><span>Continuous</span></div><div class="date"><b>Allocation rounds</b><span>Published by the admissions office</span></div><div class="date"><b>Offer acceptance</b><span>{esc(settings.get('offer_accept_days', '7'))} days from offer</span></div></div>
  <p class="lead" style="margin-top:14px;font-size:.9rem">The admissions office publishes the exact schedule in Announcements.</p></section>
<section class="section alt"><div class="kicker">Eligibility</div><h2>Programmes open this session</h2><div class="grid3">{rows}</div></section>
<section class="section faq"><div class="kicker">FAQ</div><h2>Frequently asked questions</h2>{faq_html(settings)}</section>""")


def page_campus(c, content, settings):
    page_head("Campus Life", "Classrooms, laboratories, library, sports, activities and the student experience.", "head_campus", "Campus Life")
    gallery = "".join(im.figure(f"gallery_{i}", lbl, "photo_camera", "tall" if i == 1 else "") for i, lbl in
                      [(1, "Academic block"), (2, "Laboratories"), (3, "Library"), (4, "Sports"), (5, "Events and culture"), (6, "Student life")])
    facilities = [("facility_classrooms", "co_present", "Classrooms and labs", "Smart classrooms, computing labs and engineering workshops."),
                  ("facility_library", "local_library", "Library", "Print and digital collections, quiet zones and group study rooms."),
                  ("facility_sports", "sports_soccer", "Sports", "Courts, grounds and a fitness centre."),
                  ("facility_events", "celebration", "Events and activities", "Tech fest, cultural fest, hackathons and student clubs."),
                  ("facility_labs", "science", "Laboratories", "Electronics, mechanical, biotech and data labs."),
                  ("facility_hostel", "apartment", "Residences", "On-campus hostels with dining and support.")]
    fac = "".join(f"<div class='card'>{im.figure(slot, title, icon, 'sm')}<div class='body'><h3>{ic(icon)}{title}</h3><p>{d}</p></div></div>" for slot, icon, title, d in facilities)
    st.html(f"""<section class="section alt"><div class="kicker">Gallery</div><h2>Campus gallery</h2><p class="lead">Each tile is a dedicated photo slot; add files to static/images/photos to replace the placeholders.</p><div class="gallery">{gallery}</div></section>
<section class="section lav"><div class="kicker">Facilities</div><h2>Academic facilities</h2><div class="grid">{fac}</div></section>
<section class="section"><div class="kicker">Student experience</div><h2>Life beyond the classroom</h2>
  <div class="grid3"><div class="feature"><div class="ic">{ic('diversity_3')}</div><h3>Clubs and societies</h3><p>Coding, robotics, drama, music, debate and more, run by students.</p></div>
  <div class="feature"><div class="ic">{ic('emoji_events')}</div><h3>Competitions</h3><p>Hackathons, case competitions and sports tournaments through the year.</p></div>
  <div class="feature"><div class="ic">{ic('support_agent')}</div><h3>Support services</h3><p>Mentoring, counselling and a placement cell that prepares students for recruiters.</p></div></div></section>""")


def page_contact(c, content, settings):
    page_head("Contact Us", "We are happy to help with admissions and campus queries.", "head_contact", "Contact Us")
    parts = _contact_parts(content); email = _email_in(content.get("contact_info", ""))
    icons = ["apartment", "mail", "call", "schedule"]
    lines = "".join(f"<p>{ic(icons[i] if i < len(icons) else 'info')}<span>{esc(x)}</span></p>" for i, x in enumerate(parts))
    mail_btn = f'<a class="btn purple" href="mailto:{esc(email)}?subject=Admissions%20enquiry" target="_blank">{ic("mail")} Email the admissions office</a>' if email else ""
    st.html(f"""<section class="section alt"><div class="contact-grid">
  <div class="ccard"><div class="kicker">Admissions office</div><h2 style="margin-top:6px">{esc(content.get('institute_name', ''))}</h2>{lines or '<p>Contact details will be published by the admissions office.</p>'}
    <p style="margin-top:18px;display:flex;flex-wrap:wrap;gap:10px">{mail_btn}<a class="btn gold" href="?page=login&intent=apply" target="_self">Apply Now</a><a class="btn navy" href="?page=login" target="_self">Student login</a></p>
    <p style="color:var(--muted);font-size:.85rem;margin-top:14px">Contact details are managed by the admissions office in the website CMS. Online enquiry forms are not enabled; please use email or phone.</p></div>
  <div class="ccard"><div class="kicker">Competition venue</div><h3 style="margin:6px 0 4px">{esc(VENUE_NAME)}</h3><p>{ic('location_on')}<span>{esc(VENUE_CITY)}</span></p><p>{ic('flag')}<span>{VENUE_EVENT} · problem statement PS06 FAIRSHIFT</span></p>
    <p style="margin-top:12px"><a class="btn navy sm" href="{VENUE_MAP}" target="_blank">{ic('map')} Directions</a></p>
    <div style="margin-top:16px">{im.figure('venue', 'Venue photograph', 'location_city', 'sm')}</div></div></div></section>""")


PAGES = {"home": page_home, "about": page_about, "academics": page_academics, "courses": page_courses,
         "admissions": page_admissions, "campus": page_campus, "contact": page_contact}


def render(c, page: str = "home") -> None:
    content = db.get_site_content(c)
    settings = db.get_settings(c)
    st.html(CSS)
    nav(content, page if page in PAGES else "home", settings)
    PAGES.get(page, page_home)(c, content, settings)
    footer(content)
