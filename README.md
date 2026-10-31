# DO! u want · SEATWISEE
**Discover Opportunities. Unlock Your Future.** — a college admission website with an intelligent, auditable seat-allocation engine.

| Experience | What it is |
|---|---|
| Public website (`?page=home…`) | Home, About Us, Academics, Courses (+ detail pages), Admissions (+ FAQ), Campus Life, Contact. CMS-editable copy, local demo imagery in `static/images/` (served by Streamlit), live program data. |
| Unified login | One sign-in for students and administrators; role resolved from the database. Account registration and forgot-password. |
| Student portal | Dashboard with application tracking · Apply Now (score, track, admin-defined fields, up to N ranked programs, two mandatory uploads) · My Application · Admission Result (accept offer, allotment letter) · Withdrawal request · Appeal · Notifications · Downloads (receipt, evaluation report, allotment). |
| Administrator workspace | Overview · Program Management · All Applications (filters, CSV/PDF) · Selected Candidates (program-wise) · Allocation Management · Reallocation Management (authorise withdrawals, capacity changes, vacancy report) · Appeals (counterfactual evaluation + decision) · Analytics · Notifications (integration status, delivery log, test send) · Announcements + website CMS · Audit History · Settings (policy, form builder, admin password). |

## Engine (Google OR-Tools CP-SAT)
* Hard constraints: one seat per applicant, program capacity, eligibility (score floor + track + ranked), withdrawn applicants unseated, confirmed admissions locked (policy), forced/forbidden pairs for appeals.
* Policies are **configurable, never invented**: `preference_first` (maximise ranked-preference points, entrance score breaks ties) or `merit_first` (lexicographic: seats filled → entrance-score merit → preferences → earliest application). Max preferences and the reallocation displacement penalty are settings too. Every published version stores its policy snapshot.
* Reallocation (withdrawals, capacity changes) re-optimises with minimal disruption; vacancies are filled by the next qualifying applicant or explained in the vacancy report.
* Appeals are evaluated counterfactually (force the request, re-optimise, report who is affected). Administrators decide.
* An **independent pure-Python validator** must pass before any version is published. Solver statuses (OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN / MODEL_INVALID) are reported honestly.

## Notifications
In-app always. Email (SMTP) and WhatsApp (Business Cloud API) send **only when configured**; every attempt is logged with the provider's real response, deduplicated per event. See `.env.example`.

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m assets.generate_images         # demo imagery (already committed)
.venv/bin/python -m database.db_manager            # (re)seed 200 synthetic applicants / 10 programs
.venv/bin/python -m pytest -q                      # test suite
.venv/bin/streamlit run app.py
```
Admin: `admin` / `admin123` (change it under Settings or set `SEATWISEE_ADMIN_PASSWORD` before first run). Demo student: `applicant001@seatwisee.demo`, no password.

## Deploy on Render (free plan)
`render.yaml` is a Blueprint. Push to GitHub → New + → Blueprint → Apply. Set the SMTP / WhatsApp variables from `.env.example` under Environment. The free instance has an ephemeral disk: data re-seeds on restart; for persistence use a paid instance with a disk and set `SEATWISEE_DB` / `SEATWISEE_UPLOADS` to it.

## Structure
```
app.py                router        ui/public/site.py     public website      ui/login_gateway.py   unified auth
ui/1_student_portal.py              ui/admin/workspace.py admin sections      ui/common.py          charts, PDFs
database/schema.sql + db_manager.py                       optimization/{problem,cp_sat_model,validator,counterfactual,reallocation_engine,metrics}.py
services/{auth,application,notification,email,whatsapp}_service.py             reports/{evaluation_pdf,application_pdf}.py
static/images + assets/generate_images.py                 tests/test_{allocation,reallocation,appeals,notifications,auth}.py
```

## Adding college photographs to the public website

The public site uses photo *slots* (see `ui/public/images.py`). Every slot shows a branded placeholder
until you drop a file into `static/images/photos/` named after the slot (jpg, jpeg, png or webp):

| Slot file | Where it appears |
|---|---|
| `hero.jpg` | Homepage hero background |
| `about.jpg` | About section (home + About page) |
| `venue.jpg` | Competition venue section (home, About, Contact) |
| `gallery_1.jpg` … `gallery_6.jpg` | Campus gallery (home shows 1–5, Campus Life shows 1–6) |
| `facility_classrooms.jpg`, `facility_labs.jpg`, `facility_library.jpg`, `facility_sports.jpg`, `facility_events.jpg`, `facility_hostel.jpg` | Campus Life facility cards |
| `head_about.jpg`, `head_academics.jpg`, `head_courses.jpg`, `head_admissions.jpg`, `head_campus.jpg`, `head_contact.jpg` | Page header backgrounds |
| `admissions.jpg` | Admissions page instructions section |
| `program_<code>.jpg` (e.g. `program_cse.jpg`) | Programme cards and programme detail pages |

No page code changes are needed. To use a different file name for a slot, add it to `OVERRIDES` in `ui/public/images.py`.
