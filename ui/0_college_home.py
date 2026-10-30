"""Public college website (unauthenticated view). Premium layout rendered with st.html so the
Markdown parser never touches the CSS. All copy comes from the site_content CMS; program cards
and counters come from the live database.
"""
from __future__ import annotations

import html as _html

import pandas as pd
import streamlit as st

HERO_IMG = "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?auto=format&fit=crop&w=1920&q=80"
LAB_IMG = "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?auto=format&fit=crop&w=1200&q=80"
HACK_IMG = "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1200&q=80"
CAMPUS_IMG = "https://images.unsplash.com/photo-1562774053-701939374585?auto=format&fit=crop&w=1200&q=80"
LIB_IMG = "https://images.unsplash.com/photo-1521587760476-6c12a4b040da?auto=format&fit=crop&w=1200&q=80"

ICONS = {"CSE": "💻", "ECE": "⚡", "MECH": "⚙️", "DATA": "📊", "BIO": "🧬", "PHY": "🔭", "FIN": "💹", "MKT": "📣", "DES": "🎨", "MGMT": "🏛️"}


def esc(x) -> str:
    return _html.escape(str(x if x is not None else ""))


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root {{ --navy:#0B1F3A; --ink:#0F172A; --muted:#64748B; --gold:#F5B301; --gold-2:#FFD75E; --neon:#38BDF8; --white:#FFFFFF; --bg:#F6F8FC; }}
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{ display:none !important; }}
.block-container {{ padding:0 !important; max-width:100% !important; }}
[data-testid="stAppViewContainer"] {{ background:var(--bg); }}
html, body, .stApp, [class*="css"] {{ font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; color:var(--ink); }}
[data-testid="stVerticalBlock"] {{ gap:0 !important; }} .element-container {{ margin:0 !important; }}

.nav {{ position:sticky; top:0; z-index:999; display:flex; align-items:center; justify-content:space-between; padding:16px 6vw;
  background:rgba(11,31,58,.92); backdrop-filter:blur(10px); color:var(--white); border-bottom:1px solid rgba(255,255,255,.08); }}
.nav .brand {{ display:flex; align-items:center; gap:12px; font-weight:800; letter-spacing:.5px; font-size:1.15rem; }}
.nav .crest {{ width:38px; height:38px; border-radius:10px; background:linear-gradient(135deg,var(--gold),var(--neon)); display:grid; place-items:center; color:var(--navy); font-weight:900; }}
.nav .links a {{ color:rgba(255,255,255,.82); text-decoration:none; margin-left:28px; font-weight:500; font-size:.95rem; }} .nav .links a:hover {{ color:var(--gold-2); }}

.hero {{ position:relative; min-height:70vh; display:flex; align-items:center; padding:60px 6vw 80px; color:var(--white);
  background:linear-gradient(100deg,rgba(11,31,58,.92) 0%,rgba(11,31,58,.72) 45%,rgba(11,31,58,.35) 100%),url('{HERO_IMG}');
  background-size:cover; background-position:center; background-attachment:fixed; }}
.hero::after {{ content:""; position:absolute; left:0; right:0; bottom:0; height:160px; background:linear-gradient(180deg,rgba(11,31,58,0),var(--navy)); }}
.hero > * {{ position:relative; z-index:1; }}
.eyebrow {{ display:inline-block; padding:6px 14px; border-radius:999px; border:1px solid rgba(255,255,255,.35); background:rgba(255,255,255,.08); font-size:.8rem; letter-spacing:2px; text-transform:uppercase; margin-bottom:22px; }}
.hero h1 {{ font-size:clamp(2.4rem,5.5vw,4.8rem); line-height:1.02; font-weight:900; margin:0 0 22px; max-width:16ch; letter-spacing:-1.5px; }}
.hero h1 em {{ font-style:normal; background:linear-gradient(90deg,var(--gold),var(--gold-2)); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.hero p {{ font-size:1.15rem; max-width:58ch; color:rgba(255,255,255,.85); line-height:1.6; margin:0; }}
.announce {{ margin-top:26px; max-width:62ch; background:rgba(245,179,1,.14); border-left:4px solid var(--gold); padding:12px 16px; border-radius:10px; color:#FFF3C4; font-size:.95rem; }}

/* ---- hero CTA: the Streamlit button row directly under the hero becomes a navy band ---- */
div[data-testid="stHorizontalBlock"]:has(div[data-testid="stButton"]) {{ background:var(--navy); padding:0 6vw 64px; margin:0; align-items:center; }}
div[data-testid="stButton"] > button {{ background:linear-gradient(135deg,var(--gold) 0%,#FF9F1C 100%) !important; color:var(--navy) !important;
  font-weight:800 !important; font-size:1.05rem !important; padding:14px 34px !important; border:none !important; border-radius:14px !important;
  box-shadow:0 12px 30px rgba(245,179,1,.35) !important; animation:pulse 2.2s infinite; transition:transform .15s ease; }}
div[data-testid="stButton"] > button:hover {{ transform:translateY(-2px) scale(1.02); }}
@keyframes pulse {{ 0% {{ box-shadow:0 0 0 0 rgba(245,179,1,.55),0 12px 30px rgba(245,179,1,.35); }} 70% {{ box-shadow:0 0 0 18px rgba(245,179,1,0),0 12px 30px rgba(245,179,1,.35); }} 100% {{ box-shadow:0 0 0 0 rgba(245,179,1,0),0 12px 30px rgba(245,179,1,.35); }} }}
div[data-testid="stHorizontalBlock"]:has(div[data-testid="stButton"]) p {{ color:rgba(255,255,255,.72); margin:0; }}
.nav .cta {{ margin-left:28px; padding:9px 16px; border-radius:10px; background:linear-gradient(135deg,var(--gold),#FF9F1C); color:var(--navy) !important; font-weight:800 !important; }}
.nav .cta:hover {{ color:var(--navy) !important; filter:brightness(1.06); }}

.section {{ padding:90px 6vw; }} .section.alt {{ background:var(--white); }}
.section.navy {{ background:radial-gradient(1200px 500px at 10% 0%,#1B3B6B 0%,var(--navy) 55%); color:var(--white); }}
.kicker {{ color:var(--neon); font-weight:700; letter-spacing:3px; text-transform:uppercase; font-size:.78rem; }}
.section h2 {{ font-size:clamp(2rem,3.6vw,3rem); font-weight:900; letter-spacing:-1px; margin:8px 0 12px; }}
.section .lead {{ color:var(--muted); font-size:1.1rem; max-width:62ch; margin-bottom:44px; line-height:1.6; }} .section.navy .lead {{ color:rgba(255,255,255,.75); }}

.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:22px; }}
.card {{ background:rgba(255,255,255,.8); backdrop-filter:blur(14px); border:1px solid rgba(15,23,42,.06); border-radius:22px; padding:26px;
  box-shadow:0 10px 30px rgba(11,31,58,.08); transition:transform .2s ease,box-shadow .2s ease; position:relative; overflow:hidden; }}
.card::before {{ content:""; position:absolute; inset:0 0 auto 0; height:5px; background:linear-gradient(90deg,var(--gold),var(--neon)); }}
.card:hover {{ transform:translateY(-8px); box-shadow:0 24px 50px rgba(11,31,58,.16); }}
.card .icon {{ width:52px; height:52px; border-radius:16px; display:grid; place-items:center; font-size:1.45rem; background:linear-gradient(135deg,#E0F2FE,#FEF3C7); margin-bottom:16px; }}
.card h3 {{ margin:0 0 8px; font-size:1.12rem; font-weight:800; }} .card p {{ color:var(--muted); font-size:.92rem; line-height:1.5; margin:0 0 14px; }}
.meta {{ display:flex; gap:8px; flex-wrap:wrap; }} .tag {{ font-size:.72rem; font-weight:700; padding:5px 10px; border-radius:999px; background:#EEF2FF; color:#3730A3; }} .tag.gold {{ background:#FEF3C7; color:#92400E; }}

.masonry {{ display:grid; grid-template-columns:2fr 1fr 1fr; grid-template-rows:250px 250px; gap:16px; }}
.tile {{ border-radius:22px; background-size:cover; background-position:center; position:relative; overflow:hidden; box-shadow:0 16px 40px rgba(0,0,0,.25); }}
.tile.big {{ grid-row:span 2; }} .tile::after {{ content:""; position:absolute; inset:0; background:linear-gradient(180deg,rgba(0,0,0,0) 40%,rgba(11,31,58,.85) 100%); }}
.tile span {{ position:absolute; left:20px; bottom:18px; z-index:2; color:var(--white); font-weight:800; font-size:1.05rem; }}
.counters {{ display:grid; grid-template-columns:repeat(3,1fr); gap:18px; margin-top:44px; }}
.counter {{ text-align:center; padding:26px 16px; border-radius:20px; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.14); backdrop-filter:blur(10px); }}
.counter b {{ display:block; font-size:2.4rem; font-weight:900; background:linear-gradient(90deg,var(--gold-2),var(--neon)); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.counter small {{ color:rgba(255,255,255,.78); font-weight:600; letter-spacing:.5px; }}

.banner {{ display:grid; grid-template-columns:1.3fr 1fr; gap:40px; align-items:center; }} .steps {{ display:grid; gap:14px; }}
.step {{ display:flex; gap:14px; align-items:flex-start; background:var(--white); border-radius:16px; padding:16px 18px; box-shadow:0 8px 24px rgba(11,31,58,.07); }}
.step .n {{ width:34px; height:34px; border-radius:10px; background:var(--navy); color:var(--gold-2); font-weight:900; display:grid; place-items:center; flex:none; }}
.step b {{ display:block; }} .step span {{ color:var(--muted); font-size:.92rem; }}

.footer {{ background:#07152A; color:rgba(255,255,255,.8); padding:70px 6vw 30px; }}
.footer .cols {{ display:grid; grid-template-columns:2fr 1fr 1fr 1.3fr; gap:36px; }}
.footer h4 {{ color:var(--white); margin:0 0 14px; font-size:1rem; letter-spacing:1px; text-transform:uppercase; }}
.footer a, .footer .line {{ color:rgba(255,255,255,.7); text-decoration:none; display:block; margin-bottom:9px; }} .footer a:hover {{ color:var(--gold-2); }}
.footer .bottom {{ border-top:1px solid rgba(255,255,255,.1); margin-top:44px; padding-top:20px; display:flex; justify-content:space-between; font-size:.85rem; color:rgba(255,255,255,.5); flex-wrap:wrap; gap:10px; }}
@media (max-width:900px) {{ .counters {{ grid-template-columns:repeat(2,1fr); }} .masonry {{ grid-template-columns:1fr 1fr; grid-template-rows:200px 200px 200px; }} .tile.big {{ grid-column:span 2; grid-row:span 1; }}
  .banner, .footer .cols {{ grid-template-columns:1fr; }} .nav .links {{ display:none; }} }}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def nav(content: dict) -> None:
    name = esc(content.get("institute_name", "Institute"))
    st.html(f"""
<div class="nav">
  <div class="brand"><div class="crest">{name[:1]}</div> {name}</div>
  <div class="links"><a href="#programs">Programs</a><a href="#campus">Campus</a><a href="#admissions">Admissions</a><a href="#contact">Contact</a><a class="cta" href="?page=login" target="_self">Login / Register</a></div>
</div>""")


def hero(content: dict) -> None:
    title = esc(content.get("hero_title", ""))
    # highlight the last word in gold
    parts = title.rsplit(" ", 1)
    title_html = f"{parts[0]} <em>{parts[1]}</em>" if len(parts) == 2 else title
    ann = esc(content.get("announcements", "")).strip()
    ann_html = f'<div class="announce"><b>Announcements</b> · {ann}</div>' if ann else ""
    st.html(f"""
<section class="hero">
  <div>
    <div class="eyebrow">Admissions 2026 · Now Open</div>
    <h1>{title_html}</h1>
    <p>{esc(content.get("hero_subtitle", ""))}</p>
    {ann_html}
  </div>
</section>""")


def programs(df: pd.DataFrame) -> None:
    cards = []
    for r in df.itertuples():
        track = r.required_track if isinstance(r.required_track, str) and r.required_track else "Any track"
        cards.append(
            f'<div class="card"><div class="icon">{ICONS.get(r.code, "🎓")}</div><h3>{esc(r.name)}</h3>'
            f'<p>Code {esc(r.code)} · minimum entrance score {int(r.min_score)} · open to {esc(track)} students.</p>'
            f'<div class="meta"><span class="tag">{esc(track)}</span><span class="tag gold">{int(r.capacity)} seats</span></div></div>'
        )
    st.html(f"""
<section class="section alt" id="programs">
  <div class="kicker">Academic Excellence</div>
  <h2>Programs built for the next decade</h2>
  <p class="lead">Every program below is allocated through SEATWISEE. Seats, eligibility floors and track requirements are the live values the solver uses.</p>
  <div class="grid">{''.join(cards)}</div>
</section>""")


def campus(stats: dict) -> None:
    st.html(f"""
<section class="section navy" id="campus">
  <div class="kicker">Campus Life & Infrastructure</div>
  <h2>Where ideas get built</h2>
  <p class="lead">Fifty specialised labs, a 24×7 hackathon arena, and a 60-acre green campus ten minutes from the city.</p>
  <div class="masonry">
    <div class="tile big" style="background-image:url('{CAMPUS_IMG}')"><span>Main Academic Block</span></div>
    <div class="tile" style="background-image:url('{LAB_IMG}')"><span>Robotics & AI Lab</span></div>
    <div class="tile" style="background-image:url('{HACK_IMG}')"><span>Hackathon Arena</span></div>
    <div class="tile" style="background-image:url('{LIB_IMG}')"><span>Central Library</span></div>
    <div class="tile" style="background-image:url('{HERO_IMG}')"><span>Innovation Quad</span></div>
  </div>
  <div class="counters">
    <div class="counter"><b>{stats['programs']}</b><small>PROGRAMS</small></div>
    <div class="counter"><b>{stats['seats']}</b><small>SEATS THIS YEAR</small></div>
    <div class="counter"><b>{stats['applicants']}</b><small>APPLICANTS</small></div>
    <div class="counter"><b>50+</b><small>LABS</small></div>
    <div class="counter"><b>200+</b><small>RECRUITERS</small></div>
    <div class="counter"><b>100%</b><small>PLACEMENT ASSISTANCE</small></div>
  </div>
</section>""")


def admissions(content: dict) -> None:
    st.html(f"""
<section class="section" id="admissions">
  <div class="banner">
    <div>
      <div class="kicker">Admissions · Powered by SEATWISEE</div>
      <h2>Seat allocation you can audit</h2>
      <p class="lead">{esc(content.get("about_us", ""))}</p>
    </div>
    <div class="steps">
      <div class="step"><div class="n">1</div><div><b>Apply online</b><span>Rank up to five programs and upload your marksheet and scorecard.</span></div></div>
      <div class="step"><div class="n">2</div><div><b>Optimised allocation</b><span>Google OR-Tools CP-SAT finds the provably best fair assignment.</span></div></div>
      <div class="step"><div class="n">3</div><div><b>Transparent appeals</b><span>See exactly who is affected before any change is approved.</span></div></div>
    </div>
  </div>
</section>""")


def footer(content: dict) -> None:
    name = esc(content.get("institute_name", "Institute"))
    contact_lines = "".join(f'<span class="line">{esc(x.strip())}</span>' for x in str(content.get("contact_info", "")).split("·") if x.strip())
    st.html(f"""
<footer class="footer" id="contact">
  <div class="cols">
    <div><h4>{name}</h4><p style="max-width:40ch;line-height:1.6;color:rgba(255,255,255,.65)">{esc(content.get("hero_subtitle", ""))}</p></div>
    <div><h4>Quick links</h4><a href="#programs">Programs</a><a href="#campus">Campus</a><a href="#admissions">Admissions</a><a href="?page=login" target="_self">Portal login</a></div>
    <div><h4>Students</h4><a href="?page=login" target="_self">Register</a><a href="?page=login" target="_self">Check my seat</a><a href="#admissions">How allocation works</a></div>
    <div><h4>Contact</h4>{contact_lines}</div>
  </div>
  <div class="bottom"><span>© 2026 {name}. All rights reserved.</span><span>Admissions governed by SEATWISEE · Google OR-Tools CP-SAT</span></div>
</footer>""")


def render(c) -> None:
    """Pure informational college website. The only Streamlit widget is the Login / Register CTA."""
    from database import db_manager as db

    content = db.get_site_content(c)
    programs_df = db.load_programs(c)
    stats = {
        "programs": len(programs_df),
        "seats": int(programs_df.capacity.sum()) if len(programs_df) else 0,
        "applicants": c.execute("SELECT COUNT(*) FROM applicants WHERE status='active'").fetchone()[0],
    }
    inject_css()
    nav(content)
    hero(content)
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("Login / Register →", key="cta_login", width="stretch"):
            st.session_state["current_page"] = "login"
            st.rerun()
    with c2:
        st.markdown("Students · Admissions office · one secure gateway powered by SEATWISEE")
    programs(programs_df)
    campus(stats)
    admissions(content)
    footer(content)
