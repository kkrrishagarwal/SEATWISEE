# SEATWISEE — slide-by-slide presentation content (Achithon 2026, PS06 FAIRSHIFT)

## Slide 1 — Title
SEATWISEE · public brand DO! u want · "Discover Opportunities. Unlock Your Future."
Constraint-based seat allocation and decision support for college admissions.
Problem statement PS06 · FAIRSHIFT · Achithon 2026, R.D. Engineering College, Ghaziabad (venue).

## Slide 2 — The problem
- Colleges allocate limited seats across programmes while balancing eligibility, capacity, ranked preferences and already-confirmed seats.
- When students withdraw or capacities change, manual reassignment breaks placements, creates disputes and cannot explain its decisions.
- Appeals are hard to judge: helping one applicant can displace others.
- Needed: an allocation that is valid, minimally disruptive, explainable and auditable.

## Slide 3 — Our solution in one line
SEATWISEE turns admissions into a formal optimisation model solved by Google OR-Tools CP-SAT, independently validated, and wrapped in a complete admissions platform: public website, student portal and admin workspace.

## Slide 4 — Platform overview
- Public university website (7 pages) with live programme data and CMS content.
- Unified login: students and administrators, role detected from the database, hashed passwords, registration and password reset.
- Student portal: 8 sections from application to allotment letter.
- Admin workspace: 12 operational sections plus withdrawals.
- Notification service: in-app always, email (SMTP) and WhatsApp (Meta Cloud API) with truthful delivery status.
- PDF and CSV reports, append-only audit log.

## Slide 5 — Tech stack
Python 3.12 · Streamlit · SQLite · Google OR-Tools CP-SAT · pandas · Plotly · ReportLab · pytest.
Single app.py router, lazy-loaded engine for low memory, deployable on Render free tier.

## Slide 6 — The optimisation model
- Decision variable: x[i,j] = 1 if applicant i is seated in programme j.
- Hard constraints: one seat per applicant · programme capacity · eligibility (score floor, required track, ranked only, active) · locked confirmed seats · forced seat for appeals.
- Objective (configurable policy): preference-first maximises preference points (choice 1 = 100, 2 = 50, 3 = 20, 4 = 10, 5 = 5) with entrance score then earliest application as tie-breaks; merit-first solves lexicographically: minimise displacement, maximise seats filled, merit, preferences, earliest application.
- Deterministic: single worker, fixed seed.

## Slide 7 — Minimal-disruption reallocation
- On withdrawal or capacity change the model re-solves with a per-applicant displacement penalty (default 1000), so seated applicants only move when the rules force it.
- Confirmed admissions can be locked and never moved.
- Output: who moved, who was newly seated, who lost a seat, preference delta, shown as a Sankey diagram.
- Vacancy report explains every empty seat and lists eligible waitlisted candidates.

## Slide 8 — Counterfactual appeals
- A student requests a different programme.
- The engine clones the live allocation, forces the requested seat, re-solves with confirmed seats locked and validates.
- Admin sees: feasible or proven infeasible, number of others affected, preference delta, ripple table (appellant, displaced, relocated, newly seated), resulting utilisation, recommendation (GRANT / REVIEW / REJECT / CANNOT GRANT).
- Accepting publishes a new allocation version; nothing unvalidated is ever published.

## Slide 9 — Independent validation and solver honesty
- A separate pure-Python validator re-checks every published allocation: uniqueness, capacity, eligibility, withdrawn applicants unseated, forced pairs, locked seats.
- Solver status reported exactly: OPTIMAL, FEASIBLE (not proven optimal), INFEASIBLE (proven), UNKNOWN (timeout), MODEL_INVALID.
- Every version stores its policy snapshot, parent version and notes.

## Slide 10 — Student journey
1. Register on the website; welcome notification.
2. Apply: score, track, institute-defined fields, up to N ranked programmes, two mandatory documents, review step, Application ID.
3. Dashboard shows real progress steps, status, "Up Next" action and deadline.
4. Eligibility result with programme-by-programme reasons when ineligible.
5. Allocation published, provisional offer, accept, allotment letter PDF.
6. Withdrawal request and appeal from the portal; notifications and downloads in one place.

## Slide 11 — Admin journey
1. Overview: 10 KPIs, pending tasks, occupancy chart, recent audit.
2. Verify eligibility for all applications.
3. Run initial allocation (confirmation gate), validator verdict, offers and notifications.
4. Authorise a withdrawal, automatic reallocation, Sankey of moves.
5. Evaluate and decide an appeal with the counterfactual report.
6. Analytics, notification delivery log, announcements and CMS, audit history, settings.

## Slide 12 — Analytics and transparency
Charts computed live from the database: application distribution, applicants by track, programme-wise utilisation, offer distribution, preference satisfaction, applicants moved per version, seated per version.
Metrics: fill rate, first-choice rate, top-3 rate, appeals accepted, withdrawals approved.

## Slide 13 — Design and experience
- Public site: navy, purple and gold university design, mobile hamburger navigation, photo slots ready for real campus photographs.
- Portals: purple dashboard design system with gradient headers, stat cards, progress bar, timelines, responsive down to phone width.
- Same brand across website, student and admin experiences.

## Slide 14 — Evidence it works
| Item | Result |
|---|---|
| Demo scale | 200+ applicants, 11 programmes, 224 seats |
| Initial allocation | OPTIMAL, 80% fill, 79% first choice (demo data) |
| Automated tests | 49 pytest cases: constraints, solver statuses, reallocation, appeals, notifications, auth |
| Headless UI tests | all student sections, all admin sections, deep links, filters |
| Deployment | GitHub repo, Render blueprint |

## Slide 15 — Fairness and privacy guarantees
- Same published rules for every applicant; no hidden weightings.
- Students see only their own records and documents.
- Notifications are never shown as sent unless the provider confirmed it.
- Audit log is append-only; versions are never overwritten.

## Slide 16 — Mapping to PS06 deliverables
| FAIRSHIFT requirement | SEATWISEE |
|---|---|
| Initial allocation with CP-SAT | Allocation Management |
| Reassignment after withdrawal or capacity change | Reallocation Management, Withdrawals |
| Independent constraint validation | validator.py, shown on every publish |
| Counterfactual appeal analysis | Appeals section, ripple table, PDF report |
| Solver status distinction | status badge on every run |
| Audit trail and explanations | Audit History, versions with policy snapshots |
| Web application, about 200 applicants, 10 programmes | Streamlit app with demo seed |

## Slide 17 — Roadmap
- Real email and WhatsApp credentials for live delivery.
- Campus photographs into the photo slots.
- Multi-round counselling, reservation categories, fee payment integration.
- Role hierarchy for multiple admin users.

## Slide 18 — Thank you
Live demo · GitHub: github.com/kkrrishagarwal/SEATWISEE · Team contact · "Admissions powered by SEATWISEE."

Demo cue: log in as admin (admin / admin123), run the allocation, authorise one withdrawal, evaluate one appeal.
