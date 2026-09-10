"""B (Decision Cards) vs D (Heat Grid): the start/sit layout comparison, from
real week-1 data. python design/lineup-studio/compare.py -> b-vs-d.html here."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from engine import ui, sources as S

SRC = sorted([s for s in S.load_sources() if s.get("enabled")], key=lambda s: -s.get("weight", 0))
LEAGUES = [("espn-1", "The Original 8"), ("yahoo-main", "Kid's Table")]
ST, SI, NO = "start", "sit", None
STARTERS = [
    ("QB", "Jayden Daniels", "WAS @ PHI", "Sun 4:25", 16.8, "start", 100, "neutral", [ST,ST,NO,NO,ST,ST,ST], None),
    ("RB", "Jahmyr Gibbs", "DET vs NO", "Sun 1:00", 21.6, "start", 100, "good", [ST,ST,NO,NO,ST,ST,ST], None),
    ("RB", "Breece Hall", "NYJ @ TEN", "Sun 1:00", 16.5, "start", 100, "neutral", [ST,ST,NO,NO,ST,ST,ST], "Q"),
    ("WR", "Drake London", "ATL @ PIT", "Sun 1:00", 15.1, "start", 100, "good", [ST,ST,NO,NO,ST,ST,ST], None),
    ("WR", "A.J. Brown", "NE @ SEA", "Wed 8:20", 14.3, "start", 100, "avoid", [ST,ST,NO,NO,ST,ST,ST], None),
    ("TE", "Kyle Pitts Sr.", "ATL @ PIT", "Sun 1:00", 10.4, "start", 100, "neutral", [ST,ST,NO,NO,ST,ST,ST], None),
    ("FLEX", "Travis Etienne Jr.", "NO @ DET", "Sun 1:00", 15.0, "start", 100, "neutral", [ST,ST,NO,NO,ST,ST,ST], None),
    ("FLEX", "Rico Dowdle", "PIT vs ATL", "Sun 1:00", 12.5, "start", 67, "neutral", [ST,ST,NO,NO,SI,SI,ST], None),
    ("K", "Harrison Mevis", "LAR vs SF", "Thu 8:35", 9.4, "start", 100, None, [ST,ST,NO,NO,NO,ST,NO], None),
    ("DST", "LA Chargers D/ST", "LAC vs ARI", "Sun 4:25", 7.5, "start", 83, None, [ST,ST,NO,NO,NO,SI,NO], None),
]
BENCH = [
    ("WR", "Marvin Harrison Jr.", "ARI @ LAC", "Sun 4:25", 11.5, "sit", 0, "neutral", [SI,SI,NO,NO,SI,SI,SI], None),
    ("RB", "Tony Pollard", "TEN vs NYJ", "Sun 1:00", 11.5, "sit", 0, "neutral", [SI,SI,NO,NO,SI,SI,SI], None),
    ("RB", "Jonathon Brooks", "CAR vs CHI", "Sun 1:00", 11.5, "sit", 0, "tough", [SI,SI,NO,NO,SI,SI,SI], None),
    ("WR", "Josh Downs", "IND vs BAL", "Sun 1:00", 10.9, "sit", 0, "tough", [SI,SI,NO,NO,SI,SI,SI], None),
    ("WR", "Xavier Worthy", "KC vs DEN", "Mon 8:15", 10.2, "sit", 0, "neutral", [SI,SI,NO,NO,SI,SI,SI], None),
    ("WR", "Jauan Jennings", "SF @ LAR", "Thu 8:35", 9.1, "sit", 0, "neutral", [SI,SI,NO,NO,SI,SI,SI], None),
    ("RB", "Rachaad White", "TB vs ATL", "Sun 1:00", 7.4, "sit", 0, "neutral", [SI,SI,NO,NO,SI,SI,SI], None),
]
QUOTES = {"engine": "our best legal lineup starts him this week - 12.5 projected beats every bench RB by a point",
          "chen-tiers": "his tier is past this league's starter cutoff at 8 teams"}
esc = ui.esc
def kind(s): return "creator" if s.get("type") in ("youtube", "rss", "url", "paste") else "feed"
def vote_strip(votes, size=22):
    out = []
    for s, v in zip(SRC, votes):
        cls = {"start": "vs-start", "sit": "vs-sit", "even": "vs-even"}.get(v, "vs-none")
        out.append('<span class="vs %s" title="%s">%s</span>' % (cls, esc("%s: %s" % (s["name"], (v or "no call").upper())), ui.avatar(s["id"], s["name"], size, kind(s))))
    return '<span class="vstrip">%s</span>' % "".join(out)
def split_bar(pct, width=120):
    p = max(0, min(100, int(pct)))
    return ('<span class="sb" style="width:%dpx" title="%d%% of the weight says START"><span class="sb-on" style="width:%d%%"></span><span class="sb-tick"></span></span>'
            '<span class="sb-l wr-num">%d<span class="sb-sep">·</span>%d</span>' % (width, p, p, p, 100 - p))
def flags(f): return ui.flag_badge("injury", "sm", note="Questionable") if f == "Q" else ""
def meter(g): return ui.matchup_meter(g, label=False, size="sm") if g else '<span class="wr-meter wr-meter-none" title="not graded"><span class="wr-meter-l">—</span></span>'
def pos(p): return ui.pos_badge("W/R/T" if p == "FLEX" else p)
def faces_for(votes, want):
    return "".join('<span class="vs vs-%s">%s</span>' % (want, ui.avatar(s["id"], s["name"], 26, kind(s))) for s, v in zip(SRC, votes) if v == want)
def head(kicker, title, lede):
    return '<p class="wr-kicker">%s</p><h1 class="wr-h1 wr-display">%s</h1><p class="wr-lede">%s</p>' % (kicker, title, lede)
def grp(k, n, note=""):
    return '<div class="grp"><p class="wr-kicker">%s</p><span class="n">%s</span>%s</div>' % (k, n, ('<span class="note">%s</span>' % note) if note else "")

# ---- B
def versus(title_l, meta_l, votes, verdict, pct, quote_l, quote_r, side_r_title, side_r_meta, kicker):
    right = faces_for(votes, "sit") or '<span class="note">the matchup engine (an input you can switch on)</span>'
    return ('<article class="vsc"><div class="side start"><span class="wr-kicker" style="font-size:10px">START · ' + esc(kicker) + '</span><h4>' + esc(title_l) + '</h4><div class="m">' + esc(meta_l) + '</div>'
            + '<div class="fl">' + faces_for(votes, "start") + '</div><blockquote>' + esc(quote_l) + '</blockquote></div>'
            + '<div class="gut"><span class="w">YOUR MODEL</span>' + ui.verdict_chip(verdict, pct, "lg") + split_bar(pct, 110) + '<span class="btns"><button class="btn pri">Agree</button><button class="btn">Override</button></span></div>'
            + '<div class="side sit"><span class="wr-kicker" style="font-size:10px;color:var(--wr-dim)">' + esc(side_r_title) + '</span><h4>' + esc(side_r_meta[0]) + '</h4><div class="m">' + esc(side_r_meta[1]) + '</div>'
            + '<div class="fl">' + right + '</div><blockquote>' + esc(quote_r) + '</blockquote></div></article>')
def compact(p):
    posn, name, game, when, proj, verdict, pct, mg, votes, fl = p
    return ('<div class="row" style="grid-template-columns: 52px minmax(0,1fr) 52px 176px 110px 96px;">' + pos(posn) + '<div class="who"><b>%s</b>%s<small>%s · %s</small></div>' % (esc(name), flags(fl), esc(game), esc(when))
            + '<div class="proj wr-num">%.1f</div>' % proj + '<div>%s</div><div>%s</div><div>%s</div></div>' % (vote_strip(votes, 18), ui.verdict_chip(verdict, pct, "sm"), meter(mg)))
dowdle, ajb = STARTERS[7], STARTERS[4]
B = (head("Option B · Decision Cards", "ONLY THE CALLS NEED YOUR EYES", "Players are grouped by certainty, not by slot. Splits get the full versus card. Everything unanimous collapses to one line with its faces. Two calls this week; eight locked in; seven benched.")
     + '<section><div class="card-h"><p class="wr-kicker">The calls · 2</p><span class="note">where the room disagrees, or the matchup does</span></div>'
     + versus("Rico Dowdle", "RB · PIT vs ATL · Sun 1:00 · proj 12.5 · W/R/T slot", dowdle[8], "start", 67, QUOTES["engine"], QUOTES["chen-tiers"], "SIT · 33% · 2 voices", ("Tony Pollard would take the slot", "RB · TEN vs NYJ · proj 11.5"), "67% · 3 voices")
     + versus("A.J. Brown", "WR · NE @ SEA · WED 8:20 · proj 14.3 · first lock of the week", ajb[8], "start", 100, "every voice that filed a call starts him", "SEA allowed 26.3 pts/game to WR in 2025 - 4th-stingiest of 32. Rosters and schemes changed since; treat as a prior, not a fact.", "MATCHUP · AVOID", ("the room is unanimous; the matchup dissents", "not a bench call - a temper-expectations call"), "100% · 5 voices")
     + '</section><section class="wr-card" style="padding:4px 0 0; margin-top:16px">' + grp("Locked in", "8 · unanimous starts", "no decision here - listed so nothing is hidden")
     + "".join(compact(p) for p in STARTERS if p[1] != "Rico Dowdle") + grp("Bench", "7 · unanimous sits") + "".join(compact(p) for p in BENCH) + '</section>')
BP = ('<p class="wr-kicker">Option B · phone</p><h1 class="wr-h1 wr-display" style="font-size:22px">THE CALLS · 2</h1>'
      + versus("Rico Dowdle", "RB · PIT vs ATL · proj 12.5", dowdle[8], "start", 67, QUOTES["engine"], QUOTES["chen-tiers"], "SIT · 33%", ("Tony Pollard would take the slot", "proj 11.5"), "67%")
      + versus("A.J. Brown", "WR · NE @ SEA · Wed 8:20 · proj 14.3", ajb[8], "start", 100, "every voice that filed a call starts him", "SEA allowed 26.3 pts/game to WR in 2025 - 4th-stingiest of 32.", "MATCHUP · AVOID", ("the room is unanimous; the matchup dissents", "temper expectations, not a bench call"), "100%")
      + '<p class="wr-kicker" style="margin-top:16px">Locked in · 8</p><section class="wr-card" style="padding:0 6px">'
      + "".join('<div class="row"><div class="who">' + pos(p[0]) + '<b>' + esc(p[1]) + '</b>' + flags(p[9]) + '</div>' + ui.verdict_chip("start", None, "sm") + '<div class="l2">' + vote_strip(p[8], 18) + meter(p[7]) + '</div></div>' for p in STARTERS if p[1] != "Rico Dowdle")
      + '</section><p class="wr-kicker" style="margin-top:16px">Bench · 7</p><section class="wr-card" style="padding:0 6px">'
      + "".join('<div class="row"><div class="who">' + pos(p[0]) + '<b>' + esc(p[1]) + '</b></div>' + ui.verdict_chip("sit", None, "sm") + '</div>' for p in BENCH[:4]) + '</section>')

# ---- D
def grid_row(p):
    posn, name, game, when, proj, verdict, pct, mg, votes, fl = p
    cells = "".join('<div><span class="cell c-%s" title="%s: %s"></span></div>' % ({"start": "start", "sit": "sit", "even": "even"}.get(v, "none"), esc(s["name"]), (v or "no call").upper()) for s, v in zip(SRC, votes))
    return '<div class="r"><div class="who">' + pos(posn) + '<b>%s</b>%s</div>' % (esc(name), flags(fl)) + cells + '<div style="justify-content:center">%s</div><div>%s</div></div>' % (ui.verdict_chip(verdict, pct, "sm"), meter(mg))
hdr = '<div></div>' + "".join('<div class="hd" title="%s">%s<small class="wr-num">%d</small></div>' % (esc(s["name"]), ui.avatar(s["id"], s["name"], 26, kind(s)), s["weight"]) for s in SRC) + '<div class="hd"><span class="wr-kicker" style="font-size:9px">YOUR MODEL</span></div><div class="hd"><span class="wr-kicker" style="font-size:9px">MATCHUP</span></div>'
sq = lambda c: '<span class="cell c-%s" style="width:14px;height:14px;margin:0"></span>' % c
D = (head("Option D · The Heat Grid", "THE MATRIX, SHRUNK TO A GLANCE", "Keep the source-by-source view - but each cell is a square, each column a face. Seven columns fit in 240px. A column of grey squares is a cold source; a row with one odd square is a dissent. Click a row for the quotes.")
     + '<section class="wr-card" style="padding:4px 4px 8px"><div class="grid" style="grid-template-columns: 250px repeat(7, 34px) 120px 90px;">' + hdr + "".join(grid_row(p) for p in STARTERS)
     + '<div class="r"><div style="grid-column:1/-1; min-height:26px; color:var(--wr-dim); font-size:10.5px; letter-spacing:.1em">BENCH</div></div>' + "".join(grid_row(p) for p in BENCH)
     + '</div><div class="legend"><span>' + sq("start") + ' START</span><span>' + sq("sit") + ' SIT</span><span>' + sq("even") + ' toss-up</span><span>' + sq("none") + ' no call</span><span>column head = the source, its weight</span></div></section>')
def cellrow(votes, size=22):
    return '<span class="cells">%s</span>' % "".join('<span class="cell c-%s" style="width:%dpx;height:%dpx;margin:0" title="%s: %s"></span>' % ({"start": "start", "sit": "sit", "even": "even"}.get(v, "none"), size, size, esc(s["name"]), (v or "no call").upper()) for s, v in zip(SRC, votes))
def d_phone_row(p):
    posn, name, game, when, proj, verdict, pct, mg, votes, fl = p
    return '<div class="row"><div class="who">' + pos(posn) + '<b>%s</b>%s</div>%s' % (esc(name), flags(fl), ui.verdict_chip(verdict, pct, "sm")) + '<div class="l2">' + cellrow(votes) + meter(mg) + '</div></div>'
d_hdr = '<div class="l2" style="padding:6px 10px 2px"><span class="cells">' + "".join('<span style="width:22px;display:inline-flex;justify-content:center" title="%s">%s</span>' % (esc(s["name"]), ui.avatar(s["id"], s["name"], 20, kind(s))) for s in SRC) + '</span><span class="note" style="font-size:10px;letter-spacing:.1em">MATCHUP</span></div>'
DP = ('<p class="wr-kicker">Option D · phone</p><h1 class="wr-h1 wr-display" style="font-size:22px">THE GRID</h1><section class="wr-card" style="padding:0 6px">' + d_hdr + "".join(d_phone_row(p) for p in STARTERS)
      + '<div class="grp"><p class="wr-kicker">Bench</p><span class="n">7</span></div>' + "".join(d_phone_row(p) for p in BENCH[:3]) + '</section>')

# ---- page
CSS = open(os.path.join(HERE, "extra.css")).read()
def phone_frame(inner, label):
    return '<figure class="ph"><figcaption>%s</figcaption><div class="bezel"><div class="screen phone">%s<main class="wr-page" style="padding:12px 12px 70px">%s</main></div></div></figure>' % (label, ui.shell("board", "espn-1", 1, LEAGUES), inner)
def desk_frame(inner, label, h):
    return '<figure class="dk"><figcaption>%s</figcaption><div class="dkbox" style="height:%dpx"><div class="dkin desk">%s<main class="wr-page" style="padding:20px 18px 40px">%s</main></div></div></figure>' % (label, h, ui.shell("board", "espn-1", 1, LEAGUES), inner)
html = ('<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B vs D</title>'
        + ui.style_tag() + '<style>' + CSS + ' body{background:var(--wr-canvas)}</style></head><body><div class="cmp">'
        + '<p class="wr-kicker">Decide by feel · same week, same roster, same faces</p><h1 class="wr-h1 wr-display" style="font-size:30px">B · DECISION CARDS &nbsp;vs&nbsp; D · THE HEAT GRID</h1>'
        + '<div class="crit"><span><b>Your criteria:</b></span><span>fits an iPhone</span><span>no horizontal scrolling</span><span>natural layout</span><span>nothing spills a line</span><span>easy to navigate</span></div>'
        + '<div class="cols"><div class="col"><h2 class="wr-display">B · Decision Cards</h2><p class="sub">Grouped by certainty. Splits get the versus card with the model in the gutter and Agree / Override; everything unanimous is one line with its faces. Phone needs no adaptation.</p>'
        + phone_frame(BP, "iPhone · 390px · scroll the screen") + desk_frame(B, "Desktop · 1100px · scaled to fit", 600) + '</div>'
        + '<div class="col"><h2 class="wr-display">D · The Heat Grid</h2><p class="sub">Source-by-source, one square per vote under each face. A grey column is a cold source; one odd square is a dissent. Phone folds the squares under the name.</p>'
        + phone_frame(DP, "iPhone · 390px · scroll the screen") + desk_frame(D, "Desktop · 1100px · scaled to fit", 600) + '</div></div>'
        + '<section class="wr-card verdict"><p class="wr-kicker">What each one is best at</p><div class="cols" style="gap:18px"><div><b>B answers "what needs me?"</b><p class="note">Two cards is the whole Sunday. The eight unanimous starts cost one glance each. Weak spot: judging a <i>source</i> across the roster takes scanning faces row by row.</p></div><div><b>D answers "who is right lately?"</b><p class="note">A column of grey is a cold source; you see pattern before detail. Weak spot: it needs the legend once, and the calls that need you are not lifted above the ones that don\'t.</p></div></div>'
        + '<p class="note" style="margin-top:10px"><b>They are not exclusive.</b> B as the default view, D as a toggle in the same header, sharing the row component. The Lineup Builder is its own page either way.</p></section></div></body></html>')
open(os.path.join(HERE, "b-vs-d.html"), "w").write(html)
print("b-vs-d.html", len(html) // 1024, "KB")
