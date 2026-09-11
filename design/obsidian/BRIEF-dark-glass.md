# Obsidian Glass — dark glass done well

Design brief for the Graded Takes iPhone view. Research topic: what makes dark glass UI read as expensive rather than cheap, and the palette + surface recipe that follows from it.

Files in this folder:

- `BRIEF-dark-glass.md` — this document
- `tokens.obsidian.css` — the proposed tokens in the live `--wr-*` vocabulary plus the glass recipe (`.gt-glass`, `.gt-glass-thick`, `.gt-panel`), ready to lift into `engine/prefs.py` as an `_OBSIDIAN` dict / `:root[data-theme="obsidian"]` block
- `tokens.obsidian.json` — the same tokens plus every contrast ratio quoted below, machine-readable
- `swatches.html` — a self-contained proof sheet (open it on the phone): ladder, tokens, chips, a Needs-you card, roster rows on washes, a real backdrop-filter bar with gold passing under it, a mono ledger

Nothing under `engine/` or `ios/` was touched.

---

## 0. The decisions, in one screen

| Decision | Choice | Why (short) |
|---|---|---|
| Ground | `#0A0C12` — near-black with a cool cast (hue ≈ 225°, the navy pushed to black), **not** `#000` | True black smears on OLED when scrolling and turns every shadow invisible; a cool cast keeps it in the family of the navy identity. Sources §1 |
| Ladder | canvas `#0A0C12` → panel `#12151D` → raised `#1C202B` (L\* 3.4 → 6.8 → 12.3) | Depth on dark is carried by lightness, not shadow. Apple's own base ladder is `#000 → #1C1C1E → #2C2C2E`; ours is tighter because the edge highlight does part of the work. §5 |
| Glass | Real `backdrop-filter` only where content moves beneath (sticky headers, floating verb bar, sheets). Content cards are **opaque** panels with a 1px top highlight | Apple: keep Liquid Glass on the navigation layer, never glass on glass. §2, §5 |
| Ink | Warm off-white `#E8E3D8` (15.3:1 on canvas), never `#FFF` | Pure white on near-black halates on OLED; warm off-white is also the through-line from the Night retune (`#E1DDD2`) and Broadcast's cream. §3 |
| Accent | Gold `#F2B722`, unchanged, 10.8:1 on canvas | It is text-safe on obsidian, so gold can be *text* here (it cannot on paper). Fills stay rationed: START chips and one primary verb per screen. §4 |
| Verdicts | Weight, exactly as today: gold fill / ghost outline `#6A6E77` / dashed gold | The ghost outline is tuned to ≥ 3:1 on every surface so SIT is still a legible control boundary. |
| Chrome | The native iOS 26 Liquid Glass tab bar and header **are** the chrome; the page ships no bar of its own in app mode. `.tint(gold)` on the selection only | Apple: tint only the primary element, "when every element is tinted, nothing stands out." |

---

## 1. The obsidian ground — which near-black actually works

**Pure `#000` is the wrong answer for a scrolling app, even on OLED.** Two independent reasons:

1. *Smear.* On OLED a black pixel is off; when content scrolls over true black the pixels must switch on from cold, and "the pixels find it hard to keep pace with scrolling, resulting in a smear on the screen." Vidit Bhargava's fix for LookUp was a grey of RGB(5) — "just black enough to look like black to the human eye, but grey enough to stop black smearing" — with negligible power cost versus RGB(0). ([Bhargava / LookUp Design, via MacStories](https://www.macstories.net/linked/designing-a-dark-theme-for-oled-iphones/); [XDA on the <1% battery delta](https://www.xda-developers.com/amoled-black-vs-gray-dark-mode/))
2. *Depth.* Material's rationale for `#121212` over black: "it's easier to see shadows on gray (instead of a true black)" and dark grey "can express a wider range of color, elevation, and depth." ([Material Design, Dark theme](https://m2.material.io/design/color/dark-theme.html)) Shaban Rasheed puts it more bluntly: "A shadow on a near-black surface is nearly invisible, because there is no lighter ground for it to fall on." ([Rasheed, Dark mode done right](https://shabanrasheed.com/writing/dark-mode-done-right))

**Apple's system dark ladder** is `systemBackground #000000` → `secondarySystemBackground #1C1C1E` → `tertiary #2C2C2E`, and the HIG describes two sets, *base* and *elevated*: "The base colors are dimmer, making background interfaces appear to recede, and the elevated colors are brighter, making foreground interfaces appear to advance." ([Sarunw dark color cheat sheet](https://sarunw.com/posts/dark-color-cheat-sheet/); [HIG Dark Mode, paraphrased by Median](https://median.co/blog/what-are-apples-human-interface-guidelines-for-dark-mode)) Note Apple *does* start at `#000` — but its content lives on `#1C1C1E` grouped cells, and the home/lock screens are photographs, so the OLED-smear case rarely arises there. Our pages are dense scrolling lists; we take the LookUp position.

**Cool vs warm cast.** Broadcast already owns "the dark that is warm instead of blue" (`#1A1714`). Obsidian has to be a different room again, and a *cool* near-black is what the word means — the volcanic glass reads blue-black. It also keeps the navy identity in the DNA: `#0A0C12` is `#101B33`'s hue with the lightness pulled to L\* 3.4. Robinhood's dark mode is "a deep dark gray, not pure AMOLED black" with no true-black toggle ([Northville Tech](https://www.northvilletech.com/blog/how-to-enable-dark-mode-in-robinhood/)); Bloomberg's ground is "deep black or near-black" with amber on it ([Curio, Bloomberg Terminal style](https://designbycurio.com/learn/bloomberg-terminal-green)). We sit between those: darker than Robinhood, one step off Bloomberg's void.

**Chosen:** `canvas #0A0C12` (luminance 0.0037, L\* 3.4). White-on-it contrast is 19.5:1 versus 21:1 on `#000` — nothing lost, smear and flat-shadow both avoided.

---

## 2. How glass surfaces read on dark

What Apple actually does, from the WWDC25 session transcript ([Meet Liquid Glass, session 219](https://developer.apple.com/videos/play/wwdc2025/219/)):

- The material "dynamically bends, shapes, and concentrates light" (lensing), and has a highlights layer: "Light sources inside of this environment shine on the material producing highlights that respond to geometry." That highlight is the *edge* — the thing a flat CSS fake most often forgets.
- Shadows are adaptive: "increases the opacity of its shadow when it is over text… lowers the opacity of its shadow when it is over a solid light background."
- Two variants, "never mixed." **Regular** "provides legibility regardless of context. It works in any size, over any content." **Clear** "needs a dimming layer to darken the underlying content. Without it, legibility gets noticeably worse," and is only for media-rich content with "bold and bright" content on top. We are a data app: Regular semantics, always.
- Bigger glass gets thicker: "casts deeper, richer shadows, has more pronounced lensing and refraction effects, and a softer scattering of light." So a sheet is not a bar scaled up — it is a heavier fill, a bigger blur, a deeper shadow.
- Pressed state: "the material illuminates from within… Starting right under your fingertips, the glow spreads." Feedback is a lift in the fill, not a coloured glow.

What the iOS 26 shipping releases taught: the first betas' Control Center "blend[ed] in with the background, making toggles difficult to find"; Apple then "dramatically reduced the transparency," and 26.1 added a **Tinted** option that "increases the opacity of Liquid Glass UI elements and improves contrast." ([AppleInsider, one year later](https://appleinsider.com/articles/26/05/08/ios-26-review-one-year-later-liquid-glass-complaints-hide-the-real-problem); [MacRumors on the 26.1 toggle](https://www.macrumors.com/2025/10/20/ios-26-1-transparency-option-liquid-glass/)) The dark-mode-specific advice that emerged is to run Tinted in dark: it "will improve the legibility of text and design elements in general." ([AnotherApple](https://www.anotherapple.com/2026/04/the-correct-way-to-use-dark-mode-with-liquid-glass/)) Lesson: on dark, err toward the more opaque, more tinted end. The glass should be *felt* at the edge and in the blur, not seen through.

**Fill opacity ranges that work on dark** (community consensus, consistent across write-ups): dark-tinted fills `rgba(≈10–15, ≈10–25, 0.6–0.75)` for bars, up to `0.75–0.85` for modals; blur 16–32px; border `rgba(255,255,255,0.10–0.18)`; a brighter *top* border (`0.2`) over a dimmer all-round border (`0.12`) plus a 1px inset white at `0.05`, "creates the illusion of a light catching the top edge." ([CSS Studio glassmorphism guide](https://css-studio.com/blog/glassmorphism-css-guide); [CSS Top Sites, dark backgrounds](https://csstopsites.com/glassmorphism-dark-backgrounds); [Colorffy](https://blog.colorffy.com/css-glassmorphism-effects)) Two of those guides independently list "don't nest glass elements" as a rule.

**Inner shadow vs outer glow.** The edge highlight is an *inset* top line; the separation from content below is an *outer drop shadow*, heavier and tighter than on paper (dark shadows must be ≈ 45–60% to register). An outer *glow* — light spilling outward from the element — is the single fastest way to make dark glass look like a 2019 Dribbble shot (§6). Never.

---

## 3. Text on dark glass

- **Pure white is too much.** "Pure white text on a pure black background is the maximum possible contrast, and it is too much: the letters vibrate against the void." ([Rasheed](https://shabanrasheed.com/writing/dark-mode-done-right)) Halation: retinal cells "respond more strongly to bright stimuli against dark surroundings," so white text appears to "spread, glow, or 'bloom'" — mathematically identical ratios read lower on dark than on light. ([ColorContrast dark-mode guide](https://www.colorcontrast.org/blog/dark-mode-contrast-accessibility-guide/)) Practical range: "#E0E0E0 to #F0F0F0 read as 'white'" ([Muzli](https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/)); The Skins Factory's warm examples are `#e2dfd8` / `#f4f2ed` ([Skins Factory](https://www.theskinsfactory.com/uiux-design-blog/why-your-dark-mode-looks-bad-ui-ux-guide)). Apple's own `label` is `#FFFFFF`, but its `secondaryLabel` is `#EBEBF5` at 60% — i.e. even Apple's second tier is a *warm-leaning* off-white at reduced alpha. ([Sarunw](https://sarunw.com/posts/dark-color-cheat-sheet/))
- **Warm, not cool, off-white.** On a cool ground, a cool-white text (`#EAF0FA`, today's Night ink) is icy; the Night retune already moved to warm `#E1DDD2` for the hour-long session. Obsidian keeps that logic: cream ink on blue-black is the classic film-title pairing, and it is what makes gold sit naturally beside the text instead of clashing with it.
- **The floor for muted text.** Target ≥ 7:1 for body on dark because of halation; muted ≥ 4.5:1 is the legal floor but "mid-gray (#6B7280) body copy on #121212 that looks 'fine' but fails 4.5:1 is one of the most common failures." ([ColorContrast](https://www.colorcontrast.org/blog/dark-mode-contrast-accessibility-guide/)) Our tiers: `text 15.3:1`, `muted 8.3:1`, `dim 6.3:1` on canvas; on the raised surface they are still `12.7 / 6.9 / 5.2`. Nothing dims below 4.5 on any opaque surface or wash.
- **On real glass the floor moves.** Because the fill is 72% opaque, what scrolls beneath matters. Worst realistic case — a gold START chip directly under a floating bar: cream text on the composite is **8.0:1**, gold-on-glass 5.6:1, but muted text falls to **4.35:1**. Hence the rule in the recipe: Level-2 glass carries primary text and gold only; anything with a muted line (a sheet, a menu) uses the thick 84% fill, where muted recovers to 5.6:1.

---

## 4. One accent on obsidian — where gold works and where it becomes noise

- **Gold is text-safe here, which it is not on paper.** `#F2B722` on `#0A0C12` is 10.8:1 (on white it is ≈ 1.9:1, which is why `gold` on paper is `#8F6606`). So the obsidian theme can collapse `gold` and `rule` to the same hex and let gold *say things* — the lock time, the Δ that is up, the source that is hot. Apple does the same lift for its own yellow in dark (`#FFCC00` → `#FFD60A`), keeping perceived saturation up on dark. ([Sarunw](https://sarunw.com/posts/dark-color-cheat-sheet/)) We do not need a lift; the gold is already deep.
- **Fills get louder on dark.** A gold fill that reads as "a warm chip" on cream reads as "the brightest thing on the screen" on obsidian. That is correct for START — the whole system encodes verdict by weight — and wrong for anything else. Apple's rule, verbatim: "Tinting should only be used to bring emphasis to primary elements and actions in the UI… When every element is tinted, nothing stands out." ([Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/)) Apple's designers in the WWDC lab: reserve colour for "hero actions, preferred actions (like Done), and status indicators with consistent meaning across the app." ([WWDC25 design lab transcript](https://gist.github.com/samhenrigold/2da3acec094ed339a82155583c1ab293))
- **Budget, per screen:** gold *fills* = the START chips + at most one primary verb (the "Do now" item's button, or nothing). Everything else that needs attention gets the gold **rule** (a 2px top edge), which costs almost no area and still reads at 10.8:1 as a line. Gold *text* is allowed for numbers and times, never for body copy. Gold *glow*: never (§6).
- **Where it turns to noise:** a gold verb button on every Needs-you row (three gold buttons = no primary); gold tinting the whole tab bar glass; gold hairlines on every card; gold avatars rings; a gold gradient anywhere. Underdog is the cautionary reference — black/yellow works for them precisely because the yellow is loud and *everything* is yellow, which is a betting-app register, not an editorial one. Ours is the newspaper's one gold rule, moved to a dark page.
- The other two "colours" remain what v3 made them: `mint` (positive) is ink-blue `#9DBBF3`, `coral` (negative) is stone `#BDB0A0`. Both ≥ 8.5:1 on panel. No green, no red — Bloomberg's own accessibility research found colour-vision-deficient users had "more difficulty distinguishing between darker colors on dark backgrounds" and with red/green line pairs, which is a second argument for weight-not-hue on a dark ground. ([Bloomberg UX](https://www.bloomberg.com/ux/2021/10/14/designing-the-terminal-for-color-accessibility/))

---

## 5. Depth and layering — how many layers before mud

Apple's layering rules, verbatim ([Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/)):

> "it is best reserved for the navigation layer that floats above the content of your app."
> "making [a tableview] Liquid Glass would make it compete with other elements and muddy the hierarchy. So keep it in the content layer instead."
> "always avoid glass on glass… When placing elements on top of Liquid Glass, avoid applying the material to both layers. Instead, use fills, transparency, and vibrancy for the top elements."

And the designers' lab: "Layering glass creates visual complexity. Instead, use vibrant fills and labels to show control shapes." ([design lab](https://gist.github.com/samhenrigold/2da3acec094ed339a82155583c1ab293))

The HIG's materials page adds the dark-specific caveat: darker materials "tend to hide shadows, reducing depth" — which is why our card depth comes from the lightness ladder and the top edge, not from blur. ([HIG Materials, via search summary](https://developer.apple.com/design/human-interface-guidelines/materials))

**The layer model for Graded Takes (three levels, never more on one screen):**

| Level | What | Surface | Blur | Examples |
|---|---|---|---|---|
| 0 | Ground | `canvas #0A0C12`, opaque | none | the page |
| 1 | Content | `panel #12151D`, opaque; hairline `white 8%`; inset top edge `white 6%`; **no drop shadow** | none | Decision Cards, roster groups, ledger table, Trade Desk grid |
| 1+ | Raised-in-content | `raised #1C202B`, opaque; hairline-2 | none | pills, avatars, secondary verb buttons, table hover |
| 2 | Floating over content | `rgba(14,17,24,.72)`, edge-top `white 16%`, drop `0 8px 24px rgba(0,0,0,.45)` | 20px + saturate 140% | sticky "Do now / Before lock / This week" headers, a floating verb bar, the league switcher popover, the native tab bar & header (Apple's, for free) |
| 3 | Modal | `rgba(14,17,24,.84)`, same edge, drop `0 16px 40px rgba(0,0,0,.55)` | 28px | sheets, menus, the settings tray |

Rule of thumb from the Muzli guide — step surfaces "by 5 to 8 percent" luminance each and stop at four — matches this (three opaque steps plus one glass) ([Muzli](https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/)). A Level-2 element never contains another Level-2 element; a Level-3 sheet's *contents* are Level-1 panels, not glass.

---

## 6. What makes dark UI look cheap

Collected from the write-ups above plus [Supercharge, 6 mistakes](https://supercharge.design/articles/6-mistakes-to-avoid-in-dark-ui-design), [Skins Factory](https://www.theskinsfactory.com/uiux-design-blog/why-your-dark-mode-looks-bad-ui-ux-guide), and [RAXXO on "AI-looking" dark mode](https://raxxo.shop/blogs/lab/dark-mode-design-that-doesnt-look-ai):

1. **Pure black with grey cards on it.** No ladder, so every card is a grey rectangle "floating" on a void; shadows do nothing; OLED smears.
2. **Neon.** "Bright neon colors… cause visual fatigue"; the tell of generated design is "neon-on-dark everything — glowing borders on cards and animated accent colors in the background."
3. **Gradients everywhere.** Backgrounds, buttons, chips all gradient-filled read as a template. One gradient is a mood; six is a theme store.
4. **Glow abuse.** Outer glows on buttons, on active tabs, on cards. Real glass catches light at its *edge*; it does not emit.
5. **Saturated light-mode colours pasted onto dark.** "Highly saturated colors can cause visual vibration and reduce legibility." A `#3B82F6` that is 4.6:1 on white is 2.3:1 on `#121212`.
6. **Full-white text and white blocks.** "A white panel dropped into a dark layout is a small flashbang."
7. **Inconsistent spacing.** "Inconsistent spacing registers as 'cheap' even if the colors and typography are perfect… dark mode magnifies design mistakes."
8. **Everything is glass.** Glass cards on a glass page under a glass bar: nothing has a place to be.

Bloomberg is the useful counter-example: density itself is not cheap. Its problem is amber-on-black *decoration by tradition* ("favor complexity and clutter… to sustain a fictive status symbol" — [Ted Merz](https://ted-merz.com/2021/06/26/amber-on-black/)). Keep the density, the tabular mono, the short caps headers; drop the amber-everything and the borders-around-everything.

---

## 7. The palette — tokens, justification, contrast

All ratios are WCAG 2.x relative-luminance ratios, computed from the hex values (script in `tokens.obsidian.json`). "on panel" is the number that matters most: it is where the rows live.

### Surfaces

| Token | Hex | Why | Contrast |
|---|---|---|---|
| `canvas` | `#0A0C12` | Cool near-black, L\* 3.4; not `#000` (smear, flat shadows); hue of the navy | — |
| `panel` | `#12151D` | First step up, L\* 6.8; the card | 1.07:1 vs canvas (the hairline + edge carry the boundary) |
| `raised` | `#1C202B` | Second step, L\* 12.3; pills, secondary buttons, hover | 1.12:1 vs panel |
| `hairline` | `#FFFFFF14` (white 8% → `#1D1F25`) | Alpha so the same line reads on panel, wash and glass | decorative, 1.19:1 |
| `hairline-2` | `#FFFFFF24` (white 14% → `#2D2E33`) | The stronger divider: table heads, pill borders | decorative, 1.44:1 |
| `shadow` | `#0000009E` (62%) | Dark shadows need weight to register at all | — |

### Ink

| Token | Hex | Why | on canvas / panel / raised |
|---|---|---|---|
| `text` | `#E8E3D8` | Warm off-white; reads as white, does not halate; continuous with Night's `#E1DDD2` and Broadcast's cream | **15.3 / 14.3 / 12.7** |
| `muted` | `#ABA9A1` | Warm mid-grey; ≥ 7:1 everywhere opaque, so it survives halation | **8.3 / 7.8 / 6.9** |
| `dim` | `#909298` | Cool-neutral tertiary (labels, "proj", timestamps); ≥ 4.5:1 on every surface *and* every wash | **6.3 / 5.9 / 5.2** (4.7 on wash-hot) |
| `slate` | `#909298` | alias of dim | — |
| `nav-text` | `#E8E3D8` | same ink on the chrome | 14.8 on nav |

### The accent

| Token | Hex | Why | on canvas / panel / raised |
|---|---|---|---|
| `gold` | `#F2B722` | Unchanged; text-safe on obsidian, so gold text is permitted (times, Δ, hot) | **10.8 / 10.1 / 9.0** |
| `rule` | `#F2B722` | The attention rule; same hex as gold in this theme | 10.8 as a line |
| `chip-ink` | `#101B33` | Navy ink on the gold fill — the navy survives here and in the mark's plate | **9.4 on chip-start** |

### Verdicts (weight, not colour)

| Token | Hex | Why | Contrast |
|---|---|---|---|
| `chip-start` | `#F2B722` | Solid fill. The one thing allowed to be loud | ink 9.4:1 |
| `chip-sit` | `#6A6E77` | Ghost outline, lifted from Night's `#34497A` so the boundary meets the 3:1 non-text floor on every surface | **3.8 / 3.6 / 3.2** vs canvas / panel / raised |
| `chip-lean` | `#F2B722` | Dashed gold | 10.1 on panel |
| `chip-none` | `#3C3F49` | Deliberately recessive: not a control, not a verdict | 1.7 (intentional) |
| `mint` | `#9DBBF3` | "positive" = ink-blue, never green | 9.4 on panel |
| `coral` | `#BDB0A0` | "negative" = stone, never red | 8.6 on panel |

### Washes (tints over panel; text ≥ 11:1 and muted ≥ 6:1 on all five)

| Token | Hex | Recipe | text / muted / gold |
|---|---|---|---|
| `wash-hot` | `#2D281E` | gold 12% over panel | 11.5 / 6.2 / 8.1 |
| `wash-split` | `#24221D` | gold 8% over panel | 12.4 / 6.8 / 8.8 |
| `wash-cold` | `#1B1E26` | white 4% over panel | 13.0 / 7.1 |
| `wash-good` | `#141E32` | ink-blue 16% over panel | 13.0 / 7.1 |
| `wash-bad` | `#212125` | stone 14% over panel | 12.5 / 6.8 |

### Chrome and meters

| Token | Hex | Why |
|---|---|---|
| `nav` | `#0E1118` | The glass base colour (`rgba(14,17,24,…)`) and the opaque fallback for the web header. In app mode the native Liquid Glass bar is the chrome; the page's own bar is hidden |
| `nav-raised` | `#21242A` | white 8% over nav (the league switcher's selected segment) |
| `nav-line` | `#303238` | white 14% over nav |
| `meter-hi` | `#F2B722` | gold pips |
| `meter-mid` | `#E8E3D8` | ink pips |
| `meter-lo` | `#3A3E48` | off pips (rendered at 45% opacity anyway); the ON pips carry the value |

**On the navy bar rule.** `ui.py` says "the top bar is navy in BOTH themes." In Obsidian the top bar is *Apple's* — a Liquid Glass header the page does not paint — so the navy survives as `chip-ink` (the ink on every START chip) and as the plate behind the gold diamond in the mark, which is where the identity actually lives. If the web header must still render (Safari / PWA), `nav #0E1118` is the obsidian bar and the diamond-on-navy badge sits on it. This is the one identity decision the owner should confirm.

---

## 8. The glass surface recipe

Exact CSS is in `tokens.obsidian.css`. The shape of it:

```css
/* Level 1 - content card. NOT glass. */
.wr-card { background: var(--wr-panel); border: 1px solid var(--wr-hairline);
           box-shadow: inset 0 1px 0 rgba(255,255,255,.06); border-radius: 14px; }

/* Level 2 - floating over content: sticky group headers, verb bar, popovers. */
.gt-glass {
  background: rgba(14,17,24,.72);
  -webkit-backdrop-filter: blur(20px) saturate(140%); backdrop-filter: blur(20px) saturate(140%);
  border: 1px solid rgba(255,255,255,.07);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.16),   /* the top edge that sells 'glass' */
              inset 0 -1px 0 rgba(0,0,0,.35),        /* bottom edge drops into shadow  */
              0 8px 24px rgba(0,0,0,.45);            /* separation from what's beneath */
  border-radius: 16px;
}

/* Level 3 - sheets and menus: thicker. Muted text allowed here, not on Level 2. */
.gt-glass-thick { background: rgba(14,17,24,.84); backdrop-filter: blur(28px) saturate(140%);
                  box-shadow: inset 0 1px 0 rgba(255,255,255,.16), inset 0 -1px 0 rgba(0,0,0,.35),
                              0 16px 40px rgba(0,0,0,.55); border-radius: 20px; }

/* Pressed: illuminate from within (a lift in the fill), never a glow. */
.gt-glass:active { box-shadow: inset 0 0 0 999px rgba(255,255,255,.06), inset 0 1px 0 rgba(255,255,255,.16); }

/* Attention on glass = the gold rule. */
.gt-glass.gt-attn { border-top: 2px solid var(--wr-rule); }
```

The four numbers that matter, and why:

- **Fill `.72` / `.84`.** Below ≈ 0.65 the bar disappears against busy rows (the iOS 26 beta-1 Control Center problem). 0.72 is the point where cream text stays ≥ 8:1 with a gold chip directly beneath; 0.84 is where *muted* text stays ≥ 5.5:1, so that is the sheet value.
- **Blur `20px` / `28px`.** Enough to turn a passing gold chip into a warm bloom rather than a legible shape (a bar that shows readable text through it is a bar that fights the text on it). Apple's "bigger is thicker" rule is why the sheet gets the larger radius.
- **Edge-top `white 16%`.** The 1px highlight is what separates "glass" from "a dark grey rectangle at 72%." Resolved over the nav base it is `#35373D`, a line the eye reads as a lit edge without registering as a border. The all-round border stays much fainter (7%) so the top edge is the *only* lit edge — light comes from above.
- **Shadow `0 8px 24px @ .45`.** Dark ground eats shadows; paper's 8% shadow (`#101B3314`) would be invisible. Floating things get one; Level-1 cards get none — a shadow under an opaque card on near-black is just mud around the card.

`saturate(140%)` gives the gold passing under the glass its warmth; without it the blur of gold over blue-black greys out.

**Accessibility modifiers, mirrored from Apple's** (Reduce Transparency "makes Liquid Glass frostier"; Increase Contrast "highlights them with a contrasting border"): `prefers-reduced-transparency` → fill 0.96, no blur; `prefers-contrast: more` → 50% white border, muted/dim/chip-sit lifted. Both are in the CSS file.

---

## 9. Five "do not" rules

1. **Do not paint glass on the content layer, and never glass on glass.** Cards, rows, tables and the Trade Desk grid are opaque panels on the ladder. Only things that content scrolls *under* get `backdrop-filter`, and a glass element never contains another. (Apple: "best reserved for the navigation layer… always avoid glass on glass.")
2. **Do not glow. Do not gradient.** No outer glow on any element, active tab, chip or button — the pressed state is an inset lift, attention is a 2px gold rule. No gradient fills anywhere; the ground is flat `#0A0C12`, not a radial vignette.
3. **Do not use `#000` or `#FFF`.** Canvas is `#0A0C12` (OLED smear, dead shadows); ink is `#E8E3D8` (halation). A white block or a white photo frame on this ground is a flashlight; wrap media in a `raised` frame with a hairline.
4. **Do not spend gold twice on one screen.** Gold fills = START chips + at most one primary verb. A second gold button, a gold-tinted tab bar, gold rings on avatars, gold hairlines on every card — any of these and the START chip stops being the verdict. Gold *text* is for numbers and times only.
5. **Do not put muted text on Level-2 glass, and do not dim below the floor.** Floating glass carries primary text and gold; anything with secondary copy is a Level-3 sheet at 84%. On opaque surfaces the tiers are fixed at ≥ 7:1 (`muted`) and ≥ 4.5:1 (`dim`) against *every* surface and wash — a token that fails on `wash-hot` fails, full stop.

---

## 10. Handoff notes for the shell build (observations, not edits)

Seen while reading `ios/` for context; the other build owns these.

- `WebView.swift` sets `contentInsetAdjustmentBehavior = .never` and `MainView.swift` gives the root a solid `Brand.navy` background. For Apple's tab-bar glass to have anything to refract, the web content must extend *under* the bar (automatic insets, or a bottom safe-area padding on the page and a transparent scroll view). With `.never` and an opaque navy ground, the native glass will sit over flat navy and read as a plain dark bar.
- `.tint(Brand.gold)` on the TabView is the right single tint; do not also tint the bar's glass or the header.
- The webview background (`Brand.uiGround` → `#0D1730` in dark) should become the obsidian canvas when `data-theme="obsidian"` is active, or the first frame flashes navy behind obsidian pages.
- If Obsidian becomes the app-mode default, `prefs.py`'s `_NIGHT_TUNE` logic (warm ink in both dark states) already points the same direction; Obsidian can be a third `data-theme` value validated against `ui.TOKEN_NAMES` exactly as `_BROADCAST` is.

---

## Sources

- Apple, *Meet Liquid Glass* (WWDC25 session 219, transcript) — https://developer.apple.com/videos/play/wwdc2025/219/
- Apple designers, WWDC25 design group lab transcript (Sam Henri Gold gist) — https://gist.github.com/samhenrigold/2da3acec094ed339a82155583c1ab293
- Apple HIG, Dark Mode (base vs elevated backgrounds), summarised by Median — https://median.co/blog/what-are-apples-human-interface-guidelines-for-dark-mode ; original https://developer.apple.com/design/human-interface-guidelines/dark-mode
- Apple HIG, Materials — https://developer.apple.com/design/human-interface-guidelines/materials
- iOS system colour values (dark): Sarunw, *Dark color cheat sheet* — https://sarunw.com/posts/dark-color-cheat-sheet/
- Six Colors, *iOS 26 review: Through a glass, liquidly* (adaptive light/dark flipping, inconsistency) — https://sixcolors.com/post/2025/09/ios-26-review-through-a-glass-liquidly/
- MacRumors, *How the iOS 26.1 transparency toggle changes Liquid Glass* — https://www.macrumors.com/2025/10/20/ios-26-1-transparency-option-liquid-glass/
- AppleInsider, *iOS 26 review one year later* (beta-1 Control Center legibility, transparency reduced) — https://appleinsider.com/articles/26/05/08/ios-26-review-one-year-later-liquid-glass-complaints-hide-the-real-problem
- AnotherApple, *The correct way to use dark mode with Liquid Glass* (Tinted in dark) — https://www.anotherapple.com/2026/04/the-correct-way-to-use-dark-mode-with-liquid-glass/
- Pocket-lint, *Ultra dark mode on iOS 26* — https://www.pocket-lint.com/how-to-get-ultra-dark-mode-on-ios-26/
- Vidit Bhargava, *Designing a Dark Theme for OLED iPhones* (LookUp; RGB(5) vs black, smearing) — https://medium.com/lookup-design/designing-a-dark-theme-for-oled-iphones-e13cdfea7ffe ; via MacStories https://www.macstories.net/linked/designing-a-dark-theme-for-oled-iphones/
- XDA, *AMOLED black does not save more battery than dark gray* — https://www.xda-developers.com/amoled-black-vs-gray-dark-mode/
- Material Design, *Dark theme* (#121212 rationale) — https://m2.material.io/design/color/dark-theme.html
- Shaban Rasheed, *Dark mode done right: contrast, depth and legibility* — https://shabanrasheed.com/writing/dark-mode-done-right
- ColorContrast, *Dark mode contrast guide* (halation, floors, saturated-accent failures) — https://www.colorcontrast.org/blog/dark-mode-contrast-accessibility-guide/
- Muzli, *Dark mode design systems* (5–8% luminance steps, off-white range) — https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/
- The Skins Factory, *Why your dark mode looks bad* — https://www.theskinsfactory.com/uiux-design-blog/why-your-dark-mode-looks-bad-ui-ux-guide
- Supercharge Design, *6 mistakes to avoid in dark UI design* — https://supercharge.design/articles/6-mistakes-to-avoid-in-dark-ui-design
- RAXXO, *Dark mode design that doesn't look AI* (neon-on-dark tell) — https://raxxo.shop/blogs/lab/dark-mode-design-that-doesnt-look-ai
- CSS Studio, *Glassmorphism in CSS* (top-edge highlight + inset recipe) — https://css-studio.com/blog/glassmorphism-css-guide
- CSS Top Sites, *Glassmorphism dark backgrounds* (fill/blur/border ranges, don't nest) — https://csstopsites.com/glassmorphism-dark-backgrounds
- Colorffy, *CSS glassmorphism effects* — https://blog.colorffy.com/css-glassmorphism-effects
- Northville Tech, *Robinhood dark mode* (deep dark grey, no true-black toggle) — https://www.northvilletech.com/blog/how-to-enable-dark-mode-in-robinhood/
- DesignMD, *Robinhood design tokens* — https://www.designmd.co/d/robinhood
- Curio, *Bloomberg Terminal style guide* (near-black ground, density, mono) — https://designbycurio.com/learn/bloomberg-terminal-green
- Ted Merz, *Amber on Black* — https://ted-merz.com/2021/06/26/amber-on-black/
- Bloomberg UX, *Designing the Terminal for color accessibility* — https://www.bloomberg.com/ux/2021/10/14/designing-the-terminal-for-color-accessibility/
- Underdog reviews (black/yellow register): Saturday Down South — https://www.saturdaydownsouth.com/dfs/underdog-fantasy/review/ ; Strafe — https://www.strafe.com/esports-betting/reviews/underdog/app/
- Sleeper (dark-first UI, mixed on discoverability): Gridiron.ai review — https://sleeperdynasty.com/blog/sleeper-app-fantasy-football-review-2025 ; JustUseApp reviews — https://justuseapp.com/en/app/987367543/sleeper-fantasy-leagues/reviews
