# SEATWISEE — 11-slide deck content (matches the Achithon 2026 template)

Project: SEATWISEE · public brand "DO! u want" · tagline "Discover Opportunities. Unlock Your Future."
Event: Achithon 2026 · Problem statement PS06 "FAIRSHIFT" · Theme: Constraint Optimization and Decision Support
Venue: R.D. Engineering College, Ghaziabad (venue only)
Live link: https://seatwisee.onrender.com · Code: https://github.com/kkrrishagarwal/SEATWISEE
Run locally: `streamlit run app.py` · demo admin login: admin / admin123

---

## Slide 1 — Title
- Project name: SEATWISEE
- One-line tagline: Fair, explainable, minimally disruptive seat allocation for college admissions.
- Team: [Team Name] · [Member names] · Problem ID: PS06 FAIRSHIFT · Theme: Constraint Optimization and Decision Support
- Sub-brand shown on the website: DO! u want — "Discover Opportunities. Unlock Your Future."

## Slide 2 — Problem Statement
**The problem (today):**
- Colleges allocate limited seats across many programmes while respecting eligibility rules, programme capacity, ranked student preferences and seats that are already confirmed.
- When students withdraw or capacities change, manual reassignment breaks existing placements, is inconsistent, and cannot explain who gained or lost a seat and why.
- Appeals are judged by hand even though accommodating one student can displace several others.
- Result: disputes, delays, and no audit trail.

**Three stat boxes (use real, sourced values):**
- Box 1: "1 seat, N rules" — every seat must satisfy capacity, eligibility, preference order and confirmed-seat protection simultaneously (PS06 requirement).
- Box 2: "~200 applicants × 10 programmes" — the scale PS06 asks a solution to handle; SEATWISEE's demo runs 200+ applicants and 11 programmes with 224 seats.
- Box 3: "0 explanations" — manual allocation gives students no evidence for their result; SEATWISEE gives a per-programme reason for every outcome.

## Slide 3 — Proposed Solution
**Idea:** Model admissions as a formal constraint-optimisation problem and solve it with Google OR-Tools CP-SAT, then wrap the engine in a complete admissions platform (public website, student portal, admin workspace) so every decision is explainable and auditable.

**How it works:**
1. Students register, apply, rank up to N programmes and upload two documents.
2. Eligibility is verified against each programme's minimum score and required track.
3. CP-SAT allocates seats under hard constraints (one seat per student, capacity, eligibility, locked confirmed seats) and a configurable objective (preference-first or merit-first).
4. An independent validator re-checks the result; only valid allocations are published, versioned and notified.
5. Withdrawals and capacity changes trigger minimal-disruption reallocation; appeals are evaluated counterfactually before a decision.

**Outcome:** Valid allocations every time, fewer disrupted students, evidence-based appeal decisions, and a complete audit history. Demo run: solver status OPTIMAL, 80% of seats filled, 79% of seated students got their first choice (synthetic data).

## Slide 4 — Unique Selling Points
- **USP 1 — Independent validation before publishing:** a separate pure-Python validator re-checks uniqueness, capacity, eligibility, withdrawn-student removal and locked seats; nothing invalid is ever published.
- **USP 2 — Minimal-disruption reallocation:** a per-student displacement penalty (default 1000) and locked confirmed seats mean reassignments move as few students as possible, with a Sankey diagram showing exactly who moved.
- **USP 3 — Counterfactual appeals:** the engine clones the live allocation, forces the requested seat, re-solves and reports feasibility, number of students affected and a ripple table, with a GRANT / REVIEW / REJECT recommendation and PDF report.
- **USP 4 — Honest status and full audit trail:** solver outcomes are reported exactly (OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN/timeout, MODEL_INVALID), every allocation version stores its policy snapshot, and the audit log is append-only. Notifications are never shown as sent unless the provider confirmed it.

## Slide 5 — Technical Approach
- **Frontend:** Streamlit 1.66 with a custom HTML/CSS design system (navy, purple, gold; Inter font; Material icons); public website, student portal, admin workspace; responsive to phone width.
- **Backend:** Python 3.12; services for authentication (PBKDF2 password hashing, role detection), applications, allocation, reallocation, appeals, notifications, PDF/CSV reports (ReportLab, pandas).
- **Database:** SQLite with tables for programmes, applicants, preferences, allocation versions, assignments, capacity changes, withdrawals, appeals, notifications, announcements, CMS content, settings, form schema and an append-only audit log.
- **AI / optimisation / APIs:** Google OR-Tools CP-SAT (constraint programming), Plotly analytics, SMTP email and Meta WhatsApp Cloud API notifications.
- **Workflow:** Student input (score, track, ranked preferences, documents) → eligibility verification → CP-SAT model build and solve → independent validation → publish version → offers, notifications and dashboards → withdrawals / capacity changes / appeals re-enter the loop.

## Slide 6 — Live Demo: Website Running
- Live link: https://seatwisee.onrender.com (or run `streamlit run app.py` locally).
- **Walkthrough:**
  1. Open the public website (DO! u want): hero, live programme cards, admission steps, announcements.
  2. Click Apply Now → register → submit an application with ranked programmes and two documents → receive Application ID.
  3. Log in as admin (admin / admin123) → verify eligibility → run initial allocation → see solver status, validator PASS and preference-satisfaction chart.
  4. Authorise one withdrawal → automatic reallocation → Sankey of who moved.
  5. Evaluate one appeal → feasibility, ripple table, recommendation → accept or reject.
  6. Back to the student portal: provisional offer, accept, download allotment letter.
- Screenshot caption: "Insert screenshot or screen recording of the running website here."

## Slide 7 — Key Features in Action
- **Home screen:** public website hero with live counters (programmes, seats, departments, applications) pulled from the database.
- **Core feature:** Admin → Allocation Management: run allocation, solver status badge, validator verdict, preference-satisfaction chart, allocation versions. (Alternative: Appeals screen with the counterfactual ripple table.)
- **Result / dashboard:** Student dashboard with real progress steps, status cards, "Up Next" action with offer deadline, and the Admission Result page with the allotment letter download.

## Slide 8 — Feasibility and Viability
**Challenges:**
- Solver time on larger cohorts and the risk of unproven (FEASIBLE) or timed-out (UNKNOWN) results.
- Data and cost constraints: colleges need something that runs on cheap hosting without licences.
- Adoption barrier: admissions staff are used to spreadsheets and need to trust automated decisions.

**How we handle them:**
- Time limits are configurable; status is reported truthfully; the validator guarantees that anything published is rule-compliant; deterministic solving (fixed seed) makes results reproducible.
- Zero-licence stack (Python, SQLite, OR-Tools, Streamlit) that runs on a free-tier server; lazy loading keeps memory near 170 MB.
- Explanations everywhere: per-programme eligibility reasons for students, Sankey and ripple tables for staff, policy snapshots per version, audit log, PDF reports; policies (objective mode, max preferences, seat locking, penalty) are editable in Settings.
- Future scale-up: PostgreSQL backend, multi-round counselling, reservation categories, fee integration, multiple admin roles.

## Slide 9 — Impact and Benefits
- **Social:** every applicant is treated by the same published rules; students get a reason for every outcome and a fair, evidence-based appeal path. Demo: 79% first-choice satisfaction, 0 constraint violations across 49 automated tests.
- **Economic:** open-source, zero-licence stack; one admissions officer can run allocation, reallocation and appeals in minutes instead of days of manual spreadsheet work; fewer disputes and re-admissions.
- **Environmental:** paperless process — digital applications, documents, offers and allotment letters; no printed merit lists or physical counselling rounds. (Keep qualitative unless a measured figure is available.)

## Slide 10 — Research and References
1. Achithon 2026 Problem Statement PS06 "FAIRSHIFT — Constraint Optimization and Decision Support" (Syntaxis / R.D. Engineering College problem set, 2026).
2. Google OR-Tools, "CP-SAT Solver" documentation — https://developers.google.com/optimization/cp/cp_solver
3. Gale, D. and Shapley, L. S. (1962), "College Admissions and the Stability of Marriage", The American Mathematical Monthly 69(1) — foundational work on preference-based admissions matching.
4. JoSAA (Joint Seat Allocation Authority) counselling process — https://josaa.nic.in — existing Indian practice for preference-based seat allocation and rounds.
5. Streamlit documentation — https://docs.streamlit.io
6. Meta, "WhatsApp Cloud API" documentation — https://developers.facebook.com/docs/whatsapp/cloud-api
7. SQLite documentation — https://www.sqlite.org/docs.html
8. SEATWISEE repository and README — https://github.com/kkrrishagarwal/SEATWISEE

## Slide 11 — Thank You
- Team: [Team Name] · [Member names]
- Email: [team email] · GitHub: https://github.com/kkrrishagarwal/SEATWISEE · Live: https://seatwisee.onrender.com
- Closing line: "Admissions powered by SEATWISEE."
