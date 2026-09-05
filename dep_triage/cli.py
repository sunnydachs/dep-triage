"""cli — dep-triage コマンドライン入口。

usage:
  dep-triage --repo owner/name            # dry-run（既定）。計画を表示するだけ
  dep-triage --repo owner/name --apply    # 実際にアクションを実行（write token が必要）
  dep-triage --policy dep-triage.toml ... # ポリシー指定（無ければ安全な既定値）
"""
import argparse
import json
import sys

from dep_triage import policy as policy_mod
from dep_triage import triage as triage_mod
from dep_triage.api import GitHub

PLAN_ORDER = ("auto_merge", "close_superseded", "comment_rebase", "escalate", "skip")
PLAN_MARK = {
    "auto_merge": "🟢 auto-merge",
    "close_superseded": "🗑 close (superseded)",
    "comment_rebase": "💬 @dependabot rebase",
    "escalate": "🔔 escalate",
    "skip": "⏭ skip",
}


def render_plan(results: list, applied: list, dry_run: bool) -> str:
    done = {d["number"]: d for d in (applied or [])}
    lines = []
    mode = "DRY-RUN PLAN (no changes)" if dry_run else "APPLIED"
    lines.append(f"dep-triage — {mode}")
    counts = {}
    for r in sorted(results, key=lambda x: PLAN_ORDER.index(x["decision"]["action"])):
        a = r["decision"]["action"]
        counts[a] = counts.get(a, 0) + 1
        num = r["pr"]["number"]
        title = (r["pr"].get("title") or "")[:70]
        mark = PLAN_MARK[a]
        extra = ""
        d = done.get(num)
        if d and d.get("performed"):
            extra = " [done]"
        lines.append(f"  #{num:<6} {mark}{extra}")
        lines.append(f"          {title}")
        lines.append(f"          reasons: {'; '.join(r['decision']['reasons'])}")
    lines.append("")
    lines.append(f"summary: {json.dumps(counts, ensure_ascii=False)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dep-triage",
                                 description="Triage Dependabot PRs after CI, per project policy.")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--policy", default=None, help="TOML policy file (default: built-in safe defaults)")
    ap.add_argument("--apply", action="store_true",
                    help="perform actions (default is dry-run)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    pol = policy_mod.load_policy(args.policy)
    api = GitHub()
    prs = api.list_dependabot_prs(args.repo)
    print(f"[triage] {len(prs)} open Dependabot PRs in {args.repo}", file=sys.stderr)

    results = triage_mod.collect_facts(prs, api, pol)
    applied = triage_mod.apply(api, args.repo, results, pol, dry_run=not args.apply)

    if args.json:
        print(json.dumps({"repo": args.repo, "dry_run": not args.apply,
                          "results": [{"number": r["pr"]["number"],
                                       "facts": r["facts"],
                                       "decision": r["decision"]} for r in results],
                          "applied": applied}, ensure_ascii=False, indent=2))
    else:
        print(render_plan(results, applied, dry_run=not args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
