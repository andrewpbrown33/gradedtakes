# The Obsidian palette — colour with jobs

Status: proposal, 2026-09-10. Builds on `design/obsidian/SPEC.md` (ground, text ladder, glass rules, verdict encoding — all kept) and on the two surveys in this folder: `CONVENTIONS.md` (what fantasy players already know) and `DARK_MULTIHUE.md` (how dark apps carry many hues without becoming a casino). Nothing under `design/obsidian/`, `engine/` or `ios/` was touched. Companions: `palette.json` (every token with every computed ratio), `swatches.html` (judge it by eye), `palette_verify.py` (recomputes every number here and runs the hue rule as a test; prints `ALL CHECKS PASS`).

The owner's direction, read as three rules: **more colour, used intuitively** (colour the user already reads: a QB is pink on Sleeper, ESPN is red, a hot streak is warm); **one text scale everywhere**; **colour may differ across pages and across the app**. The standing constraints stay: obsidian ground, glass on controls only, verdict chips keep their weight encoding, WCAG AA on every text/ground pair, the honesty banner unmissable, sources are faces.

The one-sentence version: **the text ladder never takes a hue; hue is carried by small objects — a two-letter code, an 8px dot, a 2px rule, a 6×13 pip, a glyph, a fill ≤ 24px under navy ink — and every hue has exactly one job, so a screen can be colourful without a single colour meaning "good" or "bad" that the user did not already believe.**

---


> **OWNER DECISION 2026-09-11 — supersedes the matchup rows below and R1's matchup clause.**
> The matchup grade is a **bipolar scale, centred by default**: neutral sits in the middle,
> a good matchup weights the indicator to the RIGHT, a matchup to avoid weights it to the
> LEFT. Colour follows position on the scale — **green toward the right, red toward the
> left** — not a one-directional fill. R1 keeps verdicts (START/SIT/TOSS-UP), status and
> urgency out of red/green; the matchup scale is the named exception. Tune both hues for
> obsidian (lifted, desaturated) and prove ≥ 4.5:1 for any label and ≥ 3:1 for the bar.
>
> **UNDER REVIEW (same date):** the gold accent itself ("feels cheap"), the gold-diamond
> mark, and source monograms/category glyphs ("don't stick"). Do not extend gold's role
> until resolved; see RUNBOOK 0d.

## 0. The palette, on one page

Ratios are WCAG 2.x contrast. "min text" is the minimum over the six obsidian grounds a token can sit on (canvas `#0A0C12`, panel `#12151D`, raised `#1C202B`, raised-2 `#262A35`, the brightest native-ground pixel `#2A3145`, the 78 % card over that pixel `#171B26`). "fill / ink" is navy `chip-ink #101B33` on the token as a fill. "pill" is the token as a glyph on the tab bar's selection pill over the worst glass (`#353946`; non-text floor 3:1). Hue/chroma/lightness are OKLCH ([Ottosson](https://bottosson.github.io/posts/oklab/)); HSV is given because the critic's existing scan speaks HSV.

| token | hex | job (one) | carrier | OKLCH L/C/h | HSV h/s | min text | fill / ink | pill |
|---|---|---|---|---|---|---|---|---|
| `text` | `#E8E3D8` | primary ink | text | .92/.02/86° | 41°/.07 | **10.1** | — | 9.0 |
| `muted` | `#ABA9A1` | secondary ink | text | .73/.01/95° | 48°/.06 | **5.5** | — | — |
| `dim` | `#909298` | tertiary ink; K and DST codes; feed glyphs; AVOID pips | text | .66/.01/271° | 225°/.05 | **5.5** on cards (4.2 on the bare worst pixel, §1.1) | — | — |
| `disabled` *(new)* | `#767A83` | disabled labels, unavailable rows | text | .58/.02/267° | 222°/.10 | 3.0 (inactive UI: house floor 3:1) | — | — |
| `nav-text-2` | `#C9C5BC` | the one secondary ink on glass | text | .82/.01/87° | 42°/.06 | **7.5** | — | 6.7 |
| `chip-ink` | `#101B33` | the one dark ink on every hue fill | text | .23/.05/264° | 221°/.69 | — | ≥ 7.5 on every fill | — |
| `gold` | `#F2B722` | **the decision** (§2.8) | fill ≤ 24px · 2–3px rule · deciding numeral · glyph | .81/.16/84° | 43°/.86 | **7.1** | **9.4** | 6.3 |
| `straw` *(new)* | `#EACE8C` | GOOD matchup pips | pip | .86/.09/88° | 42°/.40 | 8.4 | 11.2 | — |
| `cool` *(new)* | `#9AADC4` | the cool pole: TOUGH pips, COLD, negative deltas | pip · glyph · 6px dot · numeral | .74/.04/253° | 213°/.21 | **5.6** | 7.5 | 5.0 |
| `pos-qb` | `#F59ECF` | QB | 2-letter code · 3px rule · fill under ink | .80/.12/345° | 326°/.36 | **6.6** | **8.7** | 5.8 |
| `pos-rb` | `#6BD5B6` | RB | same | .80/.11/172° | 163°/.50 | **7.3** | **9.6** | 6.5 |
| `pos-wr` | `#7AC8F5` | WR | same | .80/.10/235° | 202°/.50 | **7.0** | **9.3** | 6.2 |
| `pos-te` | `#F9A782` | TE | same | .80/.11/45° | 19°/.48 | **6.7** | **8.9** | 6.0 |
| `pos-k`, `pos-dst` | = `dim` | K, DST | code | — | — | 5.5 on a row | — | — |
| `brand-red` | `#FC9192` | ESPN league dot; YouTube glyph | 8px dot · 2px rule · 12px glyph | .77/.13/20° | 359°/.42 | **5.9** | 7.8 | 5.3 |
| `brand-violet` | `#C79FF4` | Yahoo league dot; podcast glyph | same | .77/.13/305° | 268°/.35 | **6.0** | 7.9 | 5.3 |
| `brand-aqua` | `#65E1E1` | Sleeper league dot | same | .84/.11/195° | 180°/.55 | **8.3** | 10.9 | 7.3 |
| `ink-blue` (was `mint`) | `#9DBBF3` | Model / Sources identity: tab glyph + glow | glyph · glow | .79/.09/263° | 219°/.35 | 6.7 | 8.8 | 5.9 |
| `stone` (was `coral`) | `#BDB0A0` | Ledger identity: tab glyph + glow | glyph · glow | .76/.03/73° | 33°/.15 | 6.1 | 8.1 | 5.4 |
| `wash-hot` | `#2D281E` | the honesty banner, the empty-record note — only | strip | .28/.02/85° | 40°/.33 | text 11.4 · muted 6.2 · gold 8.1 on it | | |
| `wash-split` | `#24221D` | the challenger line under a contested slot | row | .25/.01/89° | 43°/.19 | text 12.4 · muted 6.8 on it | | |
| `wash-cool` *(new; replaces `wash-bad`, `wash-cold`)* | `#182031` | AVOID rows, bye rows, cold rows | row | .24/.04/265° | 221°/.51 | text 12.7 · muted 6.9 · dim 5.2 · cool 7.1 on it | | |
| `glow-gold` | `#F2B722` @ 13 % | Home, Board, Onboarding (light 2 as today) | ground | composite `#282214`, Y .0165 | | | | |
| `glow-ink` | `#5270AC` @ 30 % | Model, Sources | ground | `#202A40`, Y .0233 | | | | |
| `glow-stone` | `#956724` @ 30 % | Ledger | ground | `#342717`, Y .0224 | | | | |
| `glow-espn` / `glow-yahoo` / `glow-sleeper` | `#A45859` / `#7F62A0` / `#008384` @ 30 % | Trade Desk, in the league's colour | ground | `#382327` / `#2D263D` / `#073034`, Y .022–.024 | | | | |

Retired as *meanings* (hexes survive under new names): `mint` = positive → `cool` does the signed job, `#9DBBF3` becomes `ink-blue` (identity only); `coral` = negative → `#BDB0A0` becomes `stone` (identity only); `wash-good` (blue = good) → retired, a good-matchup row gets no wash (the meter says it); `wash-bad` and `wash-cold` → `wash-cool`. Unchanged: `canvas`, `panel`, `raised`, `raised-2`, hairlines, `chip-sit`, `chip-none`, `nav*`, `frost`, `meter-lo`, `shadow`, every glass knob.

Every glow's composite is under the spec's worst-pixel ceiling (`#2A3145`, Y .0312), so every number in SPEC §11 still holds on every page.

---

## 1. The text scale — fixed everywhere

The ladder is the spec's and it does not move: names, numbers, reasons, ledes, kickers, group heads, meter labels, the words START / SIT / TOSS-UP, HOT, SMASH, ESPN are all set in it. The only text that ever takes a hue is a **≤ 3-character code** (`QB`, `WR`, `Q`) or a **numeral that itself carries the decision** (SPEC §5.6). This is the pattern every product in `CONVENTIONS.md` §5 ships (Sleeper colours two letters, ESPN a dot, NFL an underline, FantasyPros a pastel behind one dark ink) and what Apple's Dark Mode guidance asks for ("Use the system-provided label colors for labels" — [HIG Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode)).

### 1.1 On obsidian (content layer)

| step | token | canvas | panel | raised | raised-2 | worst pixel | card over worst | glass-worst | tab pill |
|---|---|---|---|---|---|---|---|---|---|
| primary | `text #E8E3D8` | 15.3 | 14.3 | 12.7 | 11.2 | 10.1 | 13.4 | 11.5 | 9.0 |
| secondary | `muted #ABA9A1` | 8.3 | 7.8 | 6.9 | 6.1 | 5.5 | 7.3 | 6.2 | 4.9 |
| tertiary | `dim #909298` | 6.3 | 5.9 | 5.2 | 4.6 | **4.2** | 5.5 | 4.7 | 3.7 |
| disabled | `disabled #767A83` | 4.5 | 4.2 | 3.8 | 3.3 | 3.0 | 4.0 | 3.4 | 2.7 |

Floors: primary and secondary ≥ 4.5 everywhere (secondary ≥ 7 on panel, as the spec asks). **Tertiary is a card ink**: labels, kickers, times, slot badges and `wt` sit on cards, panels and washes, where `dim` is ≥ 5.1; on the bare brightest ground pixel it is 4.2 — inherited from SPEC §1, and the spec's own pixel audit found no rendered text below 4.8 because nothing dim lands on that pixel (it is under the top bar). Rule that keeps it so: **`dim` never sits on the bare ground inside light 1's ellipse** (the top-left 16 %/10 % centre); if a layout ever puts it there, use `muted`. `disabled` is inactive UI (WCAG 1.4.3 exempts it); the house floor is the 3:1 non-text floor on every surface it can sit on, and it never sits on the tab pill (a disabled tab is never the selected one).

### 1.2 On a tinted chip (a hue fill under dark ink)

A chip is ≤ 24px tall and holds a code and at most a numeral, so it has two inks, not four.

| step | ink | on `gold` | on `brand-red` (the darkest fill) | on `pos-qb` | on `pos-te` | on `pos-rb` | on `pos-wr` | on `brand-violet` | on `brand-aqua` |
|---|---|---|---|---|---|---|---|---|---|
| primary | `chip-ink #101B33` | 9.4 | 7.8 | 8.7 | 8.9 | 9.6 | 9.3 | 7.9 | 10.9 |
| secondary | `chip-ink` at 82 % (the `%` beside the word) | 6.6 | 5.7 | 6.1 | 6.2 | 6.5 | 6.3 | 5.6 | 7.1 |
| tertiary | not permitted | | | | | | | | |
| disabled | never a fill: a disabled or locked chip is the ghost (`chip-sit` outline + `dim`), SPEC §5.1 | | | | | | | | |

Cream on a hue fill is not an option — no Tier-A fill passes 4.5 under `#E8E3D8` (`DARK_MULTIHUE.md` §2.3) — so the FantasyPros rule holds: **one dark ink on every fill**.

### 1.3 On glass (Level 2: the two bars, the floating strip)

| step | token | glass-worst `#232836` | tab pill `#353946` | frost `#14171E` |
|---|---|---|---|---|
| primary | `text` | 11.5 | 9.0 | 14.0 |
| secondary | `nav-text-2 #C9C5BC` | 8.5 | 6.7 | 10.4 |
| tertiary | not permitted on Level 2 (SPEC §3: no `muted`, no `dim` on glass) | | | |
| disabled | `disabled` | 3.4 | (never on the pill) | 4.2 |

These hold because the scroll edge effect is beneath the bars; §4.4 has the numbers without it.

---

## 2. The semantic hues — each with one job

Every hue below sits in **Tier A** (`DARK_MULTIHUE.md` §2.2: OKLCH L 0.76–0.86, C ≤ 0.14), which is the band where one hex is both legal coloured text on the bare worst pixel (≥ 5.6:1) *and* a legal fill under navy ink (≥ 7.5:1). Each was built the way Apple builds its Increase-Contrast dark variants and Sleeper builds its dark tokens: the light-mode hue lifted ~0.15 in L and cut about a third in chroma ([HIG Color specifications](https://developer.apple.com/design/human-interface-guidelines/color); [Sleeper DLS CSS](https://sleepercdn.com/sleeper-web/_next/static/chunks/2b7avkr6fu8y5.css)). Nothing is drawn as a fill in the L 0.45–0.65 band — the "casino" band where neither cream nor navy passes.

### 2.1 Positions — the majority convention, tuned for obsidian

`CONVENTIONS.md` §1 found the only position-colour habit fantasy players hold: **QB in the red-violet band (265–345° HSV) and RB in the teal band (153–191°)** in all three products that colour positions (Sleeper, Underdog, FantasyPros); WR/TE are a blue/orange pair whose assignment only Sleeper's user base has learned; K/DST are noise, and FantasyPros makes DST grey. ESPN and Yahoo colour nothing, so nothing contradicts this.

| position | hex | derived from | HSV | text on obsidian (min) | fill under `chip-ink` | ΔE from gold | when it appears |
|---|---|---|---|---|---|---|---|
| **QB** | `pos-qb #F59ECF` | Sleeper `#FC2B6D` ([shipped](https://sleepercdn.com/sleeper-web/_next/static/chunks/2c7a3r5pyddzv.js)), L +.15, chroma −45 %, hue kept inside the QB band; 14° clear of the old red cut | 326°/.36 | 6.6 | 8.7 | 0.21 | the 2-letter code beside the team on every row (Home, Lineup, Board header, Trade Desk matrix heads); the widget's 3px left rule; a fill only on the Board versus-card badge |
| **RB** | `pos-rb #6BD5B6` | Sleeper `#20CEB8` / Underdog `#15997D`, lifted | 163°/.50 | 7.3 | 9.6 | 0.19 | same |
| **WR** | `pos-wr #7AC8F5` | Sleeper light `#59A7FF` (212°) and Sleeper's own *dark* WR `#00D7FF` (189°) bracket it; pulled 10° toward cyan so it cannot be read as `ink-blue` | 202°/.50 | 7.0 | 9.3 | 0.25 | same |
| **TE** | `pos-te #F9A782` | Sleeper `#FEAE58` (31°) pulled to peach so it is not gold: ΔE 0.10 — the threshold at which two chips read as different colours | 19°/.48 | 6.7 | 8.9 | **0.10** | same; **never a fill in a row that holds a START chip** |
| **K**, **DST** | `dim #909298` | FantasyPros DST grey; Sleeper's K is a C 0.06 near-neutral | — | 5.5 on a row | — | — | code only |

Pairwise separation (OKLab ΔE, enforced ≥ 0.10 by the verifier): QB/RB .23 · QB/WR .18 · QB/TE .11 · RB/WR .11 · RB/TE .20 · WR/TE .21. RB is the one to watch by eye: it sits at HSV 163°, the teal end of the band, and the old rule would have called it green (§5). If it reads as green in the frames, the alternative inside the band is OKLCH 180° `#61D5C0` (HSV 169°, min text 7.3) — the same distance from WR.

Rules: the code is **11px/700 mono, the same size on every page** (a Trade Desk cell may not shrink it); the name beside it stays `text`; never a row wash in a position hue; never a position left-rule on a row (it would compete with the gold attention rule); never the position word ("Running back") in the hue.

### 2.2 Matchup — five steps, warm → cool, no green or red at the ends

Every product that colours a matchup uses green = easy, red = tough (Sleeper's legend, ESPN's OPRK `#009444`/`#C00`, Yahoo's three levels — `CONVENTIONS.md` §3). That is the traffic light the owner rejected first, so its strength is a reason not to adopt it. The counter-evidence is FantasyPros, the largest advice site in the category, whose matchup stars are a **monochrome blue count** ([support article](https://support.fantasypros.com/hc/en-us/articles/360038154454-What-does-the-Matchup-Star-Rating-mean)) — proof that count carries the scale on its own.

So the scale keeps the spec's meter (five 6×13 pips filled from the left, a label word beside it) and adds temperature as the **third** channel, behind count and word:

| step | pips | pip colour | label ink | row wash | pip on card (non-text floor 3) |
|---|---|---|---|---|---|
| SMASH | 5 | `gold #F2B722` | `text` | none | 9.5 |
| GOOD | 4 | `straw #EACE8C` | `text` | none | 11.2 |
| NEUTRAL | 3 | `text #E8E3D8` | `text` | none | 13.4 |
| TOUGH | 2 | `cool #9AADC4` | `muted` | none | 7.5 |
| AVOID | 1 | `dim #909298` | `muted` | `wash-cool #182031` | 5.5 |

Why these hues, and not green/red or a rainbow:

- **Gold at the top** because SMASH is the matchup that decides a START, and gold already means "the decision" (§2.8). One warm pole for the whole app: gold = for you.
- **Straw** is gold with the chroma halved (C .09) — visibly "less gold" beside a SMASH meter (ΔE .085; the count differs anyway) and clearly not cream (ΔE .093 from `text`).
- **Cream in the middle**, not amber: Sleeper's "average" is orange and ESPN.com's "solid" is yellow, so an amber middle would read "meh" to Sleeper users while gold means "smash" here. The middle is the ink itself, so the ramp is symmetric around the text colour.
- **Cool, then dim, at the bottom**: the cool pole is a low-chroma slate (C .04) — ice, a wall — and AVOID is the same dim the spec already draws a wall in. Cold and dark, never warm and never red. The lightness ramp is monotonic from NEUTRAL down (.92 → .74 → .66), so the bottom half reads in greyscale even before counting.
- **The warm-good ambiguity is real** ("hot defence" = tough) and is why tint is the third channel: the count and the word are always present (SPEC §5.4), and the tint is never the only thing that differs between two meters.

Washes: `wash-cool` under AVOID rows only. The old `wash-good` (blue = good) is retired — it was one metaphor in the washes and the opposite in the meter (`CONVENTIONS.md` §3.3), and a blue wash would now read as a WR row. Opponent chips stay as the spec draws them (cream outline weight, no hue).

### 2.3 Source categories — glyphs; two carry a brand tint

Sources are faces (SPEC §5.5): the avatar and the ring (gold = a human voice, hairline = a feed) are the identity. The category is a 12px glyph beside the nameplate. Six category hues would blow the cap (§4), and the only hues the user actually associates with these are platform brands — so **the two platform-shaped categories carry the platform's colour and the four ink-shaped ones stay on the ladder**:

| category | glyph | tint | hex | min text | when |
|---|---|---|---|---|---|
| podcast | mic | `brand-violet` (Apple Podcasts' purple family, lifted) | `#C79FF4` | 6.0 | Model (your sources, the library, suggest-a-source) and Sources — pages with no position codes |
| YouTube | play | `brand-red` (YouTube's red, lifted) | `#FC9192` | 5.9 | same; the one red-family object in the content layer — fallback if the owner rejects it: `muted` |
| newsletter | envelope | `text` | `#E8E3D8` | 10.1 | same |
| analyst | person | `text` (+ the gold creator ring the spec already gives a human voice) | `#E8E3D8` | 10.1 | same |
| feed | waveform / rss | `dim` (machines are grey, like K/DST) | `#909298` | 5.5 | same |
| news | newspaper | `muted` | `#ABA9A1` | 5.5 | same |

Rule: the tint is on the glyph only — never the ring (that is the creator/feed distinction), never the name, never a card. Brand colour, never a brand glyph: the mic is the app's own mic, not Apple's; the play triangle is generic (nominative use, `CONVENTIONS.md` §2). Categories and positions never share a screen, which is what keeps the cap.

### 2.4 Urgency — Do now / Before lock / This week

No product has an urgency convention (`CONVENTIONS.md` §6) and urgency is ordinal, so it is **weight and the time**, with gold spent once:

| group | head | the item's time | the card |
|---|---|---|---|
| DO NOW | `text` 700 kicker | **`gold` mono** — the time carries the decision (SPEC §5.6) | the Needs-you card's 2px gold rule |
| BEFORE LOCK | `text` 600 | `text` mono | hairline-2 divider |
| THIS WEEK | `muted` 600 | `dim` mono | hairline |

That is a lightness ramp (gold → cream → dim) on the numeral and on the head, no new hue. The gold rule therefore has one meaning app-wide: **needs you now** — the Needs-you card, the honesty banner, a Q/D pill, your column. If a heads-up hue is ever wanted it is this gold, not an orange (an orange would sit 14° from TE peach on the same row).

### 2.5 Status — Q / D / O / IR: the letter carries it, colour supports

Two tiers everywhere a second tier exists (Sleeper, ESPN.com, NFL — `CONVENTIONS.md` §4): **Q/D yellow-orange ("might play"), O/IR red ("will not")**; and the letter is present in every product, including the two that colour every status the same red. The spec's pills already encode the two tiers by weight, and the yellow tier maps onto gold without a new hue:

| codes | treatment (SPEC §5.2, unchanged) | the convention it satisfies | ratios |
|---|---|---|---|
| Q, D | panel fill, hairline-2 border, **3px gold inset rule**, `text` letter | the "yellow" tier — gold is this app's yellow | letter 14.3 on panel; rule 10.1 on panel (non-text) |
| O, IR, SUSP | **cream fill**, `panel` ink — the loudest weight in the system | the "red" tier by *weight* | 14.3 |
| BYE, LOCK | ghost: hairline-2 border, `dim` letter | — | 5.9 on panel |

No red. O/IR is the only cream block on the screen, which is louder than any hue on obsidian, and the letter says which. The one hue that would fit the convention (a brick underline) is a *state* signal and is exactly what §5 forbids; ESPN Fantasy and Yahoo prove one treatment plus the letter is enough.

### 2.6 Streak — HOT / COLD

Fire/ice is cultural, not a product convention (`CONVENTIONS.md` §6). It maps onto the two poles that already exist, so it costs no hue:

| state | glyph | sparkline end-dot | word |
|---|---|---|---|
| HOT | flame in `gold` | `gold` (6px) | `text` |
| COLD | frost in `cool #9AADC4` | `cool` | `text` |
| neither | none | `dim` | — |

The end-dot was gold on every source before; now gold means HOT and only HOT. An ember/ice pair was rejected in `DARK_MULTIHUE.md` §7 (ember is 0.05 ΔE from TE peach; ice 0.06 from WR cyan). `cool` vs `pos-wr` is 0.087 — they never share a component (a pip or a frost glyph vs a two-letter code) and on Sources, where streaks live, there are no position codes at all.

### 2.7 League tags — ESPN / Yahoo / Sleeper, colour only

Universally known: ESPN red, Yahoo purple `#6001D2` (computed live), Sleeper navy + aqua (`CONVENTIONS.md` §2, with the ESPN CSS `#C00`/`#D00`, the Yahoo page and the Sleeper token `--color-dls-primary-400`). The brand hexes fail on obsidian (ESPN `#C00` is 2.2:1 on the worst pixel; Yahoo `#6001D2` 1.5) so the *hue* transfers and the *hex* is rebuilt in Tier A:

| league | token | hex | dot on the worst glass | glyph on the tab pill | Trade Desk glow |
|---|---|---|---|---|---|
| ESPN | `brand-red` | `#FC9192` | 6.7 | 5.3 | `#A45859` @ 30 % → `#382327` |
| Yahoo | `brand-violet` | `#C79FF4` | 6.8 | 5.3 | `#7F62A0` @ 30 % → `#2D263D` |
| Sleeper | `brand-aqua` | `#65E1E1` | 9.4 | 7.3 | `#008384` @ 30 % → `#073034` |

Where: an **8px dot before the league name in the top-bar capsule** (every page; one dot per screen — only one league is ever on screen), the **Trade Desk's ground glow and selected-tab glyph** (§3), the detected league on Onboarding, a 2px rule on a league card in Settings. Never: a logo, a wordmark, a tinted bar, a red page. The name is plain type in the app's font — nominative fair use ([Qualitex](https://supreme.justia.com/cases/federal/us/514/159/) is why colour alone is not their mark; a look-alike glyph is the trap) — and Settings carries one "not affiliated with ESPN, Yahoo or Sleeper" line.

Sleeper's aqua sits between RB (ΔE .059) and WR (.083); the dot lives in the bar and the codes in the table, so they never meet in one component, and the dot has the league name beside it.

### 2.8 Gold — the narrower job

Gold is **the decision**, and nothing else. It keeps:

1. the mark;
2. the START fill and the TOSS-UP dash (the verdict's weight vocabulary);
3. the one primary verb per screen;
4. the attention rule — one meaning, "needs you now": the honesty banner's 2px rule, the Needs-you card, the Q/D pill's 3px rule, your column on the Trade Desk, the creator ring;
5. numbers and times that carry a decision (`WK 1`, the lock time, the banner's date, the Do-now time, the challenger's deciding margin) — SPEC §5.6 exactly;
6. the warm pole of the temperature family: SMASH pips, the HOT flame and end-dot.

Gold gives up: the selected-tab tint on Model, Trade Desk and Ledger (§3); light 2 on Model, Sources, Ledger and Trade Desk; the GOOD pips (now straw); the sparkline end-dot on every source (now only HOT); the K/DST/feed glyphs it never had. Per screen, gold's pixel share can only fall from SPEC §10's numbers — every change here is a subtraction from gold and an addition somewhere it was not.

---

## 3. Page identity — one hue per room

The pattern every dark reference product uses (`DARK_MULTIHUE.md` §1: Apple Fitness/Health/Stocks, iOS Settings, Linear, Raycast, Spotify, Sleeper): the identity hue sits on **one small object and/or a glow in the ground**; text, cards and bars stay one neutral ladder; and the hue comes from a vocabulary with fixed meanings — no page gets an invented colour. Applied:

| page | identity hue | selected tab glyph (on the pill, ≥ 3:1) | ground glow (light 2) | league dot in the bar | category hues on the page |
|---|---|---|---|---|---|
| **Home** | gold — the inbox is the brand | `gold` 6.3 | `glow-gold` (as today) | yes | positions (4), cool, straw |
| **Lineup** | **none** — the four position codes *are* the colour on the most colourful page | `gold` 6.3 | light 1 only | yes | positions, cool, straw |
| **Board** | gold — the same room as Home | `gold` 6.3 | `glow-gold` | yes | positions (card header), cool, straw |
| **Model** | `ink-blue` — "the blue room": your sources, weights, the library | `ink-blue` 5.9 | `glow-ink` `#5270AC` @ 30 % → `#202A40` | yes | source tints (violet, red) |
| **Trade Desk** | **the league's hue** — the one page about the other managers | `brand-red` 5.3 / `brand-violet` 5.3 / `brand-aqua` 7.3 | `glow-espn` / `glow-yahoo` / `glow-sleeper` | yes | positions (matrix heads) |
| Ledger (if it holds the fifth slot) | `stone` — paper, the past | `stone` 5.4 | `glow-stone` `#956724` @ 30 % → `#342717` | yes | none |
| Sources / Receipts (no tab; Model lights) | `ink-blue`, with Model | `ink-blue` 5.9 | `glow-ink` | yes | source tints, HOT/COLD |
| Onboarding | gold | — | `glow-gold` | the detected league | — |

Where the identity appears — exactly three places: (1) **the selected tab's glyph** takes the page's hue (`.tint` per destination; the label stays `.primary` as the spec requires — the gold label on the pill was 4.9:1, cream is 9.0); (2) **light 2 in the native ground**, the hue at OKLCH L 0.55 C 0.10 at ≤ 30 %, which the glass bars *refract* — Apple's intended way for a page to colour its chrome ("Liquid Glass … takes on colors from the content directly behind it", [HIG Color](https://developer.apple.com/design/human-interface-guidelines/color)); (3) for the league only, the 8px dot in the header capsule.

Where it must **not** appear: body text, kickers, cards, card rules (attention rules stay gold), the glass `.tint` of the bars or the floating strip ("Refrain from adding color to the background of multiple controls"; "When every element is tinted, nothing stands out" — [WWDC25 219](https://developer.apple.com/videos/play/wwdc2025/219/)), the honesty banner, the START chip, the WK capsule, sheets. Home, Lineup and Board share gold on purpose — they are one room (the decision) — and Lineup's glow is left off so the position codes are the only colour on it. If the owner would rather keep Apple's single-tint purity on the tab bar, drop (1): the glow alone carries the identity and every other number in this document stands.

---

## 4. The cap and the consistency rules

### 4.1 Families, and the cap

Five hue families: **warm** (gold, straw), **cool** (`cool`), **position** (4 hexes), **brand** (3 hexes, used as the league dot and the two source tints), **identity** (ink-blue, stone — glow and tab glyph only). The cap, from Datawrapper's seven, Material's "limited color accents" and Apple's "limited color palette" (`DARK_MULTIHUE.md` §3):

- **Per screen, in the content layer: the warm family plus at most two of {cool, position, brand}; at most seven chromatic swatches.** The league dot in the bar is the eighth and is exempt (once per screen, beside its name). Check: Home/Lineup/Board = warm + position + cool (seven: gold, straw, four codes, cool). Model/Sources = warm + brand + cool (violet, red, gold, cool). Trade Desk = warm + position (+ the dot). Ledger = warm only.
- **Per row: one code and one chip, never two fills.** A TE code is never a fill in a row that holds a START chip.
- **Per component: one hue.** A meter is one pip colour; a nameplate has one tinted glyph; a capsule has one dot.
- **Never on a screen together:** position codes and source-category tints (they do not share a page, by the page table); an ember/ice pair; a per-manager hue on the Trade Desk (the cap's canonical violation).

### 4.2 What stays neutral

The text ladder (§1); every card, panel, row and sheet surface; the bars, the floating strip and the glass; the honesty banner (wash-hot is a warm *neutral* at C .02); opponent chips; the SIT and locked chips; K/DST; feeds and news; the segmented control; switches and sliders (cream); avatars; sparklines (`muted` line, hue only on the end-dot).

### 4.3 What colour may never encode

- **A verdict.** START / SIT / TOSS-UP stay fill / ghost / dash. No hue on a chip but gold. This is the owner's first rejection and the standing constraint.
- **A state judgement by red or green.** Q/D/O/IR, urgency, matchup grade, HOT/COLD, positive/negative are weight-and-count first; where they take a hue it is the warm pole (gold family) or the cool pole (slate) — never a red, never a green, never a mid-lightness block.
- **A word.** No hue on a word of more than three characters, on any page, ever. `HOT`, `SMASH`, `ESPN`, `DO NOW` are cream; the hue rides beside them.
- **A second meaning.** Each hex has one job (Apple: "Avoid using the same color to mean different things" — [HIG Color](https://developer.apple.com/design/human-interface-guidelines/color)). The one designed exception is the brand family, where `brand-red` means "ESPN's red" on a dot and "YouTube's red" on a play glyph — both "that brand's colour", never a judgement, and the object beside it names the brand.
- **Anything the greyscale loses.** Every hue is redundant with a code, a count, a glyph, a ring or a fill weight. Print it grey and it still reads (WCAG 1.4.1).

### 4.4 Reduce Transparency, Increase Contrast, the widget

| setting | what happens to the palette |
|---|---|
| **Reduce Transparency** | The native ground flattens to `#0A0C12` (SPEC §9) — every glow disappears, so page identity survives only in the tab glyph and the league dot. Every Tier-A hex was checked on flat canvas: ≥ 8.5:1 as text, ≥ 7.5 as a fill. Cards and floats go solid `panel`; `wash-cool` stays (it is a solid). |
| **Increase Contrast** | Text: `muted #C4C2BA`, `dim #ABADB3` (SPEC §4.2), `disabled #8A8E97` (3.9 min). Hues: the `-hc` variants in `palette.json` — each Tier-A hex lifted L +0.04 and cut C −0.02 on the same hue (gold `#FAC657` 8.2 min, cool `#AFB9C4` 6.5, QB `#FAB1D9` 7.6, RB `#8CDEC4` 8.2, WR `#97D3F8` 8.0, TE `#FDB99A` 7.8, red `#FFA4A4` 6.8, violet `#D1B0F8` 7.0, aqua `#8CEBEA` 9.3, ink-blue `#B0C8F4` 7.7, stone `#C2BEBA` 7.0). Any hue fill gains a 1px `hairline-2` ring; glows drop to 0; cards go solid with the spec's 50 % white border. |
| **Glass over colour** | Cream on the 52 % glass stand-in directly over a Tier-A fill is 3.7–4.8:1 (aqua 3.7, gold 4.1, RB 4.1, WR 4.1, QB 4.3, TE 4.3, violet 4.6, red 4.7); with the scroll edge effect's ~35 % dim beneath it is 6.3–7.4. So `.scrollEdgeEffectStyle(.soft)` stays load-bearing (SPEC §3) and **position hues are codes, not fills, on rows** — a two-letter code changes what the bar samples by a few pixels; a 24px fill under a 44pt label is a legibility event only the edge effect rescues. |
| **The widget (iOS 18+ accented mode)** | Renders as the user's tint plus alpha — every hue is stripped ([WidgetKit accented](https://developer.apple.com/documentation/widgetkit/widgetrenderingmode/accented)). Position = a 3px left rule per row (drops harmlessly); verdict = the START fill (survives as alpha); status = the letter; nothing depends on hue. In full-colour mode the widget uses the same tokens on `canvas`. |
| **Reduce Motion** | nothing changes; no hue animates. |

---

## 5. The hue rule — replacement for "no green, no red anywhere"

The old rule (SPEC §1.1) was a blanket ban: no hue 70–170° and none < 20° or > 340° at saturation ≥ 0.08, anywhere. It did its job — it kept the traffic light out — but it also bans a teal RB and a peach TE, which are category labels the user already reads, not judgements. The replacement bans the *thing that was cheap* (a green or red that tells you what to think) and lets colour label what it labels. Stated so a critic can run it:

> **R1 — Signals are never red or green.** A colour that encodes a verdict, a state or a judgement (START/SIT/TOSS-UP, Q/D/O/IR, urgency, matchup grade, HOT/COLD, positive/negative) may only be: the warm pole (OKLCH hue 80–92°, C ≤ 0.17 — gold and straw), the cool pole (hue 245–265°, C ≤ 0.05 — slate), or a neutral (C ≤ 0.02). In HSV: hue 38–48° at any saturation; hue 205–225° at saturation ≤ 0.25; or saturation ≤ 0.08. Never OKLCH 0–40°/350–360° (red) or 120–185° (green) above C 0.02.
>
> **R2 — Categories may sit in any family, at obsidian chroma and lightness.** A colour that labels a nominal thing the user already colour-codes (positions, leagues/brands, source kinds, page identity) may take any hue, including the red and green families, but only inside Tier A: OKLCH L 0.76–0.86 and C 0.02–0.14 (HSV value ≥ 0.72, saturation ≤ 0.62), and only on a carrier of fixed size: a ≤ 3-character code at ≥ 11px/700, a dot ≤ 8px, a ring ≤ 2px, a rule 2–3px, a glyph ≤ 14px, or a fill ≤ 24px tall under `chip-ink`. Never a word, a row, a card, a bar.
>
> **R3 — Nothing lives in the middle.** No fill that carries ink at OKLCH L 0.45–0.65; no chroma above 0.17 anywhere; washes at L 0.22–0.31 and C ≤ 0.05; glows at L 0.55 C 0.10 at ≤ 30 % with a composite luminance ≤ 0.0312.
>
> **R4 — Text is the ladder.** `text`/`muted`/`dim`/`disabled`/`nav-text-2` and nothing else, C ≤ 0.02; hue on text only as a ≤ 3-character code or a deciding numeral.
>
> **R5 — Every pair passes.** Text ≥ 4.5:1 and non-text ≥ 3:1 against canvas, panel, raised, the brightest ground pixel `#2A3145` and the 78 % card over it; every fill ≥ 4.5 under `chip-ink`.

The test, as the critic runs it:

1. **Token test** — `python3 design/palette/palette_verify.py --check`. Every token carries a role; R1–R5 are evaluated per role and the script exits non-zero on any violation. Under the old scan three tokens flag — `pos-rb` (green band), `pos-te` (HSV 18.7°, red band by 1.3°), `brand-red` — and under R2 all three pass, which is the whole point of the change; every signal token passes R1.
2. **Pixel test** (replaces the old `hues.py` pass): on each rendered frame, no connected region **≥ 24 × 24 px** with HSV saturation ≥ 0.45 in green (70–170°) or red (< 20° or > 340°). Code-sized text pixels are allowed; blocks are not. This is the test that catches a green START chip, a red page or a red row and lets a two-letter peach `TE` through.
3. **Word test** — on each frame, every text node with a computed colour of chroma > 0.02 has ≤ 3 characters or matches the numeral pattern `^[0-9WK:.%−+ ]+( (AM|PM)( ET)?)?$`.
4. **Count test** — per frame, distinct chromatic colours (C > 0.02) in the content layer ≤ 7, and the sets {position codes} and {source tints} never both non-empty.
5. **Greyscale test** — desaturate the frame; every element in the count test must still be identifiable by a code, count, glyph, ring or fill weight (the spec's existing check).

---

## 6. Judge it by eye, then the diff

`swatches.html` (this folder; generated, so its numbers cannot drift from `palette.json`): the five tab identities with their glows and tinted glyphs, the six positions as code / fill / rule side by side, three rows (a Lineup row with a START chip beside an RB code, a Do-now row with a Q pill and a TOSS-UP beside a WR code and a TOUGH meter, an AVOID row on `wash-cool`), the five-step matchup ramp, the three league capsules, the honesty banner, the status pills, HOT/COLD, the six source categories, then every token as a swatch with its ratios, the glass-over-colour table and the separation table.

What changes in `tokens.obsidian.*` if this is adopted (for the obsidian agent; nothing here edits that folder): add `disabled`, `straw`, `cool`, `pos-qb/rb/wr/te`, `brand-red/violet/aqua`, the five glows and their alphas, `wash-cool`; rename `mint` → `ink-blue` and `coral` → `stone` (hexes unchanged); retire `wash-good`, alias `wash-bad`/`wash-cold` → `wash-cool`; `meter-hi` stays gold, add `meter-good` = straw and `meter-tough` = cool; rewrite SPEC §1.1's scan as §5 above; per-destination `.tint` in `ObsidianBottomBar` and a per-page light 2 in `ObsidianGround`.

Open for the owner: (a) RB at 172° (teal-mint) or 180° (teal) — by eye; (b) TE peach at ΔE 0.10 from gold, or TE = `stone` if it still reads as gold in the frames; (c) the YouTube play glyph in `brand-red` or in `muted`; (d) per-page tab tint (this document) or Apple's single gold tint with the glow alone carrying identity.

---

## Sources

- Apple, HIG — Color (system colour table; Liquid Glass colour guidance; "avoid using the same color to mean different things"): https://developer.apple.com/design/human-interface-guidelines/color
- Apple, HIG — Dark Mode: https://developer.apple.com/design/human-interface-guidelines/dark-mode
- Apple, HIG — Materials (scroll edge effect; vibrant colours on materials): https://developer.apple.com/design/human-interface-guidelines/materials
- Apple, WWDC25 session 219 "Meet Liquid Glass": https://developer.apple.com/videos/play/wwdc2025/219/
- Apple, WidgetKit accented rendering mode: https://developer.apple.com/documentation/widgetkit/widgetrenderingmode/accented
- Google, Material — Dark theme (desaturation, limited accents, 4.5:1): https://m2.material.io/design/color/dark-theme.html
- W3C, WCAG 2.2 — relative luminance, 1.4.1, 1.4.3, 1.4.11: https://www.w3.org/TR/WCAG22/
- Björn Ottosson, OKLab / OKLCH: https://bottosson.github.io/posts/oklab/
- Datawrapper, "What to consider when choosing colors for data visualization" (the seven-colour ceiling): https://www.datawrapper.de/blog/colors
- Refactoring UI, "Building your color palette": https://refactoringui.com/previews/building-your-color-palette
- Sleeper position colours (shipped bundle) and DLS tokens: https://sleepercdn.com/sleeper-web/_next/static/chunks/2c7a3r5pyddzv.js , https://sleepercdn.com/sleeper-web/_next/static/chunks/2b7avkr6fu8y5.css ; League Legend: https://support.sleeper.com/en/articles/4584482-league-legend
- ESPN Fantasy OPRK and injury colours (shipped): `cdn1.espn.net/kona/…/main-82d208d52efd2b467c49.js`, `…/page/football/players/projections.js`; ESPN.com injuries CSS `injuries-2dcab3bb.css`
- Yahoo matchup and status conventions: https://help.yahoo.com/kb/SLN6390.html , https://help.yahoo.com/kb/SLN9034.html ; live purple computed on https://football.fantasysports.yahoo.com/f1/draftanalysis
- FantasyPros matchup stars (monochrome count): https://support.fantasypros.com/hc/en-us/articles/360038154454-What-does-the-Matchup-Star-Rating-mean ; position tag CSS: https://dwcdnstatic.fantasypros.com/assets/css/min/base/mcu-player-positions-f5a107ebcc9fe6bdf72ac0b08e31c979.css
- Underdog position tokens: `app.underdogsports.com/css/entry.app.b5f2e70389f37dbb.css`
- Trademark: *Qualitex Co. v. Jacobson Products*, 514 U.S. 159: https://supreme.justia.com/cases/federal/us/514/159/ ; nominative fair use: https://harriganip.com/blog/nominative-fair-use-trademark-law/
- Marketing Brew on the 2026 "ESPN red": https://www.marketingbrew.com/stories/2026/03/09/espn-brand-identity ; Yahoo brand purple: https://brandcolors.net/b/yahoo
- The two surveys this stands on: `design/palette/CONVENTIONS.md`, `design/palette/DARK_MULTIHUE.md` (both 2026-09-10, with their own full URL lists).
