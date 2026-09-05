# dep-triage

**Dependabot の PR を CI 完了後に、プロジェクトのポリシーで仕分ける。既定は dry-run。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-47%20passing-brightgreen.svg)](tests/)

[English](README.md) | 日本語

<!-- README.md（英語）の e5d3ead 時点の内容と同期。更新時は両方を直すこと -->

`dep-triage` は、オープンな Dependabot PR を5つの区分に仕分けます。判定基準はリポジトリにコミットするポリシーファイルです:

- 🟢 **auto-merge** — patch/minor アップグレード + CI 緑 + 依存ファイルのみの変更 + コンフリクト無し
- 🔔 **escalate** — major、CI 失敗、コンフリクト（報告のみ・変更しない）
- 🗑️ **close** — 同一パッケージの新しいバージョン PR に追い越されたもの
- 💬 **rebase 提案** — 老朽化した PR（`@dependabot rebase`）
- ⏭️ **skip** — CI 実行中 / 依存以外のファイルを含む

判定はすべて**決定的**です。LLM は使いません。ポリシーと機械的に確認した事実のみで判定が再現します。

## なぜ作ったか

Dependabot が PR を出し、CI が通っても、結局「マージしていいか」を人間が1件ずつ見る作業が残ります。dep-triage はその瞬間にプロジェクトの明示的なポリシーを適用し、定型的なものを処理し、判断が要るものだけを人間に届けます。

## インストール

```bash
pip install git+https://github.com/sunnydachs/dep-triage.git
```

クローンからの場合:

```bash
git clone https://github.com/sunnydachs/dep-triage.git
cd dep-triage
pip install .
```

認証: `GITHUB_TOKEN` / `GH_TOKEN` を設定してください。公開リポジトリは無認証でも動きますが、レート制限は 60 リクエスト/時で、1走査あたり約35リクエスト使います。

## クイックスタート

```bash
# dry-run（既定）。計画を表示するだけで変更はしない
dep-triage --repo owner/name

# 実際に適用（auto-merge 有効化 / superseded close / コメント）。
# write 権限の token が必要
dep-triage --repo owner/name --apply

# ポリシーファイル指定・機械可読出力
dep-triage --repo owner/name --policy dep-triage.toml --json
```

出力例:

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

## ポリシー（`dep-triage.toml`）

[`policy.example.toml`](policy.example.toml) をリポジトリのルートにコピーしてください。全キー任意・未知のキーはエラーになります（typo 防止）。

| キー | 既定値 | 意味 |
|---|---|---|
| `auto_merge_bumps` | `["patch", "minor"]` | 自動マージを許す semver 水準 |
| `never_auto_merge_bumps` | `["major"]` | 絶対に自動マージしない水準（常に優先） |
| `require_ci_green` | `true` | CI 緑を要求 |
| `require_dependency_only` | `true` | 全変更ファイルがマニフェスト/ロックファイルであることを要求 |
| `close_superseded` | `true` | 同一パッケージの新バージョン PR に追い越された PR を close |
| `rebase_stale_days` | `7` | この日数以上開いている PR に `@dependabot rebase` を提案 |
| `merge_method` | `"squash"` | `merge` \| `squash` \| `rebase` |

## 判定のしくみ

各 PR の事実（変更ファイルのスコープ、check-runs + combined status による CI 状態、タイトルから解析した semver 水準、追い越されているか、コンフリクト、経過日数）を機械的に確認し、**最初に一致した規則**が採用されます:

| # | 条件 | アクション |
|---|---|---|
| 1 | 同一パッケージの新しいバージョン PR が既にある | close_superseded |
| 2 | 依存以外のファイルを含む | skip |
| 3 | base ブランチとコンフリクト | escalate |
| 4 | CI 実行中 | skip |
| 5 | CI が緑でない | escalate |
| 6 | 水準が `never_auto_merge_bumps` に含まれる | escalate |
| 7 | 水準が `auto_merge_bumps` に含まれない | escalate（老朽化していれば rebase 提案） |
| 8 | すべての条件を満たす | auto_merge |

"Bump X from A to B" / "Update X requirement" 形式でないタイトルは `unknown` として escalate されます。推測はしません。

## 安全モデル

- **dry-run が既定**。`--apply` を明示しない限り何も変わりません
- **マージ直前の再検証**: auto-merge 有効化の直前に head SHA・CI 状態・変更ファイルスコープを再取得し、triage 時から変わっていれば断念します（TOCTOU 対策）
- **major はポリシーに関わらず絶対に自動マージしません**
- **write 権限が要るのは `--apply` のときだけ**。dry-run は read のみで完結します
- **CI が無いリポジトリでは**、その状態（`ci_none`）を理由として明示します。「CI 実行中」とは区別します

## 設計の出典

着想は [cpheinrich/morpheus#196](https://github.com/cpheinrich/morpheus/issues/196) で報告されていた実際の悩みから得ました。issue の要件と実装の対応:

| issue の要件 | 実装箇所 |
|---|---|
| "Recognize Dependabot PRs only when every changed file is a dependency manifest or lockfile" | `scope.py` — 機械的スコープ判定 |
| "Revalidate author, head SHA, changed-file scope, and CI state immediately before enabling auto-merge" | `triage.apply()` — TOCTOU 対策 |
| "applies explicit project policy first" | `policy.py` — TOML ポリシーが最上位の規則 |
| "deliver decisions without exposing the model credential" | 決定的判定・LLM 不使用 |

## 既知の限界（MVP）

- エコシステムごとのセキュリティアドバイザリ照合は未実装（major リスクの抑止は semver ベースのみ）
- auto-merge は GitHub のネイティブ auto-merge を有効化します: branch protection の要件を満たした時点で GitHub 側がマージします。branch protection 無しのリポジトリでは、CI が緑になった瞬間に依存のみの patch/minor PR がマージされるため、本ツールとは branch protection の併用を推奨します
- "Bump X from A to B" 形式でないタイトルは `unknown` として escalate されます
- CI が無いリポジトリでは、patch/minor PR が auto-merge 候補になります（待つものが無いため）。escalate のみにしたい場合は `auto_merge_bumps = []` としてください

## 開発

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q   # 47 テスト・完全オフライン
```

## 出典と謝辞

このツールは、[cpheinrich/morpheus#196](https://github.com/cpheinrich/morpheus/issues/196) で公開されていた悩み — *"Projects lack a reusable and secure workflow to automatically triage and reconcile Dependabot pull requests after CI runs."* — から着想を得ました。本リポジトリは独立した実装であり（元リポジトリのコードは参照していません）、同じ課題を持つあらゆるプロジェクトで使える汎用 CLI として書き下ろしたものです。課題を明確に言語化してくださった [@cpheinrich](https://github.com/cpheinrich) に感謝します。

## ライセンス

[MIT](LICENSE)
