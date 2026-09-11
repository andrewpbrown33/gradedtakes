#!/usr/bin/env python3
"""Reproduces every number in DARK_MULTIHUE.md.

Pure Python, no dependencies. Run from anywhere:
    python3 design/palette/verify_multihue.py

Contrast is WCAG 2.x relative luminance. Hue/lightness/chroma are OKLCH
(Bjorn Ottosson's matrices). Grounds are the obsidian spec's: canvas, panel,
raised, the brightest native-ground pixel under light 1 (#2A3145), and the
78% translucent card composited over that pixel. Rerun after any token edit.
"""
import json, math, os, sys

# ---------- colour maths ----------
def hex2rgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def rgb2hex(rgb): return '#%02X%02X%02X' % tuple(rgb)
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
    in_gamut = all(-0.0005 <= c <= 1.0005 for c in lr)
    def gam(c):
        c = min(max(c, 0.0), 1.0)
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return tuple(round(gam(c) * 255) for c in lr), in_gamut
def rgb_to_oklch(rgb):
    L, a, b = srgb_to_oklab(rgb); return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360
def dE(a, b):
    A, B = srgb_to_oklab(a), srgb_to_oklab(b); return math.sqrt(sum((A[i] - B[i]) ** 2 for i in range(3)))

# ---------- the obsidian grounds and inks (SPEC §1) ----------
canvas = hex2rgb('#0A0C12'); panel = hex2rgb('#12151D'); raised = hex2rgb('#1C202B')
worst = hex2rgb('#2A3145')                      # brightest ground pixel under light 1
card_worst = over(panel, 0.78, worst)           # translucent card over it -> #171B26
text = hex2rgb('#E8E3D8'); muted = hex2rgb('#ABA9A1'); dim = hex2rgb('#909298')
gold = hex2rgb('#F2B722'); ink = hex2rgb('#101B33')
glass = (28, 31, 40)                            # gt-glass-fill at 52%
GROUNDS = [('canvas', canvas), ('panel', panel), ('raised', raised), ('worst ground', worst), ('card/worst', card_worst)]

# ---------- candidates (DARK_MULTIHUE.md §6) ----------
CANDIDATES = {
    'pos-qb':         (0.78, 0.12, 355),
    'pos-rb':         (0.80, 0.11, 165),
    'pos-wr':         (0.80, 0.10, 228),
    'pos-te':         (0.80, 0.11, 50),
    'league-espn':    (0.72, 0.16, 20),
    'league-yahoo':   (0.74, 0.14, 305),
    'league-sleeper': (0.84, 0.11, 195),
}
EXISTING = {'gold': '#F2B722', 'mint (ink-blue)': '#9DBBF3', 'coral (stone)': '#BDB0A0', 'dim': '#909298'}

def main():
    fails = 0
    print('== grounds ==')
    for n, g in GROUNDS:
        print('  %-13s %s Y=%.4f  text needs Y>=%.3f (4.5)  %.3f (7)  non-text %.3f (3)' % (n, rgb2hex(g), Y(g), 4.5 * (Y(g) + .05) - .05, 7 * (Y(g) + .05) - .05, 3 * (Y(g) + .05) - .05))
    print('  fill under navy ink needs Y>=%.3f; fill under cream needs Y<=%.3f  -> dead zone between' % (4.5 * (Y(ink) + .05) - .05, (Y(text) + .05) / 4.5 - .05))

    print('\n== Tier A floors (min over every 15deg hue) ==')
    for L, C in [(0.72, 0.12), (0.76, 0.12), (0.80, 0.11), (0.84, 0.11)]:
        mins = {'worst ground': 99, 'card': 99, 'ink': 99}; oog = []
        for h in range(0, 360, 15):
            rgb, ok = oklch_to_rgb(L, C, h)
            if not ok: oog.append(h); continue
            mins['worst ground'] = min(mins['worst ground'], cr(rgb, worst))
            mins['card'] = min(mins['card'], cr(rgb, card_worst))
            mins['ink'] = min(mins['ink'], cr(rgb, ink))
        print('  L%.2f C%.2f: bare worst ground >= %.1f | card >= %.1f | navy ink >= %.1f | out of gamut: %s' % (L, C, mins['worst ground'], mins['card'], mins['ink'], oog or '-'))

    print('\n== dead zone: best text on a C0.12 fill by lightness ==')
    for L in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
        mc = mi = 99
        for h in range(0, 360, 30):
            rgb, ok = oklch_to_rgb(L, 0.12, h)
            if ok: mc = min(mc, cr(rgb, text)); mi = min(mi, cr(rgb, ink))
        print('  L%.2f: cream %.1f | navy %.1f' % (L, mc, mi))

    print('\n== wash tier (C0.05) ==')
    for L in [0.24, 0.27, 0.30]:
        m = [99, 99, 99]
        for h in range(0, 360, 30):
            rgb, ok = oklch_to_rgb(L, 0.05, h)
            if ok: m = [min(m[0], cr(rgb, text)), min(m[1], cr(rgb, muted)), min(m[2], cr(rgb, dim))]
        print('  L%.2f: cream %.1f muted %.1f dim %.1f' % (L, *m))

    print('\n== candidates ==')
    out = {}
    for n, (L, C, h) in CANDIDATES.items():
        rgb, ok = oklch_to_rgb(L, C, h); out[n] = rgb
        ratios = [cr(rgb, g) for _, g in GROUNDS]
        mn = min(ratios); fill = cr(rgb, ink)
        flag = '' if (mn >= 4.5 and fill >= 4.5 and ok) else '  <-- FAIL'
        if flag: fails += 1
        print('  %-15s %s okL %.2f C %.2f h %3d  min text %.1f (%s)  fill/navy %.1f  dE gold %.2f%s' % (
            n, rgb2hex(rgb), L, C, h, mn, ' '.join('%.1f' % r for r in ratios), fill, dE(rgb, gold), flag))
    for n, hx in EXISTING.items():
        rgb = hex2rgb(hx); L, C, h = rgb_to_oklch(rgb)
        print('  %-15s %s okL %.2f C %.2f h %3.0f  min text %.1f' % (n, hx, L, C, h, min(cr(rgb, g) for _, g in GROUNDS)))

    print('\n== pairwise OKLab distance, positions (>= 0.10 reads as different at chip size) ==')
    pos = [k for k in CANDIDATES if k.startswith('pos-')]
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = dE(out[pos[i]], out[pos[j]]); print('  %-7s %-7s %.3f%s' % (pos[i], pos[j], d, '' if d >= 0.10 else '  <-- close'))
    print('  placement-separated: pos-wr/league-sleeper %.3f' % dE(out['pos-wr'], out['league-sleeper']))
    print('  TE vs gold %.3f ; stone vs gold %.3f' % (dE(out['pos-te'], gold), dE(hex2rgb('#BDB0A0'), gold)))

    print('\n== wash + glow per hue; glow composite must stay <= worst pixel Y %.4f ==' % Y(worst))
    for n, (L, C, h) in CANDIDATES.items():
        w, _ = oklch_to_rgb(0.27, 0.04, h); g, _ = oklch_to_rgb(0.55, 0.10, h); comp = over(g, 0.30, canvas)
        flag = '' if Y(comp) <= Y(worst) else '  <-- glow too bright'
        if flag: fails += 1
        print('  %-15s wash %s (cream %.1f muted %.1f) | glow %s @30%% -> %s Y=%.4f%s' % (n, rgb2hex(w), cr(w, text), cr(w, muted), rgb2hex(g), rgb2hex(comp), Y(comp), flag))

    print('\n== glass over colour: cream on 52% glass over a Tier-A fill, bare vs 35% dim beneath ==')
    for n, rgb in list(out.items()) + [('gold', gold)]:
        bare = over(glass, 0.52, rgb); dimmed = over(glass, 0.52, over((0, 0, 0), 0.35, rgb))
        print('  %-15s bare %.1f%s | dimmed %.1f' % (n, cr(bare, text), ' (FAILS 4.5)' if cr(bare, text) < 4.5 else '', cr(dimmed, text)))

    print('\n%s' % ('ALL CHECKS PASS' if fails == 0 else '%d CHECK(S) FAILED' % fails))
    return fails

if __name__ == '__main__':
    sys.exit(1 if main() else 0)
