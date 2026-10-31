# SEATWISEE — project handoff and history

## 1. Identity
- Project: SEATWISEE, public brand "DO! u want", tagline "Discover Opportunities. Unlock Your Future."
- Institute identity used in the demo: Syntaxis Institute of Technology.
- Built for hackathon Achithon 2026, problem statement PS06 FAIRSHIFT (constraint-based seat allocation and decision support). Venue: R.D. Engineering College, Ghaziabad (venue only, not the owner of the project).
- Owner: Krish (GitHub kkrrishagarwal). Repo: https://github.com/kkrrishagarwal/SEATWISEE (branches master and main kept identical).
- Local path: /home/krish/Desktop/rd college /SEATWISEE, venv at .venv, Python 3.12.
- Run: cd "/home/krish/Desktop/rd college /SEATWISEE" && .venv/bin/streamlit run app.py  ->  http://localhost:8501
- Deploy target: Render free plan (https://seatwisee.onrender.com), render.yaml in repo; start command adds --server.fileWatcherType none --server.runOnSave false. Render was still serving an old build; a Manual Deploy or Render API key is needed.

## 2. Stack
Streamlit 1.66, SQLite, Google OR-Tools CP-SAT 9.15, pandas, Plotly, ReportLab, pytest, requests. Single app.py router. Lazy imports keep startup memory about 166 MB.

## 3. Architecture and key files
- app.py: loads .env, resolves st.session_state.current_page (home/public pages, login, student_portal, admin_dashboard) from role and ?page= query params; ?page=login&intent=apply[&program=CODE] sets post_login_intent, apply_intent, apply_intent_program.
- database/schema.sql, database/db_manager.py: tables programs, applicants (application_status registered/applied, eligibility_status, offer_status none/provisional/confirmed/waitlisted, status active/withdrawn, documents, form_data), preferences, allocation_runs (versions with policy_json), assignments, capacity_changes, appeals, withdrawals, notifications (dedupe_key), announcements, site_content (CMS), settings, form_schema, admin_users, password_resets, audit_log (append-only). seed_demo creates 200 applicants / 10 programmes (demo DB now has 11 programmes, 224 seats). DB file seatwisee.db is git-ignored; SEATWISEE_DB env var overrides the path.
- optimization/problem.py, cp_sat_model.py (x[i,j] booleans; constraints: one seat, capacity, eligibility, forced/forbidden/locked; objective_mode preference_first with points 100/50/20/10/5 plus merit/earliness tie-break, or merit_first lexicographic; reassign mode subtracts mu per displaced applicant; single worker, seed 7), validator.py (independent re-check), counterfactual.py (appeals), reallocation_engine.py (publish, run_initial, run_reallocation, process_withdrawal, change_capacity, confirm_offer, technical_summary, vacancy_report), metrics.py.
- services/: auth_service.py (unified login, PBKDF2 hashes, admin from admin_users; default admin/admin123), application_service.py (verify_eligibility, ineligibility_details, tracking, appeals), notification_service.py (in_app always; email via email_service.py SMTP; WhatsApp via whatsapp_service.py Meta Cloud API; statuses sent/failed/not_configured/skipped, never fake success).
- reports/: evaluation_pdf.py, application_pdf.py; ui/common.py has allotment letter, receipt, appeal PDF, charts.
- ui/design.py: shared purple design system (hero gradient header, stat/KPI cards, progress, timeline, stepper, pills, sidebar brand/profile, nav-as-menu CSS using st-key-* containers, plotly_style).
- ui/1_student_portal.py: 8 sections (Dashboard, Apply Now, My Application, Admission Result, Withdrawal, Appeal, Notifications, Downloads); apply form is one st.form("application_form") with a review step before submit.
- ui/admin/workspace.py: 13 sections grouped in 4 sidebar expanders (Command Center: Overview, Allocation, Reallocation, Analytics; Student & Program Data: Programs, Applications, Selected Candidates; Appeals & Exceptions: Appeals, Withdrawals; Settings & Logs: Settings, Notifications, Announcements, Audit History). Settings uses tabs; run-allocation and DB reset need a confirmation checkbox.
- ui/login_gateway.py: sign in, register, forgot password.
- ui/public/site.py: 7-page public website (home, about, academics, courses with search/filters and ?program=CODE detail, admissions, campus, contact) in navy/purple/gold design, mobile hamburger nav, competition-venue section. ui/public/images.py: photo-slot registry; drop photos into static/images/photos/<slot>.jpg (slots listed in README).
- .streamlit/config.toml: static serving on, toolbar minimal, theme purple #6D28D9, upload limit 8 MB.
- Tests: tests/ 49 pytest cases (allocation, reallocation, appeals, notifications, auth).

## 4. Design system
Colours: navy #0B1F3A / #122B4F, purple #6D28D9, violet #8B5CF6, lavender #EDE9FE, gold #F5B301, background #F8FAFC, text #172033, muted #64748B, border #E5E7EB, green #10B981, amber #F59E0B, red #EF4444, blue #3B82F6. Font Inter. Icons: Material Symbols Rounded via <span class="msr">name</span> inside st.html (inline SVG is stripped by st.html).

## 5. History of major steps
1. Chose PS06; built CP-SAT engine, SQLite, Streamlit, tests, PDF reports.
2. Added document uploads, dynamic form builder, RBAC login, per-applicant displacement penalty (fixed an eviction loophole).
3. UI overhauls: landing gateway, consolidated admin, student portal; then full college website, unified login, CMS, strict routing, registration decoupled from application, intent-based Apply Now.
4. Deployment to Render (free plan, no disk); Vercel rejected; memory reduced via lazy imports.
5. Full platform build: 12 admin sections, reallocation on authorised withdrawals, counterfactual appeals, notifications (email/WhatsApp), analytics, audit, settings policies.
6. Fixes: duplicate programme code error, SMTP auth error reporting, form state loss, apply-intent deep link, grouped admin sidebar, explicit ineligibility reasons.
7. Portal redesign (purple design system, ui/design.py), then public website redesign with photo placeholders.

## 6. Decisions and constraints
- Never change the CP-SAT engine, validator, schema, auth, or data during UI work.
- Credentials only in git-ignored .env (SMTP_HOST/PORT/USER/PASSWORD/FROM/TLS, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID).
- Never show a notification as sent unless the provider confirmed it.
- No R.D. Engineering College photographs until supplied; use the photo slots.
- Push normally to both master and main; no force-push.
- Use st.html for raw HTML/CSS; scope CSS with st.container(key=...) -> .st-key-<key>.

## 7. Demo data and logins
- Admin: admin / admin123 (change under Settings).
- Seeded students: applicant001@seatwisee.demo and so on (email-only login unless a password was set).

## 8. Open items
- Get Render serving the latest build (Manual Deploy or API key).
- Email: confirm which Gmail account owns the App Password; update SMTP_USER in .env and Render env vars.
- WhatsApp: needs WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID.
- Add real campus and venue photographs to static/images/photos/.
