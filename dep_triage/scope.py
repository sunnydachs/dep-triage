"""scope — PR の変更ファイルが「依存マニフェスト / ロックファイルのみ」かを判定する。

元 issue の要件: "Recognize Dependabot PRs only when every changed file is a
dependency manifest or lockfile."（依存のみの変更を機械的に同定し、
コード変更が混ざる PR を自動処理対象から外す）
"""
from pathlib import PurePosixPath

# 依存マニフェスト / ロックファイル（正規化済みパス名で比較）
DEPENDENCY_FILENAMES = {
    # JS/TS
    "package.json", "package-lock.json", "npm-shrinkwrap.json",
    "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb",
    # Python
    "pyproject.toml", "poetry.lock", "Pipfile", "Pipfile.lock",
    "requirements.txt", "uv.lock",
    # Rust / Go / Ruby / PHP / JVM / .NET / Elixir / Dart
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    "Gemfile", "Gemfile.lock", "composer.json", "composer.lock",
    "pom.xml", "mix.exs", "mix.lock", "Pubspec.lock",
}
# 拡張子 / プレフィックス系（Gradle や requirements の分割、.NET プロジェクト）
DEPENDENCY_SUFFIXES = (".csproj", ".gradle")
DEPENDENCY_PREFIXES = ("requirements",)


def is_dependency_file(path: str) -> bool:
    """1 パスが依存マニフェスト / ロックファイルか（純関数）。"""
    name = PurePosixPath(path).name
    if name in DEPENDENCY_FILENAMES:
        return True
    if name.endswith(DEPENDENCY_SUFFIXES):
        return True
    # requirements/dev-requirements.txt 等のプレフィックス
    stem = name
    if stem.endswith(".txt"):
        stem = stem[: -len(".txt")]
    return any(stem == p or stem.startswith(p + "-") for p in DEPENDENCY_PREFIXES)


def scope_check(paths: list) -> dict:
    """変更ファイル群が依存のみかを判定する（純関数）。

    返り値: {dependency_only: bool, offending: [依存以外のパス]}
    空リストは依存のみとは判定しない（情報不足として False）。
    """
    if not paths:
        return {"dependency_only": False, "offending": []}
    offending = [p for p in paths if not is_dependency_file(p)]
    return {"dependency_only": not offending, "offending": offending}
