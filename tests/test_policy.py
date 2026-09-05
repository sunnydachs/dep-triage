import pytest

from dep_triage.policy import DEFAULT_POLICY, decide, load_policy


def _facts(**kw):
    base = {"dependency_only": True, "bump": "patch", "ci_green": True,
            "ci_pending": False, "conflicting": False, "superseded_by": None,
            "stale_days": 0}
    base.update(kw)
    return base


def test_load_policy_defaults_without_file():
    p = load_policy()
    assert p["auto_merge_bumps"] == ["patch", "minor"]
    assert p["merge_method"] == "squash"


def test_load_policy_merges_toml(tmp_path):
    f = tmp_path / "dep-triage.toml"
    f.write_text('auto_merge_bumps = ["patch"]\nmerge_method = "merge"\n')
    p = load_policy(f)
    assert p["auto_merge_bumps"] == ["patch"]
    assert p["merge_method"] == "merge"
    assert p["require_ci_green"] is True  # 既定を保持


def test_load_policy_rejects_unknown_keys(tmp_path):
    f = tmp_path / "bad.toml"
    f.write_text("auto_marge_bumps = ['patch']\n")  # typo
    with pytest.raises(ValueError):
        load_policy(f)


def test_load_policy_never_wins_over_auto():
    p = load_policy()
    p["auto_merge_bumps"].append("major")
    # decide は never を優先する（load_policy が auto から major を除去する）
    p2 = load_policy()
    p2_data = dict(p2)
    p2_data["auto_merge_bumps"] = ["patch", "minor", "major"]
    p2_data["never_auto_merge_bumps"] = ["major"]
    r = decide(_facts(bump="major"), p2_data)
    assert r["action"] == "escalate"


# ── 判定マトリクス ──

def test_green_patch_is_auto_merged():
    assert decide(_facts(), DEFAULT_POLICY)["action"] == "auto_merge"


def test_green_minor_is_auto_merged():
    assert decide(_facts(bump="minor"), DEFAULT_POLICY)["action"] == "auto_merge"


def test_major_is_escalated():
    r = decide(_facts(bump="major"), DEFAULT_POLICY)
    assert r["action"] == "escalate"
    assert any("major" in x for x in r["reasons"])


def test_unknown_bump_is_escalated():
    assert decide(_facts(bump="unknown"), DEFAULT_POLICY)["action"] == "escalate"


def test_red_ci_is_escalated():
    assert decide(_facts(ci_green=False), DEFAULT_POLICY)["action"] == "escalate"


def test_pending_ci_is_skipped():
    assert decide(_facts(ci_green=False, ci_pending=True), DEFAULT_POLICY)["action"] == "skip"


def test_conflicts_are_escalated():
    assert decide(_facts(conflicting=True), DEFAULT_POLICY)["action"] == "escalate"


def test_mixed_files_are_skipped():
    assert decide(_facts(dependency_only=False), DEFAULT_POLICY)["action"] == "skip"


def test_superseded_is_closed():
    r = decide(_facts(superseded_by=42), DEFAULT_POLICY)
    assert r["action"] == "close_superseded"
    assert "42" in r["reasons"][0]


def test_stale_unknown_bump_suggests_rebase():
    r = decide(_facts(bump="unknown", stale_days=9), DEFAULT_POLICY)
    assert r["action"] == "comment_rebase"


def test_superseded_wins_over_everything():
    r = decide(_facts(superseded_by=7, bump="major", ci_green=False), DEFAULT_POLICY)
    assert r["action"] == "close_superseded"


def test_no_ci_is_transparent_in_reasons():
    """CI 無しのリポジトリで auto-merge になる場合、その旨が理由に明示される。"""
    r = decide(_facts(ci_none=True), DEFAULT_POLICY)
    assert r["action"] == "auto_merge"
    assert any("no CI configured" in x for x in r["reasons"])
