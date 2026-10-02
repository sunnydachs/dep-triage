# Working agreement for this repository

Short rules for anyone — human or agent — changing `dep-triage`.

## What this tool is

`dep-triage` sorts open Dependabot PRs into policy buckets after CI has run, and
is meant to be safe to run twice: it **defaults to dry-run** and re-checks the
head SHA and CI state immediately before it would act.

## Ground rules

- **Dry-run is the default.** A new action must be inert unless `--apply` (or the
  equivalent) is passed explicitly.
- **Re-verify just before acting.** The head SHA and the CI conclusion are read
  again immediately before a write, so a PR that moved while triage ran is not
  acted on. Keep that TOCTOU guard intact.
- **Never merge on a policy guess.** A PR whose CI is missing or unknown is its
  own bucket (`ci_none`), not a green light.
- **No LLM.** The decision must be a deterministic function of the policy file.
- **Tests come with the change.** `python -m pytest -q` must pass, and a new
  bucket needs a fixture that lands in it.
- **No secrets in Git**, and no absolute paths in code, tests or docs — a clone
  must run anywhere.
- **Do not bypass the secret scan.** `git commit --no-verify` is never a fix for a
  gitleaks hit; rotate the credential and rewrite the commit.
- **The README is a promise.** Every documented command must work on a fresh
  clone, and a badge must point at CI rather than hardcode a test count.

## Checks that must pass

```
pip install -e ".[dev]"
python -m pytest -q
```
