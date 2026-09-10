"""Creator-source registry + fetch layer: who Andrew trusts, and their words.

REGISTRY: data/sources.yaml lists every opinion source that feeds creator
consensus - built-in engine feeds plus whatever YouTubers/RSS/pages Andrew
adds - each with an enabled flag and a 0-100 weight (relative; normalized
at consensus time, so weights need not sum to anything). load_sources()
tolerates a missing file by seeding the four built-in feeds; every write is
atomic (tmp + os.replace, same as engine/state.py). A row may also carry
`topic_filter: fantasy` (TOPIC_FILTERS / topic_filter()) - the hook for a
MIXED channel; the classifier that acts on it lives in engine/calls.py and
fetching here stays unfiltered on purpose.

FETCH: fetch_source(source) returns recent items as
    [{"title", "url", "published", "text"}, ...]
with a 12h disk cache in data/cache/ (engine/adp.py pattern: fresh cache
wins, network failure falls back to the stale cache with items marked
"stale": True, and only no-cache-plus-no-network raises SourceError).

YOUTUBE, WITHOUT AN API KEY - live-verified 2026-09-02 against a major
outlet's public channel (a technical fixture only; sources.yaml ships with
no real creator pre-picked):
  * handle -> channel_id: fetch the channel page once and read
    <meta itemprop="identifier" content="UC...">. That meta tag is the
    page's OWN id; the first "channelId" in the raw HTML can belong to a
    linked sibling channel (observed live), so the meta tag wins and the
    JSON keys are only fallbacks. Resolutions are cached forever
    (data/cache/yt-channel-ids.json) - channel ids do not change.
  * latest videos: https://www.youtube.com/feeds/videos.xml?channel_id=...
    (free Atom feed, ~15 newest entries).
  * transcripts: the watch-page "captionTracks" baseUrl now returns an
    EMPTY 200 to plain GETs (proof-of-origin token gate, observed live) -
    that classic approach is dead. What works: POST the InnerTube player
    endpoint as the ANDROID client (no API key needed, verified live);
    its captionTracks baseUrl serves timedtext XML to a plain GET. When
    captions are disabled or the fetch fails, the item is still returned
    with text=None and a "reason" - honest degradation, never a vanished
    video.

NO TWITTER/X SCRAPING - anywhere, ever. X's Terms of Service prohibit
scraping and crawling without written consent, its API access is paywalled,
and logged-out HTML is deliberately unstable; building on any of that means
silent breakage and ToS violation. X takes enter the system through the
'paste' type only: Andrew copies the text in by hand (add_paste), and the
stored item says exactly where it came from.

Pattern extraction downstream is crude by design; this layer's job is only
to deliver honest raw text with provenance (url + fetched date) attached.

AVATARS (v3 pages draw a source as a FACE - engine/ui.avatar): fetch_avatar
(source) pulls one picture per creator into data/cache/avatars/<id>.jpg -
YouTube from the channel page's "avatar" thumbnail JSON at the =s176 size,
RSS from <itunes:image href> or <image><url>. It is never called from a page
render, only from `python -m engine.sources --avatars [--force]` and, best
effort, from the panel's add-source flow. A cached picture under seven days
old is never refetched unless forced; anything over 400KB is downscaled with
the macOS `sips` binary when present and discarded (with the reason) when it
still will not fit - ui.py refuses to embed a bigger file anyway.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from typing import Dict, List, Optional, Tuple

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")
SOURCES_PATH = os.path.join(HERE, "data", "sources.yaml")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# InnerTube player endpoint accepts keyless POSTs from the Android client
# (verified live); this UA matches the client context we claim.
ANDROID_UA = "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip"
ANDROID_CLIENT = {"clientName": "ANDROID", "clientVersion": "20.10.38",
                  "androidSdkVersion": 30}

TYPES = ("youtube", "rss", "url", "paste", "feed")
BUILTIN_FEEDS = ("engine", "espn-proj", "sleeper-proj", "chen-tiers")

# Optional per-source topical filter (the hook; the classifier itself lives
# in engine/calls.py). A MIXED channel - a betting outlet that also posts
# fantasy shows, MLB props and NASCAR bets - carries topic_filter: fantasy,
# and engine/calls.ingest_week classifies each fetched item before
# extraction. Fetching stays deliberately unfiltered: fetch_source returns
# everything the channel published, so the drop count is auditable against
# what was actually fetched.
TOPIC_FILTERS = ("fantasy",)

DEFAULT_SOURCES = [
    {"id": "engine", "name": "War Room Engine", "type": "feed",
     "handle": "engine", "enabled": True, "weight": 40,
     "notes": "Built-in: weekly projections + lineup verdicts."},
    {"id": "espn-proj", "name": "ESPN Projections", "type": "feed",
     "handle": "espn-proj", "enabled": True, "weight": 25,
     "notes": "Built-in: ESPN kona weekly projections."},
    {"id": "sleeper-proj", "name": "Sleeper Projections", "type": "feed",
     "handle": "sleeper-proj", "enabled": True, "weight": 20,
     "notes": "Built-in: Sleeper weekly projections."},
    {"id": "chen-tiers", "name": "Boris Chen Tiers", "type": "feed",
     "handle": "chen-tiers", "enabled": True, "weight": 15,
     "notes": "Built-in: Boris Chen clustering tiers."},
]

_HEADER = """\
# War Room creator-source registry (see engine/sources.py).
#
#   id       unique kebab-slug          type     youtube|rss|url|paste|feed
#   handle   channel URL/@handle, RSS url, page url, or builtin feed key
#   weight   0-100, relative - normalized at consensus time
#   topic_filter (optional) 'fantasy' - MIXED channel: each fetched item is
#            classified before extraction and non-fantasy items (MLB, NASCAR,
#            pure betting) are dropped with a counted, printed reason.
#
# 'feed' entries are the engine's own built-in inputs; consensus reads those
# feeds directly, so fetch_source() returns [] for them.
"""

_EXAMPLE = """\
# Example creator entry - replace with YOUR creators (this one is a disabled
# placeholder, not a recommendation):
# - id: example-youtuber
#   name: "Example Fantasy Channel"
#   type: youtube
#   handle: "https://www.youtube.com/@example-channel"
#   enabled: false
#   weight: 25
#   notes: "Placeholder. Paste any channel URL or @handle."
"""

_KEY_ORDER = ("id", "name", "type", "handle", "enabled", "weight", "notes",
              "topic_filter")


class SourceError(RuntimeError):
    """A source could not be fetched and no cache exists to fall back on."""


# --- registry ---------------------------------------------------------------

def _ordered(src: Dict) -> Dict:
    out = {}
    for k in _KEY_ORDER:
        if k in src:
            out[k] = src[k]
    for k in src:
        if k not in out:
            out[k] = src[k]
    return out


def save_sources(sources: List[Dict], path: Optional[str] = None) -> str:
    """Atomically write the registry. Returns the path written."""
    path = path or SOURCES_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = yaml.safe_dump({"sources": [_ordered(s) for s in sources]},
                          default_flow_style=False, sort_keys=False,
                          allow_unicode=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(_HEADER + "\n" + body + "\n" + _EXAMPLE)
    os.replace(tmp, path)
    return path


def load_sources(path: Optional[str] = None) -> List[Dict]:
    """Load the registry; a missing file is seeded with the built-in feeds."""
    path = path or SOURCES_PATH
    if not os.path.exists(path):
        seeded = [dict(s) for s in DEFAULT_SOURCES]
        save_sources(seeded, path)
        return seeded
    with open(path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    return list(data.get("sources") or [])


def list_sources(path: Optional[str] = None,
                 enabled_only: bool = False) -> List[Dict]:
    sources = load_sources(path)
    if enabled_only:
        sources = [s for s in sources if s.get("enabled")]
    return sources


def topic_filter(source: Dict) -> Optional[str]:
    """The source's topic_filter, normalized - or None when there is none.

    An unrecognized value returns None (no filter) rather than raising or
    inventing one: engine/calls.py reports the unknown value and extracts
    everything, so a typo never silently swallows a whole source.
    """
    raw = str((source or {}).get("topic_filter") or "").strip().lower()
    return raw if raw in TOPIC_FILTERS else None


def get_source(source_id: str, path: Optional[str] = None) -> Optional[Dict]:
    for s in load_sources(path):
        if s.get("id") == source_id:
            return s
    return None


def _edit(source_id: str, path: Optional[str], **changes) -> Dict:
    sources = load_sources(path)
    for s in sources:
        if s.get("id") == source_id:
            s.update(changes)
            save_sources(sources, path)
            return s
    raise KeyError("no source with id %r in %s" % (source_id,
                                                   path or SOURCES_PATH))


def enable(source_id: str, path: Optional[str] = None) -> Dict:
    return _edit(source_id, path, enabled=True)


def disable(source_id: str, path: Optional[str] = None) -> Dict:
    return _edit(source_id, path, enabled=False)


def set_weight(source_id: str, weight: float,
               path: Optional[str] = None) -> Dict:
    try:
        w = float(weight)
    except (TypeError, ValueError):
        raise ValueError("weight must be a number, got %r" % (weight,))
    if not (0 <= w <= 100):
        raise ValueError("weight must be 0-100, got %r" % (weight,))
    if w == int(w):
        w = int(w)
    return _edit(source_id, path, weight=w)


# --- http helpers -----------------------------------------------------------

def _http_get(url: str, ua: str = UA, timeout: float = 25.0) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _http_post_json(url: str, body: Dict, ua: str = UA,
                    timeout: float = 25.0) -> Dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": ua, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# --- youtube: handle -> channel_id ------------------------------------------

_CHANNEL_ID_RE = re.compile(r"UC[0-9A-Za-z_-]{22}$")


def _resolve_cache_path() -> str:
    return os.path.join(CACHE_DIR, "yt-channel-ids.json")


def resolve_channel_id(handle: str) -> str:
    """Resolve a channel URL / @handle / bare id to a UC... channel id.

    One channel-page fetch, then cached forever in yt-channel-ids.json.
    The page's <meta itemprop="identifier"> is authoritative; the first
    "channelId" in the HTML can be a linked SIBLING channel (seen live),
    so the JSON keys are only fallbacks.
    """
    h = (handle or "").strip()
    if not h:
        raise SourceError("empty youtube handle")
    if _CHANNEL_ID_RE.match(h):
        return h
    m = re.search(r"/channel/(UC[0-9A-Za-z_-]{22})", h)
    if m:
        return m.group(1)

    cache = _resolve_cache_path()
    known = {}
    if os.path.exists(cache):
        try:
            with open(cache, "r") as fh:
                known = json.load(fh)
        except (ValueError, OSError):
            known = {}
    if h in known:
        return known[h]

    if h.startswith("http"):
        page_url = h
    elif h.startswith("@"):
        page_url = "https://www.youtube.com/" + h
    else:
        page_url = "https://www.youtube.com/@" + h
    try:
        html = _http_get(page_url)
    except (urllib.error.URLError, OSError) as exc:
        raise SourceError("could not fetch channel page %s: %s"
                          % (page_url, exc))

    cid = None
    for pat in (r'<meta itemprop="identifier" content="(UC[0-9A-Za-z_-]{22})"',
                r'"externalId":"(UC[0-9A-Za-z_-]{22})"',
                r'"channelId":"(UC[0-9A-Za-z_-]{22})"'):
        m = re.search(pat, html)
        if m:
            cid = m.group(1)
            break
    if not cid:
        raise SourceError("no channel id found on %s" % page_url)

    known[h] = cid
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = cache + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(known, fh, indent=1)
    os.replace(tmp, cache)
    return cid


# --- youtube: videos + transcripts ------------------------------------------

_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"


def fetch_channel_videos(channel_id: str) -> List[Dict]:
    """Newest videos from the free Atom feed (no API key)."""
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id
    xml_text = _http_get(url)
    root = ET.fromstring(xml_text)
    out = []
    for entry in root.findall(_ATOM + "entry"):
        vid = entry.findtext(_YT + "videoId") or ""
        link = entry.find(_ATOM + "link")
        out.append({
            "video_id": vid,
            "title": (entry.findtext(_ATOM + "title") or "").strip(),
            "url": (link.get("href") if link is not None else
                    "https://www.youtube.com/watch?v=" + vid),
            "published": (entry.findtext(_ATOM + "published") or "").strip(),
        })
    return out


def _timedtext_to_text(xml_text: str) -> str:
    """Flatten timedtext XML (format=3 <p>/<s>, or legacy <text>) to prose."""
    root = ET.fromstring(xml_text)
    parts = []
    tags = ("p",) if root.tag == "timedtext" else ("text",)
    for tag in tags:
        for el in root.iter(tag):
            chunk = "".join(el.itertext()).strip()
            if chunk:
                parts.append(unescape(chunk))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def fetch_transcript(video_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (text, reason). text=None means degraded, reason says why.

    Live probe 2026-09-02: the watch page still embeds captionTracks, but a
    plain GET of that baseUrl returns an EMPTY 200 (POT-token gate). The
    InnerTube ANDROID player still hands out baseUrls that serve timedtext
    XML to a plain GET - so that is the one approach used here.
    """
    try:
        resp = _http_post_json(
            "https://www.youtube.com/youtubei/v1/player",
            {"context": {"client": dict(ANDROID_CLIENT)},
             "videoId": video_id},
            ua=ANDROID_UA)
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return None, "player endpoint failed: %s" % type(exc).__name__

    status = (resp.get("playabilityStatus") or {}).get("status")
    if status not in (None, "OK"):
        return None, "video not playable (%s)" % status
    tracks = ((resp.get("captions") or {})
              .get("playerCaptionsTracklistRenderer") or {}).get(
                  "captionTracks") or []
    if not tracks:
        return None, "captions disabled"

    track = tracks[0]
    for t in tracks:
        if str(t.get("languageCode", "")).startswith("en"):
            track = t
            break
    base_url = track.get("baseUrl")
    if not base_url:
        return None, "caption track has no baseUrl"
    try:
        xml_text = _http_get(base_url, ua=ANDROID_UA)
    except (urllib.error.URLError, OSError) as exc:
        return None, "timedtext fetch failed: %s" % type(exc).__name__
    if not xml_text.strip():
        return None, "empty timedtext response (token-gated URL)"
    try:
        text = _timedtext_to_text(xml_text)
    except ET.ParseError:
        return None, "unparseable timedtext XML"
    if not text:
        return None, "transcript parsed empty"
    return text, None


def fetch_youtube(source: Dict, max_items: int = 3) -> List[Dict]:
    channel_id = resolve_channel_id(source.get("handle", ""))
    items = []
    for v in fetch_channel_videos(channel_id)[:max_items]:
        text, reason = fetch_transcript(v["video_id"])
        item = {"title": v["title"], "url": v["url"],
                "published": v["published"], "text": text}
        if reason:
            item["reason"] = reason
        items.append(item)
    return items


# --- generic rss ------------------------------------------------------------

def strip_tags(html: str) -> str:
    """Crude HTML -> text: drop script/style/comments, tags, squash space."""
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html or "")
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = unescape(s)
    s = re.sub(r"[ \t]+([.,;:!?])", r"\1", s)   # "him ." -> "him."
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _first_text(el, *tags) -> str:
    for tag in tags:
        for child in el:
            if child.tag == tag or child.tag.endswith("}" + tag.split("}")[-1]):
                return (child.text or "").strip()
    return ""


def parse_rss(xml_text: str, max_items: int = 3) -> List[Dict]:
    """Parse RSS 2.0 or Atom into fetch items. Pure - fixture-testable."""
    root = ET.fromstring(xml_text)
    items = []
    if root.tag.endswith("feed"):                       # Atom
        for entry in root.findall(_ATOM + "entry")[:max_items]:
            link = entry.find(_ATOM + "link")
            body = (entry.findtext(_ATOM + "summary")
                    or entry.findtext(_ATOM + "content") or "")
            items.append({
                "title": strip_tags(entry.findtext(_ATOM + "title") or ""),
                "url": link.get("href", "") if link is not None else "",
                "published": (entry.findtext(_ATOM + "published")
                              or entry.findtext(_ATOM + "updated") or ""),
                "text": strip_tags(body),
            })
    else:                                               # RSS 2.0-ish
        for item in root.iter("item"):
            if len(items) >= max_items:
                break
            items.append({
                "title": strip_tags(_first_text(item, "title")),
                "url": _first_text(item, "link"),
                "published": _first_text(item, "pubDate", "date"),
                "text": strip_tags(_first_text(item, "description",
                                               "summary", "encoded")),
            })
    return items


def fetch_rss(source: Dict, max_items: int = 3) -> List[Dict]:
    return parse_rss(_http_get(source.get("handle", "")), max_items)


# --- single page ------------------------------------------------------------

def fetch_url(source: Dict, max_items: int = 3) -> List[Dict]:
    url = source.get("handle", "")
    html = _http_get(url)
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = strip_tags(m.group(1)) if m else source.get("name", url)
    return [{"title": title, "url": url,
             "published": datetime.now().strftime("%Y-%m-%d"),
             "text": strip_tags(html)}]


# --- paste store ------------------------------------------------------------

def _cache_path(source_id: str) -> str:
    return os.path.join(CACHE_DIR, "src-%s.json" % source_id)


def _read_cache(source_id: str) -> Optional[Dict]:
    path = _cache_path(source_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return None


def _write_cache(source_id: str, items: List[Dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(source_id)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"fetched": datetime.now().isoformat(timespec="seconds"),
                   "items": items}, fh, indent=1)
    os.replace(tmp, path)


def add_paste(source_id: str, text: str, url: str = "",
              title: str = "") -> Dict:
    """Store hand-pasted text as a fetched-style item (X/Twitter path).

    Pastes never expire and are returned newest-first by fetch_source.
    """
    item = {"title": title or "pasted %s"
            % datetime.now().strftime("%Y-%m-%d %H:%M"),
            "url": url, "published": datetime.now().isoformat(
                timespec="seconds"),
            "text": (text or "").strip()}
    cached = _read_cache(source_id) or {"items": []}
    items = [item] + list(cached.get("items") or [])
    _write_cache(source_id, items)
    return item


# --- dispatcher with cache ---------------------------------------------------

def fetch_source(source: Dict, max_items: int = 3,
                 max_age_hours: float = 12.0,
                 quiet: bool = True) -> List[Dict]:
    """Return recent items for one source: [{title,url,published,text}, ...].

    adp.py cache discipline: a cache younger than max_age_hours is served
    without touching the network; a failed fetch falls back to the stale
    cache with every item marked "stale": True (visible degradation); no
    cache plus no network raises SourceError. 'feed' sources are the
    engine's own inputs - consensus reads those directly, so [] here.
    'paste' items never go stale (they are the record, not a mirror).
    """
    stype = source.get("type", "")
    sid = source.get("id", "")
    if stype == "feed":
        return []
    if stype == "paste":
        cached = _read_cache(sid) or {"items": []}
        return list(cached.get("items") or [])[:max_items]

    fetchers = {"youtube": fetch_youtube, "rss": fetch_rss, "url": fetch_url}
    if stype not in fetchers:
        raise SourceError("unknown source type %r for %r" % (stype, sid))

    cached = _read_cache(sid)
    cache_file = _cache_path(sid)
    if cached is not None and os.path.exists(cache_file):
        age_h = (time.time() - os.path.getmtime(cache_file)) / 3600.0
        if age_h < max_age_hours:
            return list(cached.get("items") or [])[:max_items]

    try:
        items = fetchers[stype](source, max_items=max_items)
        _write_cache(sid, items)
        return items
    except (urllib.error.URLError, ET.ParseError, ValueError, OSError,
            SourceError) as exc:
        if cached is not None:
            if not quiet:
                print("  source %s fetch failed (%s) - using stale cache"
                      % (sid, type(exc).__name__))
            stale = []
            for it in list(cached.get("items") or [])[:max_items]:
                it = dict(it)
                it["stale"] = True
                stale.append(it)
            return stale
        raise SourceError("source %s (%s) unreachable and uncached: %s"
                          % (sid, stype, exc))


# --- avatars -----------------------------------------------------------------
# One picture per creator, cached as data/cache/avatars/<source-id>.jpg and
# embedded by engine/ui.avatar as a data URI. This is the ONLY place a face
# is fetched: page renders read the cache and never touch the network.

AVATAR_MAX_BYTES = 400_000     # ui._avatar_data_uri refuses anything larger
AVATAR_FRESH_DAYS = 7          # a picture younger than this is never refetched
AVATAR_PX = 176                # YouTube's =s176 variant; sips -Z target
AVATAR_TYPES = ("youtube", "rss")
_AVATAR_EXTS = ("jpg", "jpeg", "png", "webp")
_YT_AVATAR_RE = re.compile(r'"avatar":\{"thumbnails":\[\{"url":"([^"]+)"')
_ITUNES_IMAGE_RE = re.compile(
    r'<itunes:image\b[^>]*?\bhref\s*=\s*["\']([^"\']+)["\']', re.I)
_RSS_IMAGE_RE = re.compile(r'<image\b[^>]*>.*?<url\b[^>]*>\s*(.*?)\s*</url>',
                           re.I | re.S)
_SIZE_QUERY_RE = re.compile(r'([?&])size=[^&#]*', re.I)


def avatar_dir() -> str:
    """data/cache/avatars - resolved at call time so a redirected CACHE_DIR
    (tests) carries the avatar store with it."""
    return os.path.join(CACHE_DIR, "avatars")


def avatar_path(source_id: str) -> str:
    return os.path.join(avatar_dir(), "%s.jpg" % source_id)


def _http_get_bytes(url: str, ua: str = UA, timeout: float = 25.0,
                    limit: int = 8_000_000) -> bytes:
    """A binary GET with a hard size ceiling - a picture, not a video."""
    req = urllib.request.Request(url, headers={
        "User-Agent": ua, "Accept": "image/*,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise SourceError("download over %d bytes - not an avatar" % limit)
    return data


def _unescape_url(url: str) -> str:
    """A URL lifted out of JSON (\\u0026, \\/) or XML (&amp;) - plain again."""
    return unescape(url.replace("\\u0026", "&").replace("\\/", "/")).strip()


def youtube_avatar_url(channel_html: str) -> Optional[str]:
    """The channel's own avatar URL from its page JSON, forced to =s176.

    Pure - fixture-tested. None when the page carries no avatar block.
    """
    m = _YT_AVATAR_RE.search(channel_html or "")
    if not m:
        return None
    url = _unescape_url(m.group(1))
    if re.search(r"=s\d+", url):
        url = re.sub(r"=s\d+", "=s%d" % AVATAR_PX, url, count=1)
    else:
        url += "=s%d" % AVATAR_PX
    return url


def rss_avatar_url(feed_xml: str) -> Optional[str]:
    """<itunes:image href> first, else <image><url>; &amp; unescaped.

    A host that offers size variants through a size= query (Omny's
    size=Large/Medium/Small, for one) is asked for Small - the page draws
    the face at 28-36px and a 3000px cover art is bytes for nothing.
    """
    text = feed_xml or ""
    m = _ITUNES_IMAGE_RE.search(text)
    url = m.group(1) if m else None
    if not url:
        m = _RSS_IMAGE_RE.search(text)
        url = m.group(1) if m else None
    if not url:
        return None
    url = _unescape_url(url)
    if _SIZE_QUERY_RE.search(url):
        url = _SIZE_QUERY_RE.sub(r"\1size=Small", url, count=1)
    return url


def _youtube_avatar_source(source: Dict) -> Optional[str]:
    cid = resolve_channel_id(source.get("handle", ""))
    return youtube_avatar_url(_http_get("https://www.youtube.com/channel/" + cid))


def _rss_avatar_source(source: Dict) -> Optional[str]:
    return rss_avatar_url(_http_get(source.get("handle", "")))


def _is_jpeg(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff"


def _sips_path() -> Optional[str]:
    return shutil.which("sips")


def _shrink_bytes(data: bytes, max_px: int = AVATAR_PX) -> Optional[bytes]:
    """Downscale (and convert to JPEG) with macOS sips; None when sips is
    absent or fails. Works through scratch files inside the avatar dir so
    nothing lands outside the cache."""
    sips = _sips_path()
    if not sips:
        return None
    d = avatar_dir()
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, ".shrink-%d.in" % os.getpid())
    dst = os.path.join(d, ".shrink-%d.jpg" % os.getpid())
    try:
        with open(src, "wb") as fh:
            fh.write(data)
        subprocess.run([sips, "-s", "format", "jpeg", "-Z", str(max_px),
                        src, "--out", dst],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30, check=True)
        with open(dst, "rb") as fh:
            out = fh.read()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        for p in (src, dst):
            try:
                os.unlink(p)
            except OSError:
                pass


def _write_avatar(dest: str, data: bytes) -> None:
    """Atomic write, 0644, then strip any sibling <id>.png/.jpeg/.webp so
    ui.py (which checks .jpg first) can never pick up the stale variant."""
    d = os.path.dirname(dest)
    os.makedirs(d, exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, dest)
    stem = os.path.splitext(os.path.basename(dest))[0]
    for ext in _AVATAR_EXTS:
        if ext == "jpg":
            continue
        sib = os.path.join(d, "%s.%s" % (stem, ext))
        if os.path.isfile(sib):
            try:
                os.unlink(sib)
            except OSError:
                pass


def _avatar_age_days(path: str) -> Optional[float]:
    try:
        return (time.time() - os.path.getmtime(path)) / 86400.0
    except OSError:
        return None


def fetch_avatar_detail(source: Dict, force: bool = False
                        ) -> Tuple[Optional[str], str]:
    """(path or None, one-line reason) - the honest form of fetch_avatar.

    A cached picture under AVATAR_FRESH_DAYS old is returned as-is unless
    `force`. On any failure the stale picture (if one exists) is left on
    disk untouched, the return is None, and the reason says why.
    """
    src = source or {}
    sid = str(src.get("id") or "").strip()
    if not sid or "/" in sid or "\\" in sid or ".." in sid or sid.startswith("."):
        return None, "refused - not a usable source id: %r" % (sid,)
    stype = str(src.get("type") or "").strip().lower()
    dest = avatar_path(sid)
    age = _avatar_age_days(dest)
    if age is not None and age < AVATAR_FRESH_DAYS and not force:
        return dest, ("kept - cached picture is %.1f day(s) old "
                      "(--force refetches)" % age)
    if stype not in AVATAR_TYPES:
        if age is not None:
            return dest, ("kept - %r sources are not fetched; a hand-placed "
                          "picture stands" % stype)
        return None, ("no avatar convention for type %r - drop a picture at "
                      "%s by hand if you want a face" % (stype, dest))
    finder = (_youtube_avatar_source if stype == "youtube"
              else _rss_avatar_source)
    try:
        url = finder(src)
    except (SourceError, urllib.error.URLError, OSError, ValueError) as exc:
        return None, "could not read the source page: %s" % exc
    if not url:
        return None, "no avatar found on the source page"
    try:
        data = _http_get_bytes(url)
    except (SourceError, urllib.error.URLError, OSError, ValueError) as exc:
        return None, "download failed (%s): %s" % (url, exc)
    if not data:
        return None, "empty download from %s" % url
    fetched_kb = len(data) / 1024.0
    if len(data) > AVATAR_MAX_BYTES or not _is_jpeg(data):
        shrunk = _shrink_bytes(data)
        if shrunk is not None:
            data = shrunk
        elif len(data) > AVATAR_MAX_BYTES:
            return None, ("discarded - %.0fKB is over the %dKB cap and sips "
                          "%s" % (fetched_kb, AVATAR_MAX_BYTES // 1000,
                                  "could not shrink it" if _sips_path()
                                  else "is not available to shrink it"))
        # a small non-JPEG with no sips is kept as-is: browsers sniff the
        # bytes, and a face beats a monogram
    if len(data) > AVATAR_MAX_BYTES:
        return None, ("discarded - still %.0fKB after downscaling, over the "
                      "%dKB cap" % (len(data) / 1024.0,
                                    AVATAR_MAX_BYTES // 1000))
    _write_avatar(dest, data)
    return dest, "saved %.0fKB from %s" % (len(data) / 1024.0, url)


def fetch_avatar(source: Dict, force: bool = False) -> Optional[str]:
    """data/cache/avatars/<id>.jpg for a youtube/rss source, or None.

    Best-effort by contract: never raises for a network or parse failure.
    fetch_avatar_detail returns the reason alongside.
    """
    return fetch_avatar_detail(source, force=force)[0]


def fetch_avatars(sources: List[Dict], force: bool = False) -> List[Dict]:
    """One row per source: {"id", "path", "note"} - the CLI's report."""
    out = []
    for s in sources:
        path, note = fetch_avatar_detail(s, force=force)
        out.append({"id": str(s.get("id") or ""), "path": path, "note": note})
    return out


# --- CLI --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.sources",
        description="Creator-source registry utilities. --avatars fetches one "
                    "face per enabled youtube/rss source into "
                    "data/cache/avatars/ (the v3 pages embed them).")
    ap.add_argument("--avatars", action="store_true",
                    help="fetch avatars for every enabled source, one line each")
    ap.add_argument("--force", action="store_true",
                    help="refetch even when the cached picture is under %d "
                         "days old" % AVATAR_FRESH_DAYS)
    ap.add_argument("--registry", default=None,
                    help="registry yaml path (default: data/sources.yaml)")
    args = ap.parse_args(argv)
    if not args.avatars:
        ap.print_help()
        return 2
    rows = fetch_avatars(list_sources(args.registry, enabled_only=True),
                         force=args.force)
    for r in rows:
        print("%-24s %-4s %s" % (r["id"], "ok" if r["path"] else "--",
                                 r["note"]))
    if not rows:
        print("no enabled sources in %s" % (args.registry or SOURCES_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
