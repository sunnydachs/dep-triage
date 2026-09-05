# dep-triage

**Triage Dependabot PRs after CI runs, per project policy. Dry-run by default.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-47%20passing-brightgreen.svg)](tests/)

English | [日本語](README.ja.md)

<!-- Sync with README.ja.md as of commit e5d3ead (see git log for the latest sync point) -->

`dep-triage` sorts open Dependabot PRs into five buckets, according to a policy file you check into your repository:

- 🟢 **auto-merge** — patch/minor bumps with green CI, dependency-only changes, no conflicts
- 🔔 **escalate** — major bumps, failed CI, conflicts (reported, never changed)
- 🗑️ **close** — PRs superseded by a newer-version PR for the same package
- 💬 **rebase suggestion** — stale PRs (`@dependabot rebase`)
- ⏭️ **skip** — CI still running, or the PR touches non-dependency files

All decisions are **deterministic** — no LLM in the loop. Policy plus machine-checked facts only.

## Why

Dependabot opens the PRs, CI runs — and then a human still has to decide, one by one, which of them are safe to merge. dep-triage applies your project's explicit policy to that moment, so the routine cases are handled and only the judgment calls reach you.

## Install

```bash
pip install git+https://github.com/sunnydachs/dep-triage.git
```

Or from a clone:

```bash
git clone https://github.com/sunnydachs/dep-triage.git
cd dep-triage
pip install .
```

Authentication: set `GITHUB_TOKEN` / `GH_TOKEN`. Public repos work unauthenticated, but GitHub's rate limit is then 60 requests/hour and one scan uses ~35.

## Quick start

```bash
# Dry-run (default): print the plan, change nothing
dep-triage --repo owner/name

# Perform actions (enabling auto-merge, closing superseded PRs, commenting).
# Requires a token with write access.
dep-triage --repo owner/name --apply

# Use a policy file, machine-readable output
dep-triage --repo owner/name --policy dep-triage.toml --json
```

Example output:

```
dep-triage — DRY-RUN PLAN (no changes)
  #16     🟢 auto-merge
          chore(deps): bump react-router from 8.3.0 to 8.3.1
          reasons: patch bump, policy conditions met
  #19     🔔 escalate
          chore(deps): bump @nestjs/core from 11.2.1 to 12.0.1
          reasons: major bump is never auto-merged
summary: {"auto_merge": 6, "comment_rebase": 1, "escalate": 4}
```

## Policy (`dep-triage.toml`)

Copy [`policy.example.toml`](policy.example.toml) to your repository root. Every key is optional; unknown keys are rejected (typo protection).

| Key | Default | Meaning |
|---|---|---|
| `auto_merge_bumps` | `["patch", "minor"]` | Semver levels eligible for auto-merge |
| `never_auto_merge_bumps` | `["major"]` | Levels that are never auto-merged (always wins) |
| `require_ci_green` | `true` | Require green CI |
| `require_dependency_only` | `true` | Require every changed file to be a manifest/lockfile |
| `close_superseded` | `true` | Close PRs outrun by a newer-version PR of the same package |
| `rebase_stale_days` | `7` | Suggest `@dependabot rebase` for PRs open this long |
| `merge_method` | `"squash"` | `merge` \| `squash` \| `rebase` |

## How decisions are made

Facts are machine-checked per PR (changed-file scope, CI state via check-runs + combined status, semver level parsed from the title, supersession, conflicts, age). The first matching rule wins:

| # | Condition | Action |
|---|---|---|
| 1 | A newer-version PR for the same package exists | close_superseded |
| 2 | Contains non-dependency files | skip |
| 3 | Merge conflicts with base branch | escalate |
| 4 | CI still running | skip |
| 5 | CI not green | escalate |
| 6 | Bump level is in `never_auto_merge_bumps` | escalate |
| 7 | Bump level not in `auto_merge_bumps` | escalate — or rebase suggestion if stale |
| 8 | All conditions met | auto_merge |

Unparseable titles (no "Bump X from A to B" / "Update X requirement" pattern) are treated as `unknown` and escalated — never guessed.

## Safety model

- **Dry-run is the default.** Nothing changes unless you pass `--apply`
- **Revalidation immediately before merge**: head SHA, CI state, and changed-file scope are re-fetched right before enabling auto-merge; if anything moved since triage, the action is aborted (TOCTOU protection)
- **Majors are never auto-merged**, regardless of policy
- **Write access is only needed for `--apply`**; dry-run works read-only
- **No CI on the repo?** That state (`ci_none`) is reported explicitly in the reasons — it is not treated as "CI running"

## Design motivation

The requirements that shaped this tool come from patterns repeatedly reported by maintainers of dependency-heavy projects:

| Need | Where it lives |
|---|---|
| Only treat PRs whose changed files are all dependency manifests/lockfiles | `scope.py` — mechanical scope check |
| Revalidate head SHA, CI state, and changed-file scope immediately before enabling auto-merge | `triage.apply()` — TOCTOU protection |
| Project policy as the top rule, not hardcoded behavior | `policy.py` — TOML policy |
| Keep decision logic away from write credentials | Deterministic decisions, no LLM |

## Known limitations (MVP)

- Security-advisory matching per ecosystem is not implemented (major-risk gating is semver-based only)
- Auto-merge enables GitHub's native auto-merge: it merges once branch protection requirements pass. On repos without branch protection, dependency-only patch/minor PRs merge as soon as CI is green — use branch protection together with this tool
- Titles not in the "Bump X from A to B" format are escalated as `unknown`
- On repos with no CI, patch/minor PRs become auto-merge candidates (nothing to wait for). Set `auto_merge_bumps = []` if you want escalation-only behavior

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q   # 47 tests, fully offline
```

## Origin

dep-triage was inspired by a real-world pain that recurs across dependency-heavy projects: Dependabot PRs pile up, CI runs, and a human still has to reconcile each one afterwards — with no reusable, secure, policy-first workflow to do it. This tool is an independent, general-purpose implementation for any project facing the same situation.

## License

[MIT](LICENSE)
