"""SEATWISEE design system — shared purple/white UI primitives for the student and admin portals.

Everything here is presentation only: no database writes, no business rules. Helpers render HTML
through st.html (st.markdown mangles CSS) and scope CSS to Streamlit's documented `st-key-<key>`
container classes so styling survives Streamlit upgrades.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import html
import itertools

import streamlit as st

PURPLE, DEEP, VIOLET, LAVENDER, SURFACE = "#6D28D9", "#5B21B6", "#8B5CF6", "#EDE9FE", "#F5F3FF"
BG, WHITE, TEXT, MUTED, BORDER = "#F8FAFC", "#FFFFFF", "#172033", "#64748B", "#E5E7EB"
GREEN, AMBER, RED, BLUE = "#10B981", "#F59E0B", "#EF4444", "#3B82F6"
PALETTE = [PURPLE, VIOLET, "#A78BFA", "#C4B5FD", BLUE, GREEN, AMBER, RED, "#0EA5E9", "#F472B6"]

ICONS = {"bell": "<span class=\"msr\">notifications</span>", "user": "<span class=\"msr\">person</span>", "file": "<span class=\"msr\">description</span>", "check": "<span class=\"msr\">check_circle</span>", "award": "<span class=\"msr\">workspace_premium</span>", "mail": "<span class=\"msr\">mail</span>", "users": "<span class=\"msr\">group</span>", "grid": "<span class=\"msr\">grid_view</span>", "layers": "<span class=\"msr\">layers</span>", "clock": "<span class=\"msr\">schedule</span>", "alert": "<span class=\"msr\">warning</span>", "cap": "<span class=\"msr\">school</span>", "scale": "<span class=\"msr\">balance</span>", "logout": "<span class=\"msr\">logout</span>", "inbox": "<span class=\"msr\">inbox</span>", "calendar": "<span class=\"msr\">calendar_month</span>"}

esc = html.escape

GLOBAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root {{ --sw-purple:{PURPLE}; --sw-deep:{DEEP}; --sw-violet:{VIOLET}; --sw-lav:{LAVENDER}; --sw-surface:{SURFACE};
        --sw-bg:{BG}; --sw-text:{TEXT}; --sw-muted:{MUTED}; --sw-border:{BORDER}; }}
.stApp, .stApp *:not([data-testid="stIconMaterial"]):not([role="img"]):not(.msr):not(code):not(pre):not(kbd) {{ font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; }}
.msr {{ font-family: 'Material Symbols Rounded' !important; font-weight:400; font-style:normal; font-size:22px; line-height:1; display:inline-block; font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24; }}
.stApp {{ background: var(--sw-bg); color: var(--sw-text); }}
section.stMain .block-container {{ padding: 0 2rem 3rem; max-width: 1480px; }}
header[data-testid="stHeader"] {{ background: transparent; height: 2.6rem; }}
section.stMain h1, section.stMain h2, section.stMain h3, section.stMain h4, section.stMain h5 {{ color: var(--sw-text); letter-spacing:-.01em; }}
/* ---- sidebar shell ---- */
section[data-testid="stSidebar"] {{ background:#fff; border-right:1px solid var(--sw-border); }}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 1.1rem 1rem 1rem; }}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div {{ min-height: calc(100vh - 4.5rem); }}
.st-key-sidebar_profile {{ margin-top:auto; padding-top:10px; border-top:1px solid var(--sw-border); }}
.sw-brand {{ display:flex; align-items:center; gap:12px; padding:2px 4px 14px; }}
.sw-brand img {{ width:46px; height:46px; border-radius:14px; box-shadow:0 6px 16px rgba(109,40,217,.25); }}
.sw-brand b {{ display:block; font-size:1.18rem; font-weight:900; color:var(--sw-deep); letter-spacing:-.02em; line-height:1.1; }}
.sw-brand small {{ color:var(--sw-muted); font-weight:600; font-size:.74rem; }}
.sw-navhead {{ font-size:.7rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; color:var(--sw-muted); margin:10px 6px 4px; }}
.sw-profile {{ display:flex; gap:10px; align-items:center; padding:8px 4px 6px; }}
.sw-profile .av {{ width:42px; height:42px; border-radius:50%; display:grid; place-items:center; font-weight:800; color:#fff; background:linear-gradient(135deg,var(--sw-purple),var(--sw-violet)); flex:none; }}
.sw-profile b {{ display:block; font-size:.92rem; color:var(--sw-text); }} .sw-profile small {{ display:block; color:var(--sw-muted); font-size:.74rem; line-height:1.35; }}
/* ---- navigation radios styled as menus ---- */
[class*="st-key-student_nav"] [data-testid="stRadioGroup"], [class*="st-key-admin_nav_g"] [data-testid="stRadioGroup"] {{ gap:3px; }}
[class*="st-key-student_nav"] [data-testid="stRadioGroup"] > div, [class*="st-key-admin_nav_g"] [data-testid="stRadioGroup"] > div {{ width:100%; }}
[class*="st-key-student_nav"] [data-testid="stRadioOption"], [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"] {{
  width:100%; margin:0; padding:9px 12px; border-radius:12px; cursor:pointer; transition:background .15s; display:flex; align-items:center; }}
[class*="st-key-student_nav"] [data-testid="stRadioOption"] > div > div:first-child, [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"] > div > div:first-child {{ display:none; }}
[class*="st-key-student_nav"] [data-testid="stRadioOption"] p, [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"] p {{ font-size:.9rem; font-weight:600; color:#334155; margin:0; white-space:nowrap; }}
[class*="st-key-admin_nav_g"] [data-testid="stRadioOption"] p {{ font-size:.84rem; }}
[class*="st-key-admin_nav_g"] [data-testid="stRadioOption"] {{ padding:7px 10px; }}
[class*="st-key-student_nav"] [data-testid="stRadioOption"] p span[role="img"], [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"] p span[role="img"] {{ font-size:20px; margin-right:6px; color:var(--sw-muted); }}
[class*="st-key-student_nav"] [data-testid="stRadioOption"]:hover, [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"]:hover {{ background:var(--sw-surface); }}
[class*="st-key-student_nav"] [data-testid="stRadioOption"][data-selected="true"], [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"][data-selected="true"] {{
  background:var(--sw-lav); box-shadow: inset 3px 0 0 var(--sw-purple), 0 1px 0 rgba(109,40,217,.08); }}
[class*="st-key-student_nav"] [data-testid="stRadioOption"][data-selected="true"] p, [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"][data-selected="true"] p,
[class*="st-key-student_nav"] [data-testid="stRadioOption"][data-selected="true"] p span[role="img"], [class*="st-key-admin_nav_g"] [data-testid="stRadioOption"][data-selected="true"] p span[role="img"] {{ color:var(--sw-deep); font-weight:800; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{ border:none; background:transparent; box-shadow:none; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary {{ padding:6px 6px 4px; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{ font-size:.68rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:var(--sw-muted); white-space:nowrap; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] details > div {{ padding:0 0 4px; }}
/* ---- cards ---- */
div[class*="st-key-card_"] {{ position:relative; z-index:1; background:#fff; border:1px solid var(--sw-border); border-radius:18px; padding:18px 20px 16px; box-shadow:0 6px 22px rgba(23,32,51,.05); }}
div[class*="st-key-card_"] > div {{ gap:.6rem; }}
.sw-card-title {{ font-size:1.08rem; font-weight:800; color:var(--sw-text); margin:0 0 2px; display:flex; align-items:center; gap:8px; }}
.sw-card-sub {{ color:var(--sw-muted); font-size:.85rem; margin:0 0 6px; }}
/* ---- gradient header ---- */
.sw-hero {{ background:linear-gradient(118deg,{DEEP} 0%,{PURPLE} 45%,{VIOLET} 100%); color:#fff; border-radius:0 0 26px 26px; padding:30px 34px 72px; margin:0 -2rem 0; position:relative; z-index:0; box-shadow:0 12px 30px rgba(91,33,182,.25); }}
.sw-hero:after {{ content:""; position:absolute; right:-40px; top:-60px; width:260px; height:260px; border-radius:50%; background:rgba(255,255,255,.07); }}
.sw-hero .row {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; position:relative; z-index:1; }}
.sw-hero h1 {{ margin:0; font-size:2.35rem; font-weight:900; color:#fff; letter-spacing:-.02em; line-height:1.1; }}
.sw-hero .date {{ margin:6px 0 0; font-size:1rem; color:rgba(255,255,255,.85); font-weight:500; }}
.sw-hero .msg {{ margin:10px 0 0; color:rgba(255,255,255,.9); font-size:.95rem; max-width:62ch; }}
.sw-hero .chips {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
.sw-hero .chip {{ background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28); border-radius:999px; padding:4px 12px; font-size:.78rem; font-weight:700; }}
.sw-hero .chip.ok {{ background:rgba(16,185,129,.32); }} .sw-hero .chip.warn {{ background:rgba(245,158,11,.35); }} .sw-hero .chip.bad {{ background:rgba(239,68,68,.38); }}
.sw-hero .tools {{ display:flex; align-items:center; gap:14px; flex:none; }}
.sw-hero .ic {{ width:40px; height:40px; border-radius:12px; display:grid; place-items:center; background:rgba(255,255,255,.14); position:relative; }}
.sw-hero .ic .msr {{ font-size:22px; color:#fff; }}
.sw-hero .ic i {{ position:absolute; top:-6px; right:-6px; background:{RED}; color:#fff; font-style:normal; font-size:.66rem; font-weight:800; border-radius:999px; padding:1px 6px; border:2px solid {PURPLE}; }}
.sw-hero .av {{ width:46px; height:46px; border-radius:50%; display:grid; place-items:center; background:#fff; color:var(--sw-deep); font-weight:900; font-size:1rem; border:3px solid rgba(255,255,255,.6); }}
.sw-overlap {{ margin-top:-52px; position:relative; z-index:2; }}
/* ---- stat cards ---- */
.sw-stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin:14px 0 6px; }}
.sw-stat {{ border-radius:18px; padding:16px 18px; color:#fff; background:linear-gradient(135deg,{PURPLE},{VIOLET}); box-shadow:0 10px 24px rgba(109,40,217,.22); min-height:112px; display:flex; flex-direction:column; justify-content:space-between; }}
.sw-stat.light {{ background:#fff; color:var(--sw-text); border:1px solid var(--sw-border); box-shadow:0 6px 18px rgba(23,32,51,.05); }}
.sw-stat.light .lbl {{ color:var(--sw-muted); }} .sw-stat.light .ic {{ background:var(--sw-lav); color:var(--sw-purple); }}
.sw-stat.lav {{ background:linear-gradient(135deg,{LAVENDER},#DDD6FE); color:var(--sw-deep); box-shadow:none; }} .sw-stat.lav .ic {{ background:rgba(109,40,217,.15); color:var(--sw-deep); }} .sw-stat.lav .lbl {{ color:#6D28D9; }}
.sw-stat.green {{ background:linear-gradient(135deg,#059669,{GREEN}); }} .sw-stat.amber {{ background:linear-gradient(135deg,#D97706,{AMBER}); }} .sw-stat.red {{ background:linear-gradient(135deg,#DC2626,{RED}); }} .sw-stat.blue {{ background:linear-gradient(135deg,#2563EB,{BLUE}); }}
.sw-stat .top {{ display:flex; align-items:center; gap:10px; }}
.sw-stat .ic {{ width:36px; height:36px; border-radius:10px; background:rgba(255,255,255,.2); display:grid; place-items:center; flex:none; }} .sw-stat .ic .msr {{ font-size:20px; }}
.sw-stat .lbl {{ font-size:.8rem; font-weight:700; line-height:1.25; opacity:.95; }}
.sw-stat .val {{ font-size:1.9rem; font-weight:900; margin-top:10px; line-height:1; letter-spacing:-.02em; }}
.sw-stat .val small {{ font-size:.95rem; font-weight:700; opacity:.9; }}
.sw-kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:12px 0 4px; }}
.sw-kpi {{ background:#fff; border:1px solid var(--sw-border); border-radius:16px; padding:14px 16px; box-shadow:0 6px 18px rgba(23,32,51,.05); border-top:4px solid var(--sw-purple); }}
.sw-kpi.g {{ border-top-color:{GREEN}; }} .sw-kpi.a {{ border-top-color:{AMBER}; }} .sw-kpi.r {{ border-top-color:{RED}; }} .sw-kpi.b {{ border-top-color:{BLUE}; }} .sw-kpi.v {{ border-top-color:{VIOLET}; }}
.sw-kpi b {{ display:block; font-size:1.65rem; font-weight:900; color:var(--sw-text); line-height:1.1; }}
.sw-kpi span {{ display:block; color:var(--sw-muted); font-size:.74rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-top:4px; }}
/* ---- progress ---- */
.sw-prog {{ display:flex; justify-content:space-between; align-items:baseline; }} .sw-prog b {{ font-size:1.12rem; font-weight:800; }} .sw-prog .pct {{ font-size:1.3rem; font-weight:900; color:var(--sw-deep); }}
.sw-bar {{ height:10px; border-radius:999px; background:var(--sw-lav); margin:10px 0 8px; overflow:hidden; }} .sw-bar i {{ display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,{DEEP},{VIOLET}); }}
.sw-prog-steps {{ display:flex; flex-wrap:wrap; gap:6px 14px; margin-top:6px; }}
.sw-prog-steps span {{ font-size:.8rem; color:var(--sw-muted); font-weight:600; display:flex; align-items:center; gap:5px; }}
.sw-prog-steps span.d {{ color:#047857; }} .sw-prog-steps span.n {{ color:var(--sw-deep); }}
.sw-prog-steps span em {{ font-style:normal; width:16px; height:16px; border-radius:50%; display:inline-grid; place-items:center; font-size:.62rem; font-weight:800; background:#CBD5E1; color:#fff; }}
.sw-prog-steps span.d em {{ background:{GREEN}; }} .sw-prog-steps span.n em {{ background:var(--sw-purple); }}
/* ---- pills, lists, misc ---- */
.sw-pill {{ display:inline-block; padding:3px 11px; border-radius:999px; font-size:.75rem; font-weight:800; letter-spacing:.02em; background:var(--sw-lav); color:var(--sw-deep); white-space:nowrap; }}
.sw-pill.ok {{ background:#D1FAE5; color:#065F46; }} .sw-pill.warn {{ background:#FEF3C7; color:#92400E; }} .sw-pill.bad {{ background:#FEE2E2; color:#991B1B; }} .sw-pill.info {{ background:#DBEAFE; color:#1E40AF; }} .sw-pill.muted {{ background:#F1F5F9; color:#475569; }}
.sw-upnext {{ display:flex; gap:16px; align-items:flex-start; }}
.sw-upnext .ic {{ width:54px; height:54px; border-radius:16px; background:var(--sw-lav); color:var(--sw-purple); display:grid; place-items:center; flex:none; }} .sw-upnext .ic .msr {{ font-size:28px; }}
.sw-upnext h4 {{ margin:0; font-size:1.05rem; font-weight:800; }} .sw-upnext p {{ margin:4px 0 0; color:var(--sw-muted); font-size:.9rem; }}
.sw-upnext .dl {{ margin-left:auto; color:#9F1239; font-weight:800; font-size:.85rem; white-space:nowrap; }}
.sw-list {{ list-style:none; margin:0; padding:0; }} .sw-list li {{ padding:9px 0; border-bottom:1px solid #F1F5F9; font-size:.9rem; }} .sw-list li:last-child {{ border-bottom:none; }}
.sw-list li b {{ display:block; font-weight:700; color:var(--sw-text); }} .sw-list li small {{ color:var(--sw-muted); }}
.sw-facts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }}
.sw-fact {{ padding:10px 0; border-right:1px solid var(--sw-border); }} .sw-fact:last-child {{ border-right:none; }}
.sw-fact span {{ display:block; color:var(--sw-muted); font-size:.78rem; font-weight:600; }} .sw-fact b {{ display:block; font-size:1.35rem; font-weight:900; color:var(--sw-text); margin-top:2px; }}
.sw-progs {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; }}
.sw-prog-card {{ border:1px solid var(--sw-border); border-radius:16px; padding:14px 16px; background:linear-gradient(180deg,#fff,var(--sw-surface)); }}
.sw-prog-card .code {{ font-size:.72rem; font-weight:800; color:var(--sw-purple); letter-spacing:.08em; }} .sw-prog-card h4 {{ margin:2px 0 4px; font-size:1rem; font-weight:800; }}
.sw-prog-card p {{ margin:0; color:var(--sw-muted); font-size:.8rem; line-height:1.5; }} .sw-prog-card .meta {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
.sw-notif {{ border:1px solid var(--sw-border); border-left:4px solid var(--sw-purple); background:#fff; padding:12px 16px; border-radius:14px; margin-bottom:10px; box-shadow:0 4px 14px rgba(23,32,51,.04); }}
.sw-notif.unread {{ background:var(--sw-surface); }} .sw-notif .h {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }} .sw-notif b {{ font-weight:800; }} .sw-notif p {{ margin:6px 0 4px; color:#334155; font-size:.92rem; }} .sw-notif small {{ color:var(--sw-muted); }}
.sw-timeline {{ list-style:none; margin:0; padding:0 0 0 4px; border-left:2px solid var(--sw-lav); }}
.sw-timeline li {{ position:relative; padding:0 0 14px 18px; font-size:.9rem; }} .sw-timeline li:before {{ content:""; position:absolute; left:-7px; top:4px; width:12px; height:12px; border-radius:50%; background:#CBD5E1; border:2px solid #fff; }}
.sw-timeline li.d:before {{ background:{GREEN}; }} .sw-timeline li.n:before {{ background:var(--sw-purple); box-shadow:0 0 0 4px var(--sw-lav); }} .sw-timeline li b {{ display:block; font-weight:700; }} .sw-timeline li small {{ color:var(--sw-muted); }}
.sw-result {{ border-radius:20px; padding:24px 26px; border:1px solid var(--sw-border); background:#fff; }}
.sw-result.ok {{ background:linear-gradient(135deg,#ECFDF5,#F0FDF4); border-color:#A7F3D0; }} .sw-result.warn {{ background:linear-gradient(135deg,#FFFBEB,#FEF3C7); border-color:#FDE68A; }}
.sw-result.info {{ background:linear-gradient(135deg,#EFF6FF,var(--sw-surface)); border-color:#C7D2FE; }} .sw-result.bad {{ background:#FEF2F2; border-color:#FECACA; }}
.sw-result h3 {{ margin:0 0 6px; font-weight:900; font-size:1.3rem; }} .sw-result .seat {{ font-size:1.7rem; font-weight:900; color:#065F46; margin:4px 0 8px; letter-spacing:-.01em; }} .sw-result p {{ margin:0; color:#334155; }}
.sw-stepper {{ display:flex; gap:8px; margin:6px 0 14px; flex-wrap:wrap; }} .sw-stepper span {{ flex:1; min-width:120px; padding:9px 12px; border-radius:12px; background:#fff; border:1px solid var(--sw-border); font-size:.8rem; font-weight:700; color:var(--sw-muted); display:flex; align-items:center; gap:8px; }}
.sw-stepper span em {{ font-style:normal; width:22px; height:22px; border-radius:50%; background:var(--sw-lav); color:var(--sw-deep); display:inline-grid; place-items:center; font-size:.72rem; font-weight:800; }}
.sw-stepper span.on {{ border-color:var(--sw-purple); color:var(--sw-deep); background:var(--sw-surface); }} .sw-stepper span.on em {{ background:var(--sw-purple); color:#fff; }}
.sw-doc {{ display:flex; align-items:center; gap:12px; padding:12px 14px; border:1px solid var(--sw-border); border-radius:14px; background:#fff; margin-bottom:8px; }}
.sw-doc .ic {{ width:40px; height:40px; border-radius:12px; display:grid; place-items:center; background:var(--sw-lav); color:var(--sw-purple); flex:none; }} .sw-doc .ic .msr {{ font-size:22px; }}
.sw-doc b {{ display:block; font-weight:800; font-size:.92rem; }} .sw-doc small {{ color:var(--sw-muted); }}
.sw-section {{ display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin:18px 0 10px; }} .sw-section h2 {{ margin:0; font-size:1.45rem; font-weight:900; }} .sw-section p {{ margin:2px 0 0; color:var(--sw-muted); font-size:.9rem; }}
/* ---- widget polish ---- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, .stLinkButton > a {{ border-radius:12px; font-weight:700; border:1px solid var(--sw-border); }}
button[kind="primary"], button[data-testid="stBaseButton-primary"] {{ background:linear-gradient(135deg,{PURPLE},{VIOLET}) !important; border:none !important; color:#fff !important; box-shadow:0 8px 18px rgba(109,40,217,.25); }}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {{ filter:brightness(1.06); }}
.stTextInput input, .stTextArea textarea, .stNumberInput input, [data-baseweb="select"] > div, [data-baseweb="input"] {{ border-radius:12px !important; }}
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"] {{ border:1.5px solid #CBD5E1 !important; border-radius:12px !important; background:#F8FAFC !important; }}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within {{ border-color:{PURPLE} !important; background:#fff !important; box-shadow:0 0 0 4px rgba(109,40,217,.14) !important; }}
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {{ border-radius:14px; overflow:hidden; border:1px solid var(--sw-border); }}
[data-testid="stExpander"] details {{ border-radius:14px; border:1px solid var(--sw-border); background:#fff; }}
[data-testid="stMetric"] {{ background:#fff; border:1px solid var(--sw-border); border-radius:14px; padding:12px 16px; box-shadow:0 4px 14px rgba(23,32,51,.04); }}
[data-testid="stMetricLabel"] p {{ color:var(--sw-muted); font-weight:600; font-size:.8rem; }} [data-testid="stMetricValue"] {{ font-weight:900; color:var(--sw-text); }}
[data-testid="stAlert"] {{ border-radius:12px; }}
.stTabs [data-baseweb="tab-list"] {{ gap:4px; background:var(--sw-lav); padding:4px; border-radius:12px; }} .stTabs [data-baseweb="tab"] {{ border-radius:9px; padding:6px 14px; font-weight:700; }}
.stTabs [aria-selected="true"] {{ background:#fff; box-shadow:0 2px 8px rgba(23,32,51,.08); }} .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}
[data-testid="stFileUploader"] section {{ border-radius:14px; border:1.5px dashed #C4B5FD; background:var(--sw-surface); }}
[data-testid="stForm"] {{ border:none; padding:0; }}
hr {{ border-color:var(--sw-border); }}
@media (max-width: 760px) {{
  section.stMain .block-container {{ padding:0 1rem 2rem; }} .sw-hero {{ margin:0 -1rem; padding:22px 18px 64px; border-radius:0 0 22px 22px; }} .sw-hero h1 {{ font-size:1.7rem; }}
  .sw-hero .msg {{ display:none; }} .sw-stat {{ min-height:96px; }} .sw-stat .val {{ font-size:1.5rem; }} .sw-fact {{ border-right:none; border-bottom:1px solid var(--sw-border); }}
}}
</style>
"""

_card_ids = itertools.count()


def inject() -> None:
    """Inject the design system once per script run (call at the top of each portal render)."""
    global _card_ids
    _card_ids = itertools.count()
    st.html(GLOBAL_CSS)


def pill(text: str, variant: str = "") -> str:
    return f"<span class='sw-pill {variant}'>{esc(str(text))}</span>"


@contextlib.contextmanager
def card(title: str | None = None, subtitle: str | None = None, icon: str | None = None):
    """A white rounded card. Everything rendered inside the `with` block sits in the card."""
    with st.container(key=f"card_{next(_card_ids)}") as box:
        if title:
            ic = f"<span style='color:{PURPLE};display:inline-flex'>{ICONS[icon]}</span>" if icon in ICONS else ""
            st.html(f"<div class='sw-card-title'>{ic}{esc(title)}</div>" + (f"<p class='sw-card-sub'>{esc(subtitle)}</p>" if subtitle else ""))
        yield box


def section(title: str, caption: str = "", right_html: str = "") -> None:
    st.html(f"<div class='sw-section'><div><h2>{esc(title)}</h2>{f'<p>{esc(caption)}</p>' if caption else ''}</div><div>{right_html}</div></div>")


def today_label(d: _dt.date | None = None) -> str:
    d = d or _dt.date.today()
    return d.strftime("%A, %B %d, %Y").replace(" 0", " ")


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "S"


def hero(title: str, subtitle: str = "", message: str = "", chips: list[tuple[str, str]] | None = None, unread: int = 0, avatar: str = "", overlap: bool = True) -> None:
    """Purple gradient header. chips: list of (text, variant) where variant in '', 'ok', 'warn', 'bad'."""
    chip_html = "".join(f"<span class='chip {v}'>{esc(t)}</span>" for t, v in (chips or []))
    bell = f"<span class='ic'>{ICONS['bell']}{f'<i>{unread}</i>' if unread else ''}</span>"
    av = f"<span class='av'>{esc(avatar)}</span>" if avatar else ""
    st.html(f"""<div class='sw-hero'><div class='row'><div><h1>{esc(title)}</h1>{f"<p class='date'>{esc(subtitle)}</p>" if subtitle else ''}
      {f"<p class='msg'>{esc(message)}</p>" if message else ''}{f"<div class='chips'>{chip_html}</div>" if chip_html else ''}</div>
      <div class='tools'>{bell}{av}</div></div></div>""" + ("<div class='sw-overlap'></div>" if overlap else ""))


def stat_cards(items: list[dict]) -> None:
    """items: {icon, label, value, variant('' | light | lav | green | amber | red | blue), hint}."""
    cells = []
    for it in items:
        ic = ICONS.get(it.get("icon", ""), ICONS["grid"])
        hint = f"<small> {esc(it['hint'])}</small>" if it.get("hint") else ""
        cells.append(f"<div class='sw-stat {it.get('variant','')}'><div class='top'><span class='ic'>{ic}</span><span class='lbl'>{esc(str(it['label']))}</span></div><div class='val'>{esc(str(it['value']))}{hint}</div></div>")
    st.html(f"<div class='sw-stats'>{''.join(cells)}</div>")


def kpis(items: list[tuple[str, object, str]]) -> None:
    """Compact admin KPI tiles: (label, value, accent in '', g, a, r, b, v)."""
    st.html("<div class='sw-kpis'>" + "".join(f"<div class='sw-kpi {acc}'><b>{esc(str(v))}</b><span>{esc(lbl)}</span></div>" for lbl, v, acc in items) + "</div>")


def progress(title: str, done: int, total: int, steps: list[tuple[str, bool]], next_label: str = "") -> None:
    pct = int(round(100 * done / total)) if total else 0
    parts = []
    marked_next = False
    for i, (name, ok) in enumerate(steps, 1):
        cls = "d" if ok else ("n" if not marked_next else "")
        if not ok and not marked_next:
            marked_next = True
        parts.append(f"<span class='{cls}'><em>{'✓' if ok else i}</em>{esc(name)}</span>")
    st.html(f"<div class='sw-prog'><b>{esc(title)}</b><span class='pct'>{pct}%</span></div><div class='sw-bar'><i style='width:{pct}%'></i></div>"
            f"<div style='color:{MUTED};font-size:.88rem'>{done} out of {total} steps completed{(' · next: <b style=\"color:' + TEXT + '\">' + esc(next_label) + '</b>') if next_label else ''}</div>"
            f"<div class='sw-prog-steps'>{''.join(parts)}</div>")


def facts(items: list[tuple[str, object]]) -> None:
    st.html("<div class='sw-facts'>" + "".join(f"<div class='sw-fact'><span>{esc(lbl)}</span><b>{esc(str(v))}</b></div>" for lbl, v in items) + "</div>")


def stepper(steps: list[str], active: int) -> None:
    st.html("<div class='sw-stepper'>" + "".join(f"<span class='{'on' if i == active else ''}'><em>{i + 1}</em>{esc(s)}</span>" for i, s in enumerate(steps)) + "</div>")


def timeline(items: list[tuple[str, str, str]]) -> None:
    """items: (title, caption, state) with state in 'd' (done), 'n' (now), '' (later)."""
    st.html("<ul class='sw-timeline'>" + "".join(f"<li class='{s}'><b>{esc(t)}</b><small>{esc(cap)}</small></li>" for t, cap, s in items) + "</ul>")


def sidebar_brand(brand: str, institute: str, logo_url: str) -> None:
    st.html(f"<div class='sw-brand'><img src='{logo_url}' alt=''><div><b>{esc(brand)}</b><small>{esc(institute)}</small></div></div>")


def sidebar_profile(name: str, lines: list[str], on_logout) -> None:
    with st.container(key="sidebar_profile"):
        st.html(f"<div class='sw-profile'><span class='av'>{esc(initials(name))}</span><div><b>{esc(name)}</b>{''.join(f'<small>{esc(l)}</small>' for l in lines if l)}</div></div>")
        st.button("Log out", key="logout_btn", on_click=on_logout, width="stretch", icon=":material/logout:")


def refresh_button() -> None:
    """Top-of-sidebar Refresh: re-runs the page with fresh database reads, keeping sign-in and the current section."""
    st.button("Refresh", key="refresh_btn", on_click=_refresh, type="primary", width="stretch", icon=":material/refresh:",
              help="Reload this page with the latest data")
    if st.session_state.pop("_refreshed", False):
        st.toast("Refreshed with the latest data", icon="🔄")


def _refresh() -> None:
    """Re-run the page from scratch with fresh database reads; navigation and sign-in are kept."""
    st.cache_data.clear()
    st.session_state["_refreshed"] = True


def plotly_style(fig, height: int | None = None):
    """Apply the SEATWISEE palette to any Plotly figure (presentation only)."""
    fig.update_layout(template="plotly_white", colorway=PALETTE, font=dict(family="Inter, sans-serif", color=TEXT, size=12),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=16, t=48, b=20),
                      title=dict(font=dict(size=15, color=TEXT), x=0), legend=dict(orientation="h", y=-0.2, title=None))
    fig.update_xaxes(gridcolor="#EEF2F7", zerolinecolor="#EEF2F7"); fig.update_yaxes(gridcolor="#EEF2F7", zerolinecolor="#EEF2F7")
    # plotly.express pins the default blue on each trace; recolour single-colour bar/line traces to the brand palette
    for i, tr in enumerate(fig.data):
        if tr.type in ("bar", "scatter"):
            mc = getattr(tr.marker, "color", None)
            if mc is None or (isinstance(mc, str) and (mc.lower() == "#636efa" or mc.lower().startswith("#0000"))):
                tr.marker.color = PALETTE[i % len(PALETTE)]
            lc = getattr(getattr(tr, "line", None), "color", None)
            if tr.type == "scatter" and (lc is None or (isinstance(lc, str) and (lc.lower() == "#636efa" or lc.lower().startswith("#0000")))):
                tr.line.color = PALETTE[i % len(PALETTE)]
    if height:
        fig.update_layout(height=height)
    return fig
