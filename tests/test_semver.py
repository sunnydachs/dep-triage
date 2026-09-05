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
