from dep_triage.scope import is_dependency_file, scope_check


def test_manifest_and_lockfiles():
    for p in ("package.json", "package-lock.json", "Cargo.toml", "Cargo.lock",
              "pyproject.toml", "poetry.lock", "go.mod", "go.sum",
              "requirements.txt", "Gemfile.lock", "pom.xml", "composer.lock"):
        assert is_dependency_file(p), p


def test_variants():
    assert is_dependency_file("src/requirements-dev.txt")
    assert is_dependency_file("app/build.gradle")
    assert is_dependency_file("src/Server/Web.csproj")
    # ディレクトリ違いの同名は依存ファイル（GitHub では各所に置かれ得る）
    assert is_dependency_file("web/package.json")


def test_non_dependency_files():
    for p in ("src/main.py", "README.md", ".github/workflows/ci.yml",
              "app/server.py", "docs/index.html"):
        assert not is_dependency_file(p), p


def test_scope_check_all_dependency():
    r = scope_check(["package.json", "package-lock.json"])
    assert r == {"dependency_only": True, "offending": []}


def test_scope_check_mixed():
    r = scope_check(["package.json", "src/index.js"])
    assert r["dependency_only"] is False
    assert r["offending"] == ["src/index.js"]


def test_scope_check_empty_is_not_dependency_only():
    """空のファイルリストは情報不足として依存のみと判定しない。"""
    assert scope_check([])["dependency_only"] is False
