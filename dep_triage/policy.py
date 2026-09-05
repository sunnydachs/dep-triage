"""policy — TOML ポリシーの読み込みと triage 判定（純関数）。

元 issue の要件: "applies explicit project policy first"。
ポリシーはリポジトリ側（dep-triage.toml）に置き、ツール側に挙動を埋め込まない。

既定ポリシー（安全側）:
  - 自動マージは patch / minor のみ、major は常に人間確認
  - CI 緑・依存のみ・コンフリクト無しを全て要求
  - apply 時はヘッド SHA と CI を直前に再検証する（triage.apply 側の責務）
"""
import tomllib

DEFAULT_POLICY = {
    "auto_merge_bumps": ["patch", "minor"],
    "never_auto_merge_bumps": ["major"],
    "require_ci_green": True,
    "require_dependency_only": True,
    "close_superseded": True,
    "rebase_stale_days": 7,
    "merge_method": "squash",
    "extra_dependency_files": [],
}

_ACTIONS = ("auto_merge", "close_superseded", "comment_rebase", "escalate", "skip")


def load_policy(path=None) -> dict:
    """TOML ポリシーを読み込み、既定値とマージする（無ければ既定のみ）。"""
    merged = dict(DEFAULT_POLICY)
    if path:
        data = tomllib.loads(open(path, "rb").read().decode("utf-8"))
        unknown = set(data) - set(DEFAULT_POLICY)
        if unknown:
            raise ValueError(f"unknown policy keys: {sorted(unknown)}")
        for k, v in data.items():
            if k in ("auto_merge_bumps", "never_auto_merge_bumps") and not isinstance(v, list):
                raise ValueError(f"{k} must be a list")
            merged[k] = v
    # 相互矛盾の検査: never と auto の両方に入っている水準は never を優先して除外
    merged["auto_merge_bumps"] = [
        b for b in merged["auto_merge_bumps"]
        if b not in merged["never_auto_merge_bumps"]
    ]
    return merged


def decide(facts: dict, policy: dict) -> dict:
    """1 PR の事実からアクションを決める（純関数）。

    facts: {dependency_only, bump, ci_green, ci_pending, conflicting,
            superseded_by, stale_days}
    判定順（最初に一致した規則が勝つ）:
      1. superseded_by がある        -> close_superseded（同じパッケージの新 PR が既にある）
      2. 依存以外のファイルを含む     -> skip（本ツールの管轄外。変更しない）
      3. コンフリクトあり            -> escalate（rebase は人間/Dependabot コマンド判断）
      4. CI 未完了                   -> skip（まだ判断できない。次回実行を待つ）
      5. CI 失敗                     -> escalate
      6. major 等の禁止水準          -> escalate（人間確認）
      7. 許可水準 + 条件充足          -> auto_merge
      8. 老朽化（stale_days 以上）    -> comment_rebase（@dependabot rebase の提案）
      9. それ以外                    -> skip
    """
    reasons = []

    if policy["close_superseded"] and facts.get("superseded_by"):
        reasons.append(f"superseded by #{facts['superseded_by']}")
        return _out("close_superseded", reasons)

    if policy["require_dependency_only"] and not facts.get("dependency_only", False):
        reasons.append("contains non-dependency files")
        return _out("skip", reasons)

    if facts.get("conflicting"):
        reasons.append("merge conflicts with base branch")
        return _out("escalate", reasons)

    if facts.get("ci_pending"):
        reasons.append("CI is still running")
        return _out("skip", reasons)

    if policy["require_ci_green"] and not facts.get("ci_green", False):
        reasons.append("CI is not green")
        return _out("escalate", reasons)

    bump = facts.get("bump") or "unknown"
    if bump in policy["never_auto_merge_bumps"]:
        reasons.append(f"{bump} bump is never auto-merged")
        return _out("escalate", reasons)
    if bump not in policy["auto_merge_bumps"]:
        reasons.append(f"bump '{bump}' is not in auto_merge_bumps")
        limit = policy.get("rebase_stale_days") or 0
        if limit > 0 and facts.get("stale_days", 0) >= limit:
            reasons.append(f"stale for {facts['stale_days']} days -> suggest @dependabot rebase")
            return _out("comment_rebase", reasons)
        return _out("escalate", reasons)

    if facts.get("ci_none"):
        reasons.append("no CI configured (nothing to wait for)")
    reasons.append(f"{bump} bump, policy conditions met")
    return _out("auto_merge", reasons)


def _out(action: str, reasons: list) -> dict:
    if action not in _ACTIONS:
        raise ValueError(f"invalid action: {action}")
    return {"action": action, "reasons": reasons}
