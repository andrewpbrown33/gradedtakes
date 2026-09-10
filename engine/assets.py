"""Embedded page assets: cached avatar pictures and the identity fonts.

This is the ONLY place the presentation layer reads a file, and it reads
nothing but data/cache/ - never the user's rosters, registry, saves or
secrets. engine/ui.py stays pure presentation and imports from here.

Everything returns a data URI or CSS string; if a cache is missing the
result is empty and the page falls back to monograms and system fonts.
"""
import base64
import hashlib
import json
import os
import re
from typing import Dict, Optional, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVATAR_DIR = os.path.join(HERE, "data", "cache", "avatars")
FONT_DIR = os.path.join(HERE, "data", "cache", "fonts")

AVATAR_MAX_BYTES = 400_000
FONT_MAX_BYTES = 300_000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")

_AVATAR_MEM: Dict[str, Optional[str]] = {}
_FONT_MEM: Dict[str, str] = {}


def safe_id(source_id) -> Optional[str]:
    sid = str(source_id or "").strip()
    return sid if _SAFE_ID.match(sid) and ".." not in sid else None


def avatar_data_uri(source_id) -> Optional[str]:
    sid = safe_id(source_id)
    if not sid:
        return None
    if sid in _AVATAR_MEM:
        return _AVATAR_MEM[sid]
    uri = None
    for ext, mime in (("jpg", "image/jpeg"), ("jpeg", "image/jpeg"),
                      ("png", "image/png"), ("webp", "image/webp")):
        path = os.path.join(AVATAR_DIR, "%s.%s" % (sid, ext))
        if os.path.isfile(path):
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                if 0 < len(raw) <= AVATAR_MAX_BYTES:
                    uri = "data:%s;base64,%s" % (
                        mime, base64.b64encode(raw).decode("ascii"))
            except OSError:
                uri = None
            break
    _AVATAR_MEM[sid] = uri
    return uri


def avatar_ids() -> Tuple[str, ...]:
    try:
        names = sorted(os.listdir(AVATAR_DIR))
    except OSError:
        return ()
    out = []
    for fn in names:
        sid, dot, ext = fn.rpartition(".")
        if dot and ext.lower() in ("jpg", "jpeg", "png", "webp") and safe_id(sid):
            out.append(sid)
    return tuple(out)


def avatar_css() -> str:
    rules = []
    for sid in avatar_ids():
        uri = avatar_data_uri(sid)
        if uri:
            rules.append('  .wr-av-pic-%s { background-image: url("%s"); }'
                         % (sid, uri))
    return "\n".join(rules) + ("\n" if rules else "")


def fonts_css() -> str:
    if "css" in _FONT_MEM:
        return _FONT_MEM["css"]
    try:
        with open(os.path.join(FONT_DIR, "manifest.json")) as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        _FONT_MEM["css"] = ""
        return ""
    groups: Dict[Tuple[str, str], Dict] = {}
    for m in manifest if isinstance(manifest, list) else []:
        try:
            fn = os.path.basename(str(m["file"]))
            with open(os.path.join(FONT_DIR, fn), "rb") as fh:
                raw = fh.read()
        except (OSError, KeyError, TypeError):
            continue
        if not raw or len(raw) > FONT_MAX_BYTES:
            continue
        family = re.sub(r"[^A-Za-z0-9 ]", "", str(m.get("family", "")))
        key = (family, hashlib.sha256(raw).hexdigest())
        g = groups.setdefault(key, {"raw": raw, "weights": []})
        try:
            g["weights"].append(int(m.get("weight", 400)))
        except (TypeError, ValueError):
            pass
    out = []
    for (family, _h), g in groups.items():
        if not family or not g["weights"]:
            continue
        lo, hi = min(g["weights"]), max(g["weights"])
        wt = "%d" % lo if lo == hi else "%d %d" % (lo, hi)
        out.append(
            '  @font-face { font-family: "%s"; font-style: normal; '
            'font-weight: %s; font-display: swap; '
            'src: url("data:font/woff2;base64,%s") format("woff2"); }'
            % (family, wt, base64.b64encode(g["raw"]).decode("ascii")))
    css = ("\n".join(out) + "\n") if out else ""
    _FONT_MEM["css"] = css
    return css
