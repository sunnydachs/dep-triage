from dep_triage.semver import is_newer, parse_bump


def test_parse_patch():
    r = parse_bump("Bump requests from 2.31.0 to 2.31.1")
    assert r["package"] == "requests"
    assert r["from"] == "2.31.0"
    assert r["to"] == "2.31.1"
    assert r["bump"] == "patch"


def test_parse_leftmost_segment_rule():
    """2.31.0 -> 2.32.3 は「中間セグメントが変わった」ので minor（仕様どおり）。"""
    assert parse_bump("Bump requests from 2.31.0 to 2.32.3")["bump"] == "minor"


def test_parse_minor_and_major():
    assert parse_bump("Bump foo from 1.2.3 to 1.3.0")["bump"] == "minor"
    assert parse_bump("Bump foo from 1.2.3 to 2.0.0")["bump"] == "major"
    # 0.x の慣習: 0.2 -> 0.3 は minor、0.2.3 -> 0.2.4 は patch
    assert parse_bump("Bump bar from 0.2 to 0.3")["bump"] == "minor"
    assert parse_bump("Bump bar from 0.2.3 to 0.2.4")["bump"] == "patch"


def test_parse_actions_integer_versions():
    r = parse_bump("Bump actions/checkout from 3 to 4")
    assert r["package"] == "actions/checkout"
    assert r["bump"] == "major"


def test_parse_conventional_commit_prefix():
    """実データ（nishanthkj77/CampusSync-Ai_SIH）で確認された接頭辞付き形式。

    "chore(deps): bump ..." のような conventional-commit 接頭辞と
    小文字の bump を解釈できること（e2e で全件 unknown になった教訓）。
    """
    r = parse_bump("chore(deps): bump @nestjs/core from 11.2.1 to 12.0.1")
    assert r["package"] == "@nestjs/core"
    assert r["bump"] == "major"
    assert parse_bump("chore(deps): bump react-router from 8.3.0 to 8.3.1")["bump"] == "patch"
    assert parse_bump("chore(deps-dev): bump prisma from 7.9.1 to 7.10.0")["bump"] == "minor"
    assert parse_bump("build: bump foo from 1.0.0 to 1.0.2")["bump"] == "patch"


def test_parse_update_requirement_format():
    """requirements.txt 用の "Update X requirement from A to B" 形式。

    範囲変更なので semver 水準は unknown（推測しない）だが、
    パッケージ名は取れる（superseded 判定に使える）。
    """
    r = parse_bump("update pytest requirement from <9,>=8.4 to >=8.4,<10")
    assert r["package"] == "pytest"
    assert r["bump"] == "unknown"
    assert r["from"] == "<9,>=8.4"


def test_parse_without_from_is_unknown():
    r = parse_bump("Bump foo to 1.2.3")
    assert r["bump"] == "unknown"
    assert r["package"] == "foo"


def test_parse_non_dependabot_title_is_unknown():
    assert parse_bump("Fix the login page")["bump"] == "unknown"
    assert parse_bump("")["package"] is None


def test_is_newer_and_conservative():
    assert is_newer("1.2.3", "1.3.0") is True
    assert is_newer("1.3.0", "1.2.3") is False
    assert is_newer("garbage", "1.0") is False  # 解釈不能は保守側（False）


# ── grouped updates / 複数依存（issue #1 対応） ──

def test_parse_grouped_summary_official_format():
    r = parse_bump("Bump the npm_and_yarn group with 8 updates")
    assert r["package"] == "the npm_and_yarn group"
    assert r["bump"] == "unknown"
    assert r["grouped"] is True


def test_parse_grouped_summary_variants():
    assert parse_bump("Bump the monthly-batch group with 10 updates")["grouped"] is True
    assert parse_bump("Bump the types-dependencies group in /client with 1 update")["grouped"] is True
    r = parse_bump("Bump the dev group across 3 directories with 22 updates")
    assert r["grouped"] is True
    assert r["package"] == "the dev group"


def test_parse_multi_package_takes_highest_level():
    r = parse_bump("Bump actions/checkout from 3 to 4 and actions/cache from 4.0.0 to 4.1.0")
    assert r["bump"] == "major"      # major が1つでもあれば conservative に major
    assert r["packages"] == ["actions/checkout", "actions/cache"]
    r2 = parse_bump("Bump a from 1.0.0 to 1.0.1 and b from 2.0.0 to 2.0.1")
    assert r2["bump"] == "patch"
    r3 = parse_bump("Bump a from 1.0.0 to 1.1.0 and b from 2.0.0 to 2.0.1")
    assert r3["bump"] == "minor"
