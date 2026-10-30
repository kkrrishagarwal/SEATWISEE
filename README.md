# SEATWISEE  ·  public UI "DO! u want"

**Gateway:** the app opens on a single unified login (Email or Username + Password) plus a *Register as New Student* button; the sidebar stays hidden until you sign in. `admin` / `admin123` → admin workspace; a registered student email (password blank) → student portal. Landing-page text is editable by the admin in the **Website Editor** tab (CMS stored in the `site_content` table). Students sign in with their registered email (e.g. `applicant001@seatwisee.demo`); new students register on the landing page with two mandatory document uploads (12th marksheet, entrance scorecard) saved to `uploads/`.

Auditable, constraint-based seat allocation and decision support (hackathon PS06 / FAIRSHIFT).

* **Math**: Google OR-Tools CP-SAT. `x[i,j] ∈ {0,1}`; one seat per applicant, capacity, eligibility are hard.
  * Mode A: maximise preference points (rank 1→100, 2→50, 3→20, 4→10, 5→5).
  * Mode B: maximise preference − μ·displacement, where displacement = applicants not keeping their seat.
* **Counterfactual appeals**: clone state, force `x[s,t] = 1`, re-solve, report who moves and the preference delta.
* **Independent validator**: pure Python rule checker, zero OR-Tools; solver output is persisted only if it passes.
* **Solver statuses** are reported honestly: OPTIMAL / FEASIBLE (unproven) / INFEASIBLE (proven) / UNKNOWN (timeout).
* **Persistence**: SQLite with versioned runs, capacity-change history, appeals and an append-only audit log.
* **Dynamic forms**: admins add/remove application fields (text / number / select) in the Form Builder; responses are stored as JSON per applicant.
* **Documents**: uploads are written under secure names (`uploads/000123_12thMarksheet.pdf`), extension-whitelisted, size-capped, path-traversal guarded; the admin can preview/download them.
* **RBAC**: session-state login gateway; students see only their own dashboard (status, allocated program, receipt + document downloads).
* **Admin workspace** has five tabs: Command Center (KPIs, Mode A, occupancy) · Disruptions & Appeals (capacity shocks, withdrawals, Mode B, what-if sandbox with Sankey) · Student Records & Forms · Website Editor (CMS) · Audit Trail (validator, run history, audit log).

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m database.db_manager      # (re)seed 200 applicants / 10 programs
.venv/bin/python -m pytest -q                # 25 tests
.venv/bin/streamlit run app.py
```

## Deploy on Render (free plan)
This repo ships a `render.yaml` Blueprint for a **free** Python web service.

1. Push this repo to GitHub.
2. In Render: **New + → Blueprint → select the repo → Apply**.
3. Open the service URL. The app seeds 200 demo applicants on first boot. Admin login: `admin` / `admin123`.

The free instance has an ephemeral filesystem: the SQLite database and uploaded documents reset when the service
restarts or spins down after 15 minutes idle (first request afterwards takes ~1 minute to wake). For persistence,
switch to a paid instance and add a disk mounted at `/var/data`, then set `SEATWISEE_DB=/var/data/seatwisee.db`
and `SEATWISEE_UPLOADS=/var/data/uploads`.
