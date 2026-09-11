# Multi-hue on obsidian, done well

Status: research + rules, 2026-09-10. Written against `design/obsidian/SPEC.md` as it stood tonight (ground `#0A0C12`, cream ink, gold `#F2B722` as the one accent, glass on controls only, verdicts weight-encoded). Nothing under `design/obsidian/`, `engine/` or `ios/` was touched. Companion: `verify_multihue.py` in this folder reproduces every number below; rerun it on any token edit.

The owner's direction, read as three rules: **more colour, used intuitively** (colour that means something the user already knows); **one text scale everywhere**; **colour may differ across pages and across the app**. The standing constraints stay: obsidian ground, glass on controls only, verdict chips keep their weight encoding, WCAG AA on every text/ground pair, the honesty banner unmissable, sources are faces.

The one-sentence version: **hue lives in three tiers on obsidian — pastel ink (L ≥ 0.76), deep wash (L ≤ 0.30), and a glow in the ground — and never in the band between, which is where the casino lives.** The cream/muted/dim text scale never takes a hue. Each hue has exactly one meaning app-wide. A screen shows at most one identity hue plus the category hues its objects carry.

---

## 0. The rules (the short form)

| # | Rule | Why (evidence in §) |
|---|---|---|
| 1 | **The text scale is untouchable.** `text` / `muted` / `dim` / `nav-text-2` stay cream-grey on every page. Hue is carried by *objects* — codes, dots, rings, rules, fills, glows — never by sentences, ledes, labels or kickers. | §2, Apple HIG Dark Mode, Material "on" colours |
| 2 | **One hue, one meaning, app-wide.** Position hues mean positions on every page. A hue is never re-used for a second meaning, even on a different page. | Apple HIG Color ("Avoid using the same color to mean different things"), Bloomberg |
| 3 | **Three tiers, no middle.** Pastel ink tier OKLCH L 0.76–0.84, C ≤ 0.13 (one hex serves as coloured text *and* as a fill under navy ink). Wash tier L 0.24–0.30, C ≤ 0.05 (cream text on it). Glow tier: the hue at L 0.55 C 0.10 at ≤ 30 % in the native ground. **Nothing is drawn as a fill at L 0.45–0.65** — no text colour passes 4.5:1 on it. | §2.2 (the dead-zone table) |
| 4 | **Lightness up, chroma down.** Every dark-mode hue is the light-mode hue lifted ~0.15 in L and cut ~30 % in chroma. Saturated mid-tones vibrate on black and fail AA. | §4, Material, Apple's own Increase-Contrast variants, Sleeper's dark tokens |
| 5 | **One identity hue per screen; everything else neutral or category.** Identity = the page's glow in the ground + the selected tab glyph. It comes *from the vocabulary* (gold, the league's brand hue, ink-blue, stone), never a new hue per page. | §1, Apple Settings/Health/Fitness, Linear, Raycast |
| 6 | **Cap: seven hue-meanings in the vocabulary; on any one screen, gold plus at most two category *families*** (e.g. positions and a signed delta), so the distinct swatches visible never exceed seven (gold + four positions + ink-blue + the once-per-screen league dot). Beyond that, encode by weight, glyph or text. | §3, Datawrapper's seven, Refactoring UI, Material "limited color accents" |
| 7 | **Coloured fills are small and short.** A hue fill is ≤ 24 px tall and never a row or a card; it carries navy ink `#101B33`. Cream text never sits on a hue fill (it fails). | §2.3, §5 |
| 8 | **Glass is never tinted by a page.** The bars keep the single gold `.tint`. Coloured content that can scroll under a bar relies on the scroll edge effect; without it, cream on glass over a pastel chip is 3.7–5.3:1. | §5, WWDC25 "Meet Liquid Glass" |
| 9 | **Weight still beats hue for anything ordinal or evaluative.** Verdicts, injury status, urgency, matchup grade stay weight-encoded. Hue is for *nominal* categories the user already colour-codes in their head (positions, leagues, the brand). | §7, owner's first reaction |
| 10 | **Greyscale still reads.** Every hue is redundant with a code, glyph, ring or position. Rerun the greyscale check with the contrast check. | WCAG 1.4.1, Apple HIG Color |

---

## 1. The page-identity pattern — what the reference products actually do

The question was: how do dark apps give each section a hue so you know where you are, without becoming a rainbow? The answer in every product studied is the same shape: **the identity hue is applied to one or two small things, and the surface stays dark.**

| Product | Where the hue sits | What stays neutral | The rule that holds it together |
|---|---|---|---|
| **Apple Fitness / Health** (dark-only) | The ring or the category glyph; in Activity "each infographic view for the Move, Exercise, and Stand Activity rings has a background that matches the color of the ring" — a background *derived from the data*, not decoration. In Health, a favourited metric's title "will match the category color" (Heart red, Activity orange, Sleep teal…). | Body text, list labels, the black ground, the tab bar. | One hue per category, fixed for life; the hue is the *data's* hue. [HIG Color](https://developer.apple.com/design/human-interface-guidelines/color), [TechWiser on Health](https://techwiser.com/what-icons-and-symbols-mean-on-apple-health-app-complete-guide/) |
| **Apple Stocks** (dark-only) | A green or red pill on the change figure only; white numerals. Apple's own note that the meaning flips by locale ("Green indicates a positive trend in the Stocks app in English. Red indicates a positive trend in the Stocks app in Chinese") is the proof that "intuitive" colour is *learned convention*, not physics. | Everything else: `#000` ground, `#1C1C1E` cards, white/grey text. | Colour = one number's sign. [HIG Color](https://developer.apple.com/design/human-interface-guidelines/color), [HIG Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode) ("The Stocks app uses a dark-only appearance") |
| **iOS Settings icon grid** (observed, iOS 26; Apple does not document the mapping) | A tinted rounded square with a **white glyph** per row; the tint groups rows by family (radios blue/green, alerts red, focus/time indigo, system grey). | The row label — always the label colour; the chevron; the group background. | Hue on a 29 pt square, never on text. The white-glyph-on-tint recipe is exactly SF Symbols' monochrome rendering mode. [HIG SF Symbols](https://developer.apple.com/design/human-interface-guidelines/sf-symbols) |
| **Liquid Glass (iOS 26)** | "Tinting should only be used to bring emphasis to primary elements and actions in the UI." The selected tab glyph and the one prominent button. | The bars themselves: "By default, symbols and text on these elements follow a monochromatic color scheme." | "Avoid tinting all your elements. When every element is tinted, nothing stands out, and it can be confusing. If you want to imbue color into your app, do it in the content layer instead." [WWDC25 219](https://developer.apple.com/videos/play/wwdc2025/219/), [HIG Materials](https://developer.apple.com/design/human-interface-guidelines/materials) |
| **Linear** (2024 redesign) | Status dots and project/team icons carry hue; the whole theme is generated from "three: base color, accent color, and contrast" in LCH. | The chrome: they deliberately went *more* neutral, "limiting how much chrome (blue in our case) was used in the calculations applied to our color system", and lifted text: "making our text and neutral icons darker in light mode and lighter in dark mode." | One accent, computed elevations, hue on small status objects. [linear.app/now](https://linear.app/now/how-we-redesigned-the-linear-ui) |
| **Raycast** | Each extension's icon carries its own brand hue on an almost-black blue-tinted ground (`#07080A`); list text stays white/grey. Its API ships nine named colours ("Use those colors for consistency") that "automatically adapt to the Raycast theme", and any raw hex "will be adjusted to achieve high contrast with the Raycast user interface." | The list, the search bar, the action panel. | Platform-enforced lightness lift; hue is on icons, not on text. [Raycast Colors API](https://developers.raycast.com/api-reference/user-interface/colors) |
| **Spotify** | One accent (`#1ED760`) on the play button and "now playing"; the *page* identity is a gradient extracted from the album art, contrast-checked, fading into `#121212` — "If the dominant color is too dark against the #121212 background, it shifts toward a more vibrant variant." | `#121212` / `#181818` / `#282828` surface ladder; white and `#B3B3B3` text. | The page's hue is a *glow at the top*, derived from content; text never changes. [design guide](https://blakecrosley.com/guides/design/spotify) |
| **Bloomberg Terminal** | Amber for non-semantic text, a blue/red pair for up/down chosen for colour-vision deficiency ("stick with a blue and red color scheme for CVD-related information … while retaining the default Bloomberg amber color for non-semantic information"), monospace numerals. | The black ground. | "Color … is never decorative — every color assignment carries a fixed meaning"; "The palette is deliberately small: to expand it with additional colors is to dilute the semantic system." [Bloomberg](https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/), [Curio](https://designbycurio.com/learn/bloomberg-terminal-green), [Ted Merz](https://ted-merz.com/2021/06/26/amber-on-black/) |
| **Sleeper** (dark mode, live CSS) | Position hues on codes and draft-board tiles (`--color-dls-position-qb` … `-k`), one brand aqua (`--color-dls-primary-300 #00FFF9`) on links/icons, a per-league avatar. Ground `#05091D` — a near-black navy almost identical to our obsidian. | A 14-step grey ladder; text `#E6EAF0` / `#B7C5D4` / `#8996AA`. | Separate light and dark values per position (see §5); hue on ≤ 3-letter codes, never on names. [Sleeper CSS](https://sleepercdn.com/sleeper-web/_next/static/chunks/2b7avkr6fu8y5.css) (fetched 2026-09-10), [League Legend](https://support.sleeper.com/en/articles/4584482-league-legend) |
| **Robinhood** | The *whole* ground tints green or red with the portfolio ("the UI is a light green graph on a green background"), and "after trading hours, the background shifts from white to a dusky grey." | Everything else is black/white. | One state, one full-bleed hue. The most colourful of the set — and the one the owner's instinct rejects for verdicts. [Google Design](https://design.google/library/robinhood-investing-material) |

**The pattern, extracted.** Identity is (a) a hue on *one small object* — a glyph, a ring, a dot, a pill on a number — and/or (b) a *glow* in the ground that fades to the base within the first screen; never (c) a tinted bar, a tinted card, or tinted body text. The rule that stops the rainbow is that the identity hue comes from a *fixed vocabulary with fixed meanings*, and the surface + text stay one neutral ladder. Robinhood is the outlier (full-bleed) and it works only because the whole app has exactly one variable.

### 1.1 Applying it to Graded Takes

No page gets an invented hue. Each page's identity is drawn from the vocabulary in §7, by what the page is *about*:

| Page | Identity glow (light 2 in the native ground, ≤ 30 %) | Selected tab glyph | Category hues on the page |
|---|---|---|---|
| **Home** | gold (the brand; decisions) — as today | gold (the single `.tint`) | positions on roster rows (4) |
| **Lineup** | none — light 1 only; the positions are the colour | gold | positions on slot rows (4) |
| **Board** | gold — same room as Home | gold | positions in the card header |
| **Model** | the ink-blue hue of `mint #9DBBF3` (263°; glow `#5270AC` at ≤ 30 %) — the reader's model is "the blue room", and ink-blue is already the positive/graded hue | gold | none; sources are faces, categories are glyphs (§7) |
| **Sources / Receipts** | ink-blue, same as Model (Receipts fold into it) | gold | none; HOT/COLD by the gold end-dot vs `dim` (§7) |
| **Trade Desk** | the *league's* brand hue (ESPN coral, Yahoo violet, Sleeper aqua) — the one page that is about the league, so the room takes the league's colour | gold | positions in the needs matrix (4); the league dot |
| **Ledger** | the stone hue of `coral #BDB0A0` (73°; glow `#956724` at ≤ 30 %) — paper, the past | gold | none |
| **Onboarding** | gold | — | the league dot on the detected league |

Kept as-is: the tab bar's single gold tint (§6 says why the bars never take a page's hue). The glow is the only thing that says "this room is blue"; the moment a second element on the screen takes the identity hue for decoration, the rule is broken.

---

## 2. Readable text on dark with coloured surroundings

### 2.1 The text scale stays constant

Every product in §1 keeps one neutral text ladder while hue moves around it. Material: `"On" colors are primarily applied to text … By default, dark theme "on" colors are white and black`, at "87 % / 60 % / 38 %" emphasis. Apple: "Use the system-provided label colors for labels." Linear lifted text lighter in dark and *removed* blue from the neutrals. Sleeper's dark text ladder is `#E6EAF0` / `#B7C5D4` / `#8996AA` with position hue only on the code.

For Graded Takes the ladder is already right and does not move: `text #E8E3D8` (OKLCH L 0.92), `muted #ABA9A1` (L 0.73), `dim #909298` (L 0.66), `nav-text-2 #C9C5BC` on glass. The additions:

- **Hue may be text only for ≤ 3-character codes and numerals** at 11 px 700 or larger: `QB` `RB` `WR` `TE`, and the gold numerals the spec already allows. Names, reasons, ledes, kickers, group heads, meter labels stay cream/muted/dim — the spec's list in §5.6 stands.
- **A hue never appears as a word.** "HOT", "ESPN", "SMASH" are cream; the hue rides on a dot, ring or glyph beside the word.

### 2.2 The three tiers, with the numbers

Contrast is WCAG 2.x relative luminance ([W3C definition](https://www.w3.org/TR/WCAG22/#dfn-relative-luminance)); thresholds are [1.4.3](https://www.w3.org/TR/WCAG22/#contrast-minimum) 4.5:1 text and [1.4.11](https://www.w3.org/TR/WCAG22/#non-text-contrast) 3:1 non-text. Grounds are the spec's: `canvas #0A0C12` (Y 0.0037), `panel #12151D` (0.0075), `raised #1C202B` (0.0145), the brightest ground pixel under light 1 `#2A3145` (0.0312), and the 78 % card over that pixel `#171B26` (0.0111). Ink on a fill is `chip-ink #101B33` (0.0113).

**What a text colour must reach (relative luminance Y):**

| Sits on | 4.5:1 needs Y ≥ | 7:1 needs Y ≥ | 3:1 non-text needs Y ≥ |
|---|---|---|---|
| canvas | 0.192 | 0.326 | 0.111 |
| panel | 0.209 | 0.353 | 0.123 |
| raised | 0.240 | 0.402 | 0.144 |
| card over the brightest ground pixel | 0.225 | 0.377 | 0.133 |
| the bare brightest ground pixel | **0.315** | 0.518 | 0.194 |

**Tier A — pastel ink / chip (one hex, two jobs).** OKLCH L 0.76–0.84, C ≤ 0.13 (warm hues may go to C 0.16 at L ≥ 0.72). Checked at every 15° of hue:

| L / C | as text on the bare brightest ground | as text on any card | as a fill under navy ink | out of sRGB gamut at |
|---|---|---|---|---|
| 0.72 / 0.12 | ≥ 4.9 | ≥ 6.5 | ≥ 6.5 | — |
| **0.76 / 0.12** | **≥ 5.7** | **≥ 7.6** | **≥ 7.5** | — |
| 0.80 / 0.11 | ≥ 6.6 | ≥ 8.7 | ≥ 8.7 | blues 255–285° |
| 0.84 / 0.11 | ≥ 7.5 | ≥ 10.0 | ≥ 10.0 | reds and blues (pastel only) |

So the floor is **L 0.76**: AA everywhere including the bare ground, 7:1 on every card, and the *same swatch* is a legal fill with navy ink. (Gold `#F2B722` is L 0.81 C 0.16; ink-blue `#9DBBF3` is L 0.79 C 0.09; stone `#BDB0A0` is L 0.76 C 0.03 — the existing accents already live here.)

**Tier B — wash.** OKLCH L 0.24–0.30, C ≤ 0.05. A tinted *surface* under the normal text ladder: cream ≥ 10.4:1, muted ≥ 5.7:1, dim ≥ 4.3:1 at L 0.30; at L 0.27 cream 11.6 / muted 6.3 / dim 4.8. The spec's `wash-hot` (L 0.28) and `wash-good` (L 0.24) already are this tier. A wash never carries a meaning on its own (it is 1.3:1 against canvas, below the 3:1 non-text floor) — it accompanies a code or a rule.

**Tier C — glow.** The hue at L 0.55 C 0.10, painted at ≤ 30 % as light 2 in the native ground. Composited, the brightest pixel it makes is `#37222F`-class (Y ≈ 0.022), *below* the spec's worst-case `#2A3145` (0.031), so every number in SPEC §11 still holds. If a glow is ever pushed brighter than 30 %, rerun the worst-pixel check.

**The dead zone — L 0.45–0.65 as a fill.** Nothing passes on it:

| fill L (C 0.12, worst hue) | cream text on it | navy ink on it |
|---|---|---|
| 0.45 | 5.5 | 2.2 |
| 0.50 | 4.4 | 2.7 |
| **0.55** | **3.6** | **3.3** |
| 0.60 | 2.9 | 4.1 |
| 0.65 | 2.4 | 5.0 |
| 0.70 | 2.0 | 6.0 |

This band is where "generic" UI colour lives: ESPN red `#FF0033` (Y 0.215), Apple's *default* dark red/pink/indigo/blue (Y 0.25–0.28: 4.7–5.3 with navy, 2.3–2.8 with cream), Material's dark error `#CF6679` (Y 0.24). It is the band the eye reads as "casino" — mid-lightness, high-chroma blocks that neither recede nor read. **Never draw a fill in it on obsidian.** As *text*, the band fares no better on the bright ground pixel: Apple's default dark blue `#0091FF` is 6.0:1 on canvas but **4.0:1** on `#2A3145`.

### 2.3 Coloured fill with dark text, or coloured text on dark?

| Use a **fill with navy ink** when | Use **coloured text / outline / dot** when |
|---|---|
| the object must be the loudest thing in its row (the START chip is the only case today; a second fill competes with it) | the hue is a *label*, not a call to action — position codes, league dots, rings |
| the object is ≤ 24 px tall and ≤ ~4 characters | the hue must survive being tiny (a 6 px dot, a 1.5 px ring) — pastel ink at L ≥ 0.76 is ≥ 5.7:1 even on the bare ground |
| the fill is Tier A (L ≥ 0.72) — never mid-lightness | the text is a code or numeral (never a word) |

The fill-with-dark-ink form is the Settings-icon recipe: tint on a small square, monochrome glyph inside, neutral label beside. The coloured-text form is Bloomberg's: mono numerals and short codes in a small fixed palette on black. Both keep the sentence in the neutral ladder.

Cream text on a hue fill is not a third option: to pass 4.5:1 under cream a fill must be ≤ Y 0.132 (L ≈ 0.50 at C 0.05 — a *wash*), and under 7:1 ≤ Y 0.067. So "cream on colour" only exists as cream on a wash, which is Tier B.

---

## 3. How many hues before it breaks

Evidence, strongest first:

- **Apple HIG Color:** "Consider choosing a limited color palette that coordinates with your app logo. Subtle use of color can help you communicate your brand while deferring to the content." And on Liquid Glass: "Apply color sparingly … Refrain from adding color to the background of multiple controls." [link](https://developer.apple.com/design/human-interface-guidelines/color)
- **WWDC25:** "When every element is tinted, nothing stands out." [link](https://developer.apple.com/videos/play/wwdc2025/219/)
- **Material dark theme:** "Large surfaces use a dark surface color, with limited color accents (light, desaturated and bright, saturated colors)"; "Reserve bright colors for smaller surfaces"; "Don't use bright colors for large surfaces because they can emit too much brightness." [link](https://m2.material.io/design/color/dark-theme.html)
- **Refactoring UI:** greys (8–10 shades), "one, maybe two" primaries, then accents "used sparingly" for semantic states and to "distinguish or categorize similar elements" — the category accents are a *separate, bounded* set from the primary. [link](https://refactoringui.com/previews/building-your-color-palette)
- **Datawrapper (Lisa Charlotte Muth):** "try to avoid using more than seven of them. The more colors in a chart represent your data, the harder it becomes to read it quickly." [link](https://www.datawrapper.de/blog/colors)
- **Bloomberg:** a deliberately small palette; adding colours "dilutes the semantic system." [link](https://designbycurio.com/learn/bloomberg-terminal-green)
- **Sleeper in practice:** five position hues + one brand aqua + a grey ladder; K is already a near-neutral (`#B7C1EE`, C 0.06) and DEF a burnt orange used only on the draft board.

**The cap for Graded Takes: seven hue-meanings in the vocabulary; on one screen, gold plus at most two category families.** Vocabulary: gold (brand, attention, START), rose (QB), mint-green (RB), cyan (WR), apricot (TE), ink-blue (positive / the model), stone (negative / the past). The three league brand hues sit outside the count because each appears once per screen as a dot and only one league is ever on screen. K and DST get *no* hue — they are `dim`, the way Sleeper makes K a near-neutral; special teams being grey is a convention the audience already holds.

Why two families: a Lineup screen already shows the four position codes across its rows, gold on the START chips, an ink-blue delta and the league dot — seven distinct swatches, Datawrapper's ceiling. A third family (streak hues, source-category hues) on the same screen would push it past seven, which is exactly why §7 gives those elements glyphs and weight instead of hue. Any single row carries at most one code and one chip.

---

## 4. Desaturation on dark — why, and by how much

**Why saturated hues vibrate on black.** Three mechanisms, each cited:

1. **Luminance is not lightness.** WCAG's Y weights the channels 0.2126 R / 0.7152 G / 0.0722 B ([W3C](https://www.w3.org/TR/WCAG22/#dfn-relative-luminance)). A fully saturated blue can never exceed Y 0.072 — it fails 4.5:1 on *every* obsidian surface no matter how "bright" it looks — and a saturated red tops out at Y 0.21. Only yellows and cyans reach text luminance while saturated. That is why Sleeper's WR shifts from blue `#0055FF` (hue 263°) in light mode to cyan `#00D7FF` (218°) in dark, and why Apple's dark blue must go pastel to pass.
2. **Chromostereopsis.** "When red and blue are viewed side by side on a dark surrounding, most people will view the red as 'floating' in front of the blue" — saturated complementaries on black appear at different depths, which reads as shimmer. [Wikipedia](https://en.wikipedia.org/wiki/Chromostereopsis)
3. **The dilated pupil and halation.** In dark interfaces the pupil opens and optical aberrations grow; light strokes on black bloom for astigmatic readers (roughly one in three). [NN/g](https://www.nngroup.com/articles/dark-mode/), [accessibilitychecker](https://www.accessibilitychecker.org/blog/dark-mode-accessibility/). High-chroma strokes bloom hardest because the bloom is a different colour from the ground.

Material says it plainly: "A dark theme should avoid using saturated colors, as they don't pass WCAG's accessibility standard of at least 4.5:1 for body text against dark surfaces. Saturated colors also produce optical vibrations against a dark background, which can induce eye strain." And the prescription: "use lighter tones (200–50) in dark theme, rather than your default color theme (saturated tones ranging from 900–500)." Apple's HIG Dark Mode: "The color palette in Dark Mode includes dimmer background colors and brighter foreground colors."

**How much, measured** (OKLCH; Apple's values are its published "Increased contrast (dark)" variants — the ones it ships when a user asks for legibility):

| Colour | default dark | → accessible dark | ΔL | ΔC | on `#2A3145` before → after |
|---|---|---|---|---|---|
| Apple blue | `#0091FF` L .65 C .19 | `#5CB8FF` L .76 C .14 | +.11 | −30 % | 4.0 → 6.0 |
| Apple indigo | `#6D7CFF` L .64 C .19 | `#A7AAFF` L .77 C .12 | +.13 | −37 % | 3.7 → 6.1 |
| Apple purple | `#DB34F2` L .66 C .28 | `#EA8DFF` L .78 C .18 | +.12 | −35 % | 3.6 → 6.0 |
| Apple pink | `#FF375F` L .66 C .23 | `#FF8AC4` L .78 C .16 | +.12 | −33 % | 3.7 → 6.0 |
| Apple red | `#FF4245` L .66 C .23 | `#FF6165` L .70 C .19 | +.04 | −14 % | 3.8 → 4.4 (still short of 4.5 — red is the hardest hue) |
| Sleeper QB | light `#D54033` L .59 | dark `#FF6482` L .71 | +.12 | ≈ same | 2.8 → 4.6 |
| Sleeper WR | light `#0055FF` L .53 h 263° | dark `#00D7FF` L .81 h 218° | +.28 | −44 % | 2.3 → 7.5 (hue moved 45° toward cyan) |
| Sleeper K | light `#644AF7` L .55 C .24 | dark `#C96CFF` L .70 C .22; draft tile `#B7C1EE` L .82 C .06 | +.15 / +.27 | −10 % / −74 % | 2.4 → 4.4 / 7.3 |

Source values: [Apple HIG Color specifications](https://developer.apple.com/design/human-interface-guidelines/color) (June 2025 table), [Sleeper CSS](https://sleepercdn.com/sleeper-web/_next/static/chunks/2b7avkr6fu8y5.css).

**The rule that falls out:** take the light-mode hue, lift L by 0.12–0.15 and cut chroma by roughly a third; if the hue is a blue, also rotate it toward cyan (cyan is the only cool hue that reaches text luminance with chroma intact). The result lands in Tier A. Every candidate in §7 was built that way.

---

## 5. Glass and tint

How Liquid Glass takes colour, from Apple's own words:

- "By default, Liquid Glass has no inherent color, and instead takes on colors from the content directly behind it." ([HIG Color](https://developer.apple.com/design/human-interface-guidelines/color))
- Tinting is not a flat fill: "Selecting a color generates a range of tones that are mapped to content brightness underneath the tinted element … changing its hue, brightness and saturation depending on what's behind without deviating too much from the intended color." A solid fill instead "is completely opaque and breaks the visual character of Liquid Glass." ([WWDC25 219](https://developer.apple.com/videos/play/wwdc2025/219/))
- Where it goes: "To emphasize primary actions, apply color to the background rather than to symbols or text … Refrain from adding color to the background of multiple controls." ([HIG Color](https://developer.apple.com/design/human-interface-guidelines/color))
- Over colourful content: "Avoid using similar colors in control labels if your app has a colorful background … prefer a monochromatic appearance for toolbars and tab bars, or choose an accent color with sufficient visual differentiation." And: "Be aware of the placement of color in the content layer. Make sure your interface maintains sufficient contrast by avoiding overlap of similar colors in the content layer and controls … make sure its default or resting state — like the top of a screen of scrollable content — maintains clear legibility." ([HIG Color](https://developer.apple.com/design/human-interface-guidelines/color))
- The legibility machinery: the regular variant "blurs and adjusts the luminosity of background content"; "Scroll edge effects further enhance legibility by blurring and reducing the opacity of background content"; for clear glass over bright content "consider adding a dark dimming layer of 35 % opacity." ([HIG Materials](https://developer.apple.com/design/human-interface-guidelines/materials), [Adopting Liquid Glass](https://developer.apple.com/documentation/TechnologyOverviews/adopting-liquid-glass))
- Symbols on glass "flip from light to dark and vice versa, mirroring the glass's behavior to maximize contrast." Vibrant colours are the safe way to colour a symbol on a material: "Regardless of the material you choose, use vibrant colors on top of it." ([WWDC25 219](https://developer.apple.com/videos/play/wwdc2025/219/), [HIG Materials](https://developer.apple.com/design/human-interface-guidelines/materials))

**What happens to our text when glass sits over colour, computed** with the spec's stand-in glass `rgba(28,31,40,.52)` and cream `#E8E3D8` on it:

| content under the bar | cream on bare glass | with the 35 % dim beneath (≈ the scroll edge effect) |
|---|---|---|
| gold START chip `#F2B722` | **4.1 (fails)** | 6.8 |
| rose (QB) `#F496BB` | 4.6 | 7.2 |
| mint (RB) `#73D4AC` | **4.1 (fails)** | 6.7 |
| cyan (WR) `#73CBF0` | **4.1 (fails)** | 6.8 |
| apricot (TE) `#F7A97C` | **4.3 (fails)** | 6.9 |
| Sleeper aqua `#65E1E1` | **3.7 (fails)** | 6.3 |
| Yahoo violet `#BF93F1` | 4.9 | 7.6 |
| ESPN coral `#F8767A` | 5.3 | 8.1 |

So: any Tier-A fill that can scroll under a bar puts the bar's cream at 3.7–5.3, and five of the eight fail 4.5:1, unless the edge effect is beneath it. Rules:

1. **The bars keep the single gold tint and monochrome glyphs.** No page identity on glass, ever — the identity glow lives in the ground, *under* the content, where the glass can refract it the way Apple intends.
2. **`.scrollEdgeEffectStyle(.soft)` stays load-bearing** (SPEC §3) — now for colour as well as for gold.
3. **Hue fills ≤ 24 px tall** so no bar label ever sits *entirely* over one; a code in coloured text (not a fill) has no effect on the glass at all.
4. **A tinted glass control** (`.glassProminent`) exists once per screen and is gold — a second tinted control is the "every element is tinted" failure.
5. **Reduce Transparency / Increase Contrast** flatten the glow with the ground (SPEC §9); the Tier-A swatches were checked against the *flat* `#0A0C12` too (all ≥ 8.6:1).

---

## 6. The obsidian hue ranges (the spec sheet)

| Tier | OKLCH | Role | Ink on it | Floor proven |
|---|---|---|---|---|
| **A — pastel ink / chip** | L 0.76–0.84, C 0.09–0.13 (warm hues C ≤ 0.16 at L ≥ 0.72) | coloured codes and numerals; dots; rings; 2 px rules; small fills | as text: on any ground. As fill: `chip-ink #101B33` | ≥ 5.7 on the bare brightest ground, ≥ 7.5 on cards and under navy ink |
| **B — wash** | L 0.24–0.30, C 0.03–0.05 | tinted row/strip surfaces (accompanying a code or rule) | `text` ≥ 10.4, `muted` ≥ 5.7, `dim` ≥ 4.3 | at L 0.30; the spec's washes sit at L 0.24–0.28 |
| **C — glow** | L 0.55, C 0.10, drawn at ≤ 30 % as light 2 of the native ground | page identity | none directly — content cards sit over it | composite brightest pixel ≤ `#2A3145` |
| **forbidden** | L 0.45–0.65 as a fill; C > 0.16 anywhere; any hue as a word | — | — | see §2.2 dead zone |

**Candidate tokens** (all Tier A; hex is OKLCH snapped to sRGB; every ratio is the *minimum* over canvas / panel / raised / bare worst ground / card-over-worst; "ink" is navy on the swatch as a fill; ΔE is OKLab distance from gold — ≥ 0.10 reads as a different colour at chip size):

| token | hex | OKLCH | min text ratio | as fill, navy ink | ΔE vs gold | meaning |
|---|---|---|---|---|---|---|
| `pos-qb` | `#F496BB` | 0.78 / 0.12 / 355° | 6.1 | 8.1 | 0.20 | QB (Sleeper's rose family: `#FF80AD`) |
| `pos-rb` | `#73D4AC` | 0.80 / 0.11 / 165° | 7.2 | 9.6 | 0.18 | RB (Sleeper's draft tile `#49E8CC`) |
| `pos-wr` | `#73CBF0` | 0.80 / 0.10 / 228° | 7.1 | 9.4 | 0.25 | WR (Sleeper's `#49D0EE`) |
| `pos-te` | `#F7A97C` | 0.80 / 0.11 / 50° | 6.7 | 8.9 | **0.09** | TE (Sleeper's orange, pulled toward peach so it is not gold — see note) |
| `pos-k`, `pos-dst` | = `dim #909298` | — | 5.5 | — | — | special teams are grey (Sleeper's K is a C 0.06 near-neutral) |
| `league-espn` | `#F8767A` | 0.72 / 0.16 / 20° | 4.8 | 6.4 | 0.19 | ESPN's red, lifted (ESPN standardised "ESPN red" in 2026 after "two dozen shades"; [Marketing Brew](https://www.marketingbrew.com/stories/2026/03/09/espn-brand-identity)) |
| `league-yahoo` | `#BF93F1` | 0.74 / 0.14 / 305° | 5.3 | 7.1 | 0.29 | Yahoo purple `#6001D2` (hue 291°) lifted ([brandcolors](https://brandcolors.net/b/yahoo)) |
| `league-sleeper` | `#65E1E1` | 0.84 / 0.11 / 195° | 8.3 | 10.9 | 0.23 | Sleeper aqua `#00E1E0` (`--color-dls-primary-400`) |
| existing `gold` | `#F2B722` | 0.81 / 0.16 / 84° | 7.1 | 9.4 | — | brand, START, attention |
| existing `mint` | `#9DBBF3` | 0.79 / 0.09 / 263° | 6.7 | — | 0.29 | positive; the hue of the Model/Sources glow |
| existing `coral` | `#BDB0A0` | 0.76 / 0.03 / 73° | 6.1 | — | 0.14 | negative; the hue of the Ledger glow |

Pairwise separation among the four position hues: every pair ≥ 0.11 ΔE (closest: RB–WR 0.109, QB–TE 0.110). Collisions to keep apart by *placement*, not by hue (they never share a component): `pos-wr` ↔ `league-sleeper` 0.07 (a code vs a dot in the bar); `pos-k` would have collided with `league-yahoo` — which is one reason K is grey.

**Cross-reference.** `CONVENTIONS.md` (same folder, written in parallel) surveys what Sleeper, Underdog, FantasyPros, ESPN and Yahoo actually ship for these categories and proposes its own obsidian-tuned values (QB `#F06CC2`, RB `#3ED7C1`, WR `#6FB4FF`, TE `#FFA857`, K/DST `dim`). The two documents agree on the families and on K/DST being grey; they differ in two deliberate places — this document pulls WR toward cyan (228° OKLCH) so it cannot be confused with the ink-blue `mint` that already means "positive", and pulls TE toward peach so it sits farther from gold. Note the hue angles are in different spaces (CONVENTIONS.md quotes HSL, this document OKLCH). Whichever hexes the owner picks, they must sit inside Tier A (§6) and pass `verify_multihue.py`. Checked: CONVENTIONS' RB, WR and TE are inside Tier A (min text 7.2 / 5.9 / 6.8); its QB `#F06CC2` passes AA (4.7 on the worst ground, 6.2 under navy) but at OKLCH L 0.72 C 0.19 it is above the chroma cap and below the L 0.76 floor — the saturated-magenta band that vibrates — and should be lifted to about L 0.78 C 0.13 (which is `pos-qb` `#F496BB`, or the same hue at 343° if the survey's angle is preferred).

**The TE note.** Sleeper's TE is `#FFAB0E` — hue 73° in OKLCH, i.e. *our gold*. Keeping TE orange would make every TE code read as attention. The candidate pulls it to 50° (peach); ΔE from gold is 0.09 — legible as different beside a START chip, but the closest pair in the set. If it proves too close in the mockup, the alternative is TE = the existing stone `coral #BDB0A0` (ΔE 0.13; "the blocking position is the neutral one") and the owner should judge that by eye.

Wash and glow values for each hue are generated, not hand-picked: wash = same hue at L 0.27 C 0.04 (e.g. rose wash `#361E27`, cyan wash `#0E2A36`, ESPN wash `#381E1E`, Yahoo wash `#2B2136`, Sleeper wash `#082C2C`); glow = same hue at L 0.55 C 0.10 at ≤ 30 % (rose `#9F5774`, ESPN `#A45859`, Yahoo `#7F62A0`, Sleeper `#008384`; the ink-blue glow for Model/Sources is `#5270AC`, compositing to `#202A40`, Y 0.023; the stone glow for Ledger is `#956724`, compositing to `#342717`, Y 0.022 — both under the spec's `#2A3145` ceiling).

---

## 7. What does *not* get a hue, and why

| Element | Verdict | Reason |
|---|---|---|
| **Verdict chips** START / SIT / TOSS-UP | weight (unchanged) | the standing constraint; a green/red verdict is the thing the owner rejected first |
| **Status pills** Q / D / O / IR | weight (SPEC §5.2) | the audience's convention *is* a traffic light (ESPN/Yahoo red O, orange Q); O/IR are already the loudest object (cream fill). A hue here re-introduces the exact reading the owner called cheap |
| **Urgency groups** Do now / Before lock / This week | weight + the time text | urgency is ordinal, and its only intuitive colour is red-now; the gold rule on the Needs-you card already says "now" |
| **Matchup grade** SMASH … AVOID | the pip meter (weight) | a five-step ordinal scale is a *ramp*, not five hues; the meter already ramps gold → cream → dim |
| **Source categories** podcast / YouTube / newsletter / analyst / feed / news | glyphs, not hues | six more hues would blow the cap, and the only real conventions are brand hues (YouTube red, Podcasts purple, RSS orange) that would collide with league and position hues. A mic / play / envelope / person / rss / newspaper glyph in `dim` beside the nameplate says it; the creator-vs-feed distinction keeps the gold ring |
| **Streaks** HOT / COLD | temperature by *lightness*: HOT = the existing gold end-dot + a flame glyph in gold; COLD = `dim` sparkline + frost glyph; the words stay cream | an ember hue for HOT sits 0.05 ΔE from TE apricot and an ice hue 0.06 from WR cyan; both would appear on the same Board card as a player's code. Gold already means "this is on" |
| **Sources' faces** | faces; rings stay gold (creator) / hairline (feed) | "sources are faces" — a hue ring would compete with the creator ring |
| **The honesty banner** | opaque `wash-hot`, gold rule (SPEC §6) | it must stay the loudest non-colour on the screen; a page glow never reaches it (it is in the bar) |
| **The widget** | position hue as a 3 px left rule on each row + the gold START fill; ground obsidian | the widget sits on the user's wallpaper, which is coloured content the glass rules in §5 apply to |

---

## 8. Five annotated examples

Each is drawn against the spec's tokens; numbers are the minimum over the grounds the element can sit on.

### 8.1 Lineup row — a position hue beside a START chip

```
┌ card rgba(18,21,29,.78) over the ground ──────────────────────────────────┐
│ FLEX2   Bijan Robinson   ATL · RB              [ START 68% ]  ← gold fill,│
│         ─────────────    ^^^^^ ^^                navy ink 9.4:1            │
│         text #E8E3D8     muted  pos-rb #73D4AC 11px 700 (≥ 7.2:1)        │
│  vs TB · Sun 1:00 PM ET · ▮▮▮▯▯ · 15.2 proj                               │
│  ^chip: hairline-2 outline, cream   ^gold numeral (SPEC §5.6)             │
└────────────────────────────────────────────────────────────────────────────┘
```

- The *only* hue text on the row is the two-letter code `RB` (Tier A, 11 px 700). The player's name, team, kickoff and projection stay on the text ladder. The START chip is unchanged and still the brightest object: gold Y 0.53 vs mint Y 0.54 — equal luminance, but gold is a *fill* and mint is two letters, so weight, not hue, still says "start him."
- Greyscale check: the code `RB` reads because it is the letters; the chip reads because it is the fill. Hue is redundant.
- Hue count on the screen: two families (positions, the signed delta) plus gold and the league dot — at most seven distinct swatches across the whole page, and any single row carries one code and one chip.
- Never: a mint *fill* behind `RB` (it would compete with START), a mint left rule on the row (it would compete with the gold attention rule), mint on the name.

### 8.2 Home — the identity glow and a Needs-you card

```
native ground: light 1 cool (as today) + light 2 = GOLD at 13 % (as today; Home keeps gold)
┌ NEEDS YOU ── 2px gold rule ───────────────────────────────────────────────┐
│ DO NOW                              ← kicker: dim #909298 (not gold, SPEC §5.6)
│ ● WR  Nico Collins   Q · vs IND   [ TOSS-UP ]   Sun 1:00 PM ET            │
│   ^pos-wr #73CBF0 code              dashed gold   gold numeral            │
│ BEFORE LOCK …                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

- Home's identity hue is gold because Home *is* the decision inbox — same room as Board. The glow is the existing light 2; nothing new is painted.
- Urgency ("DO NOW" / "BEFORE LOCK") is weight and position, never hue: the gold rule on the card is the only "now" on the screen.
- The `Q` pill stays panel + hairline-2 + 3 px gold inset rule (SPEC §5.2) — no orange.
- If the owner later wants a *cool* Home to distinguish it from Board: swap light 2 to the ink-blue glow `#5270AC` at 30 % (L 0.55 C 0.10 at 263°); the composite brightest pixel is `#202A40` (Y 0.023), below `#2A3145`; no other token moves.

### 8.3 Trade Desk — the league owns the room

```
native ground: light 2 = league glow (ESPN #A45859 / Yahoo #7F62A0 / Sleeper #008384) at 30 %
top bar (glass, untinted): [◆] [ ● Kid's Table ▾ · Live · 9:04 PM ] [WK 1]
                              ^league dot 8px, league-yahoo #BF93F1 (5.3:1 min, 3:1 non-text floor met)
┌ NEEDS MATRIX ───────────────────────────────────────────────────────────┐
│           QB    RB    WR    TE    K    DST     ← column heads: hue codes│
│           rose  mint  cyan  peach dim  dim      11px 700, Tier A         │
│ Andrew ─── your column: 2px gold rule (SPEC §10)                        │
│ Marcus     ·     ▮▮    ·     ▮    ·    ·      ← cells: cream/dim weight  │
└──────────────────────────────────────────────────────────────────────────┘
```

- Identity: one dot in the bar + the glow in the ground. The bar glass is *not* tinted purple — Apple: "Refrain from adding color to the background of multiple controls"; the glass refracts the purple ground instead, which is the intended way for a page to colour its chrome.
- The matrix column heads carry the four position hues once, as codes; cells stay weight (filled pips = need). Six columns, four hues, two greys.
- Collision check: Yahoo violet `#BF93F1` vs the old K-lavender idea (ΔE 0.078) is why K is grey. Sleeper aqua vs WR cyan (0.071) never share a component: the dot is in the bar, the code is in the table.
- Hue count on screen: one family (positions) plus gold (your rule) and the league dot — six swatches, inside the cap. This is the busiest screen in the app; a second family here (say, a per-manager hue) is what the cap forbids.

### 8.4 Sources / Receipts — temperature without a new hue

```
native ground: light 2 = ink-blue glow at 30 % (Model and Sources are "the blue room")
┌ nameplate ─────────────────────────────────────────────────────────────────┐
│ (JB)  Fantasy Footballers   🎙  wt 17    HOT ▲ 71% · n38                    │
│  ^avatar on raised, gold ring (creator)    ^word cream; flame glyph gold;   │
│                                             ^the sparkline's END-DOT gold   │
│ ╭╮╭─╮  ╭╮╭╮╭──●   sparkline muted, end-dot gold (HOT) / dim (COLD)          │
│ 63% over 41 graded calls · last episode Tue                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

- The category is the `🎙`-class glyph in `dim` (mic / play / envelope / person / rss / newspaper) — six categories, zero hues.
- HOT/COLD: the *end-dot* and the glyph carry it in gold vs dim — lightness, which is what temperature already means on this spec's meter (gold pips = smash). An ember/ice pair was tested and rejected: ember `#F69370` sits 0.05 ΔE from TE apricot and both would meet on a Board card.
- The gold budget: the flame glyph is a glyph, not a word and not a fill; the gold text rule (numbers and times only) is untouched — `71%` stays cream because it is a record, not a decision.

### 8.5 The tab bar over a row of position chips (glass over colour)

```
scroll position: a Lineup card has scrolled under the bottom bar
without edge effect:  cream on 52% glass over [RB] mint fill  → 4.1:1   (FAILS 4.5)
                                          over Sleeper aqua   → 3.7:1   (FAILS)
with .soft edge effect (≈35% dim beneath): over mint          → 6.7:1
                                          over aqua           → 6.3:1
with codes drawn as TEXT not fills:       the bar sees the card (#171B26) → 8.6:1 regardless
```

- This is why §2.3 and §6 make position hues *codes*, not fills, on rows: a 2-letter code in `#73D4AC` changes what the glass samples by a few pixels; a 24 px mint fill under a 44 pt bar label is a legibility event that only the edge effect rescues.
- The only fill that legitimately scrolls under the bar is the START chip, and the spec already proved that case (4.14 → 8.64 with the edge dim).
- On a widget or a Reduce-Transparency device the glass is opaque/frosted and none of this applies — the flat-ground numbers (≥ 8.6:1 for every Tier-A swatch) hold.

---

## 9. Verification

`verify_multihue.py` (this folder) recomputes: the luminance floors per ground; every Tier-A candidate on canvas / panel / raised / `#2A3145` / card-over-`#2A3145`; the fill-with-navy-ink ratio; pairwise OKLab distances; the wash tier; the glow's composite brightest pixel; and the glass-over-colour table. Run it after any change to `design/obsidian/tokens.obsidian.json` or to the candidates. Also rerun the spec's hue scan (SPEC §1.1) — with these tokens it will flag rose (hue < 20° band in HSV terms) and mint (70–170°) by design; the scan's rule should become "no *fill* at L 0.45–0.65 and no hue on a word," which is the rule that actually keeps the traffic light out.

---

## Sources

- Apple, HIG — Color (system colour table, June 2025 values; Liquid Glass colour guidance): https://developer.apple.com/design/human-interface-guidelines/color
- Apple, HIG — Dark Mode (brighter foreground / dimmer background; 4.5 minimum, 7:1 for custom colours; base vs elevated): https://developer.apple.com/design/human-interface-guidelines/dark-mode
- Apple, HIG — Materials (regular vs clear glass; 35 % dimming layer; vibrant colours on materials; "Don't use Liquid Glass in the content layer"): https://developer.apple.com/design/human-interface-guidelines/materials
- Apple, HIG — SF Symbols (monochrome / hierarchical / palette / multicolor): https://developer.apple.com/design/human-interface-guidelines/sf-symbols
- Apple, WWDC25 session 219 "Meet Liquid Glass" (tinting; "When every element is tinted, nothing stands out"): https://developer.apple.com/videos/play/wwdc2025/219/
- Apple, "Adopting Liquid Glass" (be judicious with colour in controls; scroll edge effect): https://developer.apple.com/documentation/TechnologyOverviews/adopting-liquid-glass
- Google, Material Design 2 — Dark theme (#121212; desaturation; 200 tone; 15.8:1; limited colour accents; 87/60/38 %; #CF6679): https://m2.material.io/design/color/dark-theme.html and the codelab https://codelabs.developers.google.com/codelabs/design-material-darktheme
- Linear, "How we redesigned the Linear UI (part II)": https://linear.app/now/how-we-redesigned-the-linear-ui
- Raycast API — Colors: https://developers.raycast.com/api-reference/user-interface/colors
- Sleeper web CSS (design-language tokens, fetched 2026-09-10): https://sleepercdn.com/sleeper-web/_next/static/chunks/2b7avkr6fu8y5.css ; Sleeper support, "League Legend": https://support.sleeper.com/en/articles/4584482-league-legend
- Google Design on Robinhood: https://design.google/library/robinhood-investing-material
- Bloomberg, "Designing the Terminal for color accessibility" (page is bot-gated; cited from its abstract): https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/ ; Ted Merz, "Amber on Black": https://ted-merz.com/2021/06/26/amber-on-black/ ; Curio style guide: https://designbycurio.com/learn/bloomberg-terminal-green
- Spotify dark palette and extraction (secondary): https://blakecrosley.com/guides/design/spotify
- Refactoring UI, "Building your color palette": https://refactoringui.com/previews/building-your-color-palette
- Datawrapper, "What to consider when choosing colors for data visualization": https://www.datawrapper.de/blog/colors
- Nielsen Norman Group, "Dark Mode vs. Light Mode": https://www.nngroup.com/articles/dark-mode/ ; halation for astigmatic readers: https://www.accessibilitychecker.org/blog/dark-mode-accessibility/
- Chromostereopsis: https://en.wikipedia.org/wiki/Chromostereopsis
- W3C WCAG 2.2 — relative luminance, 1.4.3, 1.4.11: https://www.w3.org/TR/WCAG22/
- Marketing Brew on "ESPN red" (2026): https://www.marketingbrew.com/stories/2026/03/09/espn-brand-identity ; Yahoo purple `#6001D2`: https://brandcolors.net/b/yahoo
- Apple Health category colours (secondary): https://techwiser.com/what-icons-and-symbols-mean-on-apple-health-app-complete-guide/
