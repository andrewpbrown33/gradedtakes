"""Creator call extraction: mine start/sit calls out of transcripts and articles.

TIER-2 QUALITY, BY DESIGN. Pattern extraction over free text is crude: it
finds player names with the fuzzy Matcher (n-gram scan) and looks for a small
family of start/sit patterns in a window around each hit. It will miss
sarcasm, hedges, and any phrasing outside the families below. Because of
that, every auto-extracted call carries a `confidence` tier and the exact
`quote` window it came from - a call without evidence is a call you can't
audit. Consumers should weight accordingly.

THE SCHEMA IS THE API (the optional Claude weekly pass). The week file
`data/creator_calls/week-<N>.yaml` is deliberately hand-editable: a human or
Claude reading/watching the sources directly can write high-confidence calls
straight into the file in the same shape and they flow through consensus
identically to auto-extracted ones. When the crude extractor and a careful
reader disagree, hand-written entries (typically `confidence: high` with a
real quote) are the fix - not a smarter regex.

NO TWITTER/X SCRAPING - ANYWHERE. X's Terms of Service prohibit scraping,
and logged-in scraping risks the account. X content enters this system one
way only: the user pastes text by hand (engine/sources.py add_paste, or
straight into the week file). A `paste`-type source in data/sources.yaml is
"fetched" only from that hand-paste store - ingest_week() never touches
x.com/twitter.com, and an empty paste store is reported visibly instead of
pretending it was covered.

Pattern families (case-insensitive, windowed around Matcher name hits):
  "start X" / "sit X" / "bench X"        verb adjacent = high, within ~8 = med
  "start X over Y"                       start-X (high) AND sit-Y (med), linked
  "X over Y" near start/sit context      both med (verb near) or low (loose)
  "X is a must-start / smash play /
     league-winner"                      start, high
  "fade X"                               sit, med (a lean, not a slam)
  "can't trust X"                        sit, med
  "X ... WR3/RB12" (position rank)       rank + value, med
  "X is a flex play"                     flex, med
Negation guard: "don't start X" -> sit, "you can't sit X" -> start (flipped,
same tier); "not a must-start" -> dropped. A negation bug here poisons the
whole feature, so the guard is tested explicitly in tests/calls_test.py.

Interrogative guard: A QUESTION IS NOT A CALL - it is dropped outright, not
downgraded. A sentence that ends with "?" or OPENS with an interrogative
auxiliary (should/do/does/did/would, or "is it") emits nothing: "Should I
start Justin Jefferson this week?" is usually a read-out viewer question
whose answer lives in a different sentence, and even a creator musing aloud
is expressing doubt, not a verdict - keeping it at low confidence would
still count doubt as a lean, wrong about half the time. Dropping is chosen
over downgrading for exactly that reason. The opener list is deliberately
narrow (no "can"/"will"/"is" alone) so "Will Levis is a must-start" never
reads as a question; punctuated text gets the "?" check too, and
unpunctuated caption transcripts still get the opener check. Tested in
tests/calls_test.py alongside the negation guard.

FANTASY TOPIC FILTER (mixed sources). A source row may carry
`topic_filter: fantasy` (engine/sources.py owns the field). When it does,
every fetched item is CLASSIFIED BEFORE EXTRACTION: title+text are scored
against fantasy-football signals (fantasy football, start/sit, waiver, PPR,
flex, league winner, lineup, target share...) and against other-sport /
pure-betting signals (MLB, NASCAR, NBA, CFB, survivor pool, moneyline,
parlay, spread...). An item is kept only when the fantasy score clears an
absolute floor AND is not dominated by the other-topic score. Both scores
and the matched evidence are recorded on every decision - kept or dropped.

The bar is "does this discuss fantasy football relevance", NOT "is this a
fantasy-only show": a betting episode that spends two minutes on fantasy
fallout PASSES. That asymmetry is deliberate - a weak-but-real fantasy
signal is kept unless another topic outweighs it by DOMINANCE.

Dropped items are never silent. ingest_week() counts them per source
("11 of 15 items dropped as non-fantasy" in the row's note), keeps the
per-item reasons in row["drops"], and the CLI prints them. A source with no
topic_filter is untouched - every item goes to extraction as before.

Honest degradation: ingest_week() returns a row for EVERY enabled non-feed
source - fetch failures, caption-less videos, stale caches, empty paste
stores and topic-filtered drops are reported, never silently absent.

CLI:
    .venv/bin/python -m engine.calls --week 3 [--league yahoo-main]
"""

import argparse
import datetime
import os
import re
from typing import Dict, List, Optional, Tuple

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS_DIR = os.path.join(HERE, "data", "creator_calls")
REGISTRY_PATH = os.path.join(HERE, "data", "sources.yaml")

MIN_NAME_SCORE = 76        # matcher score floor for an n-gram to count as a name
NEAR_WINDOW = 8            # "verb within ~8 tokens" = med
FAR_WINDOW = 14            # verb 9..14 tokens back, same sentence = low
QUOTE_PAD = 45             # chars of context on each side of the evidence
QUOTE_MAX = 200

START_VERBS = {"start", "starting"}
SIT_VERBS = {"sit", "sitting", "bench", "benching"}
FADE_VERBS = {"fade", "fading"}    # a lean: med even when adjacent
NEGATORS = {"not", "no", "never", "dont", "don't", "cant", "can't", "cannot",
            "wouldnt", "wouldn't", "shouldnt", "shouldn't", "couldnt",
            "couldn't", "aint", "ain't", "isnt", "isn't", "wont", "won't"}
CONTEXT_WORDS = START_VERBS | SIT_VERBS | {"lineup", "lineups", "flex"}
# Interrogative sentence OPENERS (see the interrogative guard in the module
# docstring). Deliberately narrow: "will"/"can"/"is" alone would swallow
# "Will Levis is a must-start" - "is" counts only as the pair "is it".
QUESTION_OPENERS = {"should", "do", "does", "did", "would"}

MUST_START_RE = re.compile(
    r"\b(must[\s\-]?start|smash[\s\-]?play|league[\s\-]?winner)\b", re.I)
FLEX_RE = re.compile(r"\bflex\b[\s\-]?(play|start|option)\b", re.I)
RANK_TOKEN_RE = re.compile(r"^(qb|rb|wr|te|k|def|dst)(\d{1,2})$", re.I)

# Words that never begin or end a player-name n-gram (keeps the fuzzy scan
# from swallowing verbs/articles into the name span).
EDGE_STOPWORDS = {
    "start", "starting", "sit", "sitting", "bench", "benching", "fade",
    "fading", "over", "under", "the", "a", "an", "and", "or", "but", "if",
    "so", "as", "is", "was", "are", "be", "been", "i", "you", "we", "they",
    "he", "she", "it", "him", "her", "them", "me", "us", "my", "your", "his",
    "their", "our", "this", "that", "these", "those", "to", "of", "in", "on",
    "at", "for", "with", "by", "from", "against", "vs", "not", "no", "never",
    "do", "dont", "don't", "cant", "can't", "cannot", "would", "wouldnt",
    "wouldn't", "should", "could", "will", "wont", "won't", "must", "trust",
    "play", "playing", "week", "guy", "guys", "gonna", "really", "here",
    "there", "up", "out", "ever", "very", "just", "who", "what", "when",
    "love", "like", "hate", "want", "have", "has", "had", "get", "got",
}

CONF_RANK = {"high": 3, "med": 2, "low": 1}


# ---------------------------------------------------------------------------
# tokenizing
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[A-Za-z0-9'’.\-]+")
SENT_BREAK_RE = re.compile(r"[.!?;]|\n\s*\n")


class Tok(object):
    __slots__ = ("word", "low", "start", "end", "sent")

    def __init__(self, word, start, end, sent):
        self.word = word
        self.low = word.lower().replace("’", "'").strip(".,")
        self.start = start
        self.end = end
        self.sent = sent


def _tokenize(text: str) -> List[Tok]:
    toks = []
    sent = 0
    prev_end = 0
    for m in TOKEN_RE.finditer(text):
        gap = text[prev_end:m.start()]
        if toks and SENT_BREAK_RE.search(gap):
            sent += 1
        toks.append(Tok(m.group(0), m.start(), m.end(), sent))
        prev_end = m.end()
    return toks


def _question_sents(text: str, toks: List[Tok]) -> set:
    """Sentence ids that read as questions (the interrogative guard).

    A sentence qualifies when (a) its terminating punctuation contains "?"
    (checked in the raw gap after its last token, so a trailing "?" at end
    of text counts too), or (b) its FIRST token is an interrogative
    auxiliary from QUESTION_OPENERS, or the pair "is it" - the opener check
    is what still catches unpunctuated caption transcripts. Every pattern
    family requires verb/name/phrase in one sentence, so dropping hits in
    these sentences drops the whole would-be call.
    """
    out = set()
    first = {}
    for idx, t in enumerate(toks):
        if t.sent not in first:
            first[t.sent] = idx
    for sent, idx in first.items():
        low = toks[idx].low
        if low in QUESTION_OPENERS:
            out.add(sent)
        elif (low == "is" and idx + 1 < len(toks)
              and toks[idx + 1].sent == sent and toks[idx + 1].low == "it"):
            out.add(sent)
    for k, t in enumerate(toks):
        gap = (text[t.end:toks[k + 1].start] if k + 1 < len(toks)
               else text[t.end:])
        if "?" in gap:
            out.add(t.sent)
    return out


# ---------------------------------------------------------------------------
# name scan
# ---------------------------------------------------------------------------

class _Hit(object):
    __slots__ = ("i", "j", "match")

    def __init__(self, i, j, match):
        self.i = i      # first token index (inclusive)
        self.j = j      # last token index (exclusive)
        self.match = match


def _name_like(words: List[str]) -> bool:
    lows = [w.lower().replace("’", "'").strip(".,") for w in words]
    if lows[0] in EDGE_STOPWORDS or lows[-1] in EDGE_STOPWORDS:
        return False
    for w in lows:
        if len(w) < 2 or not re.search(r"[a-z]", w):
            return False
    return True


def _player_token_set(matcher) -> set:
    toks = set()
    for alias in matcher.aliases:
        toks.update(alias.split())
    return toks


def _scan_players(toks: List[Tok], matcher) -> List[_Hit]:
    """Find player-name spans via bigram-then-trigram fuzzy scan."""
    from .models import norm_name  # local import keeps module load cheap
    pool_tokens = _player_token_set(matcher)
    hits, used, memo = [], set(), {}
    for n in (2, 3):
        for i in range(len(toks) - n + 1):
            span = range(i, i + n)
            if any(k in used for k in span):
                continue
            words = [toks[k].word for k in span]
            if toks[i].sent != toks[i + n - 1].sent:
                continue
            if not _name_like(words):
                continue
            # cheap prefilter: at least one token must appear in the pool
            if not any(t in pool_tokens for t in norm_name(" ".join(words)).split()):
                continue
            key = " ".join(w.lower() for w in words)
            if key not in memo:
                memo[key] = matcher.match(" ".join(words))
            m = memo[key]
            if m is not None and m.score >= MIN_NAME_SCORE and not m.ambiguous:
                hits.append(_Hit(i, i + n, m))
                used.update(span)
    hits.sort(key=lambda h: h.i)
    return hits


# ---------------------------------------------------------------------------
# pattern evaluation
# ---------------------------------------------------------------------------

def _quote(text: str, toks: List[Tok], lo_tok: int, hi_tok: int) -> str:
    lo = max(0, toks[lo_tok].start - QUOTE_PAD)
    hi = min(len(text), toks[hi_tok - 1].end + QUOTE_PAD)
    q = re.sub(r"\s+", " ", text[lo:hi]).strip()
    return q[:QUOTE_MAX]


def _negated_before(toks: List[Tok], verb_idx: int, back: int = 3) -> bool:
    sent = toks[verb_idx].sent
    for k in range(max(0, verb_idx - back), verb_idx):
        if toks[k].sent == sent and toks[k].low in NEGATORS:
            return True
    return False


def _flip(verdict: str) -> Optional[str]:
    return {"start": "sit", "sit": "start"}.get(verdict)


def _verb_before(toks: List[Tok], i: int) -> Optional[Tuple[str, str, int]]:
    """Nearest start/sit/fade verb before token i in the same sentence.

    Returns (verdict, confidence, verb_idx) with the negation guard applied,
    or None. Fade is capped at med; a negated fade is dropped outright.
    """
    sent = toks[i].sent
    for k in range(i - 1, max(-1, i - 1 - FAR_WINDOW), -1):
        if k < 0 or toks[k].sent != sent:
            break
        low = toks[k].low
        verdict = None
        if low in START_VERBS:
            verdict = "start"
        elif low in SIT_VERBS:
            verdict = "sit"
        elif low in FADE_VERBS:
            if _negated_before(toks, k):
                return None            # "wouldn't fade X" - too twisty, drop
            dist = i - k
            if dist > NEAR_WINDOW:
                return ("sit", "low", k)
            return ("sit", "med", k)
        if verdict is None:
            continue
        if _negated_before(toks, k):
            verdict = _flip(verdict)
            if verdict is None:
                return None
        dist = i - k
        if dist == 1:
            return (verdict, "high", k)
        if dist <= NEAR_WINDOW:
            return (verdict, "med", k)
        return (verdict, "low", k)
    return None


def _cant_trust_before(toks: List[Tok], i: int) -> Optional[int]:
    """'can't trust X' immediately before the name -> sit, med."""
    if i >= 2 and toks[i - 1].low == "trust" and toks[i - 2].low in NEGATORS \
            and toks[i - 1].sent == toks[i].sent:
        return i - 2
    return None


def _phrase_after(text: str, toks: List[Tok], hit: _Hit):
    """must-start / flex / positional-rank patterns in the following window.

    Returns (verdict, confidence, value, last_tok_idx) or None. A negator
    between the name and the phrase drops the call (never flips - "not a
    must-start" is a shrug, not a sit).
    """
    sent = toks[hit.i].sent
    follow = []
    for k in range(hit.j, min(len(toks), hit.j + NEAR_WINDOW)):
        if toks[k].sent != sent:
            break
        follow.append(k)
    if not follow:
        return None
    joined = " ".join(toks[k].low for k in follow)

    m = MUST_START_RE.search(joined)
    if m is not None:
        prefix_words = joined[:m.start()].split()
        if not any(w in NEGATORS for w in prefix_words):
            return ("start", "high", None, follow[-1] + 1)

    m = FLEX_RE.search(joined)
    if m is not None:
        prefix_words = joined[:m.start()].split()
        if not any(w in NEGATORS for w in prefix_words):
            return ("flex", "med", None, follow[-1] + 1)

    for k in follow[:4]:
        rm = RANK_TOKEN_RE.match(toks[k].low)
        if rm is not None:
            pos = {"PK": "K", "DST": "DEF"}.get(rm.group(1).upper(),
                                                rm.group(1).upper())
            if pos == hit.match.player.pos:
                if any(toks[x].low in NEGATORS for x in range(hit.j, k)):
                    return None
                val = int(rm.group(2))
                if 1 <= val <= 99:
                    return ("rank", "med", val, k + 1)
    return None


def _pair_over(text: str, toks: List[Tok], a: _Hit, b: _Hit):
    """'X over Y' -> start-X + sit-Y, linked. Requires start/sit context.

    Returns a list of linked calls, [] when the pair is recognized but too
    twisty to trust (negated / sit-framed - both hits are consumed so the
    generic pass can't mis-read them), or None when this isn't a pair.
    """
    between = [k for k in range(a.j, b.i)]
    if len(between) != 1 or toks[between[0]].low != "over":
        return None
    if toks[a.i].sent != toks[b.i].sent:
        return None
    vb = _verb_before(toks, a.i)
    if vb is not None and vb[0] == "start":
        _, conf, verb_idx = vb
        x_conf = conf
        y_conf = "med" if conf == "high" else conf
        lo = min(verb_idx, a.i)
    elif vb is not None:
        return []       # "don't start X over Y" etc - consume both, emit none
    else:
        sent = toks[a.i].sent
        has_ctx = any(t.sent == sent and t.low in CONTEXT_WORDS for t in toks)
        if not has_ctx:
            return None
        x_conf = y_conf = "low"
        lo = a.i
    q = _quote(text, toks, lo, b.j)
    return [(a, "start", x_conf, None, q), (b, "sit", y_conf, None, q)]


# ---------------------------------------------------------------------------
# topic classification (the fantasy filter for MIXED sources)
# ---------------------------------------------------------------------------

FANTASY = "fantasy"

TITLE_WEIGHT = 2.0     # a title is a topic label, not a passing remark
KEEP_FLOOR = 4.0       # absolute fantasy evidence required to extract at all
DOMINANCE = 2.0        # other-topic score this many x fantasy -> drop


def _compile(rows):
    return [(w, re.compile(p, re.I), label) for w, p, label in rows]


# Fantasy-football signals. Weights are evidence strength, not frequency:
# each PATTERN scores at most once per field, so a transcript that says
# "points" forty times cannot out-shout one "fantasy football".
FANTASY_SIGNALS = _compile([
    (5.0, r"fantasy\s+football", "fantasy football"),
    (4.5, r"\bstart\s*[/&+-]\s*sit\b|\bstart\s+or\s+sit\b"
          r"|start\s*'?\s*em\b[^.]{0,20}\bsit\s*'?\s*em", "start/sit"),
    (4.0, r"\bwaivers?\b|\bwaiver\s+wire\b|\bfaab\b"
          r"|\bfree\s+agent\s+pick\s?ups?\b", "waiver wire"),
    (4.0, r"\bppr\b|\bhalf[\s-]ppr\b|\bsuperflex\b|\bdynasty\b"
          r"|\bbest\s+ball\b|\bstandard\s+scoring\b", "fantasy format"),
    (4.0, r"\bfantasy\s+(points?|managers?|value|relevance|relevant|lineups?"
          r"|owners?|playoffs?|championship|purposes|fallout|implications?)\b",
     "fantasy relevance"),
    (3.5, r"\bmust[\s-]?starts?\b|\bmust[\s-]?sits?\b", "must-start"),
    (3.0, r"\bleague[\s-]?win(ner|ners|ning)\b", "league winner"),
    (3.0, r"\bsmash\s+(play|spot)\b|\bboom[\s-]or[\s-]bust\b", "smash play"),
    (3.0, r"\bflex\b", "flex"),
    (3.0, r"\btarget\s+share\b|\bsnap\s+(share|counts?)\b"
          r"|\btouch(es)?\s+share\b|\bair\s+yards\b", "usage share"),
    (3.0, r"\badp\b|\bhandcuffs?\b|\bstreamers?\b|\bstartable\b",
     "fantasy jargon"),
    (3.0, r"\blineups?\b|\b(start|sit|bench)\s+(him|them)\b"
          r"|\bin\s+your\s+(lineup|flex|starting)\b", "lineup talk"),
    (2.5, r"\bsleepers?\b|\bbusts?\b|\bbreakouts?\b", "sleeper/bust"),
    (2.0, r"\brosters?\b|\bbench\b|\bwaiver\s+claim\b|\bdrop\s+candidates?\b",
     "roster talk"),
    (2.0, r"\bred[\s-]zone\b|\btouches\b|\btargets\b|\bcarries\b|\bsnaps\b"
          r"|\bvolume\b|\busage\b", "usage volume"),
    (1.5, r"\bfantasy\b", "fantasy (generic)"),
    (1.5, r"\brankings?\b|\btiers?\b|\bprojections?\b", "rankings"),
    (1.0, r"\bpoints?\b|\bmatchups?\b", "points/matchup"),
])

# Other-sport and pure-betting signals. NFL/football terms are deliberately
# ABSENT: they are shared ground between a fantasy show and a betting show,
# so they can never be evidence against fantasy.
OTHER_SIGNALS = _compile([
    (6.0, r"\bmlb\b|\bbaseball\b|\bworld\s+series\b", "mlb"),
    (6.0, r"\bnascar\b|\bcup\s+series\b|\bxfinity\s+series\b|\bdaytona\b"
          r"|\btalladega\b|\bdarlington\b|\bsouthern\s+500\b|\bindycar\b"
          r"|\bformula\s*(1|one)\b|\bgrand\s+prix\b", "motorsports"),
    (6.0, r"\bnba\b|\bwnba\b|\bbasketball\b", "nba"),
    (6.0, r"\bnhl\b|\bhockey\b|\bufc\b|\bmma\b|\bpga\b|\bgolf\b|\btennis\b"
          r"|\bsoccer\b|\bpremier\s+league\b", "other sport"),
    (6.0, r"fantasy\s+(baseball|basketball|hockey|golf|nascar|soccer)",
     "fantasy other-sport"),
    (4.0, r"\bcollege\s+football\b|\bcfb\b|\bncaa\b|\bheisman\b",
     "college football"),
    (4.0, r"\bsurvivor\s+pool\b|\bmoneylines?\b|\bparlays?\b|\bteasers?\b"
          r"|\bprop\s+bets?\b|\bhome\s+run\s+props?\b", "pure betting"),
    (4.0, r"\bhome\s+runs?\b|\bpitchers?\b|\bpitching\b|\bstrikeouts?\b"
          r"|\bbullpen\b|\binnings?\b|\bdingers?\b", "baseball terms"),
    (3.0, r"\bbest\s+bets?\b|\bbettors?\b|\bsportsbooks?\b"
          r"|\bagainst\s+the\s+spread\b|\bats\b", "betting"),
    (2.5, r"\bbetting\b|\bodds\b|\bwagers?\b|\bvig\b", "odds/wagers"),
    (2.0, r"\bspreads?\b|\bover/under\b|\bo/u\b|\bpuck\s+line\b"
          r"|\bcover\s+the\s+spread\b", "spread"),
])


def _score(field: str, signals) -> Tuple[float, List[Tuple[float, str]]]:
    """Sum the weights of the DISTINCT patterns that match `field`."""
    if not field:
        return 0.0, []
    total = 0.0
    hits = []
    for weight, rx, label in signals:
        if rx.search(field):
            total += weight
            hits.append((weight, label))
    return total, hits


def _evidence(hits: List[Tuple[float, str]], limit: int = 3) -> List[str]:
    best = {}
    for weight, label in hits:
        if label not in best or weight > best[label]:
            best[label] = weight
    ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
    return [label for label, _ in ranked[:limit]]


def classify_topic(title: Optional[str], text: Optional[str],
                   topic: str = FANTASY) -> Dict:
    """Score one fetched item for topical fit. Never raises.

    Returns {"topic", "keep", "fantasy", "other", "floor", "reason",
    "fantasy_evidence", "other_evidence"}. `reason` always says WHY, with
    both scores and the matched signals - a drop you cannot audit is a
    silent drop.

    Only "fantasy" is implemented; any other (or empty) topic means no
    filter, so keep=True with a reason that says so.
    """
    if (topic or "").strip().lower() != FANTASY:
        return {"topic": topic or None, "keep": True, "fantasy": 0.0,
                "other": 0.0, "floor": KEEP_FLOOR,
                "reason": "no topic filter applied",
                "fantasy_evidence": [], "other_evidence": []}

    f_title, fh_title = _score(title or "", FANTASY_SIGNALS)
    f_text, fh_text = _score(text or "", FANTASY_SIGNALS)
    o_title, oh_title = _score(title or "", OTHER_SIGNALS)
    o_text, oh_text = _score(text or "", OTHER_SIGNALS)

    fantasy = f_title * TITLE_WEIGHT + f_text
    other = o_title * TITLE_WEIGHT + o_text
    f_ev = _evidence(fh_title + fh_text)
    o_ev = _evidence(oh_title + oh_text)

    detail = "fantasy %.1f (%s) vs other %.1f (%s)" % (
        fantasy, ", ".join(f_ev) or "none",
        other, ", ".join(o_ev) or "none")
    if fantasy < KEEP_FLOOR:
        keep = False
        head = ("no fantasy signal: " if fantasy == 0 else
                "fantasy signal below the %.1f floor: " % KEEP_FLOOR)
    elif other >= fantasy * DOMINANCE:
        keep = False
        head = "other topic dominates (%.1fx): " % (other / fantasy)
    else:
        keep = True
        head = "discusses fantasy relevance: "
    return {"topic": FANTASY, "keep": keep, "fantasy": round(fantasy, 1),
            "other": round(other, 1), "floor": KEEP_FLOOR,
            "reason": head + detail,
            "fantasy_evidence": f_ev, "other_evidence": o_ev}


def filter_items(items: List[Dict],
                 topic: Optional[str]) -> Tuple[List[Dict], List[Dict]]:
    """Split fetched items into (kept, dropped) for a source's topic filter.

    `dropped` rows are report-shaped: {"title", "url", "reason", "fantasy",
    "other"}. An absent or unsupported topic keeps EVERYTHING - a filter
    nobody implements must never quietly eat a source's items.
    """
    items = list(items or [])
    if (topic or "").strip().lower() != FANTASY:
        return items, []
    kept, dropped = [], []
    for it in items:
        verdict = classify_topic(it.get("title"), it.get("text"), FANTASY)
        if verdict["keep"]:
            kept.append(it)
        else:
            dropped.append({"title": it.get("title") or "(untitled)",
                            "url": it.get("url") or "",
                            "reason": verdict["reason"],
                            "fantasy": verdict["fantasy"],
                            "other": verdict["other"]})
    return kept, dropped


def source_topic(src: Dict) -> Tuple[Optional[str], Optional[str]]:
    """(applied_topic, warning) for one source row's topic_filter field.

    engine/sources.py owns the field and its vocabulary; an unrecognized
    value is NOT applied and comes back as a warning string, so a typo
    degrades to "no filter, loudly" instead of dropping every item.
    """
    raw = str(src.get("topic_filter") or "").strip().lower()
    if not raw:
        return None, None
    try:
        from . import sources as sources_mod
        topic = sources_mod.topic_filter(src)
    except ImportError:
        topic = raw if raw == FANTASY else None
    if topic:
        return topic, None
    return None, "unknown topic_filter %r - not applied" % raw


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def extract(text: str, matcher, source_id: str, url: str,
            week: int) -> List[Dict]:
    """Mine creator calls from free text. Returns CALLS-CONTRACT dicts.

    Every call carries the verbatim quote window it was extracted from and a
    confidence tier; ambiguous name matches are dropped, not guessed.
    """
    toks = _tokenize(text or "")
    if not toks:
        return []
    hits = _scan_players(toks, matcher)
    # Interrogative guard: a question is not a call (module docstring) -
    # any hit inside a question sentence is dropped before pattern matching.
    q_sents = _question_sents(text or "", toks)
    if q_sents:
        hits = [h for h in hits if toks[h.i].sent not in q_sents]
    found = []      # (hit, verdict, confidence, value, quote)
    consumed = set()

    for a, b in zip(hits, hits[1:]):
        pair = _pair_over(text, toks, a, b)
        if pair is not None:
            found.extend(pair)
            consumed.add(id(a))
            consumed.add(id(b))

    for hit in hits:
        if id(hit) in consumed:
            continue
        ct = _cant_trust_before(toks, hit.i)
        if ct is not None:
            found.append((hit, "sit", "med", None,
                          _quote(text, toks, ct, hit.j)))
            continue
        vb = _verb_before(toks, hit.i)
        if vb is not None and vb[1] == "high":
            found.append((hit, vb[0], "high", None,
                          _quote(text, toks, vb[2], hit.j)))
            continue
        ph = _phrase_after(text, toks, hit)
        if ph is not None:
            verdict, conf, value, hi = ph
            found.append((hit, verdict, conf, value,
                          _quote(text, toks, hit.i, hi)))
            continue
        if vb is not None:
            found.append((hit, vb[0], vb[1], None,
                          _quote(text, toks, vb[2], hit.j)))

    fetched = datetime.date.today().isoformat()
    best = {}       # (player_key, verdict) -> call dict, highest confidence
    order = []
    for hit, verdict, conf, value, quote in found:
        p = hit.match.player
        call = {"source": source_id, "player": p.name, "player_key": p.key,
                "verdict": verdict}
        if value is not None:
            call["value"] = value
        call.update({"confidence": conf, "quote": quote, "url": url or "",
                     "fetched": fetched})
        k = (p.key, verdict)
        if k not in best:
            best[k] = call
            order.append(k)
        elif CONF_RANK[conf] > CONF_RANK[best[k]["confidence"]]:
            best[k] = call
    return [best[k] for k in order]


def store_calls(calls: List[Dict], week: int,
                calls_dir: Optional[str] = None) -> Tuple[int, str]:
    """Append calls into data/creator_calls/week-<N>.yaml.

    Dedupes on (source, player_key, verdict) - first write wins, so a
    hand-written call is never clobbered by a later auto-extraction.
    Returns (number_added, path).
    """
    d = calls_dir or CALLS_DIR
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "week-%d.yaml" % int(week))
    existing = []
    if os.path.exists(path):
        with open(path, "r") as fh:
            doc = yaml.safe_load(fh) or {}
        existing = list(doc.get("calls") or [])
    seen = set((c.get("source"), c.get("player_key"), c.get("verdict"))
               for c in existing)
    added = 0
    for c in calls:
        k = (c.get("source"), c.get("player_key"), c.get("verdict"))
        if k in seen:
            continue
        seen.add(k)
        existing.append(dict(c))
        added += 1
    with open(path, "w") as fh:
        yaml.safe_dump({"week": int(week), "calls": existing}, fh,
                       sort_keys=False, allow_unicode=True,
                       default_flow_style=False, width=1000)
    return added, path


# ---------------------------------------------------------------------------
# registry + orchestration (fetching lives in engine/sources.py)
# ---------------------------------------------------------------------------

def load_registry(path: Optional[str] = None) -> List[Dict]:
    """Load data/sources.yaml via engine/sources.py (which seeds a missing
    file with the four built-in feeds). If sources.py itself cannot be
    imported, fall back to reading the yaml directly - no seeding."""
    try:
        from . import sources as sources_mod
        return sources_mod.load_sources(path)
    except ImportError:
        pass
    path = path or REGISTRY_PATH
    if not os.path.exists(path):
        return []
    with open(path, "r") as fh:
        doc = yaml.safe_load(fh) or {}
    return list(doc.get("sources") or [])


def _fetch_items(src: Dict) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """Fetch one source's items via engine/sources.py -> (items, error).

    Items follow sources.fetch_source's shape: {title, url, published,
    text[, stale][, reason]}. Any failure - import, network with no cache,
    anything - comes back as a visible error string, never an exception.
    """
    try:
        from . import sources as sources_mod
    except ImportError as e:
        return None, "engine/sources.py unavailable (%s)" % e
    try:
        items = sources_mod.fetch_source(src)
    except Exception as e:                     # honest degradation, not a crash
        return None, "%s: %s" % (type(e).__name__, e)
    if items is None:
        return None, "fetch returned nothing"
    return list(items), None


def ingest_week(week: int, matcher, registry: Optional[List[Dict]] = None,
                calls_dir: Optional[str] = None) -> Dict:
    """Fetch + classify + extract + store for every enabled non-feed source.

    Returns {"week": N, "sources": {id: {status, topic_filter, items, kept,
    dropped, drops, with_text, stale, calls, added, note}}, "failures":
    [{"source", "error"}], "totals": {...}}. Every enabled non-feed source
    appears in "sources" - failures, caption-less videos, stale caches and
    topic-filtered drops are visibly degraded, never dropped from the report.

    A source carrying topic_filter: fantasy has each item classified BEFORE
    extraction (classify_topic); non-fantasy items never reach extract(),
    but they are counted in "dropped", explained one-by-one in "drops", and
    summarized in the note as "11 of 15 items dropped as non-fantasy".
    Sources without a topic_filter behave exactly as before: kept == items.

    'paste' sources are fetched like any other, but their items only ever
    come from the hand-paste store (sources.add_paste) - nothing is scraped.
    """
    if registry is None:
        registry = load_registry()
    if isinstance(registry, dict):
        registry = list(registry.get("sources") or [])
    report = {"week": int(week), "sources": {}, "failures": [],
              "totals": {"sources": 0, "failed": 0, "items": 0, "kept": 0,
                         "dropped": 0, "calls": 0, "added": 0}}
    totals = report["totals"]
    for src in registry:
        if not src.get("enabled"):
            continue
        stype = (src.get("type") or "").strip().lower()
        sid = str(src.get("id") or src.get("name") or "?")
        if stype == "feed":
            continue    # built-in feeds are consumed at consensus time
        totals["sources"] += 1
        topic, topic_warn = source_topic(src)
        items, err = _fetch_items(src)
        if err is not None:
            report["sources"][sid] = {"status": "failed", "topic_filter": topic,
                                      "items": 0, "kept": 0, "dropped": 0,
                                      "drops": [], "with_text": 0, "stale": 0,
                                      "calls": 0, "added": 0, "note": err}
            report["failures"].append({"source": sid, "error": err})
            totals["failed"] += 1
            continue
        kept, drops = filter_items(items, topic)
        n_calls = n_added = 0
        with_text = stale = 0
        for it in kept:
            if it.get("stale"):
                stale += 1
            text = it.get("text")
            if not text:
                continue
            with_text += 1
            found = extract(text, matcher, sid,
                            it.get("url") or str(src.get("handle") or ""),
                            week)
            added, _ = store_calls(found, week, calls_dir=calls_dir)
            n_calls += len(found)
            n_added += added
        notes = []
        if topic_warn:
            notes.append(topic_warn)
        if not items:
            notes.append("no pasted items yet (X/Twitter is paste-only: ToS)"
                         if stype == "paste" else "no items returned")
        if drops:
            notes.append("%d of %d items dropped as non-%s"
                         % (len(drops), len(items), topic))
        if with_text < len(kept):
            notes.append("%d/%d item(s) have no text (missing captions?)"
                         % (len(kept) - with_text, len(kept)))
        if stale:
            notes.append("%d stale cached item(s) - live fetch failed"
                         % stale)
        report["sources"][sid] = {"status": "ok", "topic_filter": topic,
                                  "items": len(items), "kept": len(kept),
                                  "dropped": len(drops), "drops": drops,
                                  "with_text": with_text, "stale": stale,
                                  "calls": n_calls, "added": n_added,
                                  "note": "; ".join(notes)}
        totals["items"] += len(items)
        totals["kept"] += len(kept)
        totals["dropped"] += len(drops)
        totals["calls"] += n_calls
        totals["added"] += n_added
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.calls",
        description="Pull creator start/sit calls into data/creator_calls/.")
    ap.add_argument("--week", type=int, required=True, help="NFL week number")
    ap.add_argument("--league", default="yahoo-main",
                    help="league id (leagues/<id>.yaml) for the player pool")
    args = ap.parse_args(argv)

    from .ingest import Matcher
    from .models import LeagueConfig, load_players
    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            args.league + ".yaml"))
    players = load_players(os.path.join(HERE, league.rankings_csv))
    matcher = Matcher(players)

    registry = load_registry()
    creators = [s for s in registry if s.get("enabled")
                and (s.get("type") or "").lower() != "feed"]
    print("CREATOR CALLS - week %d (%d creator source%s enabled)" % (
        args.week, len(creators), "" if len(creators) == 1 else "s"))
    if not creators:
        print("  no enabled creator sources in data/sources.yaml - add "
              "youtube/rss/url entries (X content is paste-only: ToS)")
        return 0

    report = ingest_week(args.week, matcher, registry)
    for sid, row in report["sources"].items():
        if row["status"] == "ok":
            items_part = "%d item(s)" % row["items"]
            if row.get("dropped"):
                items_part += " (%d kept)" % row.get("kept", row["items"])
            line = "  %-24s %s, %d call(s), %d new" % (
                sid, items_part, row["calls"], row["added"])
            if row["note"]:
                line += "  [%s]" % row["note"]
            print(line)
            # WHY each item was dropped - a filtered item you can't audit is
            # a silently missing source.
            for drop in (row.get("drops") or [])[:3]:
                print("      dropped: %s - %s" % (drop["title"],
                                                  drop["reason"]))
            extra = len(row.get("drops") or []) - 3
            if extra > 0:
                print("      ... %d more dropped item(s)" % extra)
        else:
            print("  %-24s %s: %s" % (sid, row["status"].upper(), row["note"]))
    totals = report.get("totals") or {}
    if totals.get("dropped"):
        print("  topic filter: %d of %d fetched item(s) dropped as "
              "non-fantasy across all sources"
              % (totals["dropped"], totals["items"]))
    if report["failures"]:
        print("  %d source(s) FAILED - their calls are missing from this "
              "week, not silently zero" % len(report["failures"]))
    print("  file: %s" % os.path.join(CALLS_DIR, "week-%d.yaml" % args.week))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
