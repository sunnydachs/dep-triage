"""triage オーケストレータのテスト（API はフェイクでオフライン検証）。"""
import pytest

from dep_triage import triage
from dep_triage.policy import DEFAULT_POLICY, load_policy


def _pr(number, title, sha="s1", created="2026-09-01T00:00:00Z"):
    return {
        "number": number, "title": title, "user": {"login": "dependabot[bot]"},
        "head": {"sha": sha, "ref": f"dependabot/pip/x-{number}"},
        "base": {"repo": {"full_name": "owner/repo"}},
        "created_at": created, "mergeable_state": "clean",
    }


class FakeAPI:
    """GitHub API のフェイク。シナリオは __init__ 引数で差し込む。"""

    def __init__(self, files=None, ci=None, head_sha=None, ci_after=None):
        self.files = files or {}          # number -> [paths]
        self.ci = ci or {}                # sha -> {ci_green, ci_pending}
        self.head_sha = head_sha or {}    # number -> sha（get() 用。既定は収集時と同じ）
        self.ci_after = ci_after          # 「flip_after 回以降」の ci_state が返す状態
        self.ci_calls = 0                 # ci_state の呼び出し回数（収集と再検証の区別用）
        self.flip_after = None            # None なら常に self.ci を使う
        self.auto_merged, self.closed, self.commented = [], [], []

    def pr_files(self, repo, number):
        return self.files[number]

    def ci_state(self, repo, sha):
        self.ci_calls += 1
        if self.flip_after is not None and self.ci_calls > self.flip_after:
            return self.ci_after
        return self.ci.get(sha) or {"ci_green": True, "ci_pending": False}

    def get(self, path):
        num = int(path.rsplit("/", 1)[1])
        return {"head": {"sha": self.head_sha.get(num, f"sha{num}")}}

    def enable_auto_merge(self, repo, number, merge_method):
        self.auto_merged.append(number)

    def close_pr(self, repo, number, comment=None):
        self.closed.append(number)

    def comment(self, repo, number, text):
        self.commented.append(number)


# ── collect_facts ──

def test_collect_facts_superseded_detection():
    """同一パッケージの古いバージョン PR は superseded になる。"""
    prs = [
        _pr(1, "Bump requests from 2.31.0 to 2.32.0"),
        _pr(2, "Bump requests from 2.31.0 to 2.33.0"),
    ]
    api = FakeAPI(files={1: ["requirements.txt"], 2: ["requirements.txt"]},
                  ci={"s1": {"ci_green": True, "ci_pending": False},
                      "s2": {"ci_green": True, "ci_pending": False}})
    out = triage.collect_facts(prs, api, DEFAULT_POLICY)
    by_num = {r["pr"]["number"]: r for r in out}
    assert by_num[1]["facts"]["superseded_by"] == 2
    assert by_num[2]["facts"]["superseded_by"] is None
    assert by_num[1]["decision"]["action"] == "close_superseded"


def test_collect_facts_happy_patch():
    prs = [_pr(1, "Bump requests from 2.31.0 to 2.31.1")]
    api = FakeAPI(files={1: ["requirements.txt"]},
                  ci={"sha1": {"ci_green": True, "ci_pending": False}})
    api.head_sha[1] = "sha1"
    out = triage.collect_facts(prs, api, DEFAULT_POLICY)
    assert out[0]["decision"]["action"] == "auto_merge"
    assert out[0]["facts"]["dependency_only"] is True


# ── apply: 再検証（TOCTOU 対策） ──

def _results_for(prs, api):
    return triage.collect_facts(prs, api, DEFAULT_POLICY)


def test_apply_dry_run_performs_nothing():
    prs = [_pr(1, "Bump requests from 2.31.0 to 2.31.1", sha="sha1")]
    api = FakeAPI(files={1: ["requirements.txt"]}, ci={"sha1": {"ci_green": True, "ci_pending": False}})
    api.head_sha[1] = "sha1"
    results = _results_for(prs, api)
    applied = triage.apply(api, "owner/repo", results, DEFAULT_POLICY, dry_run=True)
    assert all(not d["performed"] for d in applied)
    assert api.auto_merged == []


def test_apply_aborts_when_head_sha_changed():
    """収集後に新しいコミットが乗った PR は auto-merge を断念する。"""
    prs = [_pr(1, "Bump requests from 2.31.0 to 2.31.1", sha="sha1")]
    api = FakeAPI(files={1: ["requirements.txt"]}, ci={"sha1": {"ci_green": True, "ci_pending": False}})
    api.head_sha[1] = "sha1"
    api.get = lambda path: {"head": {"sha": "sha2-NEW"}}  # 収集後に変わった
    results = _results_for(prs, api)
    applied = triage.apply(api, "owner/repo", results, DEFAULT_POLICY, dry_run=False)
    assert applied[0]["action"] == "escalate"
    assert api.auto_merged == []


def test_apply_aborts_when_ci_failed_before_merge():
    prs = [_pr(1, "Bump requests from 2.31.0 to 2.31.1", sha="sha1")]
    api = FakeAPI(files={1: ["requirements.txt"]}, ci={"sha1": {"ci_green": True, "ci_pending": False}})
    api.head_sha[1] = "sha1"
    results = _results_for(prs, api)          # 収集時は CI 緑（1 回目の ci_state 呼び出し）
    api.ci_after = {"ci_green": False, "ci_pending": False}
    api.flip_after = 1                        # apply 時（2 回目以降）は失敗扱い
    applied = triage.apply(api, "owner/repo", results, DEFAULT_POLICY, dry_run=False)
    assert applied[0]["action"] == "escalate"
    assert api.auto_merged == []


def test_apply_happy_path_enables_auto_merge():
    prs = [_pr(1, "Bump requests from 2.31.0 to 2.31.1", sha="sha1")]
    api = FakeAPI(files={1: ["requirements.txt"]}, ci={"sha1": {"ci_green": True, "ci_pending": False}})
    api.head_sha[1] = "sha1"
    results = _results_for(prs, api)
    applied = triage.apply(api, "owner/repo", results, DEFAULT_POLICY, dry_run=False)
    assert applied[0]["action"] == "auto_merge"
    assert applied[0]["performed"] is True
    assert api.auto_merged == [1]


def test_apply_closes_superseded():
    prs = [
        _pr(1, "Bump requests from 2.31.0 to 2.32.0"),
        _pr(2, "Bump requests from 2.31.0 to 2.33.0"),
    ]
    api = FakeAPI(files={1: ["requirements.txt"], 2: ["requirements.txt"]},
                  ci={"s1": {"ci_green": True, "ci_pending": False},
                      "s2": {"ci_green": True, "ci_pending": False}})
    api.head_sha = {1: "s1", 2: "s2"}
    results = _results_for(prs, api)
    applied = triage.apply(api, "owner/repo", results, DEFAULT_POLICY, dry_run=False)
    by_num = {d["number"]: d for d in applied}
    assert by_num[1]["action"] == "close_superseded" and by_num[1]["performed"]
    assert api.closed == [1]


def test_collect_facts_policy_file_roundtrip(tmp_path):
    f = tmp_path / "dep-triage.toml"
    f.write_text('auto_merge_bumps = ["patch"]\nrebase_stale_days = 0\n')
    pol = load_policy(f)
    assert "minor" not in pol["auto_merge_bumps"]


def test_merge_state_pending_is_skipped():
    """mergeable_state が計算中（unknown）の間は skip して待つ（issue #3）。"""
    pr = _pr(1, "Bump requests from 2.31.0 to 2.31.1")
    pr["mergeable_state"] = "unknown"
    api = FakeAPI(files={1: ["requirements.txt"]},
                  ci={"sha1": {"ci_green": True, "ci_pending": False}})
    api.head_sha[1] = "sha1"
    out = triage.collect_facts([pr], api, DEFAULT_POLICY)
    assert out[0]["facts"]["merge_state_pending"] is True
    assert out[0]["decision"]["action"] == "skip"


def test_pr_files_paginates():
    """100件/ページをまたぐ diff もページ送りで全件見る（issue #2）。"""
    from dep_triage.api import GitHub

    g = GitHub(token="test")

    def fake_get(path, params=None):
        page = (params or {}).get("page", 1)
        if page == 1:
            return [{"filename": f"a{i}.txt"} for i in range(100)]
        if page == 2:
            return [{"filename": "z-last.json"}]
        return []

    g.get = fake_get
    files = g.pr_files("o/r", 1)
    assert len(files) == 101
    assert files[-1] == "z-last.json"
