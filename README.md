# dep-triage

**Triage Dependabot PRs after CI runs, per project policy. Dry-run by default.**

> ProblemForge の悩み発見パイプラインが発見した [Solution #196](https://github.com/cpheinrich/morpheus/issues/196)
> （"Projects lack a reusable and secure workflow to automatically triage and reconcile
> Dependabot pull requests after CI runs"）の実装プロトタイプです。

Dependabot の PR は CI が終わっても「マージしていいのか」を人間が1件ずつ確認する作業が残る。
dep-triage は、プロジェクトごとの明示的なポリシーに従って、CI 完了後の Dependabot PR を
機械的に仕分けする CLI です。

## 何をするか

1. オープンな Dependabot PR を収集する
2. 各 PR の事実を機械的に判定する:
   - **依存のみスコープ**: 変更ファイルが全てマニフェスト / ロックファイルか
     （`package.json`、`Cargo.lock`、`requirements*.txt` 等。1つでもコードが混ざれば対象外）
   - **CI 状態**: check-runs + combined status を集約（CI 無しは「無し」として区別）
   - **semver 水準**: タイトルから major / minor / patch を解析（推測しない。解釈不能は unknown）
   - **superseded**: 同一パッケージのより新しいバージョン PR が既に無いか
   - **コンフリクト / 老朽化**
3. ポリシーに従って仕分ける:
   - 🟢 **auto-merge**: patch/minor + CI 緑 + 依存のみ + コンフリクト無し
   - 🔔 **escalate**: major / CI 失敗 / コンフリクト（人間確認。変更はしない）
   - 🗑 **close**: 同一パッケージの新バージョン PR に追い越されたもの
   - 💬 **rebase 提案**: 老朽化した PR
   - ⏭ **skip**: CI 実行中 / 依存以外の変更を含む

## 使い方

```bash
# dry-run（既定）。変更は一切しない。計画だけ表示する
dep-triage --repo owner/name

# 実際に適用する（auto-merge 有効化 / close / コメント。write 権限の token が必要）
dep-triage --repo owner/name --apply

# ポリシーファイルを指定
dep-triage --repo owner/name --policy dep-triage.toml --json
```

認証: `GITHUB_TOKEN` / `GH_TOKEN` 環境変数（無認証でも公開リポジトリは動作するが
レート制限 60 req/h）。

## ポリシー（dep-triage.toml）

```toml
auto_merge_bumps = ["patch", "minor"]  # 自動マージを許す水準
never_auto_merge_bumps = ["major"]     # 絶対に自動マージしない水準（常に優先）
require_ci_green = true                # CI 緑を要求
require_dependency_only = true         # 依存ファイルのみの変更を要求
close_superseded = true                # 追い越された PR を close
rebase_stale_days = 7                  # 老朽 PR への @dependabot rebase 提案
merge_method = "squash"
```

例は `policy.example.toml`。未知のキーはエラーになる（typo 防止）。

## 安全モデル

- **dry-run が既定**。`--apply` を明示したときだけ変更する
- **アクション直前の再検証**: auto-merge 有効化の直前に、ヘッド SHA / CI 状態 /
  変更ファイルスコープを再取得し、収集時から変わっていれば断念する（TOCTOU 対策）
- **major は決して自動マージしない**（ポリシーで never 側に置いた水準は auto 側に書いても無効）
- **write 権限は --apply 時のみ要求**。dry-run は read だけで完結する
- **判断は決定的**: LLM を使わない。ポリシー + 機械的事実のみで判定が再現する

## 設計の由来（元 issue からの要件対応）

| 元 issue の要件 | dep-triage の実装 |
|---|---|
| "every changed file is a dependency manifest or lockfile" | `scope.py` の機械的スコープ判定 |
| "Revalidate author, head SHA, changed-file scope, and CI state immediately before" | `triage.apply()` の直前再検証（TOCTOU 対策） |
| "applies explicit project policy first" | `policy.py` — TOML ポリシーが全判定の上位規則 |
| "deliver decisions without exposing the model credential" | LLM を使わない決定的判定（将来の ambiguous 判定は read-only で分離可能な構造） |

## 既知の限界（MVP）

- パッケージエコシステムごとのセキュリティアドバイザリ照合は未実装（major 抑止は
  semver ベースのみ）
- auto-merge は GitHub の auto-merge 機能（branch protection の要件を満たした時点で
  GitHub 側がマージ）を有効化する。branch protection 無しのリポジトリでは
  CI 緑の直後にマージされるため、`require_ci_green` と併用の上、ブランチ保護を推奨
- タイトル形式が "Bump X from A to B" でない PR は水準 unknown（保守側に escalate）
- CI 無しのリポジトリでは「待つものが無い」ため patch/minor が auto-merge 候補に
  なる。それを避けたい場合は `auto_merge_bumps = []` にして escalate のみにする

## 開発

```bash
python -m pytest tests/ -q   # オフラインで完結するテスト一式
```

## ライセンス

MIT
