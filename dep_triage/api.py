"""api — GitHub REST クライアント（最小限・レート制限配慮）。

認証: GITHUB_TOKEN / GH_TOKEN 環境変数（無認証でも公開リポジトリは動作するが
レート制限 60 req/h。推奨は read 権限のみの token）。
セキュリティ方針（元 issue より）: ツールは write 権限を要求しない。
auto-merge の有効化は GitHub 側がポリシー通りに実行するため、
token に write が必要になるのは --apply 実行時のみ。
"""
import os
import time

import requests

API = "https://api.github.com"
DEPENDABOT_LOGINS = ("dependabot[bot]", "dependabot-preview[bot]")


class GitHub:
    def __init__(self, token: str = None, timeout: int = 30):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.timeout = timeout
        self.session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dep-triage",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

    def get(self, path: str, params: dict = None):
        """GET 1 リクエスト。レート制限時は Retry-After を尊重して 1 回のみ待機。"""
        url = path if path.startswith("http") else f"{API}{path}"
        for attempt in range(2):
            r = self.session.get(url, params=params, timeout=self.timeout)
            if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
                wait = int(r.headers.get("Retry-After") or 60)
                if attempt == 0:
                    print(f"[api] rate limited; waiting {wait}s")
                    time.sleep(wait)
                    continue
            r.raise_for_status()
            return r.json() if r.text else None
        return None

    # ── 高レベル ──

    def list_dependabot_prs(self, repo: str) -> list:
        """オープンな Dependabot PR の生リスト（用户 login でフィルタ）。"""
        prs = []
        page = 1
        while True:
            data = self.get(f"/repos/{repo}/pulls",
                            params={"state": "open", "per_page": 100, "page": page})
            if not data:
                break
            prs.extend(data)
            if len(data) < 100:
                break
            page += 1
        return [p for p in prs if p.get("user", {}).get("login") in DEPENDABOT_LOGINS]

    def pr_files(self, repo: str, number: int, max_pages: int = 5) -> list:
        """変更ファイルのパス一覧（ページネーション付き）。

        100件/ページ × max_pages(既定5) = 最大500ファイル。
        切り詰めは scope 誤判定（依存のみ偽陽性）に繋がるため、
        無制限ではなく上限を明示して扱う。
        """
        files, page = [], 1
        while page <= max_pages:
            data = self.get(f"/repos/{repo}/pulls/{number}/files",
                            params={"per_page": 100, "page": page}) or []
            files.extend(f.get("filename", "") for f in data)
            if len(data) < 100:
                break
            page += 1
        return files

    def ci_state(self, repo: str, sha: str) -> dict:
        """CI 状態を集約する。

        check-runs が使えない（権限/未対応リポジトリ）場合は combined status に
        フォールバックする。返り値: {ci_green, ci_pending, ci_none}
        ci_none=True は「CI チェック自体が存在しない」ことを示す。
        GitHub API の注意: CI が全く無いコミットの combined status は
        state="pending" + statuses=0 で返るため、それを「CI 無し」と区別する。
        """
        try:
            runs = self.get(f"/repos/{repo}/commits/{sha}/check-runs",
                            params={"per_page": 100}) or {}
        except requests.HTTPError:
            runs = {}
        try:
            st = self.get(f"/repos/{repo}/commits/{sha}/status") or {}
        except requests.HTTPError:
            st = {}
        return _aggregate_ci(runs, st)

    def enable_auto_merge(self, repo: str, number: int, merge_method: str):
        r = self.session.put(f"{API}/repos/{repo}/pulls/{number}/auto-merge",
                             json={"merge_method": merge_method}, timeout=self.timeout)
        r.raise_for_status()
        return r.status_code

    def close_pr(self, repo: str, number: int, comment: str = None):
        if comment:
            self.comment(repo, number, comment)
        r = self.session.patch(f"{API}/repos/{repo}/pulls/{number}",
                               json={"state": "closed"}, timeout=self.timeout)
        r.raise_for_status()
        return r.status_code

    def comment(self, repo: str, number: int, text: str):
        r = self.session.post(f"{API}/repos/{repo}/issues/{number}/comments",
                              json={"body": text}, timeout=self.timeout)
        r.raise_for_status()
        return r.status_code


def _aggregate_ci(check_runs_json: dict, status_json: dict) -> dict:
    """check-runs と combined status から CI 状態を集約する（純関数）。

    - 実行中の check-run / status があれば pending
    - 失敗系 conclusion / status があれば failed
    - 両エンドポイントに何も無ければ ci_none=True（「CI 無し」を pending と混同しない）
    - 同じチェックが両方に出ても集合ベースで扱うため二重計上しない
    """
    pending, failed = False, False
    runs = check_runs_json.get("check_runs") or []
    statuses = status_json.get("statuses") or []

    for run in runs:
        if run.get("status") in ("in_progress", "queued", "waiting", "pending"):
            pending = True
        if run.get("conclusion") in ("failure", "timed_out", "cancelled",
                                     "action_required", "startup_failure", "stale"):
            failed = True
    state = status_json.get("state")
    if state == "pending" and statuses:
        pending = True
    if state == "failure":
        failed = True

    if not runs and not statuses:
        return {"ci_green": True, "ci_pending": False, "ci_none": True}
    return {"ci_green": not pending and not failed, "ci_pending": pending,
            "ci_none": False}
