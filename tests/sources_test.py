#!/usr/bin/env python3
"""Acceptance test: creator-source registry + fetch layer (engine/sources.py).

Everything here runs OFFLINE from fixtures - registry round-trip in a temp
dir, enable/disable/weight edits, RSS 2.0 + Atom parsing from strings, the
timedtext transcript flattener, the paste store, and the cache freshness /
stale-fallback discipline (a bogus URL that would explode if the network
were touched proves the fresh cache short-circuits, and the stale path marks
items "stale": True). Live YouTube resolution/transcript behavior is
documented in the engine/sources.py docstring, not asserted here - a
creator's caption settings are not this suite's to promise.

AVATARS (fetch_avatar): the YouTube "avatar" thumbnail regex and both RSS
shapes (<itunes:image href>, <image><url>) from fixture strings, with
urllib monkeypatched so nothing is fetched; the 400KB size guard with the
sips shrink step faked both ways; the never-overwrite-fresh rule (a
picture under seven days old is kept, --force or age refetches); the
sibling-extension strip; and the --avatars CLI printing one line per
enabled source. The avatar store follows CACHE_DIR into the tempdir.

State discipline (tests/mock_draft.py test_persistence pattern): every test
that writes redirects sources.SOURCES_PATH / sources.CACHE_DIR into a temp
dir in try/finally, and the real data/sources.yaml is byte-checked untouched
at the end.

    .venv/bin/python tests/sources_test.py
"""

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import sources                                   # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _tmp_registry():
    return os.path.join(tempfile.mkdtemp(prefix="sources-test-"),
                        "sources.yaml")


# --- 1. registry seeding + round-trip ---------------------------------------
def test_registry_roundtrip():
    print("\n1. REGISTRY SEED + ROUND-TRIP (temp dir)")
    path = _tmp_registry()
    first = sources.load_sources(path)
    check(os.path.exists(path), "missing file seeded on first load")
    check(len(first) == 4, "seed has the four built-in feed sources")
    check(all(s["type"] == "feed" and s["enabled"] for s in first),
          "all seeds are enabled 'feed' entries")
    weights = {s["id"]: s["weight"] for s in first}
    check(weights == {"engine": 40, "espn-proj": 25,
                      "sleeper-proj": 20, "chen-tiers": 15},
          "seed weights engine40/espn25/sleeper20/chen15")
    check(sources.load_sources(path) == first, "reload is stable")

    added = dict(first[0])
    added.update({"id": "some-creator", "name": "Some Creator",
                  "type": "youtube", "handle": "https://www.youtube.com/@x",
                  "enabled": False, "weight": 33, "notes": "n"})
    sources.save_sources(first + [added], path)
    back = sources.load_sources(path)
    check(len(back) == 5 and back[-1] == added,
          "added youtube source survives save/load byte-identically")
    check(not os.path.exists(path + ".tmp"),
          "atomic write leaves no .tmp behind")
    with open(path) as fh:
        raw = fh.read()
    check("example-youtuber" in raw and "enabled: false" in raw,
          "commented placeholder example persists through saves")


# --- 2. enable / disable / weight edits -------------------------------------
def test_registry_edits():
    print("\n2. ENABLE / DISABLE / SET_WEIGHT")
    path = _tmp_registry()
    sources.load_sources(path)

    s = sources.disable("chen-tiers", path)
    check(s["enabled"] is False, "disable() returns the updated source")
    check(sources.get_source("chen-tiers", path)["enabled"] is False,
          "disable persisted to disk")
    check([x["id"] for x in sources.list_sources(path, enabled_only=True)]
          == ["engine", "espn-proj", "sleeper-proj"],
          "list_sources(enabled_only) drops the disabled one")
    sources.enable("chen-tiers", path)
    check(sources.get_source("chen-tiers", path)["enabled"] is True,
          "enable() flips it back")

    sources.set_weight("engine", 55, path)
    check(sources.get_source("engine", path)["weight"] == 55,
          "set_weight persisted")
    for bad in (-1, 101, "heavy"):
        try:
            sources.set_weight("engine", bad, path)
            check(False, "weight %r rejected" % (bad,))
        except ValueError:
            check(True, "weight %r rejected" % (bad,))
    try:
        sources.enable("nobody", path)
        check(False, "unknown id raises KeyError")
    except KeyError:
        check(True, "unknown id raises KeyError")


# --- 3. rss parsing from fixtures -------------------------------------------
RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Waiver Wire Blog</title>
<item><title>Week 1 Sleepers &amp; Starts</title>
  <link>https://example.com/wk1</link>
  <pubDate>Tue, 01 Sep 2026 09:00:00 GMT</pubDate>
  <description>&lt;p&gt;Start &lt;b&gt;Jordan Mason&lt;/b&gt; this week.&lt;/p&gt;
  &lt;p&gt;Sit the backup.&lt;/p&gt;</description></item>
<item><title>Second Post</title><link>https://example.com/2</link>
  <pubDate>Mon, 31 Aug 2026 09:00:00 GMT</pubDate>
  <description>short</description></item>
<item><title>Third Post</title><link>https://example.com/3</link>
  <description>oldest</description></item>
</channel></rss>"""

ATOM_FIXTURE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Blog</title>
<entry><title>Atom Take</title>
  <link rel="alternate" href="https://example.com/a1"/>
  <published>2026-09-01T08:00:00+00:00</published>
  <summary>Bench &lt;i&gt;him&lt;/i&gt;.</summary></entry>
</feed>"""


def test_rss_parse():
    print("\n3. RSS / ATOM PARSE (fixture strings, no network)")
    items = sources.parse_rss(RSS_FIXTURE, max_items=3)
    check(len(items) == 3, "parses all three RSS items")
    first = items[0]
    check(first["title"] == "Week 1 Sleepers & Starts",
          "entity in title unescaped")
    check(first["url"] == "https://example.com/wk1", "link mapped to url")
    check(first["published"].startswith("Tue, 01 Sep 2026"),
          "pubDate carried through")
    check("Start Jordan Mason this week." in first["text"]
          and "<" not in first["text"],
          "description HTML stripped to text")
    check(len(sources.parse_rss(RSS_FIXTURE, max_items=2)) == 2,
          "max_items caps RSS items")

    a = sources.parse_rss(ATOM_FIXTURE, max_items=3)
    check(len(a) == 1 and a[0]["title"] == "Atom Take"
          and a[0]["url"] == "https://example.com/a1"
          and a[0]["published"].startswith("2026-09-01")
          and a[0]["text"] == "Bench him.",
          "Atom feed parsed (title/href/published/summary)")


# --- 4. timedtext transcript flattening -------------------------------------
TIMEDTEXT_F3 = """<?xml version="1.0" encoding="utf-8" ?>
<timedtext format="3"><head><ws id="0"/></head><body>
<p t="0" d="2000"><s>I&#39;m</s><s> starting</s><s> him</s></p>
<p t="2000" d="1500">over the rookie</p>
<p t="3500" d="1"> </p>
</body></timedtext>"""

TIMEDTEXT_LEGACY = """<transcript>
<text start="0" dur="2">Sit him &amp; wait</text>
<text start="2" dur="2">this week</text>
</transcript>"""


def test_timedtext():
    print("\n4. TIMEDTEXT XML -> TEXT")
    check(sources._timedtext_to_text(TIMEDTEXT_F3)
          == "I'm starting him over the rookie",
          "format=3 <p>/<s> flattened, entities unescaped, blanks dropped")
    check(sources._timedtext_to_text(TIMEDTEXT_LEGACY)
          == "Sit him & wait this week",
          "legacy <transcript><text> format flattened")


# --- 5. paste store + feed passthrough (temp cache dir) ----------------------
def test_paste_and_cache():
    print("\n5. PASTE STORE, FEED TYPE, CACHE DISCIPLINE (temp cache dir)")
    real_cache = sources.CACHE_DIR
    sources.CACHE_DIR = tempfile.mkdtemp(prefix="sources-cache-")
    try:
        # paste: engine-side store only (X/Twitter is paste-only - ToS)
        it = sources.add_paste("friend-texts", "Bench the TE.",
                               url="https://example.com/status/1")
        check(it["text"] == "Bench the TE." and it["published"],
              "add_paste returns the stored item with a timestamp")
        sources.add_paste("friend-texts", "Actually start him.")
        src = {"id": "friend-texts", "type": "paste", "handle": "",
               "enabled": True, "weight": 10}
        got = sources.fetch_source(src)
        check(len(got) == 2 and got[0]["text"] == "Actually start him.",
              "fetch_source(paste) returns pastes newest-first")
        check(got[1]["url"] == "https://example.com/status/1",
              "paste provenance url preserved")
        check(len(sources.fetch_source(src, max_items=1)) == 1,
              "max_items caps pastes")

        # built-in feeds: consensus reads them directly, not through here
        check(sources.fetch_source({"id": "engine", "type": "feed",
                                    "handle": "engine"}) == [],
              "feed type returns [] from fetch layer")

        # fresh cache short-circuits the network (bogus URL would raise)
        rss_src = {"id": "cached-blog", "type": "rss",
                   "handle": "http://127.0.0.1:1/nope"}
        sources._write_cache("cached-blog",
                             [{"title": "t", "url": "u",
                               "published": "p", "text": "cached words"}])
        got = sources.fetch_source(rss_src)
        check(got == [{"title": "t", "url": "u", "published": "p",
                       "text": "cached words"}],
              "fresh cache served without touching the network")

        # stale cache + dead network -> stale items, visibly marked
        old = time.time() - 48 * 3600
        os.utime(sources._cache_path("cached-blog"), (old, old))
        got = sources.fetch_source(rss_src)
        check(len(got) == 1 and got[0]["stale"] is True
              and got[0]["text"] == "cached words",
              "failed refetch falls back to stale cache marked stale:True")

        # no cache + dead network -> SourceError, never a silent []
        try:
            sources.fetch_source({"id": "gone", "type": "rss",
                                  "handle": "http://127.0.0.1:1/nope"})
            check(False, "uncached+unreachable raises SourceError")
        except sources.SourceError:
            check(True, "uncached+unreachable raises SourceError")
    finally:
        sources.CACHE_DIR = real_cache


# --- 6. crude page-to-text --------------------------------------------------
def test_strip_tags():
    print("\n6. CRUDE HTML -> TEXT")
    html = ("<html><head><title>T</title><style>p{color:red}</style>"
            "<script>var x=1;</script></head><body><h1>Rankings</h1>"
            "<p>QB1 is <b>obvious</b>.</p><!-- hidden --><ul><li>A</li>"
            "<li>B</li></ul></body></html>")
    text = sources.strip_tags(html)
    check("var x=1" not in text and "color:red" not in text,
          "script/style bodies dropped")
    check("hidden" not in text, "comments dropped")
    check("QB1 is obvious." in text.replace("\n", " "),
          "inline tags stripped, punctuation tightened")
    check("A\nB" in text, "block boundaries become newlines")


# --- 7. avatars: fetch, size guard, freshness, CLI (all offline) -------------
YT_CHANNEL_HTML = (
    '<html><script>var ytInitialData = {"header":{"c4TabbedHeaderRenderer":'
    '{"avatar":{"thumbnails":[{"url":"https://yt3.googleusercontent.com/'
    'abc=s88-c-k-c0x00ffffff-no-rj\\u0026x=1","width":88,"height":88},'
    '{"url":"https://yt3.googleusercontent.com/abc=s176-c-k","width":176}]}'
    '}}};</script></html>')

RSS_ITUNES = """<?xml version="1.0"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel><title>Show</title>
<itunes:image href="https://img.example/cover.jpg?t=1&amp;size=Large"/>
<item><title>ep</title><itunes:image href="https://img.example/ep.jpg"/></item>
</channel></rss>"""

RSS_IMAGE_URL = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Blog</title>
<image><url> https://img.example/logo.png?x=1&amp;y=2 </url><title>Blog</title>
<link>https://example.com</link></image>
<item><title>post</title></item></channel></rss>"""

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"J" * 120 + b"\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"P" * 40


class _Net(object):
    """Fake urllib layer: pages by URL, one image, every URL recorded."""

    def __init__(self):
        self.pages = {}
        self.image = JPEG_BYTES
        self.got = []
        self.raise_on_image = None

    def get(self, url, **kw):
        self.got.append(url)
        if url not in self.pages:
            raise sources.SourceError("fixture has no page for %s" % url)
        return self.pages[url]

    def get_bytes(self, url, **kw):
        self.got.append(url)
        if self.raise_on_image:
            raise self.raise_on_image
        return self.image


def test_avatars():
    print("\n7. AVATARS - regexes, size guard, freshness, CLI (offline)")
    real = (sources.CACHE_DIR, sources._http_get, sources._http_get_bytes,
            sources.resolve_channel_id, sources._shrink_bytes,
            sources._sips_path)
    tmp = tempfile.mkdtemp(prefix="sources-avatars-")
    sources.CACHE_DIR = os.path.join(tmp, "cache")
    net = _Net()
    cid = "UC" + "x" * 22
    net.pages["https://www.youtube.com/channel/" + cid] = YT_CHANNEL_HTML
    net.pages["https://example.com/show.rss"] = RSS_ITUNES
    net.pages["https://example.com/blog.rss"] = RSS_IMAGE_URL
    sources._http_get = net.get
    sources._http_get_bytes = net.get_bytes
    sources.resolve_channel_id = lambda handle: cid
    sources._sips_path = lambda: None
    sources._shrink_bytes = lambda data, max_px=176: None
    try:
        # pure regexes -------------------------------------------------------
        check(sources.youtube_avatar_url(YT_CHANNEL_HTML)
              == "https://yt3.googleusercontent.com/abc=s176-c-k-c0x00ffffff"
                 "-no-rj&x=1",
              "youtube: first avatar thumbnail, \\u0026 unescaped, =s88 -> =s176")
        check(sources.youtube_avatar_url("no avatar block") is None,
              "youtube: no avatar block -> None")
        check(sources.rss_avatar_url(RSS_ITUNES)
              == "https://img.example/cover.jpg?t=1&size=Small",
              "rss: channel <itunes:image href> wins over the episode's, "
              "&amp; unescaped, size=Large -> size=Small")
        check(sources.rss_avatar_url(RSS_IMAGE_URL)
              == "https://img.example/logo.png?x=1&y=2",
              "rss: <image><url> fallback, whitespace trimmed, no size= left alone")
        check(sources.rss_avatar_url("<rss><channel/></rss>") is None,
              "rss: no image -> None")

        # youtube end to end -------------------------------------------------
        yt = {"id": "yt-guy", "name": "YT Guy", "type": "youtube",
              "handle": "https://www.youtube.com/@ytguy", "enabled": True}
        path, note = sources.fetch_avatar_detail(yt)
        want = os.path.join(sources.CACHE_DIR, "avatars", "yt-guy.jpg")
        check(path == want and os.path.isfile(want),
              "youtube avatar saved to data/cache/avatars/<id>.jpg")
        check(net.got[-1].endswith("=s176-c-k-c0x00ffffff-no-rj&x=1"),
              "the =s176 variant was what got downloaded")
        with open(want, "rb") as fh:
            check(fh.read() == JPEG_BYTES, "file holds the downloaded bytes")
        check(stat.S_IMODE(os.stat(want).st_mode) == 0o644,
              "file mode 0644")
        check(not os.path.exists(want + ".tmp"),
              "atomic write leaves no .tmp behind")
        check(note.startswith("saved") and "&x=1" in note,
              "the note says saved + the URL it came from")
        check(sources.fetch_avatar(yt) == want,
              "fetch_avatar returns the path")

        # never overwrite a fresh picture ------------------------------------
        net.raise_on_image = AssertionError("network touched for a fresh face")
        path, note = sources.fetch_avatar_detail(yt)
        check(path == want and note.startswith("kept"),
              "a picture under 7 days old is kept - nothing fetched")
        net.raise_on_image = None
        n_before = len(net.got)
        path, _ = sources.fetch_avatar_detail(yt, force=True)
        check(path == want and len(net.got) > n_before,
              "force=True refetches a fresh picture")
        old = time.time() - 8 * 86400
        os.utime(want, (old, old))
        n_before = len(net.got)
        path, note = sources.fetch_avatar_detail(yt)
        check(path == want and len(net.got) > n_before
              and note.startswith("saved"),
              "an 8-day-old picture is refetched without force")
        check(time.time() - os.path.getmtime(want) < 60,
              "...and the file is fresh again")

        # sibling extension variants are stripped ----------------------------
        stale_png = os.path.join(sources.CACHE_DIR, "avatars", "yt-guy.png")
        with open(stale_png, "wb") as fh:
            fh.write(PNG_BYTES)
        sources.fetch_avatar_detail(yt, force=True)
        check(not os.path.exists(stale_png) and os.path.exists(want),
              "a stale <id>.png sibling is removed when <id>.jpg is written")

        # rss, both shapes ---------------------------------------------------
        pod = {"id": "pod", "type": "rss", "handle": "https://example.com/show.rss"}
        path, _ = sources.fetch_avatar_detail(pod)
        check(path == os.path.join(sources.CACHE_DIR, "avatars", "pod.jpg")
              and net.got[-1] == "https://img.example/cover.jpg?t=1&size=Small",
              "rss itunes:image -> the Small variant downloaded and saved")
        net.image = PNG_BYTES
        blog = {"id": "blog", "type": "rss", "handle": "https://example.com/blog.rss"}
        path, note = sources.fetch_avatar_detail(blog)
        with open(path, "rb") as fh:
            saved = fh.read()
        check(path.endswith("blog.jpg") and saved == PNG_BYTES
              and net.got[-1] == "https://img.example/logo.png?x=1&y=2",
              "rss <image><url> -> downloaded; a small non-JPEG with no sips "
              "is kept as-is under .jpg (a face beats a monogram)")
        net.image = JPEG_BYTES

        # the 400KB guard ----------------------------------------------------
        big = {"id": "big", "type": "rss", "handle": "https://example.com/show.rss"}
        net.image = b"\xff\xd8\xff" + b"B" * 500_000
        path, note = sources.fetch_avatar_detail(big)
        check(path is None and "over the 400KB cap" in note
              and "not available" in note,
              "over 400KB with no sips -> discarded, None, the reason")
        check(not os.path.exists(os.path.join(sources.CACHE_DIR, "avatars",
                                              "big.jpg")),
              "...and nothing was written")
        sources._sips_path = lambda: "/usr/bin/sips"
        sources._shrink_bytes = lambda data, max_px=176: JPEG_BYTES
        path, note = sources.fetch_avatar_detail(big)
        check(path is not None and note.startswith("saved")
              and os.path.getsize(path) == len(JPEG_BYTES),
              "over 400KB + sips shrinks it -> the shrunk bytes are saved")
        sources._shrink_bytes = lambda data, max_px=176: b"\xff\xd8\xff" + b"S" * 410_000
        path, note = sources.fetch_avatar_detail(big, force=True)
        check(path is None and "still" in note and "after downscaling" in note,
              "still over 400KB after sips -> discarded with the reason")
        sources._shrink_bytes = lambda data, max_px=176: None
        path, note = sources.fetch_avatar_detail(big, force=True)
        check(path is None and "could not shrink" in note,
              "sips present but failing -> discarded, says so")
        sources._sips_path = lambda: None
        net.image = JPEG_BYTES

        # failures are reasons, never exceptions -----------------------------
        net.raise_on_image = OSError("connection refused")
        path, note = sources.fetch_avatar_detail(
            {"id": "down", "type": "rss", "handle": "https://example.com/show.rss"})
        check(path is None and "download failed" in note,
              "a dead image host -> None + reason")
        net.raise_on_image = None
        path, note = sources.fetch_avatar_detail(
            {"id": "nopage", "type": "rss", "handle": "https://example.com/404.rss"})
        check(path is None and "could not read the source page" in note,
              "a dead feed URL -> None + reason")
        path, note = sources.fetch_avatar_detail(
            {"id": "engine", "type": "feed", "handle": "engine"})
        check(path is None and "no avatar convention" in note,
              "a built-in feed has no face to fetch - says so")
        hand = os.path.join(sources.CACHE_DIR, "avatars", "engine.jpg")
        with open(hand, "wb") as fh:
            fh.write(JPEG_BYTES)
        path, note = sources.fetch_avatar_detail(
            {"id": "engine", "type": "feed", "handle": "engine"}, force=True)
        check(path == hand and "hand-placed" in note,
              "...but a hand-placed picture for it stands")
        for bad in ("", "../x", "a/b", ".hidden"):
            path, note = sources.fetch_avatar_detail({"id": bad, "type": "rss"})
            check(path is None and "refused" in note,
                  "unusable id refused: %r" % bad)

        # the CLI: one line per enabled source -------------------------------
        reg = os.path.join(tmp, "sources.yaml")
        seeded = sources.load_sources(reg)
        sources.save_sources(seeded + [dict(yt), dict(pod, name="Pod",
                                                      enabled=False)], reg)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sources.main(["--avatars", "--registry", reg])
        lines = buf.getvalue().strip().splitlines()
        check(rc == 0 and len(lines) == len(seeded) + 1,
              "--avatars prints one line per ENABLED source (%d)" % len(lines))
        check(any(ln.startswith("yt-guy") and " ok " in ln for ln in lines),
              "the youtube source's line says ok")
        check(any(ln.startswith("engine") and " ok " in ln for ln in lines),
              "the hand-placed engine picture reports ok too")
        check(not any(ln.startswith("pod") for ln in lines),
              "a disabled source is not fetched")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sources.main([])
        check(rc == 2 and "--avatars" in buf.getvalue(),
              "no flag -> usage, exit 2")
        check(not os.path.exists(os.path.join(HERE, "data", "cache",
                                              "avatars", "yt-guy.jpg")),
              "nothing landed in the real data/cache/avatars/")
    finally:
        (sources.CACHE_DIR, sources._http_get, sources._http_get_bytes,
         sources.resolve_channel_id, sources._shrink_bytes,
         sources._sips_path) = real


def main():
    print("=" * 74)
    print("SOURCES TEST - registry + fetch layer")
    print("=" * 74)

    real_registry = os.path.join(HERE, "data", "sources.yaml")
    before = None
    if os.path.exists(real_registry):
        with open(real_registry, "rb") as fh:
            before = fh.read()

    test_registry_roundtrip()
    test_registry_edits()
    test_rss_parse()
    test_timedtext()
    test_paste_and_cache()
    test_strip_tags()
    test_avatars()

    print("\n8. PRODUCTION STATE UNTOUCHED")
    if before is not None:
        with open(real_registry, "rb") as fh:
            check(fh.read() == before,
                  "data/sources.yaml byte-identical after the run")
    else:
        check(not os.path.exists(real_registry),
              "no data/sources.yaml created as a side effect")

    print("\n" + "=" * 74)
    if FAILURES:
        print("FAILED %d check(s):" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
