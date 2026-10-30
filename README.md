# SEATWISEE  ·  public UI "DO! u want"

Auditable, constraint-based seat allocation and decision support (hackathon PS06 / FAIRSHIFT).

* **Math**: Google OR-Tools CP-SAT. `x[i,j] ∈ {0,1}`; one seat per applicant, capacity, eligibility are hard.
  * Mode A: maximise preference points (rank 1→100, 2→50, 3→20, 4→10, 5→5).
  * Mode B: maximise preference − μ·displacement, where displacement = applicants not keeping their seat.
* **Counterfactual appeals**: clone state, force `x[s,t] = 1`, re-solve, report who moves and the preference delta.
* **Independent validator**: pure Python rule checker, zero OR-Tools; solver output is persisted only if it passes.
* **Solver statuses** are reported honestly: OPTIMAL / FEASIBLE (unproven) / INFEASIBLE (proven) / UNKNOWN (timeout).
* **Persistence**: SQLite with versioned runs, capacity-change history, appeals and an append-only audit log.

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m database.db_manager      # (re)seed 200 applicants / 10 programs
.venv/bin/python -m pytest -q                # 17 tests
.venv/bin/streamlit run app.py
```
