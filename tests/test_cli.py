"""CLI の出力整形とスモークテスト（API はモック）。"""
from dep_triage.cli import main, render_plan


def test_render_plan_contains_actions():
    pr = {"number": 12, "title": "Bump requests from 2.31.0 to 2.31.1"}

    results = [{"pr": pr, "facts": {}, "decision": {"action": "auto_merge",
                                                     "reasons": ["patch bump, policy conditions met"]}}]
    plan = render_plan(results, [{"number": 12, "action": "auto_merge",
                                  "reasons": [], "performed": False}], dry_run=True)
    assert "DRY-RUN PLAN" in plan
    assert "#12" in plan
    assert "auto-merge" in plan
    assert "patch bump" in plan


def test_main_smoke_with_mocked_api(monkeypatch, capsys):
    """CLI 全経路のスモークテスト（GitHub をフェイクに差し替え）。"""
    class FakeGH:
        def list_dependabot_prs(self, repo):
            return [{
                "number": 5, "title": "Bump requests from 2.31.0 to 2.31.1",
                "user": {"login": "dependabot[bot]"},
                "head": {"sha": "sha5"}, "base": {"repo": {"full_name": repo}},
                "created_at": "2026-09-01T00:00:00Z", "mergeable_state": "clean",
            }]

        def pr_files(self, repo, number):
            return ["requirements.txt"]

        def ci_state(self, repo, sha):
            return {"ci_green": True, "ci_pending": False}

        def get(self, path):
            return {"head": {"sha": "sha5"}}

    from dep_triage import cli as cli_mod
    monkeypatch.setattr(cli_mod, "GitHub", lambda: FakeGH())
    rc = main(["--repo", "owner/repo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN PLAN" in out
    assert "#5" in out
