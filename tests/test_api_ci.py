"""api.py の純関数部分（CI 集約）のテスト。"""
from dep_triage.api import _aggregate_ci


def _run(status="completed", conclusion="success"):
    return {"status": status, "conclusion": conclusion}


def test_green_when_all_checks_success():
    r = _aggregate_ci({"check_runs": [_run()]}, {"state": "success", "statuses": []})
    assert r == {"ci_green": True, "ci_pending": False, "ci_none": False}


def test_pending_when_check_running():
    r = _aggregate_ci({"check_runs": [_run(status="in_progress", conclusion=None)]}, {})
    assert r["ci_pending"] is True
    assert r["ci_green"] is False


def test_failed_conclusion():
    r = _aggregate_ci({"check_runs": [_run(conclusion="failure")]}, {})
    assert r["ci_green"] is False and r["ci_pending"] is False


def test_combined_status_failure():
    r = _aggregate_ci({"check_runs": []}, {"state": "failure", "statuses": [{"state": "failure"}]})
    assert r["ci_green"] is False


def test_no_ci_at_all_is_not_pending():
    """GitHub は「CI 無し」を combined state=pending + statuses=0 で返す。
    それを pending と混同せず ci_none として返すこと。"""
    r = _aggregate_ci({"check_runs": []}, {"state": "pending", "statuses": []})
    assert r == {"ci_green": True, "ci_pending": False, "ci_none": True}


def test_pending_with_statuses_is_real_pending():
    r = _aggregate_ci({"check_runs": []},
                      {"state": "pending", "statuses": [{"state": "pending"}]})
    assert r["ci_pending"] is True
    assert r["ci_none"] is False
