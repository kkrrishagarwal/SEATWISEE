"""TDD suite for SEATWISEE: constraints, solver statuses, shock reassignment, counterfactuals, validator."""
from __future__ import annotations

import sqlite3

import pytest

from database import db_manager as db
from optimization.counterfactual import evaluate_appeal
from optimization.cp_sat_model import AllocationModel, MODE_REASSIGN, solve_initial, solve_reassign
from optimization.problem import Applicant, Program, ProblemData, points_for_rank
from optimization.validator import validate


# ----------------------------------------------------------------------------- fixtures
def tiny_problem() -> ProblemData:
    """4 applicants, 2 programs. A1/A2/A3 all want P1 first; P1 holds 2."""
    apps = [
        Applicant(1, "A1", 90, "Eng"), Applicant(2, "A2", 80, "Eng"),
        Applicant(3, "A3", 70, "Eng"), Applicant(4, "A4", 40, "Arts"),
    ]
    progs = [Program(1, "P1", "Prog 1", 2, min_score=60, required_track="Eng"), Program(2, "P2", "Prog 2", 3)]
    pref = {(1, 1): 1, (1, 2): 2, (2, 1): 1, (2, 2): 2, (3, 1): 1, (3, 2): 2, (4, 2): 1, (4, 1): 2}
    return ProblemData(apps, progs, pref)


@pytest.fixture(scope="module")
def seeded_conn() -> sqlite3.Connection:
    conn = db.get_conn(":memory:")
    db.seed_demo(conn, n_applicants=200, seed=42)
    return conn


@pytest.fixture(scope="module")
def demo_problem(seeded_conn) -> ProblemData:
    return db.build_problem(seeded_conn, previous={})


# ----------------------------------------------------------------------------- hard constraints
def test_one_seat_per_applicant_and_capacity(demo_problem):
    res = solve_initial(demo_problem)
    assert res.status == "OPTIMAL"
    assert len(res.assignment) == len(set(res.assignment))      # dict => one seat each
    cap = demo_problem.capacity
    from collections import Counter
    used = Counter(res.assignment.values())
    for pid, n in used.items():
        assert n <= cap[pid], f"program {pid} over capacity"
    assert validate(demo_problem, res.assignment).ok


def test_eligibility_is_hard():
    p = tiny_problem()
    res = solve_initial(p)
    assert res.status == "OPTIMAL"
    assert res.assignment.get(4) != 1          # A4: wrong track + low score -> never P1
    assert res.assignment[4] == 2
    assert validate(p, res.assignment).ok


def test_mode_a_maximises_preference():
    p = tiny_problem()
    res = solve_initial(p)
    # P1 (rank 1 for A1..A3) has 2 seats -> 2*100 + one Eng gets P2 at rank 2 (50) + A4 rank 1 (100) = 350
    assert res.preference_score == 350
    assert 350 <= res.objective < 351          # tie-break term is strictly below one preference point


def test_200x10_solves_fast(demo_problem):
    res = solve_initial(demo_problem, time_limit_s=20)
    assert res.status == "OPTIMAL"
    assert res.wall_time_s < 10
    assert res.assigned_count >= 170          # 190 seats, some applicants ineligible everywhere
    assert sum(res.rank_histogram.values()) == res.assigned_count


# ----------------------------------------------------------------------------- Mode B: capacity shock
def test_capacity_drop_by_5_moves_exactly_5(demo_problem):
    base = solve_initial(demo_problem)
    assert base.status == "OPTIMAL"
    prev = dict(base.assignment)

    # Pick a program that is full; shrink it by 5. Make sure slack exists elsewhere so the
    # displaced can be re-seated without pushing anyone else out.
    from collections import Counter
    used = Counter(prev.values())
    full = [pid for pid in demo_problem.program_ids if used[pid] == demo_problem.capacity[pid]]
    assert full, "need a full program for the shock test"
    shock_pid = full[0]

    p2 = db_problem_with_capacity(demo_problem, shock_pid, demo_problem.capacity[shock_pid] - 5, previous=prev)
    res = solve_reassign(p2)
    assert res.status == "OPTIMAL"
    assert validate(p2, res.assignment).ok

    moved = {a for a, (b, n) in res.changed.items()}
    left_program = [a for a in moved if prev.get(a) == shock_pid]
    assert len(left_program) == 5, f"expected exactly 5 to leave program {shock_pid}, got {len(left_program)}"
    # with mu >> preference points, nobody else should be disturbed
    assert res.reassigned_count == 5, f"collateral moves detected: {res.changed}"
    assert Counter(res.assignment.values())[shock_pid] == demo_problem.capacity[shock_pid] - 5


def db_problem_with_capacity(problem: ProblemData, pid: int, new_cap: int, previous) -> ProblemData:
    import copy
    p = copy.deepcopy(problem)
    p.program(pid).capacity = new_cap
    p.previous = dict(previous)
    return p


def test_withdrawal_frees_seat_and_keeps_everyone_else(demo_problem):
    import copy
    base = solve_initial(demo_problem)
    prev = dict(base.assignment)
    # withdraw someone who holds a seat in a full program
    from collections import Counter
    used = Counter(prev.values())
    full = next(pid for pid in demo_problem.program_ids if used[pid] == demo_problem.capacity[pid])
    victim = next(a for a, pp in prev.items() if pp == full)

    p = copy.deepcopy(demo_problem)
    p.applicant(victim).status = "withdrawn"
    p.previous = prev
    res = solve_reassign(p)
    assert res.status == "OPTIMAL"
    assert victim not in res.assignment
    rep = validate(p, res.assignment)
    assert rep.ok
    # the withdrawn applicant counts as one change; any further change must be someone gaining the seat
    others = {a: c for a, c in res.changed.items() if a != victim}
    for a, (b, n) in others.items():
        assert n is not None, "reassignment must never strip a seat from someone who had one"
    assert len(others) <= 2  # a chain of at most a couple of upgrades filling the freed seat


def test_mode_b_prefers_stability_over_preference():
    """Mode B must keep a worse-but-existing seat rather than upgrade everyone when mu is high."""
    p = tiny_problem()
    # Baseline: suboptimal but valid allocation: A3 in P1, A1 in P2
    p.previous = {3: 1, 2: 1, 1: 2, 4: 2}
    res = solve_reassign(p, mu=1000)
    assert res.status == "OPTIMAL"
    assert res.assignment == p.previous           # zero displacement beats +50 preference
    res_low_mu = AllocationModel(p, mode=MODE_REASSIGN, mu=1).solve()
    assert res_low_mu.preference_score >= res.preference_score  # low mu lets preference win


# ----------------------------------------------------------------------------- solver statuses
def test_infeasible_is_proven_and_explained():
    p = tiny_problem()
    p.previous = {}
    m = AllocationModel(p, forced={4: 1})         # A4 is ineligible for P1
    res = m.solve()
    assert res.status == "INFEASIBLE"
    assert not res.has_solution
    assert any("ineligible" in n for n in res.notes)


def test_forced_overflow_is_infeasible():
    p = tiny_problem()
    m = AllocationModel(p, forced={1: 1, 2: 1, 3: 1})   # 3 forced into capacity 2
    res = m.solve()
    assert res.status == "INFEASIBLE"
    assert any("capacity" in n for n in res.notes)


def test_status_names_distinguish_optimal_feasible_unknown(demo_problem):
    res = solve_initial(demo_problem)
    assert res.status in ("OPTIMAL", "FEASIBLE", "UNKNOWN")
    assert res.explanation
    # an absurdly tiny time limit must never be mislabeled as OPTIMAL unless proven
    quick = AllocationModel(demo_problem, time_limit_s=1e-4).solve()
    assert quick.status in ("OPTIMAL", "FEASIBLE", "UNKNOWN")
    if quick.status == "OPTIMAL":
        assert abs(quick.objective - quick.best_bound) < 1e-6


# ----------------------------------------------------------------------------- validator
def test_validator_catches_capacity_and_eligibility():
    p = tiny_problem()
    bad = {1: 1, 2: 1, 3: 1, 4: 1}               # 4 in a 2-seat program, A4 ineligible
    rep = validate(p, bad)
    rules = {v.rule for v in rep.violations}
    assert "capacity" in rules and "eligibility" in rules
    assert not rep.ok


def test_validator_catches_withdrawn_seated():
    p = tiny_problem()
    p.applicant(1).status = "withdrawn"
    rep = validate(p, {1: 1})
    assert {v.rule for v in rep.violations} >= {"withdrawn_unassigned", "eligibility"}


# ----------------------------------------------------------------------------- counterfactual appeals
def test_appeal_into_free_seat_displaces_nobody():
    p = tiny_problem()
    p.previous = {1: 1, 2: 1, 3: 2, 4: 2}        # P2 has 3 seats, 2 used
    # new applicant 5 wants P2
    p.applicants.append(Applicant(5, "A5", 50, "Arts"))
    p.pref_rank[(5, 2)] = 1
    cf = evaluate_appeal(p, 5, 2)
    assert cf.feasible and cf.solve.status == "OPTIMAL"
    assert cf.displaced_count == 0
    assert cf.alternative[5] == 2
    assert cf.recommendation.startswith("GRANT")


def test_appeal_into_full_program_displaces_exactly_one():
    p = tiny_problem()
    p.previous = {1: 1, 2: 1, 3: 2, 4: 2}        # P1 full with A1, A2; A3 appeals for P1
    cf = evaluate_appeal(p, 3, 1)
    assert cf.feasible
    assert cf.alternative[3] == 1
    displaced = [r for r in cf.ripple if r.kind == "displaced"]
    assert len(displaced) == 1
    assert displaced[0].after_program == 2        # bumped applicant lands in P2, not on the street
    assert cf.displaced_count == 1
    assert cf.validation.ok
    assert cf.preference_delta == 0               # swap of equal-rank holders: net zero


def test_appeal_ineligible_is_infeasible_with_reason():
    p = tiny_problem()
    p.previous = {1: 1, 2: 1, 3: 2, 4: 2}
    cf = evaluate_appeal(p, 4, 1)
    assert not cf.feasible
    assert cf.solve.status == "INFEASIBLE"
    assert "CANNOT GRANT" in cf.recommendation
    assert cf.pre_check_reasons


def test_appeal_does_not_mutate_live_problem(demo_problem):
    base = solve_initial(demo_problem)
    demo_problem.previous = dict(base.assignment)
    before = dict(demo_problem.previous)
    unassigned = base.unassigned[0] if base.unassigned else next(iter(base.assignment))
    target = next(pid for (a, pid) in demo_problem.pref_rank if a == unassigned)
    evaluate_appeal(demo_problem, unassigned, target)
    assert demo_problem.previous == before


# ----------------------------------------------------------------------------- persistence round-trip
def test_db_round_trip_and_audit(seeded_conn):
    conn = seeded_conn
    problem = db.build_problem(conn, previous={})
    res = solve_initial(problem)
    run_id = db.save_run(conn, mode="initial", solver_status=res.status, assignment=res.assignment, problem=problem,
                         objective=res.objective, best_bound=res.best_bound, wall_time_s=res.wall_time_s,
                         reassigned_count=0, parent_run_id=None, notes="test")
    assert db.get_current_run(conn)["id"] == run_id
    assert db.get_current_assignment_map(conn) == res.assignment
    df = db.load_assignments(conn, run_id)
    assert len(df) == 200
    audit = db.load_audit(conn)
    assert (audit.action == "run:initial").any()

    # capacity change is versioned
    old, new = db.update_capacity(conn, 1, 25, "test shock")
    assert (old, new) == (30, 25)
    assert len(db.load_capacity_changes(conn)) == 1
    p2 = db.build_problem(conn)                   # previous defaults to current run
    assert p2.previous == res.assignment
    assert p2.capacity[1] == 25


# ----------------------------------------------------------------------------- deterministic tie-breaking
def test_tie_break_prefers_higher_merit_then_earlier_application():
    """Two applicants, one seat, identical preferences: higher score wins; equal score -> earlier applied_at wins."""
    apps = [Applicant(1, "Low", 60, "Eng", applied_at="2026-10-01 10:00:00"),
            Applicant(2, "High", 90, "Eng", applied_at="2026-10-02 10:00:00")]
    progs = [Program(1, "P1", "Only", 1)]
    p = ProblemData(apps, progs, {(1, 1): 1, (2, 1): 1})
    res = solve_initial(p)
    assert res.status == "OPTIMAL" and res.assignment == {2: 1}

    apps = [Applicant(1, "Later", 75, "Eng", applied_at="2026-10-05 10:00:00"),
            Applicant(2, "Earlier", 75, "Eng", applied_at="2026-10-01 10:00:00")]
    p = ProblemData(apps, progs, {(1, 1): 1, (2, 1): 1})
    res = solve_initial(p)
    assert res.assignment == {2: 1}


def test_tie_break_never_overrides_preference(demo_problem):
    """Scaling guarantee: the solution must equal the pure preference optimum."""
    res = solve_initial(demo_problem)
    pure = AllocationModel(demo_problem, tie_break=False).solve()
    assert pure.status == res.status == "OPTIMAL"
    assert res.preference_score == pure.preference_score
    assert 0 <= res.objective - res.preference_score < 1


def test_solve_is_deterministic(demo_problem):
    a = solve_initial(demo_problem).assignment
    b = solve_initial(demo_problem).assignment
    assert a == b


# ----------------------------------------------------------------------------- dynamic forms & documents
def test_form_schema_crud_and_validation(seeded_conn):
    conn = seeded_conn
    schema = db.load_form_schema(conn)
    assert {f["field_key"] for f in schema} >= {"category", "city", "phone"}
    key = db.add_form_field(conn, label="Hostel Required?", field_type="select", required=True, options=["Yes", "No"])
    assert key == "hostel_required"
    key2 = db.add_form_field(conn, label="Hostel Required?", field_type="text", required=False)
    assert key2 == "hostel_required_2"          # duplicate labels get unique keys
    schema = db.load_form_schema(conn)
    problems = db.validate_form_response(schema, {"category": "OBC", "city": "Pune", "phone": "9000000000", "hostel_required": "Maybe"})
    assert any("Hostel Required?" in p for p in problems)
    problems = db.validate_form_response(schema, {"category": "OBC", "city": "Pune", "phone": "9000000000", "hostel_required": "Yes", "gap_years": "x"})
    assert any("must be a number" in p for p in problems)
    db.remove_form_field(conn, key); db.remove_form_field(conn, key2)
    assert not any(f["field_key"].startswith("hostel") for f in db.load_form_schema(conn))
    with pytest.raises(ValueError):
        db.add_form_field(conn, label="Bad", field_type="select", required=True, options=[])


def test_document_upload_secure_path(seeded_conn, tmp_path, monkeypatch):
    conn = seeded_conn
    monkeypatch.setattr(db, "UPLOAD_DIR", tmp_path / "uploads")
    aid = db.add_applicant(conn, name="Doc Tester", email="doc@test.demo", score=70, track="Engineering",
                           ranked_program_ids=[1], form_data={"category": "General", "city": "Pune", "phone": "9"})
    rel = db.save_document(conn, aid, "marksheet", "../../etc/passwd.PDF", b"%PDF-1.4 fake")
    assert rel == f"uploads/{aid:06d}_12thMarksheet.pdf"       # client filename never used
    assert (tmp_path / rel).read_bytes().startswith(b"%PDF")
    row = conn.execute("SELECT marksheet_path, scorecard_path FROM applicants WHERE id = ?", (aid,)).fetchone()
    assert row["marksheet_path"] == rel and row["scorecard_path"] is None
    assert db.resolve_document(rel) == (tmp_path / rel).resolve()
    assert db.resolve_document("uploads/../schema.sql") is None  # traversal guard
    with pytest.raises(ValueError):
        db.save_document(conn, aid, "scorecard", "virus.exe", b"MZ")
    with pytest.raises(ValueError):
        db.save_document(conn, aid, "scorecard", "big.png", b"0" * (db.MAX_UPLOAD_BYTES + 1))
    # re-upload with a different extension replaces the old file
    db.save_document(conn, aid, "marksheet", "scan.jpg", b"\xff\xd8 jpeg")
    assert not (tmp_path / rel).exists()
    assert (tmp_path / f"uploads/{aid:06d}_12thMarksheet.jpg").exists()


def test_seeded_users_have_simulated_paths(seeded_conn):
    df = db.load_applicants_full(seeded_conn)
    assert df.marksheet_path.str.startswith("uploads/").all()
    assert not df.marksheet_on_disk.iloc[:200].any()          # simulated, not materialised
    assert "Category" in df.columns and df.Category.notna().all()


# ----------------------------------------------------------------------------- CMS site content
def test_site_content_seed_update_reset(seeded_conn):
    conn = seeded_conn
    content = db.get_site_content(conn)
    assert content["hero_title"] == db.DEFAULT_SITE_CONTENT["hero_title"][1]
    assert {"announcements", "about_us"} <= set(content)
    db.set_site_content(conn, "hero_title", "Admissions 2026")
    assert db.get_site_text(conn, "hero_title") == "Admissions 2026"
    db.init_db(conn)                                   # re-running the migration must NOT overwrite edits
    assert db.get_site_text(conn, "hero_title") == "Admissions 2026"
    db.reset_site_content(conn, "hero_title")
    assert db.get_site_text(conn, "hero_title") == db.DEFAULT_SITE_CONTENT["hero_title"][1]
    with pytest.raises(ValueError):
        db.set_site_content(conn, "bad key!", "x")
    assert (db.load_audit(conn).action == "site_content_updated").any()


def test_unified_login_resolution(seeded_conn, monkeypatch):
    from ui import auth
    state = {}
    monkeypatch.setattr(auth.st, "session_state", state, raising=False)
    assert auth.login_unified("admin", "admin123", seeded_conn) == "admin"
    assert auth.login_unified("admin", "nope", seeded_conn) is None
    assert auth.login_unified("applicant001@seatwisee.demo", "", seeded_conn) == "student"
    assert auth.login_unified("ghost@nowhere.io", "", seeded_conn) is None
    assert auth.login_unified("", "", seeded_conn) is None


# ----------------------------------------------------------------------------- accounts vs applications
def test_register_then_apply_enters_pool(seeded_conn, monkeypatch, tmp_path):
    conn = seeded_conn
    monkeypatch.setattr(db, "UPLOAD_DIR", tmp_path / "uploads")
    aid = db.register_account(conn, name="Onboard Test", email="onboard@test.io", phone="9876543210", address="Pune", password="hunter2")
    row = db.find_applicant_by_email(conn, "onboard@test.io")
    assert row["application_status"] == "registered" and not db.has_applied(row)
    assert db.verify_password(row["password_hash"], "hunter2") and not db.verify_password(row["password_hash"], "wrong")
    assert aid not in db.build_problem(conn, previous={}).applicant_ids      # no application -> not in solver pool
    with pytest.raises(ValueError):
        db.register_account(conn, name="Dup", email="onboard@test.io", phone="1", address="x", password="hunter2")
    with pytest.raises(ValueError):
        db.register_account(conn, name="Short", email="s@s.io", phone="1", address="x", password="123")
    with pytest.raises(ValueError):
        db.submit_application(conn, aid, score=70, track="Engineering", ranked_program_ids=[])
    db.save_document(conn, aid, "marksheet", "m.pdf", b"%PDF-1.4 x")
    db.save_document(conn, aid, "scorecard", "s.pdf", b"%PDF-1.4 y")
    db.submit_application(conn, aid, score=81, track="Engineering", ranked_program_ids=[1, 2, 3], form_data={"city": "Pune"})
    row = db.find_applicant_by_email(conn, "onboard@test.io")
    assert db.has_applied(row) and row["score"] == 81 and row["track"] == "Engineering"
    p = db.build_problem(conn, previous={})
    assert aid in p.applicant_ids and p.pref_rank[(aid, 1)] == 1 and p.pref_rank[(aid, 3)] == 3
    res = solve_initial(p)
    assert res.status == "OPTIMAL" and validate(p, res.assignment).ok
    actions = set(db.load_audit(conn).action)
    assert {"account_registered", "application_submitted"} <= actions


def test_student_login_requires_password_when_account_has_one(seeded_conn, monkeypatch):
    from ui import auth
    monkeypatch.setattr(auth.st, "session_state", {}, raising=False)
    db.register_account(seeded_conn, name="PW Test", email="pw@test.io", phone="1", address="x", password="secret9")
    assert auth.login_unified("pw@test.io", "secret9", seeded_conn) == "student"
    assert auth.login_unified("pw@test.io", "", seeded_conn) is None
    assert auth.login_unified("pw@test.io", "nope", seeded_conn) is None
    assert auth.login_unified("applicant002@seatwisee.demo", "", seeded_conn) == "student"   # seeded: no password
