#!/usr/bin/env python3
"""Acceptance test: creator call extraction (engine/calls.py).

A planted transcript fixture must yield EXACTLY 8 calls - including two
negations ("don't start", "can't sit"), one "start X over Y" linked pair,
and a name typo ("Jamar Chase") - with exact verdicts and confidences.
The negation guard is the load-bearing piece: a bug there poisons every
downstream consensus, so flips and drops are asserted explicitly. Its
sibling, the interrogative guard, is asserted right beside it: a question
("Should I start X?", or any '?'-terminated sentence) is not a call and
must emit nothing - never a high-confidence start.

The fantasy topic filter is asserted on the REAL titles of a mixed channel
(Action Network: two fantasy videos, one NFL betting, one MLB, one NASCAR)
plus a betting episode with a genuine fantasy segment, which must PASS. The
counts must be reported ("3 of 6 items dropped as non-fantasy"), each drop
must carry its reason, and a source with no topic_filter must extract from
all six - proven by a call that exists only on the unfiltered source.

All persistence goes to a mkdtemp dir removed in a finally block - never
into data/creator_calls/ (same isolation pattern as tests/mock_draft.py
test_persistence).

    .venv/bin/python tests/calls_test.py
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import yaml                                                  # noqa: E402

from engine import calls                                     # noqa: E402
from engine.ingest import Matcher                            # noqa: E402
from engine.models import Player                             # noqa: E402

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _pool():
    names = [
        ("Ja'Marr Chase", "WR", "CIN"),
        ("Justin Jefferson", "WR", "MIN"),
        ("CeeDee Lamb", "WR", "DAL"),
        ("Puka Nacua", "WR", "LAR"),
        ("Jaxon Smith-Njigba", "WR", "SEA"),
        ("Bijan Robinson", "RB", "ATL"),
        ("Jahmyr Gibbs", "RB", "DET"),
        ("Travis Etienne Jr.", "RB", "JAC"),
        ("Josh Allen", "QB", "BUF"),
        ("Patrick Mahomes", "QB", "KC"),
    ]
    return [Player(rank=i + 1, name=n, pos=p, team=t)
            for i, (n, p, t) in enumerate(names)]


MATCHER = Matcher(_pool())

FIXTURE = """\
Welcome back to the show, let's get into week 3 lineups.
You have to start Justin Jefferson this week, no question.
I would sit Jaxon Smith-Njigba against that secondary.
Jamar Chase is a must-start, period.
Don't start Puka Nacua on Thursday, I know it's tempting.
You can't sit Bijan Robinson, ever - he's matchup-proof.
Start Jahmyr Gibbs over Travis Etienne in PPR formats.
I'm fading CeeDee Lamb this week, that matchup scares me.
"""

EXPECTED = {
    ("Justin Jefferson", "start", "high"),        # verb adjacent
    ("Jaxon Smith-Njigba", "sit", "high"),        # verb adjacent
    ("Ja'Marr Chase", "start", "high"),           # typo + must-start phrase
    ("Puka Nacua", "sit", "high"),                # "don't start" -> flipped
    ("Bijan Robinson", "start", "high"),          # "can't sit" -> flipped
    ("Jahmyr Gibbs", "start", "high"),            # "start X over Y"
    ("Travis Etienne Jr.", "sit", "med"),         # linked sit side of the pair
    ("CeeDee Lamb", "sit", "med"),                # fade = sit-lean, med
}


def _ex(text):
    return calls.extract(text, MATCHER, "test-src", "http://example.test", 3)


# --- 1. planted transcript -------------------------------------------------
def test_fixture():
    print("\n1. PLANTED TRANSCRIPT (8 calls, 2 negations, 1 pair, 1 typo)")
    out = _ex(FIXTURE)
    got = {(c["player"], c["verdict"], c["confidence"]) for c in out}
    check(len(out) == 8, "exactly 8 calls extracted (got %d)" % len(out))
    for trip in sorted(EXPECTED):
        check(trip in got, "%s -> %s (%s)" % trip)
    for trip in sorted(got - EXPECTED):
        check(False, "unexpected call: %s -> %s (%s)" % trip)

    by_player = {c["player"]: c for c in out}
    jj = by_player.get("Justin Jefferson", {})
    check("start Justin Jefferson" in jj.get("quote", ""),
          "quote window carries the verbatim evidence")
    check(all(0 < len(c["quote"]) <= 200 for c in out),
          "every quote is non-empty and <= 200 chars")
    check(all(c["source"] == "test-src" and c["url"] == "http://example.test"
              and c["fetched"] for c in out),
          "every call carries source, url, fetched")
    check(by_player.get("Ja'Marr Chase", {}).get("player_key") == "jamarr chase|WR",
          "typo 'Jamar Chase' resolved to pool key jamarr chase|WR")
    gibbs = by_player.get("Jahmyr Gibbs", {})
    etienne = by_player.get("Travis Etienne Jr.", {})
    check(gibbs.get("quote") == etienne.get("quote") and
          "over" in gibbs.get("quote", ""),
          "'X over Y' pair shares one linked quote window")


# --- 2. negation guard -----------------------------------------------------
def test_negation():
    print("\n2. NEGATION GUARD (flip or drop - never a false positive)")
    out = _ex("Justin Jefferson is not a must-start this week.")
    check(out == [], "'not a must-start' drops the call entirely")

    out = _ex("I would NOT start Justin Jefferson in that weather.")
    check(len(out) == 1 and out[0]["verdict"] == "sit"
          and out[0]["confidence"] == "high",
          "'would NOT start X' flips to sit (high)")

    out = _ex("You cannot trust Josh Allen here.")
    check(len(out) == 1 and out[0]["verdict"] == "sit"
          and out[0]["confidence"] == "med",
          "'cannot trust X' reads as sit (med)")

    out = _ex("Don't start Jahmyr Gibbs over Travis Etienne this week.")
    check(out == [], "negated 'start X over Y' is consumed and dropped, "
                     "not misread for either side")


# --- 2b. interrogative guard ------------------------------------------------
def test_interrogative():
    print("\n2b. INTERROGATIVE GUARD (a question is not a call - dropped, "
          "never a high-confidence verdict)")
    out = _ex("Should I start Justin Jefferson this week?")
    check(out == [], "'Should I start X this week?' emits NOTHING "
                     "(was start/high before the guard)")

    out = _ex("should i start justin jefferson this week")
    check(out == [], "unpunctuated transcript: 'should' opener alone "
                     "drops it (captions carry no '?')")

    out = _ex("Do you start Justin Jefferson over CeeDee Lamb?")
    check(out == [], "'Do you start X over Y?' drops BOTH sides of the pair")

    out = _ex("Would you sit Josh Allen in that spot?")
    check(out == [], "'Would you sit X?' emits nothing")

    out = _ex("Is it smart to start Justin Jefferson here")
    check(out == [], "'is it' opener reads as a question even unpunctuated")

    out = _ex("Justin Jefferson is a must-start, right?")
    check(out == [], "a '?'-terminated sentence drops even a must-start "
                     "phrase")

    # statements stay untouched - the guard must not eat real calls
    out = _ex("Should I start Justin Jefferson this week? "
              "Yes - start Justin Jefferson with total confidence.")
    check(len(out) == 1 and out[0]["verdict"] == "start"
          and out[0]["confidence"] == "high",
          "the ANSWER sentence after the question still counts (high)")

    out = _ex("Start Justin Jefferson this week.")
    check(len(out) == 1 and out[0]["verdict"] == "start"
          and out[0]["confidence"] == "high",
          "plain imperative statement still start/high")

    out = _ex("You should absolutely start Josh Allen.")
    check(len(out) == 1 and out[0]["verdict"] == "start",
          "'You should start...' is a statement - 'should' mid-sentence "
          "never triggers the opener check")


# --- 3. confidence tiers ---------------------------------------------------
def test_confidence_tiers():
    print("\n3. CONFIDENCE TIERS")
    out = _ex("You should absolutely start, and I mean it, Josh Allen.")
    check(len(out) == 1 and out[0]["verdict"] == "start"
          and out[0]["confidence"] == "med",
          "verb within ~8 tokens = med")

    out = _ex("Start him if you want but the guy I really love this "
              "week is Josh Allen.")
    check(len(out) == 1 and out[0]["verdict"] == "start"
          and out[0]["confidence"] == "low",
          "distant same-sentence verb = low")

    out = _ex("Random chatter about the slate with nobody named at all.")
    check(out == [], "no player hit means no calls")


# --- 4. rank + flex patterns ----------------------------------------------
def test_rank_flex():
    print("\n4. RANK AND FLEX")
    out = _ex("Puka Nacua is the WR3 this week for me.")
    check(len(out) == 1 and out[0]["verdict"] == "rank"
          and out[0].get("value") == 3 and out[0]["confidence"] == "med",
          "'X ... WR3' emits rank with value 3 (med)")

    out = _ex("Puka Nacua is the RB3 this week for me.")
    check(out == [], "position-rank mismatched to player's position is dropped")

    out = _ex("Travis Etienne is a flex play this week.")
    check(len(out) == 1 and out[0]["verdict"] == "flex"
          and out[0]["confidence"] == "med"
          and out[0]["player"] == "Travis Etienne Jr.",
          "'X is a flex play' emits flex (med), suffix-tolerant name")


# --- 5. store + dedupe (tempdir isolated) ----------------------------------
def test_store_dedupe():
    print("\n5. STORE + DEDUPE (tempdir, never data/creator_calls/)")
    tmp = tempfile.mkdtemp(prefix="calls-test-")
    try:
        out = _ex(FIXTURE)
        added, path = calls.store_calls(out, 3, calls_dir=tmp)
        check(added == 8, "first store adds all 8")
        check(path.startswith(tmp), "week file landed in the temp dir")
        added2, _ = calls.store_calls(out, 3, calls_dir=tmp)
        check(added2 == 0, "re-storing the same calls adds 0 (dedupe on "
                           "source/player_key/verdict)")
        other = [dict(out[0], source="other-src")]
        added3, _ = calls.store_calls(other, 3, calls_dir=tmp)
        check(added3 == 1, "same call from a different source is kept")
        with open(path) as fh:
            doc = yaml.safe_load(fh)
        check(doc["week"] == 3 and len(doc["calls"]) == 9,
              "week file round-trips: week 3, 9 calls")
        c0 = doc["calls"][0]
        check(all(k in c0 for k in ("source", "player", "player_key",
                                    "verdict", "confidence", "quote", "url",
                                    "fetched")),
              "stored calls carry the full contract fields")
        # hand-written call first (the Claude weekly pass), then auto: the
        # hand-written entry must win the dedupe.
        hand = {"source": "test-src", "player": "Josh Allen",
                "player_key": "josh allen|QB", "verdict": "start",
                "confidence": "high", "quote": "hand-written",
                "url": "", "fetched": "2026-09-02"}
        calls.store_calls([hand], 4, calls_dir=tmp)
        auto = _ex("Start Josh Allen this week.")
        addedh, path4 = calls.store_calls(auto, 4, calls_dir=tmp)
        with open(path4) as fh:
            doc4 = yaml.safe_load(fh)
        check(addedh == 0 and doc4["calls"][0]["quote"] == "hand-written",
              "hand-written call is never clobbered by auto-extraction")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 6. ingest_week orchestration ------------------------------------------
def test_ingest_week():
    print("\n6. INGEST WEEK (per-source counts, visible failures)")
    tmp = tempfile.mkdtemp(prefix="calls-ingest-")
    real_fetch = calls._fetch_items

    def fake_fetch(src):
        if src["id"] == "good-yt":
            return [{"title": "Week 3 rankings", "url": "http://yt.test/v1",
                     "published": "2026-09-02",
                     "text": "Start Justin Jefferson this week."},
                    {"title": "No captions", "url": "http://yt.test/v2",
                     "published": "2026-09-01", "text": None,
                     "reason": "captions disabled"}], None
        if src["id"] == "x-pastes":
            return [], None                     # empty hand-paste store
        return None, "SourceError: source dead-rss (rss) unreachable (planted)"

    try:
        calls._fetch_items = fake_fetch
        registry = [
            {"id": "engine", "type": "feed", "enabled": True, "weight": 40},
            {"id": "good-yt", "type": "youtube", "enabled": True, "weight": 20,
             "handle": "http://yt.test"},
            {"id": "dead-rss", "type": "rss", "enabled": True, "weight": 10,
             "handle": "http://rss.test"},
            {"id": "x-pastes", "type": "paste", "enabled": True, "weight": 10},
            {"id": "off", "type": "url", "enabled": False, "weight": 5},
        ]
        report = calls.ingest_week(3, MATCHER, registry, calls_dir=tmp)
        srcs = report["sources"]
        check("engine" not in srcs, "feed sources are not fetched by calls")
        check("off" not in srcs, "disabled sources are not fetched")
        good = srcs.get("good-yt", {})
        check(good.get("status") == "ok" and good.get("items") == 2
              and good.get("calls") == 1 and good.get("added") == 1,
              "good source: 2 items, 1 call extracted, 1 added")
        check("1/2" in good.get("note", ""),
              "caption-less item is a visible partial, not a vanished video")
        dead = srcs.get("dead-rss", {})
        check(dead.get("status") == "failed"
              and "unreachable" in dead.get("note", ""),
              "failed source stays VISIBLE in the report with its error")
        check(len(report["failures"]) == 1
              and report["failures"][0]["source"] == "dead-rss",
              "failures list names the dead source")
        paste = srcs.get("x-pastes", {})
        check(paste.get("status") == "ok" and paste.get("items") == 0
              and "paste-only" in paste.get("note", ""),
              "empty paste store is visible (X is paste-only: ToS)")
        with open(os.path.join(tmp, "week-3.yaml")) as fh:
            doc = yaml.safe_load(fh)
        check(len(doc["calls"]) == 1
              and doc["calls"][0]["source"] == "good-yt"
              and doc["calls"][0]["url"] == "http://yt.test/v1",
              "stored call carries the item's own url")
    finally:
        calls._fetch_items = real_fetch
        shutil.rmtree(tmp, ignore_errors=True)


# --- 7. registry loading ----------------------------------------------------
def test_registry():
    print("\n7. REGISTRY (delegates to engine/sources.py, seeds if missing)")
    tmp = tempfile.mkdtemp(prefix="calls-reg-")
    try:
        path = os.path.join(tmp, "sources.yaml")
        srcs = calls.load_registry(path)
        by_id = {s["id"]: s for s in srcs}
        check(set(by_id) == {"engine", "espn-proj", "sleeper-proj",
                             "chen-tiers"},
              "missing registry is seeded with exactly the four feeds")
        check(os.path.exists(path), "seed was written to disk")
        check(all(s["type"] == "feed" and s["enabled"] for s in srcs),
              "all four seeds are enabled feeds")
        weights = {"engine": 40, "espn-proj": 25, "sleeper-proj": 20,
                   "chen-tiers": 15}
        check(all(by_id[k]["weight"] == w for k, w in weights.items()),
              "seed weights are 40/25/20/15")
        again = calls.load_registry(path)
        check([s["id"] for s in again] == [s["id"] for s in srcs],
              "reloading an existing registry does not reseed or reorder")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 8. fantasy topic filter (classification) -------------------------------
# The five titles below are REAL items seen live on the Action Network
# YouTube channel (the "the-favorites" source, topic_filter: fantasy) - a
# genuinely mixed feed where only ~3 of 15 recent videos were fantasy. The
# sixth is the case the filter must NOT over-reject: a betting show that
# spends real time on fantasy fallout.
REAL_ITEMS = [
    {"title": "Herbert & Love could be 2026 Fantasy Football LEAGUE WINNERS!",
     "url": "http://yt.test/fantasy1", "published": "2026-09-02",
     "keep": True,
     "text": "Two quarterbacks we love as league winners this year. "
             "Start Josh Allen every week, but Herbert and Love are the "
             "values at their cost."},
    {"title": "2026 Fantasy Football League Winners",
     "url": "http://yt.test/fantasy2", "published": "2026-09-02",
     "keep": True,
     "text": "Our full league winner list for 2026 fantasy football. "
             "Start Justin Jefferson with total confidence in PPR."},
    {"title": "NFL Trends Expert Bettors MUST Know",
     "url": "http://yt.test/betting", "published": "2026-09-01",
     "keep": False,
     "text": "The sharp bettors are on the Bills moneyline. Josh Allen is "
             "the best quarterback in the league against the spread, and we "
             "would fade Josh Allen at that number."},
    {"title": "TWO MLB Home Run Plays For Today",
     "url": "http://yt.test/mlb", "published": "2026-09-01", "keep": False,
     "text": "Two home run props for tonight's MLB slate plus a pitcher "
             "strikeout play."},
    {"title": "Cook Out Southern 500 Best Bets",
     "url": "http://yt.test/nascar", "published": "2026-08-31", "keep": False,
     "text": "Our best bets for the Cook Out Southern 500 at Darlington, "
             "including the race winner and top-10 finishes."},
    {"title": "NFL Week 3 Betting Preview: Every Total and Spread",
     "url": "http://yt.test/mixed", "published": "2026-09-02", "keep": True,
     "text": "The Lions team total is up to fifty-one, and that game script "
             "matters for fantasy football too. Puka Nacua is a smash play "
             "in PPR. I would start Bijan Robinson over Travis Etienne in "
             "your flex."},
]


def test_topic_filter():
    print("\n8. FANTASY TOPIC FILTER (real mixed-channel titles)")
    for it in REAL_ITEMS:
        v = calls.classify_topic(it["title"], it["text"], "fantasy")
        want = "KEEP" if it["keep"] else "DROP"
        got = "KEEP" if v["keep"] else "DROP"
        check(v["keep"] == it["keep"],
              "%s  %s  (fantasy %.1f vs other %.1f)"
              % (got if got == want else "%s (want %s)" % (got, want),
                 it["title"][:52], v["fantasy"], v["other"]))

    mixed = calls.classify_topic(REAL_ITEMS[5]["title"], REAL_ITEMS[5]["text"],
                                 "fantasy")
    check(mixed["keep"] and mixed["fantasy"] > mixed["other"],
          "MIXED betting show with a fantasy segment PASSES - the bar is "
          "'discusses fantasy relevance', not 'fantasy-only show'")
    check(calls.classify_topic(REAL_ITEMS[5]["title"], "", "fantasy")["keep"]
          is False,
          "...and that same betting TITLE alone would drop - the fantasy "
          "evidence came from the body, as intended")

    # every verdict is auditable
    for it in REAL_ITEMS:
        v = calls.classify_topic(it["title"], it["text"], "fantasy")
        check(bool(v["reason"]) and "fantasy" in v["reason"]
              and "other" in v["reason"],
              "reason records both scores: %s" % v["reason"][:74])

    mlb = calls.classify_topic("TWO MLB Home Run Plays For Today", "", "fantasy")
    check("mlb" in mlb["other_evidence"],
          "dropped MLB item names its own evidence (%s)"
          % ", ".join(mlb["other_evidence"]))

    # an other-sport signal cannot win when real fantasy content is present
    both = calls.classify_topic(
        "Fantasy Football Week 3 Start/Sit", "Quick NBA note at the top, "
        "then start Justin Jefferson and stream a defense in PPR leagues.",
        "fantasy")
    check(both["keep"], "a passing NBA mention does not sink a fantasy show")

    # a fantasy-shaped phrase for the WRONG sport is still out
    fb = calls.classify_topic("Fantasy Baseball Waiver Wire Adds",
                              "Our fantasy baseball waiver wire pickups and "
                              "two-start pitchers for the week.", "fantasy")
    check(not fb["keep"], "'fantasy baseball waiver wire' is dropped - the "
                          "filter is fantasy FOOTBALL")


def test_topic_filter_off():
    print("\n8b. NO TOPIC FILTER = NO FILTERING (sources are unaffected)")
    items = [dict(it) for it in REAL_ITEMS]
    for topic in (None, "", "  "):
        kept, drops = calls.filter_items(items, topic)
        check(len(kept) == len(items) and drops == [],
              "topic_filter=%r keeps every item (%d), drops none"
              % (topic, len(kept)))
    v = calls.classify_topic("TWO MLB Home Run Plays For Today", "", None)
    check(v["keep"] and v["reason"] == "no topic filter applied",
          "an unfiltered source keeps even an MLB item, and says why")

    kept, drops = calls.filter_items(items, "hockey")
    check(len(kept) == len(items) and drops == [],
          "an UNSUPPORTED topic_filter keeps everything - a filter nobody "
          "implements never silently eats a source")
    topic, warn = calls.source_topic({"topic_filter": "hockey"})
    check(topic is None and "unknown topic_filter" in (warn or ""),
          "...and the unknown value comes back as a visible warning")
    check(calls.source_topic({"topic_filter": "FANTASY "}) == ("fantasy", None),
          "topic_filter is normalized (case/space tolerant)")
    check(calls.source_topic({}) == (None, None),
          "a source with no topic_filter field reports no filter, no warning")


# --- 9. ingest_week with the topic filter -----------------------------------
def test_ingest_topic_filter():
    print("\n9. INGEST WEEK + TOPIC FILTER (counts reported, never silent)")
    tmp = tempfile.mkdtemp(prefix="calls-topic-")
    real_fetch = calls._fetch_items

    def fake_fetch(src):
        return [{k: v for k, v in it.items() if k != "keep"}
                for it in REAL_ITEMS], None

    try:
        calls._fetch_items = fake_fetch
        registry = [
            {"id": "the-favorites", "type": "youtube", "enabled": True,
             "weight": 20, "handle": "http://yt.test",
             "topic_filter": "fantasy"},
            {"id": "unfiltered", "type": "youtube", "enabled": True,
             "weight": 20, "handle": "http://yt.test"},
        ]
        report = calls.ingest_week(3, MATCHER, registry, calls_dir=tmp)
        filt = report["sources"]["the-favorites"]
        raw = report["sources"]["unfiltered"]

        check(filt.get("items") == 6 and filt.get("kept") == 3
              and filt.get("dropped") == 3,
              "filtered source reports items=6, kept=3, dropped=3")
        check("3 of 6 items dropped as non-fantasy" in filt.get("note", ""),
              "the drop count is REPORTED in the note (%s)"
              % filt.get("note", ""))
        check(filt.get("topic_filter") == "fantasy",
              "row names the filter that was applied")
        dropped_titles = {d["title"] for d in filt.get("drops", [])}
        check(dropped_titles == {"NFL Trends Expert Bettors MUST Know",
                                 "TWO MLB Home Run Plays For Today",
                                 "Cook Out Southern 500 Best Bets"},
              "exactly the betting/MLB/NASCAR items were dropped")
        check(all(d.get("reason") and d.get("url")
                  for d in filt.get("drops", [])),
              "every dropped item carries its own reason and url")

        check(raw.get("items") == 6 and raw.get("kept") == 6
              and raw.get("dropped") == 0 and raw.get("drops") == [],
              "source WITHOUT topic_filter is unaffected: 6 items, 6 kept, "
              "0 dropped")
        check("dropped as non-fantasy" not in raw.get("note", ""),
              "...and its note says nothing about dropping")
        check(raw.get("topic_filter") is None,
              "...and its row reports no filter")

        check(filt.get("calls") == 5 and raw.get("calls") == 6,
              "same 6 items -> 5 calls filtered vs 6 unfiltered (got %s/%s)"
              % (filt.get("calls"), raw.get("calls")))

        totals = report.get("totals", {})
        check(totals.get("items") == 12 and totals.get("dropped") == 3
              and totals.get("kept") == 9,
              "report totals aggregate items/kept/dropped for the CLI+panel")
        check(totals.get("calls") == 11 and totals.get("added") == 11,
              "report totals aggregate calls/added (got %s/%s)"
              % (totals.get("calls"), totals.get("added")))

        with open(os.path.join(tmp, "week-3.yaml")) as fh:
            doc = yaml.safe_load(fh)
        by_src = {}
        for c in doc["calls"]:
            by_src.setdefault(c["source"], []).append(c)
        dropped_urls = {d["url"] for d in filt.get("drops", [])}
        check(not any(c["url"] in dropped_urls
                      for c in by_src.get("the-favorites", [])),
              "no stored call traces back to a dropped item")
        fade = [c for c in by_src.get("unfiltered", [])
                if c["url"] == "http://yt.test/betting"]
        check(len(fade) == 1 and fade[0]["verdict"] == "sit",
              "the betting item's 'fade Josh Allen' call EXISTS for the "
              "unfiltered source (proving the filter, not the extractor, "
              "made the difference)")
        check(not [c for c in by_src.get("the-favorites", [])
                   if c["url"] == "http://yt.test/betting"],
              "...and does NOT exist for the filtered source")
    finally:
        calls._fetch_items = real_fetch
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("CREATOR CALLS TEST")
    test_fixture()
    test_negation()
    test_interrogative()
    test_confidence_tiers()
    test_rank_flex()
    test_store_dedupe()
    test_ingest_week()
    test_registry()
    test_topic_filter()
    test_topic_filter_off()
    test_ingest_topic_filter()
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0]
                    if not FAILURES else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
