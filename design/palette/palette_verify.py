#!/usr/bin/env python3
"""Graded Takes - Obsidian multi-hue palette: the numbers, the rule, the swatch sheet.

Pure Python, no dependencies. Run from anywhere:
    python3 design/palette/palette_verify.py            # verify + rewrite palette.json and swatches.html
    python3 design/palette/palette_verify.py --check    # verify only (exit 1 on any failure)

What it does
  1. Defines every token (hex, role, tier, job, carrier).
  2. Computes WCAG 2.x contrast for every token against every ground it can sit on
     (canvas, panel, raised, raised-2, the brightest native-ground pixel #2A3145,
     the 78% card over that pixel, the worst-case glass, the tab pill on that glass),
     plus navy chip-ink on every fill and the 82% secondary ink.
  3. Runs THE HUE RULE (PALETTE.md section 5) as a machine test: each token's role
     fixes an OKLCH box it must sit in; verdict/state signals may not be green or red;
     categories may sit in any family at obsidian chroma/lightness; nothing carries
     ink at L 0.45-0.65; nothing exceeds C 0.17.
  4. Writes palette.json (tokens + computed ratios) and swatches.html (the eye test).

Colour maths: sRGB -> linear (IEC 61966-2-1), WCAG relative luminance, OKLab/OKLCH
(Bjorn Ottosson's published matrices). HSV is reported too because the critic's
existing scan (hues.py) speaks HSV.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------- colour maths
def hex2rgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def rgb2hex(rgb): return '#%02X%02X%02X' % tuple(int(round(c)) for c in rgb)
def lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def Y(rgb): r, g, b = rgb; return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
def cr(a, b):
    ya, yb = Y(a), Y(b); hi, lo = max(ya, yb), min(ya, yb); return (hi + 0.05) / (lo + 0.05)
def over(fg, alpha, bg): return tuple(round(fg[i] * alpha + bg[i] * (1 - alpha)) for i in range(3))
def srgb_to_oklab(rgb):
    r, g, b = [lin(c) for c in rgb]
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)
def oklch_to_rgb(L, C, h):
    a = C * math.cos(math.radians(h)); b = C * math.sin(math.radians(h))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lr = (+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
          -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
          -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    ok = all(-0.0005 <= c <= 1.0005 for c in lr)
    def gam(c):
        c = min(max(c, 0.0), 1.0)
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return tuple(round(gam(c) * 255) for c in lr), ok
def oklch(rgb):
    L, a, b = srgb_to_oklab(rgb); return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360
def dE(a, b):
    A, B = srgb_to_oklab(a), srgb_to_oklab(b); return math.sqrt(sum((A[i] - B[i]) ** 2 for i in range(3)))
def hsv(rgb):
    r, g, b = [c / 255 for c in rgb]; mx, mn = max(r, g, b), min(r, g, b); d = mx - mn
    if d == 0: h = 0.0
    elif mx == r: h = (60 * ((g - b) / d)) % 360
    elif mx == g: h = 60 * ((b - r) / d + 2)
    else: h = 60 * ((r - g) / d + 4)
    return h, (d / mx if mx else 0.0), mx

# ----------------------------------------------------------------------------- grounds (design/obsidian/SPEC.md section 1, 1.2)
CANVAS = hex2rgb('#0A0C12'); PANEL = hex2rgb('#12151D'); RAISED = hex2rgb('#1C202B'); RAISED2 = hex2rgb('#262A35')
WORST = hex2rgb('#2A3145')                           # brightest native-ground pixel (under light 1)
CARD_WORST = over(PANEL, 0.78, WORST)                # the translucent card over it -> #171B26
GLASS_WORST = hex2rgb('#232836')                     # tokens.obsidian.json "resolved.glass-worst"
TAB_PILL = hex2rgb('#353946')                        # white 8% selection pill on the worst glass
FROST = hex2rgb('#14171E')                           # Reduce-Transparency bar fill
CHIP_INK = hex2rgb('#101B33')
GLASS_FILL = (28, 31, 40)                            # gt-glass-fill at 52%
GROUNDS = [('canvas', CANVAS), ('panel', PANEL), ('raised', RAISED), ('raised-2', RAISED2),
           ('worst-ground', WORST), ('card-over-worst', CARD_WORST)]
GLASS_GROUNDS = [('glass-worst', GLASS_WORST), ('tab-pill', TAB_PILL), ('frost', FROST)]

# ----------------------------------------------------------------------------- the tokens
# role: text | chip-ink | signal | category | brand | identity | surface | glow
# tier: ladder | A (pastel ink / small fill) | B (wash) | C (glow) | ground
T = []
def tok(name, hex_, role, tier, job, carrier, family=None, aliases=(), note=''):
    T.append(dict(name=name, hex=hex_.upper(), role=role, tier=tier, job=job, carrier=carrier,
                  family=family, aliases=list(aliases), note=note))

# 1. the text scale (unchanged from SPEC section 1, plus 'disabled')
tok('text',       '#E8E3D8', 'text', 'ladder', 'primary ink on every surface; names, numbers, verdict words on SIT/TOSS-UP',
    'text', 'ladder')
tok('muted',      '#ABA9A1', 'text', 'ladder', 'secondary ink: ledes, reasons, sub-lines, tough/avoid meter labels', 'text', 'ladder')
tok('dim',        '#909298', 'text', 'ladder', 'tertiary ink: labels, kickers, slot badges, wt, n, K/DST codes, feed glyphs', 'text', 'ladder')
tok('disabled',   '#767A83', 'text', 'ladder', 'disabled control labels and unavailable rows (WCAG 1.4.3 exempts inactive UI; house floor 3:1 everywhere it sits)',
    'text', 'ladder', note='new')
tok('nav-text-2', '#C9C5BC', 'text', 'ladder', 'the only secondary ink on glass: the status line under the league', 'text', 'ladder')
tok('chip-ink',   '#101B33', 'chip-ink', 'ladder', 'the one dark ink on every hue fill (navy; the brand survives here)', 'text', 'ladder')

# 2. gold - the decision (narrowed, PALETTE.md section 2.8)
tok('gold',       '#F2B722', 'signal', 'A', 'THE DECISION: the mark; START fill; TOSS-UP dash; the one primary verb; attention rules (honesty banner, Needs-you, Q/D, your column, creator ring); numbers and times that decide; SMASH pips; HOT',
    'fill <= 24px / 2-3px rule / numeral / glyph', 'warm', aliases=('rule', 'chip-start', 'chip-lean', 'meter-hi', 'status-qd-rule', 'streak-hot', 'urgency-now'))
tok('straw',      '#EACE8C', 'signal', 'A', 'GOOD matchup pips (the warm pole, one step cooler than gold)', '6x13 pip', 'warm',
    aliases=('meter-good',), note='new')
tok('cool',       '#9AADC4', 'signal', 'A', 'the cool pole: TOUGH pips; COLD streak glyph and sparkline end-dot; negative delta numerals',
    'pip / glyph / 6px dot / numeral', 'cool', aliases=('meter-tough', 'streak-cold', 'delta-neg'), note='new; replaces mint/coral as the signed pair')

# 3. positions (CONVENTIONS.md section 1: QB red-violet band, RB teal band, WR/TE follow Sleeper; K/DST grey)
tok('pos-qb', '#F59ECF', 'category', 'A', 'QB code', 'code 11px/700 | 3px rule (widget) | fill under chip-ink (card header only)', 'position',
    note='Sleeper QB #FC2B6D lifted +0.15 L, chroma cut ~45%, hue 345 OKLCH / 326 HSV: inside the 265-345 QB band')
tok('pos-rb', '#6BD5B6', 'category', 'A', 'RB code', 'same', 'position',
    note='Sleeper RB #20CEB8 / Underdog #15997D, lifted; hue 172 OKLCH / 163 HSV: the teal band')
tok('pos-wr', '#7AC8F5', 'category', 'A', 'WR code', 'same', 'position',
    note="Sleeper's own dark-mode WR (#00D7FF, hue 189 HSV) and light WR (#59A7FF, 212) bracket this at 203 HSV")
tok('pos-te', '#F9A782', 'category', 'A', 'TE code', 'same', 'position',
    note='Sleeper TE #FEAE58 pulled 12 deg toward peach so it is not gold: dE from gold 0.10 (the legibility threshold at chip size)')
tok('pos-k',   '#909298', 'category', 'ladder', 'K code = dim', 'code', 'position', note='special teams are grey (Sleeper K is C 0.06; FantasyPros DST grey)')
tok('pos-dst', '#909298', 'category', 'ladder', 'DST code = dim', 'code', 'position')

# 4. brands (league identity + the two platform-shaped source categories). Colour only, never a logo.
tok('brand-red',    '#FC9192', 'brand', 'A', "ESPN's red, lifted: the ESPN league dot; the YouTube play-glyph tint", '8px dot / 2px rule / 12px glyph',
    'brand', aliases=('league-espn', 'src-youtube'), note='ESPN #C00/#D00 and YouTube #FF0000 are the same red on white; on obsidian one lifted hex serves both, the glyph/name says which')
tok('brand-violet', '#C79FF4', 'brand', 'A', "Yahoo's purple, lifted: the Yahoo league dot; the podcast mic-glyph tint", 'same',
    'brand', aliases=('league-yahoo', 'src-podcast'), note='Yahoo #6001D2 (computed) and Apple Podcasts #B150E2 share the family')
tok('brand-aqua',   '#65E1E1', 'brand', 'A', "Sleeper's aqua: the Sleeper league dot", 'same',
    'brand', aliases=('league-sleeper',), note='Sleeper --color-dls-primary-400 #00E1E0 lifted')

# 5. page identity hues (Tier A hex for the selected tab glyph; Tier C glow for the ground)
tok('ink-blue', '#9DBBF3', 'identity', 'A', 'Model and Sources: the selected tab glyph; the glow in the ground', 'tab glyph 22pt / ground glow',
    'identity', aliases=('mint',), note='existing hex; no longer means "positive" (cool does the signed job)')
tok('stone',    '#BDB0A0', 'identity', 'A', 'Ledger: the selected tab glyph (if it holds the fifth slot); the glow', 'same',
    'identity', aliases=('coral',), note='existing hex; no longer means "negative"')

# 6. washes (Tier B) and glows (Tier C) - computed, not hand-picked
tok('wash-hot',   '#2D281E', 'surface', 'B', 'the honesty banner and the empty-record note ONLY (attention)', 'strip', 'warm')
tok('wash-split', '#24221D', 'surface', 'B', 'the challenger line under a contested slot', 'row', 'warm')
tok('wash-cool',  '#182031', 'surface', 'B', 'AVOID rows, bye rows, cold rows (replaces wash-cold, wash-bad; wash-good is retired - a good row gets no wash, the meter says it)',
    'row', 'cool', aliases=('wash-bad', 'wash-cold'), note='new hex: cool family at L 0.26 C 0.035')

GLOWS = {  # page glows: the hue at OKLCH L 0.55 C 0.10, painted at <= 30% as light 2 (SPEC 1.2)
    'glow-gold':   ('#F2B722', 0.13, 'Home, Board, Onboarding (light 2 as today)'),
    'glow-ink':    (rgb2hex(oklch_to_rgb(0.55, 0.10, 263)[0]), 0.30, 'Model, Sources'),
    'glow-stone':  (rgb2hex(oklch_to_rgb(0.55, 0.10, 73)[0]), 0.30, 'Ledger'),
    'glow-espn':   (rgb2hex(oklch_to_rgb(0.55, 0.10, 20)[0]), 0.30, 'Trade Desk in an ESPN league'),
    'glow-yahoo':  (rgb2hex(oklch_to_rgb(0.55, 0.10, 305)[0]), 0.30, 'Trade Desk in a Yahoo league'),
    'glow-sleeper':(rgb2hex(oklch_to_rgb(0.55, 0.10, 195)[0]), 0.30, 'Trade Desk in a Sleeper league'),
}

# Increase-Contrast variants of the Tier-A hues: L +0.04, C -0.02, same hue
HC = {}
for t in T:
    if t['tier'] == 'A' and t['role'] in ('signal', 'category', 'brand', 'identity'):
        L, C, h = oklch(hex2rgb(t['hex']))
        HC[t['name']] = rgb2hex(oklch_to_rgb(min(L + 0.04, 0.90), max(C - 0.02, 0.0), h)[0])
HC_TEXT = {'muted': '#C4C2BA', 'dim': '#ABADB3', 'disabled': '#8A8E97'}  # first two are SPEC 4.2; disabled is new

# ----------------------------------------------------------------------------- THE HUE RULE, as a test (PALETTE.md section 5)
GREEN = (120.0, 185.0)   # OKLCH hue band we call "green" (HSV ~70-170)
RED   = (0.0, 40.0)      # OKLCH hue band we call "red" (HSV <20 or >340); wraps: also 350-360
def in_band(h, lo, hi): return lo <= h <= hi
def is_red(h): return in_band(h, *RED) or h >= 350
def is_green(h): return in_band(h, *GREEN)

def hue_rule(t):
    """Return a list of violations for one token."""
    rgb = hex2rgb(t['hex']); L, C, h = oklch(rgb); v = []
    if C > 0.17: v.append('chroma %.3f > 0.17 (nothing in the theme exceeds it)' % C)
    if t['role'] == 'text':
        if C > 0.02: v.append('text ink must be neutral (C <= 0.02), got %.3f' % C)
    elif t['role'] == 'chip-ink':
        pass  # the brand navy on fills; judged by the fill-under-ink ratios, not by neutrality
    elif t['role'] == 'signal':
        warm = in_band(h, 80, 92) and C <= 0.17
        straw = in_band(h, 84, 92) and C <= 0.10
        cool = in_band(h, 245, 265) and C <= 0.05
        neutral = C <= 0.02
        if not (warm or straw or cool or neutral):
            v.append('a signal colour must be gold-warm (h 80-92), cool (h 245-265, C<=0.05) or neutral; got h %.0f C %.3f' % (h, C))
        if (is_red(h) or is_green(h)) and C > 0.02:
            v.append('a signal colour may never be red or green')
    elif t['role'] in ('category', 'brand', 'identity') and t['tier'] == 'A':
        if not (0.76 <= L <= 0.86): v.append('Tier A lightness %.2f outside 0.76-0.86' % L)
        if not (0.02 <= C <= 0.14): v.append('Tier A chroma %.3f outside 0.02-0.14' % C)
    elif t['role'] == 'surface':
        if not (0.22 <= L <= 0.31): v.append('wash lightness %.2f outside 0.22-0.31' % L)
        if C > 0.05: v.append('wash chroma %.3f > 0.05' % C)
    if t['tier'] in ('A',) and 0.45 <= L <= 0.65: v.append('a fill in the dead zone L 0.45-0.65')
    return v

# ----------------------------------------------------------------------------- compute
def compute():
    fails = []
    rows = []
    for t in T:
        rgb = hex2rgb(t['hex']); L, C, h = oklch(rgb); hh, s, vv = hsv(rgb)
        r = dict(t)
        r.update(oklch=dict(L=round(L, 3), C=round(C, 3), h=round(h, 1)), hsv=dict(h=round(hh, 1), s=round(s, 2), v=round(vv, 2)))
        r['contrast'] = {n: round(cr(rgb, g), 2) for n, g in GROUNDS}
        r['contrast_glass'] = {n: round(cr(rgb, g), 2) for n, g in GLASS_GROUNDS}
        if t['tier'] == 'A' or t['name'] == 'gold':
            r['as_fill'] = dict(chip_ink=round(cr(CHIP_INK, rgb), 2), chip_ink_82=round(cr(over(CHIP_INK, 0.82, rgb), rgb), 2))
        if t['role'] == 'surface':
            r['ink_on_it'] = dict(text=round(cr(hex2rgb('#E8E3D8'), rgb), 2), muted=round(cr(hex2rgb('#ABA9A1'), rgb), 2),
                                  dim=round(cr(hex2rgb('#909298'), rgb), 2), gold=round(cr(hex2rgb('#F2B722'), rgb), 2))
        r['dE_gold'] = round(dE(rgb, hex2rgb('#F2B722')), 3)
        r['violations'] = hue_rule(t)
        rows.append(r)

    # --- floors
    for r in rows:
        name = r['name']; c = r['contrast']; cg = r['contrast_glass']
        if r['role'] == 'text' and name != 'chip-ink':
            floor = 3.0 if name == 'disabled' else 4.5
            for n, val in c.items():
                # dim and disabled are card/panel inks (labels, kickers, times sit on cards); on the bare
                # brightest ground pixel dim is 4.16 - inherited from SPEC section 1, reported in PALETTE.md 1.1
                if name == 'dim' and n == 'worst-ground': continue
                if val < floor: fails.append('%s on %s = %.2f < %.1f' % (name, n, val, floor))
            if name in ('text', 'nav-text-2'):
                for n, val in cg.items():
                    if val < 4.5: fails.append('%s on %s = %.2f < 4.5' % (name, n, val))
        if r['tier'] == 'A':
            for n, val in c.items():
                if val < 4.5: fails.append('%s as text on %s = %.2f < 4.5' % (name, n, val))
            if r['as_fill']['chip_ink'] < 4.5: fails.append('%s fill under chip-ink = %.2f' % (name, r['as_fill']['chip_ink']))
            if r['as_fill']['chip_ink_82'] < 4.5: fails.append('%s fill under 82%% chip-ink = %.2f' % (name, r['as_fill']['chip_ink_82']))
            if cg['tab-pill'] < 3.0: fails.append('%s glyph on tab pill = %.2f < 3' % (name, cg['tab-pill']))
        if r['role'] == 'surface':
            i = r['ink_on_it']
            if i['text'] < 7 or i['muted'] < 4.5: fails.append('%s: text %.1f muted %.1f' % (name, i['text'], i['muted']))
        if r['violations']:
            fails.append('%s breaks the hue rule: %s' % (name, '; '.join(r['violations'])))
    # dim as a non-text pip (AVOID) on the worst ground
    if cr(hex2rgb('#909298'), WORST) < 3.0: fails.append('dim pip on worst ground < 3')

    # --- glows: composite brightest pixel must stay <= the spec's worst pixel
    glows = {}
    for n, (hx, a, where) in GLOWS.items():
        comp = over(hex2rgb(hx), a, CANVAS)
        glows[n] = dict(hex=hx, alpha=a, where=where, composite=rgb2hex(comp), composite_Y=round(Y(comp), 4))
        if Y(comp) > Y(WORST): fails.append('%s composite brighter than the worst pixel' % n)

    # --- pairwise separation among the objects that can share a component
    pos = ['pos-qb', 'pos-rb', 'pos-wr', 'pos-te']
    H = {r['name']: hex2rgb(r['hex']) for r in rows}
    pairs = {}
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = dE(H[pos[i]], H[pos[j]]); pairs['%s/%s' % (pos[i], pos[j])] = round(d, 3)
            if d < 0.10: fails.append('%s vs %s dE %.3f < 0.10' % (pos[i], pos[j], d))
    for p in pos: pairs['%s/gold' % p] = round(dE(H[p], H['gold']), 3)
    for p in pos:
        if dE(H[p], H['gold']) < 0.10: fails.append('%s vs gold dE < 0.10' % p)
    placement = {  # never share a component; reported, not enforced
        'pos-wr/brand-aqua (code vs bar dot)': round(dE(H['pos-wr'], H['brand-aqua']), 3),
        'pos-rb/brand-aqua (code vs bar dot)': round(dE(H['pos-rb'], H['brand-aqua']), 3),
        'pos-wr/ink-blue (code vs glow/tab glyph)': round(dE(H['pos-wr'], H['ink-blue']), 3),
        'pos-wr/cool (code vs pip)': round(dE(H['pos-wr'], H['cool']), 3),
        'pos-qb/brand-red (code vs bar dot)': round(dE(H['pos-qb'], H['brand-red']), 3),
        'pos-te/brand-red (code vs bar dot)': round(dE(H['pos-te'], H['brand-red']), 3),
        'cool/ink-blue (pip vs glow/tab glyph)': round(dE(H['cool'], H['ink-blue']), 3),
        'straw/gold (pip vs pip, different meters)': round(dE(H['straw'], H['gold']), 3),
        'straw/text (pip vs ink)': round(dE(H['straw'], H['text']), 3),
        'brand-violet/ink-blue (dot vs glow/tab glyph)': round(dE(H['brand-violet'], H['ink-blue']), 3),
    }

    # --- glass over colour (cream on 52% glass over a Tier-A fill), bare vs with the 35% scroll-edge dim
    glass = {}
    for n in ['gold', 'pos-qb', 'pos-rb', 'pos-wr', 'pos-te', 'brand-red', 'brand-violet', 'brand-aqua']:
        f = H[n]; bare = over(GLASS_FILL, 0.52, f); dimmed = over(GLASS_FILL, 0.52, over((0, 0, 0), 0.35, f))
        glass[n] = dict(bare=round(cr(bare, H['text']), 2), dimmed=round(cr(dimmed, H['text']), 2))

    # --- the text scale on each surface family, as the spec sheet
    scale = {
        'on obsidian (canvas / panel / raised / raised-2 / worst pixel / card over worst)': {
            n: {g: round(cr(H[n], gg), 2) for g, gg in GROUNDS} for n in ['text', 'muted', 'dim', 'disabled']},
        'on a tinted chip (the darkest Tier-A fill is brand-red; gold shown too)': {
            'primary = chip-ink 100%': {n: round(cr(CHIP_INK, H[n]), 2) for n in ['brand-red', 'gold', 'pos-qb', 'pos-te']},
            'secondary = chip-ink 82%': {n: round(cr(over(CHIP_INK, 0.82, H[n]), H[n]), 2) for n in ['brand-red', 'gold', 'pos-qb', 'pos-te']},
            'tertiary': 'not permitted - a chip holds a code and at most a numeral',
            'disabled': 'a disabled chip is never a fill: chip-sit outline + dim ink (SPEC 5.1)'},
        'on glass (glass-worst / tab pill / frost)': {
            'primary = text': {g: round(cr(H['text'], gg), 2) for g, gg in GLASS_GROUNDS},
            'secondary = nav-text-2': {g: round(cr(H['nav-text-2'], gg), 2) for g, gg in GLASS_GROUNDS},
            'tertiary': 'not permitted on Level 2 (SPEC 3): no muted, no dim on glass',
            'disabled': {g: round(cr(H['disabled'], gg), 2) for g, gg in GLASS_GROUNDS}},
    }
    hc = {n: dict(hex=hx, oklch=[round(x, 3) for x in oklch(hex2rgb(hx))],
                  min_text=round(min(cr(hex2rgb(hx), g) for _, g in GROUNDS), 2)) for n, hx in HC.items()}
    hc_text = {n: dict(hex=hx, min_text=round(min(cr(hex2rgb(hx), g) for _, g in GROUNDS), 2)) for n, hx in HC_TEXT.items()}
    return rows, glows, pairs, placement, glass, scale, hc, hc_text, fails

# ----------------------------------------------------------------------------- outputs
def write_json(rows, glows, pairs, placement, glass, scale, hc, hc_text):
    out = {
        '_about': 'Graded Takes Obsidian multi-hue palette. Generated by palette_verify.py; PALETTE.md is the prose. Grounds from design/obsidian/SPEC.md.',
        'grounds': {n: rgb2hex(g) for n, g in GROUNDS + GLASS_GROUNDS},
        'tokens': {r['name']: {k: r[k] for k in r if k not in ('name',)} for r in rows},
        'glows': glows,
        'increase_contrast': {'hues': hc, 'text': hc_text},
        'separation_dE': {'enforced_min_0.10': pairs, 'placement_separated': placement},
        'glass_over_colour_cream_on_52pct_glass': glass,
        'text_scale': scale,
        'cap': {'families': ['warm(gold,straw)', 'cool', 'position', 'brand', 'identity(glow+tab glyph only)'],
                'per_screen': 'gold family + at most two of {cool, position, brand} in the content layer; the league dot in the bar is exempt; <= 7 chromatic swatches in content',
                'per_row': 'one code + one chip; never two fills'},
        'hue_rule': {
            'signal': 'OKLCH h 80-92 C<=0.17 (gold/straw) | h 245-265 C<=0.05 (cool) | C<=0.02 (neutral). Never h 0-40/350-360 (red) or 120-185 (green) at C>0.02. HSV: 38-48 any sat | 205-225 sat<=0.25 | sat<=0.08.',
            'category_brand_identity_tierA': 'any hue; OKLCH L 0.76-0.86, C 0.02-0.14. HSV: v>=0.72, s<=0.62. Carrier: <=3-char code >=11px/700, dot <=8px, ring <=2px, rule 2-3px, fill <=24px tall under chip-ink. Never a word, row or card.',
            'wash': 'OKLCH L 0.22-0.31, C<=0.05; carries the normal text ladder; never a meaning on its own',
            'glow': 'OKLCH L 0.55 C 0.10 at <=30% in the native ground; composite Y <= 0.0312 (#2A3145)',
            'text': 'the ladder only, C<=0.02; never takes a hue except <=3-char codes and deciding numerals',
            'global': 'no C>0.17; no ink-carrying fill at L 0.45-0.65; text>=4.5:1 and non-text>=3:1 on canvas/panel/raised/worst/card-over-worst; pixel test: no region >=24x24px with HSV sat>=0.45 in green 70-170 or red <20/>340',
        },
    }
    with open(os.path.join(HERE, 'palette.json'), 'w') as f: json.dump(out, f, indent=2)

def write_html(rows, glows, pairs, placement, glass, scale):
    H = {r['name']: r for r in rows}
    def sw(name, big=False):
        r = H[name]; c = r['contrast']; mn = min(c.values())
        extra = ''
        if r.get('as_fill'): extra = '<div class="k">fill / navy ink <b>%.1f</b></div>' % r['as_fill']['chip_ink']
        if r.get('ink_on_it'): extra = '<div class="k">text on it <b>%.1f</b> · muted <b>%.1f</b></div>' % (r['ink_on_it']['text'], r['ink_on_it']['muted'])
        tier = {'A': 'Tier A · ink / small fill', 'B': 'Tier B · wash', 'ladder': 'text ladder', 'C': 'glow'}[r['tier']]
        if r['role'] == 'surface':
            ratios = '<div class="k">vs canvas <b>%.1f</b> (a wash carries no meaning on its own: it is under the 3:1 non-text floor by design)</div>' % c['canvas']
        elif r['name'] in ('pos-k', 'pos-dst'):
            ratios = '<div class="k">text on a row/card <b>%.1f</b> (canvas %.1f; the bare worst pixel %.1f - a code never sits there)</div>' % (c['card-over-worst'], c['canvas'], c['worst-ground'])
        else:
            ratios = '<div class="k">min text on obsidian <b>%.1f</b> (worst pixel %.1f · card %.1f · canvas %.1f)</div>' % (mn, c['worst-ground'], c['card-over-worst'], c['canvas'])
        return ('<div class="sw%s"><div class="chip" style="background:%s"></div><div class="meta"><div class="n">%s</div>'
                '<div class="h">%s · OKLCH %.2f / %.2f / %.0f° · HSV %.0f° s%.2f</div><div class="r">%s</div>'
                '%s%s<div class="t">%s</div></div></div>'
                % (' big' if big else '', r['hex'], name + (' <i>(' + ', '.join(r['aliases']) + ')</i>' if r['aliases'] else ''), r['hex'],
                   r['oklch']['L'], r['oklch']['C'], r['oklch']['h'], r['hsv']['h'], r['hsv']['s'], r['job'], ratios, extra, tier))
    def glowsw(n):
        g = glows[n]
        return ('<div class="sw"><div class="chip glow" style="--g:%s;--a:%.2f"></div><div class="meta"><div class="n">%s</div><div class="h">%s at %d%% · composite %s · Y %.4f (ceiling 0.0312)</div><div class="r">%s</div><div class="t">Tier C · glow</div></div></div>'
                % (g['hex'], g['alpha'], n, g['hex'], int(g['alpha'] * 100), g['composite'], g['composite_Y'], g['where']))
    pos = ['pos-qb', 'pos-rb', 'pos-wr', 'pos-te', 'pos-k', 'pos-dst']
    poslabel = dict(zip(pos, ['QB', 'RB', 'WR', 'TE', 'K', 'DST']))
    tabs = [('Home', 'gold', 'glow-gold', '⌂'), ('Lineup', 'gold', None, '≡'), ('Board', 'gold', 'glow-gold', '▤'), ('Model', 'ink-blue', 'glow-ink', '◎'), ('Trade Desk', 'brand-violet', 'glow-yahoo', '⇄')]
    extra_tabs = [('Ledger (if it holds the fifth slot)', 'stone', 'glow-stone', '☰'), ('Sources (no tab: Model lights)', 'ink-blue', 'glow-ink', '◉')]
    def tab(name, hue, glow, glyph, on=True):
        g = glows[glow] if glow else None
        ground = ('radial-gradient(60%% 40%% at 50%% 100%%, rgba(%d,%d,%d,%.2f), transparent), ' % (*hex2rgb(g['hex']), g['alpha'])) if g else ''
        hx = H[hue]['hex']; pill = TAB_PILL; ratio = cr(hex2rgb(hx), pill)
        return ('<div class="tabcard"><div class="tabground" style="background:%s#0A0C12"><div class="mini"><div class="row"><span class="code" style="color:%s">%s</span><span>identity</span></div></div></div>'
                '<div class="tabbar"><div class="tabitem on"><span class="glyph" style="color:%s">%s</span><span class="lbl">%s</span></div></div>'
                '<div class="k">glyph on pill <b>%.1f</b> · %s%s</div></div>'
                % (ground, hx, hue, hx, glyph, name, ratio, hue, (' · glow ' + glow) if glow else ' · no glow: positions are the colour'))
    meter = [('SMASH', 'gold', 5), ('GOOD', 'straw', 4), ('NEUTRAL', 'text', 3), ('TOUGH', 'cool', 2), ('AVOID', 'dim', 1)]
    def pips(n, tokn):
        hx = H[tokn]['hex']
        return ''.join('<i class="pip" style="background:%s"></i>' % (hx if i < n else '#3A3E48') for i in range(5))
    html = []
    html.append('''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Obsidian palette - swatches</title>
<style>
:root{--canvas:#0A0C12;--panel:#12151D;--raised:#1C202B;--text:#E8E3D8;--muted:#ABA9A1;--dim:#909298;--gold:#F2B722;--hair:#FFFFFF14;--hair2:#FFFFFF24}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--text);font:14px/1.45 -apple-system,"SF Pro Text","Archivo",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.ground{min-height:100vh;background:
  radial-gradient(62% 38% at 16% 10%, rgba(86,102,148,.34), transparent 70%),
  radial-gradient(48% 30% at 88% 26%, rgba(242,183,34,.13), transparent 70%),
  radial-gradient(90% 40% at 55% 104%, rgba(120,132,168,.18), transparent 70%),
  linear-gradient(#0A0C12, #0D1018 55%, #0A0C12)}
main{max-width:1180px;margin:0 auto;padding:36px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:17px;margin:44px 0 12px;letter-spacing:.02em}
h2 small{color:var(--dim);font-weight:500;font-size:13px;margin-left:8px}
p.lede{color:var(--muted);max-width:820px;margin:0 0 6px}
.mono{font-family:"SF Mono","Spline Sans Mono",ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px}
.sw{display:flex;gap:12px;background:rgba(18,21,29,.78);border:1px solid var(--hair);box-shadow:inset 0 1px 0 rgba(255,255,255,.06);border-radius:14px;padding:12px}
.sw.big{grid-column:span 2}
.chip{width:56px;height:56px;border-radius:12px;flex:0 0 auto;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}
.chip.glow{background:radial-gradient(circle at 50% 60%, rgba(var(--gr,0),0,0,0), transparent);background:linear-gradient(rgba(0,0,0,0),rgba(0,0,0,0)),#0A0C12;position:relative;overflow:hidden}
.chip.glow::after{content:"";position:absolute;inset:0;background:radial-gradient(60% 60% at 50% 70%, var(--g), transparent 75%);opacity:var(--a)}
.meta{min-width:0}
.n{font-weight:700;font-size:14px}.n i{color:var(--dim);font-weight:500;font-style:normal}
.h{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-size:11px;color:var(--dim);margin-top:2px}
.r{font-size:12px;color:var(--muted);margin-top:4px}
.k{font-size:11px;color:var(--dim);margin-top:4px}.k b{color:var(--text);font-weight:600}
.t{font-size:10.5px;color:var(--dim);letter-spacing:.06em;text-transform:uppercase;margin-top:6px}
.strip{display:flex;gap:10px;flex-wrap:wrap;align-items:stretch}
.tabcard{flex:1 1 200px;min-width:200px;background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;overflow:hidden}
.tabground{height:96px;padding:12px}
.mini .row{display:flex;gap:8px;align-items:baseline;color:var(--dim);font-size:11px}
.code{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-weight:700;font-size:12px;letter-spacing:.06em}
.tabbar{margin:0 10px;background:rgba(28,31,40,.52);border:1px solid rgba(255,255,255,.07);box-shadow:inset 0 1px 0 rgba(255,255,255,.16);border-radius:22px;padding:4px;display:flex}
.tabitem{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 0;border-radius:18px;font-size:11px;font-weight:500}
.tabitem.on{background:rgba(255,255,255,.08);font-weight:600}
.glyph{font-size:20px;line-height:1}
.tabcard .k{padding:8px 12px 12px}
.posrow{display:flex;gap:8px;flex-wrap:wrap}
.poschip{display:flex;flex-direction:column;align-items:center;gap:6px;background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;padding:14px 12px;min-width:120px;flex:1}
.poschip .code{font-size:14px}
.poschip .fill{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-weight:700;font-size:12px;color:#101B33;padding:3px 8px;border-radius:6px}
.poschip .rule{width:100%;height:3px;border-radius:2px}
.row3{background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;padding:10px 14px;display:flex;flex-direction:column;gap:6px;max-width:390px}
.row3 .l1{display:flex;align-items:center;gap:10px}
.row3 .slot{font-family:"SF Mono",ui-monospace,Menlo,monospace;color:var(--dim);font-size:11px;letter-spacing:.06em;width:46px}
.row3 .name{font-weight:700;flex:1}
.row3 .team{color:var(--muted);font-size:12px}
.chipv{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-weight:700;font-size:11px;padding:4px 8px;border-radius:6px}
.chip-start{background:#F2B722;color:#101B33}.chip-sit{background:rgba(255,255,255,.03);border:1px solid #6A6E77;color:var(--muted)}.chip-lean{border:1px dashed #F2B722;color:#F2B722}
.pct{font-family:"SF Mono",ui-monospace,Menlo,monospace;color:var(--dim);font-size:11px}
.row3 .l2{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px;flex-wrap:wrap}
.pip{display:inline-block;width:6px;height:13px;border-radius:1px;margin-right:2px;vertical-align:middle}
.mlabel{font-size:11px;font-weight:700;letter-spacing:.08em;margin-left:6px}
.pill{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-size:11px;font-weight:700;padding:1px 6px;border-radius:5px;border:1px solid var(--hair2)}
.pill.q{background:var(--panel);box-shadow:inset 3px 0 0 #F2B722;color:var(--text)}
.pill.o{background:var(--text);color:var(--panel);border-color:var(--text)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}
.cap{display:flex;gap:12px;flex-wrap:wrap}
.cap .item{background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;padding:12px 14px;flex:1;min-width:230px}
table{border-collapse:collapse;font-size:12px;width:100%}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--hair)}th{color:var(--dim);font-weight:600;letter-spacing:.04em;font-size:11px;text-transform:uppercase}
.bar{display:flex;gap:8px;align-items:center;background:rgba(28,31,40,.52);border:1px solid rgba(255,255,255,.07);box-shadow:inset 0 1px 0 rgba(255,255,255,.16);border-radius:22px;padding:6px 12px;max-width:390px}
.bar .cap2{display:flex;flex-direction:column}
.bar .league{font-weight:600;font-size:15px}.bar .status{font-size:11px;color:#C9C5BC}
.bar .wk{margin-left:auto;font-family:"SF Mono",ui-monospace,Menlo,monospace;font-weight:700;font-size:11px;color:#F2B722}
.honesty{background:#2D281E;box-shadow:inset 0 2px 0 #F2B722;border-radius:14px;padding:10px 14px;max-width:390px;font-size:13px}
.honesty .d{font-family:"SF Mono",ui-monospace,Menlo,monospace;color:#F2B722}
.src{display:flex;gap:10px;flex-wrap:wrap}
.src .s{display:flex;align-items:center;gap:8px;background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;padding:10px 12px;flex:1;min-width:150px;font-size:12px}
.src .g{font-size:16px;width:20px;text-align:center}
.av{width:28px;height:28px;border-radius:50%;background:var(--raised);display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;box-shadow:0 0 0 2px var(--panel),0 0 0 3.5px var(--hair2)}
.av.creator{box-shadow:0 0 0 2px var(--panel),0 0 0 3.5px #F2B722}
footer{color:var(--dim);font-size:11px;margin-top:40px}
</style></head><body><div class="ground"><main>
<h1>Obsidian palette <span class="mono" style="color:var(--dim);font-size:13px;font-weight:500">generated by palette_verify.py</span></h1>
<p class="lede">Every swatch on the real ground (the spec's ramp and three lights). Ratios are WCAG 2.x against the obsidian grounds; "min text" is the minimum over canvas, panel, raised, raised-2, the brightest ground pixel #2A3145 and the 78% card over it. The text scale never takes a hue; hue lives on codes, dots, rings, rules, pips and small fills.</p>
''')
    # tab identities
    html.append('<h2>Five tab identities<small>selected glyph takes the page hue; the glass stays untinted; the ground carries the glow</small></h2><div class="strip">')
    for t_ in tabs: html.append(tab(*t_))
    html.append('</div><div class="strip" style="margin-top:10px">')
    for t_ in extra_tabs: html.append(tab(*t_))
    html.append('</div>')
    # positions
    html.append('<h2>Six positions<small>code ink at 11px/700 · the fill form under chip-ink · the widget\'s 3px rule</small></h2><div class="posrow">')
    for p in pos:
        r = H[p]; hx = r['hex']; fillink = r.get('as_fill', {}).get('chip_ink')
        html.append('<div class="poschip"><span class="code" style="color:%s">%s</span>%s<span class="rule" style="background:%s"></span><div class="h">%s</div><div class="k">text <b>%.1f</b>%s</div></div>'
                    % (hx, poslabel[p], ('<span class="fill" style="background:%s">%s</span>' % (hx, poslabel[p])) if fillink else '<span class="fill" style="background:transparent;color:%s;border:1px solid var(--hair2)">%s</span>' % (hx, poslabel[p]), hx, hx, min(r['contrast'].values()) if fillink else r['contrast']['card-over-worst'], (' · fill/ink <b>%.1f</b>' % fillink) if fillink else ' on a row · grey by convention'))
    html.append('</div>')
    # a row
    html.append('<h2>A Lineup row, a Do-now row, an avoid row<small>the only hue text is the two-letter code; the chip is weight; the meter is count + word + tint; gold on a time only where it decides (the Do-now row)</small></h2><div class="strip">')
    html.append('<div class="row3"><div class="l1"><span class="slot">FLEX2</span><span class="name">Bijan Robinson</span><span class="team"><span class="code" style="color:%s">RB</span> · ATL</span><span class="chipv chip-start">START</span><span class="pct">68%%</span></div>'
                '<div class="l2"><span>vs TB</span><span class="mono">Sun 1:00 PM ET</span><span>%s<span class="mlabel">SMASH</span></span><span class="mono">15.2</span></div></div>' % (H['pos-rb']['hex'], pips(5, 'gold')))
    html.append('<div class="row3"><div class="l1"><span class="slot">WR2</span><span class="name">Nico Collins</span><span class="team"><span class="code" style="color:%s">WR</span> · HOU</span><span class="pill q">Q</span><span class="chipv chip-lean">TOSS-UP</span><span class="pct">54%%</span></div>'
                '<div class="l2"><span>@ IND</span><span class="mono" style="color:#F2B722">Sun 1:00 PM ET</span><span>%s<span class="mlabel" style="color:var(--muted)">TOUGH</span></span><span class="mono" style="color:%s">−2.1</span></div></div>' % (H['pos-wr']['hex'], pips(2, 'cool'), H['cool']['hex']))
    html.append('<div class="row3" style="background:%s"><div class="l1"><span class="slot">TE1</span><span class="name">Trey McBride</span><span class="team"><span class="code" style="color:%s">TE</span> · ARI</span><span class="pill o">O</span><span class="chipv chip-sit">SIT</span><span class="pct">—</span></div>'
                '<div class="l2"><span>vs SEA</span><span class="mono" style="color:var(--dim)">Sun 4:05 PM ET</span><span>%s<span class="mlabel" style="color:var(--muted)">AVOID</span></span></div></div>' % (H['wash-cool']['hex'], H['pos-te']['hex'], pips(1, 'dim')))
    html.append('</div>')
    # matchup ramp
    html.append('<h2>Matchup scale<small>five steps, warm → cool; count carries the ordinal, the word anchors it, tint is the third channel</small></h2><div class="strip">')
    for w, tk, n in meter:
        r = H[tk]; html.append('<div class="item" style="background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;padding:12px 14px;flex:1;min-width:150px"><div>%s<span class="mlabel" style="color:%s">%s</span></div><div class="h">%s %s</div><div class="k">pip on card <b>%.1f</b> (floor 3)</div></div>'
                    % (pips(n, tk), 'var(--text)' if n >= 3 else 'var(--muted)', w, tk, r['hex'], r['contrast']['card-over-worst']))
    html.append('</div>')
    # bar + honesty + status + streak + sources
    html.append('<h2>League dots in the bar · the honesty banner · status · streak<small>colour in the bar is one 8px dot; the banner is the loudest non-colour</small></h2><div class="strip">')
    for lg, tk in [('ESPN · Kid\'s Table', 'brand-red'), ('Yahoo · Sunday Regrets', 'brand-violet'), ('Sleeper · The Basement', 'brand-aqua')]:
        html.append('<div style="flex:1;min-width:300px"><div class="bar"><span style="font-size:14px">◆</span><div class="cap2"><span class="league"><span class="dot" style="background:%s"></span>%s ▾</span><span class="status">Live · checked 9:04 PM</span></div><span class="wk">WK 1</span></div><div class="k" style="margin-top:6px">%s %s · dot on glass <b>%.1f</b> (floor 3)</div></div>'
                    % (H[tk]['hex'], lg, tk, H[tk]['hex'], H[tk]['contrast_glass']['glass-worst']))
    html.append('</div><div class="strip" style="margin-top:12px"><div class="honesty">Couldn\'t refresh — showing week 1 as of <span class="d">Thu 10 Sep, 9:04 PM</span>. Nothing in it has been re-checked since then.</div>')
    html.append('<div class="item" style="background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;padding:12px 14px;min-width:260px"><div style="display:flex;gap:8px;align-items:center"><span class="pill q">Q</span><span class="pill q">D</span><span class="pill o">O</span><span class="pill o">IR</span><span class="pill" style="color:var(--dim)">BYE</span></div><div class="k" style="margin-top:8px">Q/D = gold 3px rule (the yellow tier) · O/IR = cream fill (the loudest weight) · the letter carries it</div></div>')
    html.append('<div class="item" style="background:rgba(18,21,29,.78);border:1px solid var(--hair);border-radius:14px;padding:12px 14px;min-width:260px"><div style="display:flex;gap:18px;align-items:center"><span><span style="color:#F2B722">▲</span> <b>HOT</b> <span class="mono" style="color:var(--muted)">71%%</span></span><span><span style="color:%s">❄</span> <b>COLD</b> <span class="mono" style="color:var(--muted)">41%%</span></span><span><span style="color:var(--dim)">●</span> <b style="color:var(--muted)">—</b></span></div><div class="k" style="margin-top:8px">HOT = gold glyph + gold end-dot · COLD = cool glyph + cool end-dot · the word stays cream</div></div></div>' % H['cool']['hex'])
    html.append('<h2>Source categories<small>sources are faces; the category is a 12px glyph; only the two platform-shaped kinds carry a brand tint</small></h2><div class="src">')
    for g, name, tk, ring in [('🎙', 'podcast', 'brand-violet', 'creator'), ('▶', 'YouTube', 'brand-red', 'creator'), ('✉', 'newsletter', 'text', 'creator'), ('◍', 'analyst', 'text', 'creator'), ('◌', 'feed', 'dim', ''), ('▤', 'news', 'muted', '')]:
        hx = H[tk]['hex']
        html.append('<div class="s"><span class="av %s">JB</span><span class="g" style="color:%s">%s</span><span><b>%s</b><div class="h">%s %s</div></span></div>' % (ring, hx, g, name, tk, hx))
    html.append('</div>')
    # all tokens
    html.append('<h2>Every token<small>name · hex · role · ratios</small></h2><div class="grid">')
    for r in rows: html.append(sw(r['name']))
    for n in glows: html.append(glowsw(n))
    html.append('</div>')
    # glass table
    html.append('<h2>Glass over colour<small>cream on the 52% glass stand-in over a Tier-A fill; the scroll edge effect is load-bearing</small></h2><table><tr><th>fill under the bar</th><th>bare glass</th><th>with the 35% edge dim</th></tr>')
    for n, v in glass.items(): html.append('<tr><td>%s</td><td class="mono" style="color:%s">%.1f%s</td><td class="mono">%.1f</td></tr>' % (n, 'var(--muted)' if v['bare'] < 4.5 else 'var(--text)', v['bare'], ' (fails)' if v['bare'] < 4.5 else '', v['dimmed']))
    html.append('</table>')
    html.append('<h2>Separation<small>OKLab ΔE; ≥ 0.10 reads as a different colour at chip size</small></h2><table><tr><th>pair</th><th>ΔE</th><th>rule</th></tr>')
    for k, v in pairs.items(): html.append('<tr><td>%s</td><td class="mono">%.3f</td><td>enforced ≥ 0.10</td></tr>' % (k, v))
    for k, v in placement.items(): html.append('<tr><td>%s</td><td class="mono">%.3f</td><td style="color:var(--muted)">never share a component</td></tr>' % (k, v))
    html.append('</table><footer>Grounds and the text ladder from design/obsidian/SPEC.md. Rerun: python3 design/palette/palette_verify.py</footer></main></div></body></html>')
    with open(os.path.join(HERE, 'swatches.html'), 'w') as f: f.write('\n'.join(html))

def print_tables(rows, glows, pairs, placement, glass, scale, hc, hc_text):
    print('== tokens ==')
    for r in rows:
        c = r['contrast']; g = r['contrast_glass']
        print('%-13s %s  okL %.2f C %.3f h %5.1f  HSV %5.1f s%.2f | canvas %.1f panel %.1f raised %.1f r2 %.1f worst %.1f card %.1f | glass %.1f pill %.1f%s%s%s' % (
            r['name'], r['hex'], r['oklch']['L'], r['oklch']['C'], r['oklch']['h'], r['hsv']['h'], r['hsv']['s'],
            c['canvas'], c['panel'], c['raised'], c['raised-2'], c['worst-ground'], c['card-over-worst'], g['glass-worst'], g['tab-pill'],
            (' | fill/ink %.1f (82%% %.1f)' % (r['as_fill']['chip_ink'], r['as_fill']['chip_ink_82'])) if r.get('as_fill') else '',
            (' | text %.1f muted %.1f dim %.1f gold %.1f' % tuple(r['ink_on_it'].values())) if r.get('ink_on_it') else '',
            ('  <-- ' + '; '.join(r['violations'])) if r['violations'] else ''))
    print('\n== glows ==')
    for n, g in glows.items(): print('%-13s %s @%d%% -> %s Y %.4f  (%s)' % (n, g['hex'], g['alpha'] * 100, g['composite'], g['composite_Y'], g['where']))
    print('\n== separation ==')
    for k, v in pairs.items(): print('  %-22s %.3f' % (k, v))
    for k, v in placement.items(): print('  %-50s %.3f' % (k, v))
    print('\n== glass over colour ==')
    for n, v in glass.items(): print('  %-13s bare %.1f%s dimmed %.1f' % (n, v['bare'], ' (FAILS)' if v['bare'] < 4.5 else '', v['dimmed']))
    print('\n== increase contrast ==')
    for n, v in hc.items(): print('  %-13s %s okLCH %s min text %.1f' % (n, v['hex'], v['oklch'], v['min_text']))
    for n, v in hc_text.items(): print('  %-13s %s min text %.1f' % (n, v['hex'], v['min_text']))
    print('\n== text scale ==')
    print(json.dumps(scale, indent=1))

if __name__ == '__main__':
    rows, glows, pairs, placement, glass, scale, hc, hc_text, fails = compute()
    print_tables(rows, glows, pairs, placement, glass, scale, hc, hc_text)
    if '--check' not in sys.argv:
        write_json(rows, glows, pairs, placement, glass, scale, hc, hc_text)
        write_html(rows, glows, pairs, placement, glass, scale)
        print('\nwrote palette.json and swatches.html')
    print('\n%s' % ('ALL CHECKS PASS' if not fails else '%d CHECK(S) FAILED:\n  ' % len(fails) + '\n  '.join(fails)))
    sys.exit(1 if fails else 0)
