"""semver — Dependabot PR タイトルからパッケージ名とアップグレード水準を解析する。

対応するタイトル形式（実データ + 公式確認済み）:
  "Bump <pkg> from <from> to <to>"
  "chore(deps): bump <pkg> from <from> to <to>"   ← conventional-commit 接頭辞付き
  "Update <pkg> requirement from <from> to <to>"  ← requirements.txt 用（水準は unknown）
  "Bump the <group> group with N updates"         ← grouped updates（公式形式）
  "Bump the <group> group in /path with N updates"
  "Bump the <group> group across N directories with N updates"
  "Bump A from a to b and B from c to d"          ← 複数依存（最も高い水準を採用）
  例: "Bump requests from 2.31.0 to 2.32.3"
      "chore(deps): bump @nestjs/core from 11.2.1 to 12.0.1"
      "Bump actions/checkout from 3 to 4"（actions は単純な整数バージョン）

grouped summary 形式はタイトルに semver 水準が含まれないため unknown
（escalate = 安全側）。from が取れない形式・一致しないタイトルも
推測せず unknown にする。
"""
import re

# conventional-commit 接頭辞（chore(deps): / build: 等）は任意で許容。大小文字を無視。
_TITLE_RE = re.compile(
    r"^(?:[a-z]+(?:\([^)]*\))?:\s*)?bump\s+"
    r"(?P<pkg>\S+)\s+(?:from\s+(?P<frm>\S+)\s+)?to\s+(?P<to>\S+)",
    re.IGNORECASE,
)
# requirements.txt 用フォーマット（バージョン範囲の変更で semver 水準は推定できない）
_REQUIREMENT_RE = re.compile(
    r"^update\s+(?P<pkg>\S+)\s+requirement\s+from\s+(?P<frm>\S+)\s+to\s+(?P<to>\S+)",
    re.IGNORECASE,
)
# grouped updates のサマリ形式（公式: github.blog "Tame Dependabot"）
_GROUPED_RE = re.compile(
    r"^(?:[a-z]+(?:\([^)]*\))?:\s*)?bump\s+the\s+(?P<group>.+?)\s+group\b"
    r".*?\s+with\s+(?P<n>\d+)\s+updates?$",
    re.IGNORECASE,
)
# 複数依存の "bump A from a to b and B from c to d" 形式
_MULTI_SEG_RE = re.compile(r"(\S+)\s+from\s+(\S+)\s+to\s+(\S+)", re.IGNORECASE)
_LEVEL_ORDER = {"patch": 1, "minor": 2, "major": 3}


def _version_tuple(v: str):
    """バージョン文字列 → 数値タプル（非数値セグメントは除外）。"""
    parts = []
    for seg in re.split(r"[.\-+]", v):
        if seg.isdigit():
            parts.append(int(seg))
        else:
            # プレリリース等（"1.2.3b1" の "b1"）は以降を無視
            m = re.match(r"(\d+)", seg)
            if m:
                parts.append(int(m.group(1)))
            break
    return tuple(parts)


def _bump_level(frm: str, to: str) -> str:
    """セマンティック比較: 最初に変わったセグメント位置で水準を決める。

    0.x の慣習（0.2 → 0.3 は minor、0.2.3 → 0.2.4 は patch）は
    「左から何番目のセグメントが変わったか」で一貫して扱う。
    """
    a, b = _version_tuple(frm), _version_tuple(to)
    width = max(len(a), len(b))
    a += (0,) * (width - len(a))
    b += (0,) * (width - len(b))
    for pos in range(width):
        if a[pos] != b[pos]:
            return {0: "major", 1: "minor"}.get(pos, "patch")
    return "patch"


def is_newer(frm: str, to: str) -> bool:
    """バージョン比較（superseded 判定用）。

    どちらか一方でも解釈不能（空タプル）の場合は False（保守側）。
    """
    try:
        a, b = _version_tuple(to), _version_tuple(frm)
    except Exception:
        return False
    if not a or not b:
        return False
    return a > b


def parse_bump(title: str) -> dict:
    """Dependabot タイトルを解析する（純関数）。

    返り値: {package, from, to, bump: "major"|"minor"|"patch"|"unknown",
             grouped: bool, packages: list|None}
    """
    t = (title or "").strip()

    # grouped updates のサマリ形式: 水準がタイトルに無いため unknown（安全側）
    g = _GROUPED_RE.match(t)
    if g:
        return {"package": f"the {g.group('group')} group", "from": None,
                "to": None, "bump": "unknown", "grouped": True,
                "packages": None,
                "notes": f"grouped updates: {g.group('n')} updates (levels not in title)"}

    # 複数依存: "bump A from a to b and B from c to d"
    segs = _MULTI_SEG_RE.findall(t)
    if len(segs) >= 2 and t.lower().lstrip().startswith("bump"):
        pkgs, levels = [], []
        for pkg, frm, to in segs:
            pkgs.append(pkg)
            try:
                levels.append(_bump_level(frm, to))
            except Exception:
                levels.append("unknown")
        level = "unknown" if "unknown" in levels else max(
            levels, key=lambda x: _LEVEL_ORDER[x])
        return {"package": "multiple", "from": segs[0][1], "to": segs[-1][2],
                "bump": level, "grouped": False, "packages": pkgs}

    m = _TITLE_RE.match(t)
    if not m:
        # requirements.txt 用フォーマットは範囲変更なので水準は unknown のまま
        m2 = _REQUIREMENT_RE.match(t)
        if m2:
            return {"package": m2.group("pkg"), "from": m2.group("frm"),
                    "to": m2.group("to"), "bump": "unknown", "grouped": False,
                    "packages": None}
        return {"package": None, "from": None, "to": None, "bump": "unknown",
                "grouped": False, "packages": None}
    frm, to = m.group("frm"), m.group("to")
    if frm is None:
        return {"package": m.group("pkg"), "from": None, "to": to,
                "bump": "unknown", "grouped": False, "packages": None}
    try:
        level = _bump_level(frm, to)
    except Exception:
        level = "unknown"
    return {"package": m.group("pkg"), "from": frm, "to": to, "bump": level,
            "grouped": False, "packages": None}


def is_newer_any(frm_list, to) -> bool:
    """to が frm_list のいずれかより新しいか（superseded 判定の補助）。"""
    return any(is_newer(f, to) for f in frm_list)
