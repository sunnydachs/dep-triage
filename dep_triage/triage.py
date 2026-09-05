"""triage — 収集 → 事実化 → 判定 → 適用（dry-run 規定）のオーケストレータ。

元 issue の要件: "Revalidate author, head SHA, changed-file scope, and CI state
immediately before enabling auto-merge"。
--apply 時も auto_merge 前に最新状態を再取得し、収集時と head SHA が
変わっていた場合は自動マージを断念する（TOCTOU 対策）。
"""
from datetime import datetime, timezone

from dep_triage import policy as policy_mod
from dep_triage import scope as scope_mod
from dep_triage import semver as semver_mod


def _parse_created(pr: dict) -> str:
    return pr.get("created_at") or ""


def _stale_days(pr: dict, now: datetime) -> int:
    created = _parse_created(pr)
    if not created:
        return 0
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return max(0, (now - dt).days)
    except ValueError:
        return 0


def collect_facts(prs: list, api, policy: dict, now: datetime = None) -> list:
    """オープン Dependabot PR 群 → 1 PR あたりの事実 + 判定のリスト。"""
    now = now or datetime.now(timezone.utc)

    # 先に全 PR の semver を解析して superseded を確定させる
    parsed = []
    for pr in prs:
        info = semver_mod.parse_bump(pr.get("title", ""))
        parsed.append({"pr": pr, "info": info})

    # 同一パッケージで新しいバージョンの PR が別にある → 古い方は superseded
    best = {}
    for i, item in enumerate(parsed):
        pkg, to = item["info"]["package"], item["info"]["to"]
        if not pkg or not to:
            continue
        cur = best.get(pkg)
        if cur is None or semver_mod.is_newer(cur["info"]["to"], to):
            best[pkg] = item
    for item in parsed:
        pkg, to, num = item["info"]["package"], item["info"]["to"], item["pr"]["number"]
        winner = best.get(pkg)
        if winner and winner["pr"]["number"] != num and to and winner["info"]["to"]:
            # 自分より新しいバージョンの PR が残っている場合のみ superseded
            if semver_mod.is_newer(to, winner["info"]["to"]):
                item["superseded_by"] = winner["pr"]["number"]
            else:
                item["superseded_by"] = None
        else:
            item["superseded_by"] = None

    results = []
    for item in parsed:
        pr = item["pr"]
        paths = api.pr_files(pr["base"]["repo"]["full_name"], pr["number"])
        sc = scope_mod.scope_check(paths)
        ci = api.ci_state(pr["base"]["repo"]["full_name"], pr["head"]["sha"])
        facts = {
            "dependency_only": sc["dependency_only"],
            "offending_files": sc["offending"][:5],
            "bump": item["info"]["bump"],
            "package": item["info"]["package"],
            "ci_green": ci["ci_green"],
            "ci_pending": ci["ci_pending"],
            "ci_none": ci.get("ci_none", False),
            "conflicting": pr.get("mergeable_state") == "dirty",
            "superseded_by": item["superseded_by"],
            "stale_days": _stale_days(pr, now),
            "head_sha": pr["head"]["sha"],
        }
        decision = policy_mod.decide(facts, policy)
        results.append({"pr": pr, "facts": facts, "decision": decision})
    return results


def apply(api, repo: str, results: list, pol: dict, dry_run: bool = True) -> list:
    """判定に従ってアクションを実行する。dry_run=True（既定）は何も変更しない。

    auto_merge 実行前の再検証: ヘッド SHA が収集時から変わっていないか、
    CI が今も緑かを直前に確認し、変わっていたら escalate に切り替える。
    """
    done = []
    for r in results:
        num = r["pr"]["number"]
        action = r["decision"]["action"]
        record = {"number": num, "action": action, "reasons": r["decision"]["reasons"],
                  "performed": False}

        # dry-run は一切の API 書き込み・再検証を行わず計画のみ返す
        if dry_run or action == "skip":
            done.append(record)
            continue

        if action == "auto_merge":
            # ── 再検証（TOCTOU 対策） ──
            fresh = api.get(f"/repos/{repo}/pulls/{num}") or {}
            if fresh.get("head", {}).get("sha") != r["facts"]["head_sha"]:
                record["action"] = "escalate"
                record["reasons"] = r["decision"]["reasons"] + [
                    "head SHA changed since triage — re-run before merging"]
                done.append(record)
                continue
            ci = api.ci_state(repo, fresh["head"]["sha"])
            if not ci["ci_green"] or ci["ci_pending"]:
                record["action"] = "escalate"
                record["reasons"] = r["decision"]["reasons"] + [
                    "CI state changed before merge — re-run"]
                done.append(record)
                continue
            scope = scope_mod.scope_check(api.pr_files(repo, num))
            if pol["require_dependency_only"] and not scope["dependency_only"]:
                record["action"] = "escalate"
                record["reasons"] = r["decision"]["reasons"] + [
                    "changed-file scope changed before merge — re-run"]
                done.append(record)
                continue
            api.enable_auto_merge(repo, num, pol["merge_method"])
            record["performed"] = True
            done.append(record)
            continue

        if action == "close_superseded":
            api.close_pr(repo, num,
                         comment="dep-triage: superseded by a newer version PR for the same package.")
            record["performed"] = True
            done.append(record)
            continue

        if action == "comment_rebase":
            api.comment(repo, num, "@dependabot rebase")
            record["performed"] = True
            done.append(record)
            continue

        # escalate / その他は報告のみ（変更しない）
        done.append(record)
    return done
