"""Lifecycle tests: publish, offers, confirmed-seat lock, authorised withdrawal, capacity change, vacancy report, policy modes."""
from collections import Counter

import pytest

from database import db_manager as db
from optimization import reallocation_engine as re_
from optimization.cp_sat_model import AllocationModel, solve_initial
from optimization.validator import validate


@pytest.fixture
def conn():
    c = db.get_conn(":memory:")
    db.seed_demo(c, n_applicants=60, seed=7)
    _contest(c)
    return c


def _contest(c):
    """Shrink capacities so programs are genuinely contested (full programs, waitlist, rank-2 placements)."""
    for r in c.execute("SELECT id, capacity FROM programs").fetchall():
        c.execute("UPDATE programs SET capacity = ? WHERE id = ?", (max(2, r["capacity"] // 4), r["id"]))
    c.commit()


def test_initial_publish_sets_offers_and_notifies(conn):
    out = re_.run_initial(conn)
    assert out.published and out.solve.status == "OPTIMAL" and out.validation.ok
    offers = {r["offer_status"] for r in conn.execute("SELECT offer_status FROM applicants")}
    assert offers <= {"provisional", "waitlisted"}
    n = db.load_notifications(conn, limit=2000)
    assert ((n.event == "provisional_offer") & (n.channel == "in_app")).sum() == out.solve.assigned_count
    assert (n[n.channel == "in_app"].status == "sent").all()
    assert set(n[n.channel == "email"].status) <= {"not_configured", "skipped"}   # no SMTP in tests, never claims 'sent'
    run = db.get_current_run(conn)
    assert run["policy_json"] and "objective_mode" in run["policy_json"]


def test_invalid_solution_is_never_published(conn, monkeypatch):
    re_.run_initial(conn)
    problem = db.build_problem(conn)
    res = solve_initial(problem)
    res.assignment = dict(res.assignment)
    bad = next(a for a in problem.active_applicant_ids if a not in res.assignment)
    res.assignment[bad] = 1      # ineligible applicant forced into a program -> validator must block
    before = len(db.load_runs(conn))
    out = re_.publish(conn, res, problem, mode="initial", notes="tampered")
    assert not out.published and not out.validation.ok and len(db.load_runs(conn)) == before


def test_confirmed_seat_is_locked_during_reallocation(conn):
    re_.run_initial(conn)
    cur = db.get_current_assignment_map(conn)
    problem = db.build_problem(conn)
    used = Counter(cur.values())
    full = next(p for p in problem.program_ids if used[p] == problem.capacity[p])
    holder = next(a for a, p in cur.items() if p == full)
    assert re_.confirm_offer(conn, holder)
    out = re_.change_capacity(conn, full, problem.capacity[full] - 3, "lab closed")
    assert out.published and out.validation.ok
    assert db.get_current_assignment_map(conn)[holder] == full          # confirmed seat untouched
    assert conn.execute("SELECT offer_status FROM applicants WHERE id=?", (holder,)).fetchone()[0] == "confirmed"
    assert Counter(db.get_current_assignment_map(conn).values())[full] == problem.capacity[full] - 3


def test_authorised_withdrawal_releases_seat_keeps_record_and_reallocates(conn):
    re_.run_initial(conn)
    cur = db.get_current_assignment_map(conn)
    leaver = next(iter(cur))
    wid = db.request_withdrawal(conn, leaver, "accepted elsewhere")
    assert db.load_withdrawals(conn, "requested").shape[0] == 1
    out = re_.process_withdrawal(conn, wid, approve=True, actor="admin")
    assert out is not None and out.published
    row = conn.execute("SELECT * FROM applicants WHERE id=?", (leaver,)).fetchone()
    assert row["status"] == "withdrawn" and row["offer_status"] == "none"          # record retained, not deleted
    assert leaver not in db.get_current_assignment_map(conn)
    w = db.get_withdrawal(conn, wid)
    assert w["status"] == "approved" and w["run_id_after"] == out.run_id and w["released_program_id"] == cur[leaver]
    ev = set(db.load_notifications(conn, leaver).event)
    assert "withdrawal_confirmed" in ev
    assert validate(db.build_problem(conn), db.get_current_assignment_map(conn)).ok


def test_withdrawal_rejection_changes_nothing(conn):
    re_.run_initial(conn)
    runs_before = len(db.load_runs(conn))
    leaver = next(iter(db.get_current_assignment_map(conn)))
    wid = db.request_withdrawal(conn, leaver, "changed my mind")
    assert re_.process_withdrawal(conn, wid, approve=False) is None
    assert db.get_withdrawal(conn, wid)["status"] == "rejected"
    assert conn.execute("SELECT status FROM applicants WHERE id=?", (leaver,)).fetchone()[0] == "active"
    assert len(db.load_runs(conn)) == runs_before


def test_capacity_cut_then_restore_never_strands_an_eligible_applicant(conn):
    """Cutting a full program moves/bumps someone; restoring it must leave every previously seated applicant seated."""
    re_.run_initial(conn)
    problem = db.build_problem(conn)
    cur = db.get_current_assignment_map(conn)
    used = Counter(cur.values())
    full = next(p for p in problem.program_ids if used[p] == problem.capacity[p])
    out = re_.change_capacity(conn, full, problem.capacity[full] - 1, "temporary")
    assert out.published and out.comparison["moved_count"] >= 1
    assert Counter(db.get_current_assignment_map(conn).values())[full] == problem.capacity[full] - 1
    out2 = re_.change_capacity(conn, full, problem.capacity[full], "restored")
    assert out2.published
    now = db.get_current_assignment_map(conn)
    assert all(a in now for a in cur)                       # nobody who had a seat ends up without one
    assert validate(db.build_problem(conn), now).ok


def test_vacancy_report_explains_unfilled_seats(conn):
    re_.run_initial(conn)
    rep = re_.vacancy_report(conn)
    assert isinstance(rep, list)
    for r in rep:
        assert r["vacant"] > 0 and r["explanation"]


def test_merit_first_policy_is_lexicographic(conn):
    db.set_setting(conn, "objective_mode", "merit_first")
    out = re_.run_initial(conn)
    assert out.published and out.solve.status == "OPTIMAL"
    assert "merit_first" in out.solve.notes[0]
    problem = db.build_problem(conn, previous={})
    pref = AllocationModel(problem, objective_mode="preference_first").solve()
    # Level 1 (seats filled) can never be worse than the preference-first solution
    assert out.solve.assigned_count >= pref.assigned_count
    assert validate(problem, out.solve.assignment).ok


def test_max_preferences_setting_enforced(conn):
    db.set_setting(conn, "max_preferences", "2")
    aid = db.register_account(conn, name="Pref Test", email="pref@test.io", phone="1", address="x", password="secret1")
    with pytest.raises(ValueError):
        db.submit_application(conn, aid, score=70, track="Engineering", ranked_program_ids=[1, 2, 3])
    db.submit_application(conn, aid, score=70, track="Engineering", ranked_program_ids=[1, 2])
