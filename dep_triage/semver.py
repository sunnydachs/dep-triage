"""semver — Dependabot PR タイトルからパッケージ名とアップグレード水準を解析する。

タイトル形式: "Bump <pkg> from <from> to <to>"
  例: "Bump requests from 2.31.0 to 2.32.3"
      "Bump actions/checkout from 3 to 4"（actions は単純な整数バージョン）
from が取れない場合（Dependabot は初回から記載するが、将来形式変更に備え）
bump は "unknown" にする。推測しない。
"""
import re

_TITLE_RE = re.compile(
    r"^Bump\s+(?P<pkg>\S+)\s+(?:from\s+(?P<frm>\S+)\s+)?to\s+(?P<to>\S+)"
)


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


def parse_bump(title: str) -> dict:
    """Dependabot タイトルを解析する（純関数）。

    返り値: {package, from, to, bump: "major"|"minor"|"patch"|"unknown"}
    """
    m = _TITLE_RE.match((title or "").strip())
    if not m:
        return {"package": None, "from": None, "to": None, "bump": "unknown"}
    frm, to = m.group("frm"), m.group("to")
    if frm is None:
        return {"package": m.group("pkg"), "from": None, "to": to, "bump": "unknown"}
    try:
        level = _bump_level(frm, to)
    except Exception:
        level = "unknown"
    return {"package": m.group("pkg"), "from": frm, "to": to, "bump": level}


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
