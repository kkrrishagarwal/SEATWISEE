"""Student-submitted appeals: submission, counterfactual evaluation, admin decision, publication."""
import pytest

from database import db_manager as db
from optimization import reallocation_engine as re_
from services import application_service as aps


@pytest.fixture
def conn():
    c = db.get_conn(":memory:")
    db.seed_demo(c, n_applicants=60, seed=11)
    for r in c.execute("SELECT id, capacity FROM programs").fetchall():
        c.execute("UPDATE programs SET capacity = ? WHERE id = ?", (max(2, r["capacity"] // 4), r["id"]))
    c.commit()
    re_.run_initial(c)
    return c


def _seated_at_rank_2_with_eligible_first(conn):
    problem = db.build_problem(conn)
    cur = problem.previous
    for a, p in cur.items():
        if problem.pref_rank.get((a, p)) == 2:
            first = next(pid for (x, pid), r in problem.pref_rank.items() if x == a and r == 1)
            if problem.is_eligible(a, first):
                return a, first
    pytest.skip("no suitable applicant in this seed")


def test_student_appeal_lifecycle_accept(conn):
    a, target = _seated_at_rank_2_with_eligible_first(conn)
    appeal_id = aps.submit_student_appeal(conn, a, target, "First choice, lives nearby.")
    with pytest.raises(ValueError):
        aps.submit_student_appeal(conn, a, target, "duplicate")
    cf = aps.evaluate_existing_appeal(conn, appeal_id)
    row = conn.execute("SELECT * FROM appeals WHERE id=?", (appeal_id,)).fetchone()
    assert row["decision"] == "evaluated" and row["source"] == "student" and row["solver_status"] == cf.solve.status
    if cf.feasible:
        run_id = aps.decide_appeal(conn, appeal_id, accept=True)
        assert run_id and db.get_current_assignment_map(conn)[a] == target
        assert db.get_current_run(conn)["mode"] == "appeal"
        assert conn.execute("SELECT decision FROM appeals WHERE id=?", (appeal_id,)).fetchone()[0] == "accepted"
    else:
        with pytest.raises(ValueError):
            aps.decide_appeal(conn, appeal_id, accept=True)
    ev = set(db.load_notifications(conn, a).event)
    assert "appeal_submitted" in ev


def test_appeal_reject_keeps_allocation(conn):
    a, target = _seated_at_rank_2_with_eligible_first(conn)
    before = db.get_current_assignment_map(conn)
    appeal_id = aps.submit_student_appeal(conn, a, target, "please")
    aps.evaluate_existing_appeal(conn, appeal_id)
    assert aps.decide_appeal(conn, appeal_id, accept=False) is None
    assert db.get_current_assignment_map(conn) == before
    assert "appeal_evaluated" in set(db.load_notifications(conn, a).event)


def test_appeal_respects_confirmed_seats(conn):
    a, target = _seated_at_rank_2_with_eligible_first(conn)
    # confirm everyone currently in the target program -> appeal must not displace them
    holders = [x for x, p in db.get_current_assignment_map(conn).items() if p == target]
    for h in holders:
        re_.confirm_offer(conn, h)
    appeal_id = aps.submit_student_appeal(conn, a, target, "want in")
    cf = aps.evaluate_existing_appeal(conn, appeal_id)
    if cf.feasible:
        assert all(cf.alternative.get(h) == target for h in holders)
        assert cf.validation.ok
