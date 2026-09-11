# The colours fantasy players already know

Status: research, not a spec. Feeds the palette work that follows the owner's direction ("use different colours, intuitively, across the app and across pages; keep text readable and consistent"). Nothing under `design/obsidian/`, `engine/` or `ios/` was touched. Where a recommendation collides with the current Obsidian hue rule (SPEC §1.1, being revised separately) it is flagged, not resolved.

Method, so it can be rerun: on 2026-09-10 the shipped web CSS/JS of Sleeper, ESPN Fantasy, ESPN.com, Yahoo Fantasy, Underdog and FantasyPros was fetched and grepped, and computed styles were read off live public pages in a browser. NFL Fantasy no longer exists as a product (it was folded into ESPN for 2026), so its values come from a September 2024 Wayback capture of its stylesheet and icon sprite. Help-centre articles supply the *meaning* of colours where the CSS only supplies the value. Every hex below is either copied from those sources (marked **shipped**) or read from a computed style (marked **computed**); nothing is from memory. Contrast figures are WCAG 2.x relative luminance against the Obsidian grounds (`canvas #0A0C12`, `panel #12151D`, and the worst-case lit pixel `#2A3145` from SPEC §1.2).

---

## 0. The short version

| Element | Is there a convention? | Strength | Adopt? |
|---|---|---|---|
| Position colour | Yes for **QB** (red-violet band) and **RB** (teal band). WR/TE are a blue/orange *pair* whose assignment flips between products. K/DST are noise. | QB, RB strong; WR, TE weak (Sleeper plurality); K, DST none | QB, RB yes; WR, TE follow Sleeper; K, DST neutral |
| Platform identity | ESPN = red, Yahoo = purple, Sleeper = navy + cyan/teal. Universally known. | Strong | Yes, as a small tag with the name in plain text. Never the logo. |
| Matchup scale | Green = easy, red = tough, everywhere (Sleeper, ESPN, Yahoo). FantasyPros stars are a **blue count**, no hue. | Strong, but it is exactly the traffic light the owner rejected | No hue endpoints. Keep count + weight (FantasyPros proves it works); tint warm→cool only as a wash. |
| Injury status | Two tiers: **Q/D = yellow/orange**, **O/IR = red** (Sleeper, ESPN.com, NFL). ESPN Fantasy and Yahoo use *one* red for every letter. | Strong on the two-tier idea; the **letter** carries the meaning in every product | Letter always; two-tier severity via warm hue (Q/D) and weight or brick (O/IR), see §4 |
| Text on coloured labels | Colour lives in a fixed-shape carrier (dot, underline, chip ink, pastel fill); the type scale never moves | Strong, consistent across all six | Yes, as a rule |
| Source category | Platform brands (YouTube red, Spotify green, Apple Podcasts purple, Substack orange) | Known, but sources are faces here | Glyph tint only, never a fill |
| Page identity | No fantasy product colours its pages; each has one brand hue | None | Free territory, but nearly every hue is already spent (see §6) |
| Urgency groups | No product convention | None | Weight + gold rule (existing) |
| Streak HOT/COLD | Fire/orange vs ice/blue is cultural, not product-verified | Medium | Fine as a tint; never as the only channel |

---

## 1. Position colours

### 1.1 What each product ships

Only three of the six colour positions at all. ESPN, Yahoo and (until it closed) NFL Fantasy render the position as grey text — so most season-long players have **no** position-colour habit, and the habit that exists is Sleeper's.

| Product | QB | RB | WR | TE | K | DEF/DST | Carrier | Source |
|---|---|---|---|---|---|---|---|---|
| **Sleeper** (app colour function, NFL branch) | `#FC2B6D` pink-red | `#20CEB8` teal (FB same) | `#59A7FF` blue (WR1–3 same) | `#FEAE58` orange | `#C96CFF` purple | `#BF5F40` rust | Coloured **text** on transparent, 12px/500; BN `#A3BBD3`, FLEX `#333333` | **shipped** — `sleepercdn.com/sleeper-web/_next/static/chunks/2c7a3r5pyddzv.js?dpl=0-2-0-1294--ae02e55` (`case"qb":s="#FC2B6D"` …). **computed** on https://sleeper.com/nfl/scores/ne-patriots-sea-seahawks-2026-09-09: QB `rgb(252,43,109)`, RB `rgb(32,206,184)`, WR `rgb(89,167,255)`, TE `rgb(254,174,88)` |
| **Sleeper** (2026 web "DLS" player pages) | `#FF005C` | `#029855` text / `#28E757` fill | `#00D7FF` aqua | `#FFAB0E` amber | `#0055FF` blue | — | Coloured text on a uniform dark chip `#0B1028` with uniform border `#2D3650`, 12px/700; the page-hero badge is a **fill** with navy ink `#131B38` | **computed** on https://sleeper.com/nfl/players/jeremiyah-love-13287 and https://sleeper.com/nfl/players/aj-brown-5859 |
| **Underdog** (app CSS tokens) | `#9647B8` purple | `#15997D` teal-green | `#E67D23` orange | `#297FB9` blue | — (no K) | — (no DEF) | Tokens `--nfl-qb/rb/wr/te`; FLEX `#C8384A`, SFLEX `#C73893` | **shipped** — the `:root` rule among the stylesheets loaded by https://app.underdogsports.com/login (`entry.app.b5f2e70389f37dbb.css` et al.; read in-browser because Cloudflare blocks curl) |
| **FantasyPros** (Draft Wizard / My Playbook position tags) | `#C8A1FF` lavender | `#83DCEF` sky | `#85DE9E` mint | `#FF8AA2` pink | `#FDB97C` peach | `#BDC3CD` grey | Pastel **fill**, dark ink `#16191D` on every tag; `-light` variants at half strength; IDP all `#F6E5AB`; BN `#EBEEF4` | **shipped** — https://dwcdnstatic.fantasypros.com/assets/css/min/base/mcu-player-positions-f5a107ebcc9fe6bdf72ac0b08e31c979.css |
| **FantasyPros** (rankings tables) | — | — | — | — | — | — | Neutral `#16191D` text, 12px/400, on white/`#F5F5F5` rows | **computed** on https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php |
| **ESPN Fantasy** | — | — | — | — | — | — | Grey `#797B7D` text, 12px/400 (`.position-eligibility`) | **computed** on https://fantasy.espn.com/football/players/projections |
| **Yahoo Fantasy** | — | — | — | — | — | — | Grey `#61697C` text, 12px/500 (`"Buf - QB"`) | **computed** on https://football.fantasysports.yahoo.com/f1/draftanalysis |
| **NFL Fantasy** (defunct 2026) | — | — | — | — | — | — | Grey `#777777` position nav; no per-position hue | archived CSS, https://web.archive.org/web/20240919172514/https://fantasy.nfl.com/research/players ; shutdown: https://espnpressroom.com/feature/nfl-fantasy-is-moving-to-espn-fantasy-your-questions-answered/ |

Sleeper's own tokens also carry a second, lighter "picked" set (`--color-dls-picked-qb #FF80AD`, `-rb #49E8CC`, `-wr #49D0EE`, `-k #B7C1EE`) in the same hue families — presumably the draft-board "picked" fills (shipped in `2b7avkr6fu8y5.css`; not observed rendered).

### 1.2 Where they agree

Hue is HSV degrees; the band is what matters, not the exact value.

| Position | Sleeper | Sleeper DLS | Underdog | FantasyPros | Agreement |
|---|---|---|---|---|---|
| QB | 341° pink-red | 338° | 282° purple | 265° lavender | **All three sit in the red-violet band 265–345°.** Nobody uses blue, green or orange for QB. Majority family: **magenta/violet**. Plurality value (largest user base): Sleeper `#FC2B6D`. |
| RB | 172° teal | 153° green | 167° teal-green | 191° sky | **All within 153–191°, the teal band.** Majority: **teal ~170°**, value `#20CEB8` (Sleeper and Underdog are 5° apart). |
| WR | 212° blue | 189° aqua | 28° orange | 137° mint | **No majority.** Sleeper blue is the plurality by users. |
| TE | 31° orange | 39° amber | 204° blue | 348° pink | **No majority.** Sleeper orange is the plurality. Note Sleeper and Underdog use the *same pair* (blue + orange) for the two pass-catchers and assign it opposite ways. |
| K | 278° purple | 220° blue | — | 28° peach | Noise. |
| DEF | 15° rust | — | — | 218° grey | Noise; FantasyPros' grey is the sensible precedent. |

Reading: **QB = magenta-ish, RB = teal** is what a fantasy player has already learned if they have learned anything. WR blue / TE orange is not a convention, it is "what Sleeper does" — which is still the best available default because the ESPN/Yahoo majority has no habit to contradict it and Sleeper's is the only habit in the room.

### 1.3 Majority convention hex, and an Obsidian-tuned equivalent

The "majority hex" is the shipped value from the product(s) in the majority. The Obsidian column keeps the hue and lifts value/lowers saturation so the colour works as **12px/500 text on the worst-case ground** (≥ 4.5:1 at `#2A3145`) and as a **fill under `chip-ink #101B33`** (≥ 4.5:1). All numbers computed.

| Position | Majority hex (shipped) | Obsidian-tuned | Hue | vs canvas | vs panel | vs worst | chip-ink on it | Note |
|---|---|---|---|---|---|---|---|---|
| QB | `#FC2B6D` (Sleeper) | **`#F06CC2`** | 321° | 7.1 | 6.6 | 4.7 | 6.2 | Slid 20° toward violet: still inside the QB band, meets the current rule's red cut-off (>340°) with margin, and no longer reads as "red". |
| RB | `#20CEB8` (Sleeper ≈ Underdog `#15997D`) | **`#3ED7C1`** | 171° | 10.9 | 10.2 | 7.2 | 9.5 | Sits 1° outside the current green ban (70–170°). Flag: SPEC §1.1 as worded would need a 1° tolerance or an explicit "category colours" carve-out. Pushing to 180° (cyan) breaks the RB convention and collides with the Sleeper tag. |
| WR | `#59A7FF` (Sleeper, plurality) | **`#6FB4FF`** | 211° | 9.0 | 8.4 | 5.9 | 7.9 | Close to `mint #9DBBF3` (219°); if WR blue is adopted, `mint` should stop meaning "positive" (see §3.3). |
| TE | `#FEAE58` (Sleeper, plurality) | **`#FFA857`** | 29° | 10.2 | 9.6 | 6.8 | 9.0 | 14° from gold (43°). Distinguishable side by side, but a TE tag must never be a *fill* next to a START chip; use it as text or a hairline ring. |
| K | none | `dim #909298` (existing) | — | 6.3 | 5.9 | — | — | Neutral, as FantasyPros does for DST. If a hue is wanted, lavender `#BCA6F0` (258°) is free and reads 6.1 on worst. |
| DEF/DST | none | `dim` or `coral #BDB0A0` stone (existing) | — | 9.2 | 8.6 | 6.1 | 8.1 | Neutral. |

Position colours in the products are **text colours or pastel fills at 12px, never row washes**. Sleeper colours only the two letters; the name beside it stays white. That is the model to copy: position ink on a fixed chip, everything else on the cream scale.

---

## 2. Platform / league identity colours

| Platform | Hue users know | Value the product ships | Obsidian-tuned tag | vs worst | Source |
|---|---|---|---|---|---|
| ESPN | Red | Their fantasy CSS uses `#C00`/`#D00` for everything "red" (`--icon-redX-color:#d00`, injury text `#c00`); brand-reference sites list the logo as `#E52534` (PMS Red 032) or `#FF0033` | `#F0605F` (0°, sat .60) — **inside the current red ban; flag** | 4.0 (text fails AA at the worst pixel; 5.7 on panel) | ESPN CSS `cdn1.espn.net/fitt-v3/…/fusion-db0c8d23.css`; https://www.color-name.com/espn-red.color ; https://chromacreator.com/brands/espn |
| Yahoo | Purple | `#6001D2` — the live search button on football.fantasysports.yahoo.com (**computed** `rgb(96,1,210)`), Yahoo's "Grape Jelly" | `#B48CFF` (261°) | 5.0 | https://football.fantasysports.yahoo.com/f1/draftanalysis |
| Sleeper | Near-black navy ground with a cyan/teal accent | Ground `#05091D` (`--color-dls-gray-900`, body **computed** `rgb(5,9,29)`); primary `#00FFF9` / `#03C3C5` (`--color-dls-primary-300/500`); legacy teal `#00CEB8` still in gradient tokens | `#4FE0E8` (183°) | 8.1 | `sleepercdn.com/…/2b7avkr6fu8y5.css`; https://api.sleeper.app/branding (press kit) |
| Underdog | Yellow on black/green | `--yellow-500: #FFFF00`, `--neutral-black: #01070E`, `--green-500: #00D455` | not needed (not a league host for this app) | — | `app.underdogsports.com/css/entry.app…css`; App Store screenshots |

**Helpful or a trap?** Helpful, with three fences:

1. **Colour alone is not their trademark.** A single colour is protectable only once it has acquired secondary meaning for that source and is non-functional (*Qualitex Co. v. Jacobson Products*, 514 U.S. 159 (1995): https://supreme.justia.com/cases/federal/us/514/159/). "Red" for a sports network or "purple" for a web portal has never been asserted against a third-party app that merely names the service, and no single-colour registration for fantasy software is publicly cited for any of the three (this survey did not query the USPTO register; do that before shipping if counsel wants certainty). Risk is low, not zero.
2. **The name in plain text is nominative fair use.** Naming "ESPN league" / "Yahoo league" / "Sleeper league" to identify where the roster lives is the textbook case; what sinks nominative use is the *logo*, the wordmark's typography, or copy that implies endorsement (https://harriganip.com/blog/nominative-fair-use-trademark-law/ ; https://www.worldtrademarkreview.com/article/united-states-how-use-third-party-mark-without-infringing-it). So: plain type in the app's own font, a coloured dot or 2px rule, never a glyph that resembles the mark, and one "not affiliated with ESPN, Yahoo or Sleeper" line in Settings/onboarding.
3. **Keep the colour small.** A red *page* reads as "an ESPN page"; a red *dot* beside "ESPN · Kid's Table" reads as a label. The products themselves do this at 8px (ESPN's status dot) and 2px (NFL's underline).

Practical: tag = 8px dot or 2px left rule in the platform hue + the platform name in `dim` text on the cream scale. The ESPN tag is the one place the app would carry a red-family hue; if the hue rule stays, ESPN gets the stone `coral #BDB0A0` and the name does the work (users will not miss red — ESPN and Yahoo users have never had a coloured league tag).

---

## 3. Matchup / difficulty scales

### 3.1 What each product does

| Product | Scale | Hues | Carrier | Source |
|---|---|---|---|---|
| **Sleeper** | Opponent label, three levels | Green = favourable, orange/yellow = average, red = tough | Coloured **text** of the opponent abbreviation | https://support.sleeper.com/en/articles/4584482-league-legend ("color-coded label… quality of the expected matchup") |
| **ESPN Fantasy** | OPRK 1–32, three bands | rank ≤ 10 → `#C00` red (tough); 11–20 → `#48494A` grey; > 20 → `#009444` green (easy). Same pair colours ± deltas. | Coloured **number** | **shipped** — `cdn1.espn.net/kona/5a90d30cd38d-1.490/_next/…/page/football/players/projections.js` module 108 (`n=Math.floor(32/3)`, `a<=n?red : a>2n&&green`) and module 24 (`"#C00"`, `"#009444"`); definition string "Low numbers mean it may be a tough opponent" in `main-82d208d52efd2b467c49.js` |
| **ESPN.com** editorial matchup rating | 0–100 | red = highly unfavourable, yellow = solid, green = highly favourable | Coloured grade | https://www.espn.com/fantasy/football/insider/story/_/id/23893301/measuring-schedule-strength-fantasy-football |
| **Yahoo** | Opponent rank | Green = "Easy matchup", grey = "Mild matchup", red = "Difficult matchup" | Coloured text | https://help.yahoo.com/kb/SLN6390.html |
| **Yahoo** | Matchup Rating, 5 stars | Green = top-10 matchup, yellow = 11–22, red = 23–32 | Stars + hue | https://help.yahoo.com/kb/SLN9034.html |
| **FantasyPros** | Matchup Star Rating, 1–5 | **One blue** `#366ACB` for filled, `#CBCBCB` empty — no hue scale at all | Star **count** | **computed** on https://www.fantasypros.com/nfl/rankings/ppr-flex.php (`.template-stars-star-filled`); meaning: https://support.fantasypros.com/hc/en-us/articles/360038154454-What-does-the-Matchup-Star-Rating-mean ("1-2 stars = worse than average… 4-5 = better") |
| **FantasyPros** | Upside / Bust meters | segments `#2ABB7F` green (`is-good`), `#E2483D` red (`is-bad`), `#E2E7EE` empty | Segment count + hue | same page (`.mcu-rating-meter__segment`) |

Every product that uses hue uses **green = attack, red = avoid**, with grey/yellow in the middle. That is the strongest convention in this whole survey — and it is precisely the traffic light the owner rejected on sight, so its strength is a reason to be careful, not a reason to adopt it.

### 3.2 Does a temperature scale read without green/red endpoints?

The evidence that a matchup scale survives without hue: FantasyPros — the largest advice site in the category — ships its matchup rating as a **monochrome count** (blue stars) and users read it fine; the number of stars is the signal. Yahoo's stars carry hue *and* count; nobody complains that FantasyPros' don't. So: **count and weight are sufficient; hue is a bonus channel.** The current SPEC §5.4 meter (five pips, gold for smash/good, cream neutral, dim for tough/avoid, label word beside it) is already a FantasyPros-shaped scale and needs no hue endpoints.

Warm = good, cool = bad is intuitive in the *heat-map* sense (weather, "hot hand", "on fire") but it has a known ambiguity in *this* domain: "hot defense" means tough, "cold offence" means avoid, and Sleeper/ESPN/Yahoo have trained people that the warm end (orange/red) is the **bad** end of a matchup. Two of three hues on their scale are warm. A warm-good scale therefore reads correctly only when a **word or a count** anchors it; with the pip count and the SMASH…AVOID label present, gold→cream→slate is safe. Without them it is not.

Rules that follow:
- Never a warm-vs-cool tint as the *only* channel on a matchup. Count + word first; tint third.
- Do not use yellow/amber as the *middle* of the scale — Sleeper's "average" is orange, ESPN.com's "solid" is yellow, so an amber middle would read as "meh" to Sleeper users while gold means "smash" here. Keep the middle **cream**.
- The avoid end stays a cool or dark neutral (`dim`, slate), never a warm colour and never red.

### 3.3 One inconsistency to fix in the current tokens

SPEC §1 has `mint #9DBBF3` = "positive = ink-blue" and `wash-good #141E32` = a blue wash, while `meter-hi` (smash/good pips) is **gold**. That is two metaphors: "cool = good" in the washes, "warm = good" in the meter. If WR takes blue (§1.3) a blue wash under a good matchup would also read as a WR row. Recommendation: one metaphor — warm = attack (gold meter, warm `wash-good`), cool/dark = avoid — and retire `mint`/`coral` as *semantic* names (keep the hexes as `ink-blue`/`stone`).

---

## 4. Injury / status conventions (Q / D / O / IR)

### 4.1 What each product does

| Product | Q | D | O | IR | Other | Carrier | Text | Source |
|---|---|---|---|---|---|---|---|---|
| **Sleeper** (2026 web) | white on `#FF7A00` orange pill | (not observed) | white on `#D54033` red pill | white on `#D54033` | PUP same red | Filled capsule, 10–12px/600 uppercase, full word ("QUESTIONABLE", "OUT") | white on the fill | **computed** on the Sleeper player pages above; tokens `--color-dls-decoration-orange-200 #ff7a00`, `--color-dls-alert-error-100 #d54033` |
| **ESPN Fantasy** (web app) | `#C00` | `#C00` | `#C00` | `#C00` | SSPD `#C00`; healthy `#4A4A4A` | Letter as coloured **text**, 11px, after the name | red letter | **shipped** — `.playerinfo__injurystatus{color:#c00}` `.playerinfo__healthystatus{color:#4A4A4A}` in `main-82d208d52efd2b467c49.js` (styled-jsx `2813592384`); player-card injury type: white on `#B80000` |
| **ESPN.com** injuries page | 8px dot `#FFCE07` yellow | dot `#FFCE07` | dot `#C00` | dot `#C00` | a green variant `#009444` exists in the CSS (not mapped to a status on the page observed) | 8px dot **before** grey text | text stays `#6C6D6F` | **computed** on https://www.espn.com/nfl/injuries (`TextStatus--yellow` / `--red`); rule `.TextStatus--red:before{background-color:#c00}` in `injuries-2dcab3bb.css` |
| **Yahoo** (web) | `#C11629` on `#FFF2F4` pill | (not observed) | **same** `#C11629` on `#FFF2F4` | — | — | Tiny pill, 10px/700 | red ink | **computed** on https://football.fantasysports.yahoo.com/f1/draftanalysis |
| **NFL Fantasy** (2024, defunct) | `#404041` letter, 2px underline `#F4CF3B` yellow | underline `#F4CF3B` | underline `#FF3636` red | underline `#FF3636` | P/FP/LP/DNP grey underline; IA/PUP/SUS/COV red | Grey letters, **coloured underline** | letters stay dark grey | sprite `fantasy.nfl.com/static/img/iconSpritePlayers_1726509901.png` via Wayback (pixels sampled); player-card `.out{#c80611}` `.probable{#e6e42d}` `.go{#00a601}` |

### 4.2 What users rely on

- **The letter is present in every product**, including the two (ESPN Fantasy, Yahoo) that colour every designation the same red. Colour is never the sole channel; a user who cannot tell Q from O by hue has never been able to on the two biggest platforms.
- Where a second tier exists (Sleeper, ESPN.com, NFL) it is always the same split: **Q/D warm-yellow/orange ("might play"), O/IR/PUP/SUS red ("will not")**. Nobody uses three tiers; nobody colours "D" differently from "Q".
- Sleeper is the only one that fills the pill; the other three keep the text neutral and put colour in a dot, an underline, or the letter itself.

### 4.3 Recommendation

Keep SPEC §5.2 ("weight, never hue") as the floor — it matches ESPN Fantasy/Yahoo, where the letter alone works. On top of it, the two-tier convention is strong enough to adopt **as a hint**:

| Tier | Letters | Obsidian carrier | Hex | Hue | vs worst | Flag |
|---|---|---|---|---|---|---|
| Might play | Q, D | letter in warm orange text, or a 2px orange underline (NFL pattern) | `#FF9A3D` | 29° | 6.1 (text passes) | 14° from gold; keep it as text/underline, never a fill, so it cannot be mistaken for a START chip |
| Will not play | O, IR, PUP, SUS, NA | **weight**: filled `raised-2` capsule + letter in `text`; optionally a brick underline | `#E0705A` | 10° | 4.1 (fails as 11px text; passes 3:1 as an underline) | **Inside the current red ban.** If the ban holds, the weight carrier alone is enough — ESPN Fantasy and Yahoo prove a single treatment works. |

Never colour the row, never colour the name. The pill is 10–12px, so the colour must be at ≥ 3:1 as a non-text mark and the letter must pass 4.5:1 on its own.

---

## 5. How the products keep text consistent while labels vary

The same trick, six ways: **the type scale is fixed and colour is poured into a small container of fixed shape.**

| Product | Body text | Where colour goes | What stays put |
|---|---|---|---|
| Sleeper (scores page) | White `#FFFFFF` names, `#98B3D6` secondary, `#4C5E93` tertiary on `#05091D` | The two-letter position **ink** at 12px/500; opponent abbreviation ink for matchups | Name size/weight, row layout, chip size |
| Sleeper (player page) | White on `#0B1028` chips | Position ink only — chip fill `#0B1028` and border `#2D3650` are the **same for every position**; status is the one filled pill, always white 10–12px/600 uppercase | Chip geometry, border, type |
| ESPN.com | `#6C6D6F` / `#2B2C2D` grey text, 12px/600 | An **8px dot** before the word | The word itself is never coloured |
| ESPN Fantasy | `#4A4A4A` | The status **letter** at 11px, one colour | Everything else |
| NFL Fantasy | `#404041` letters | A **2px underline** | Letter colour, size |
| FantasyPros | `#16191D` ink everywhere (`--text-color`), 12px/400 tags | **Pastel fills** at ~45% saturation chosen so the same dark ink passes on all of them (QB lavender 8.4:1 under their ink, TE pink 7.9:1, DST grey 10.0:1 — computed); stars in one blue | Ink colour, tag size |
| Yahoo | `#61697C` positions, `#232A31` names | A 10px/700 pill with pale fill | Name colour and size |

Rules to carry into Obsidian, in priority order:

1. **Ink never changes hue.** Names, numbers, reasons, times stay on `text / muted / dim`. The only text that takes a hue is a ≤ 2-letter code (position, status letter) or a numeral that is itself the grade (ESPN's OPRK). Gold numerals already follow this.
2. **Colour lives in a carrier with one geometry:** the 12px position code, an 8px dot, a 2px rule/underline, a 1.5px ring, a pastel fill behind dark ink. Pick two carriers for the whole app (recommend: **2px rule** for page/urgency/platform, **12px code ink** for position/status) and do not invent a third per page.
3. **If a fill is used, the ink on it is always `chip-ink #101B33`** (FantasyPros' one-dark-ink model). Every Obsidian-tuned hex in §1.3 clears 6:1 under `chip-ink`; none clears 2.5:1 under cream, so cream-on-colour is out.
4. **Same hue, same size everywhere.** The position code is 12px/500 in Sleeper regardless of the screen; a Trade Desk grid must not shrink it to 9px and expect the hue to survive.

---

## 6. The other elements in the brief

**Source categories (podcast / YouTube / newsletter / analyst / feed / news).** The colours people know are the platforms': YouTube `#FF0000`, Spotify `#1ED760`, Apple Podcasts purples `#B150E2`/`#872EC4`, Substack `#FF6719`, RSS orange (https://lockedownseo.com/social-media-colors/ ; https://brandpalettes.com/apple-podcasts-app-icon-2017-colors/ ; https://mobbin.com/colors/brand/substack). Two of those are the banned hues and all of them are trademark-adjacent when paired with a look-alike glyph. Since **sources are faces** (SPEC §5.5: avatar + gold ring for a creator, hairline ring for a feed), the category should be a tinted 12px glyph or ring at most: podcast `#C98BFF` (272°, 5.3 on worst), newsletter `#FF9A5C` (23°, 6.2), feed `#9AA6B8` slate (216°, 5.2), news `text` cream, analyst = the existing gold ring, YouTube = coral `#FF7A70` (4°, 5.1 — **red band, flag**; a neutral play-glyph is the fallback). Never a card fill.

**Page identity.** No fantasy product does it; each has one brand hue (Sleeper navy/cyan, ESPN red, Yahoo purple, Underdog yellow) on every page. So there is no user expectation to honour — but there is also almost no free hue: magenta (QB), teal (RB), blue (WR), orange (TE), yellow-gold (attention), red-family (injury/ESPN), purple (Yahoo/podcast), cyan (Sleeper) are all spoken for by §1–§4. Free bands are violet 250–270° (collides with Yahoo purple at a glance) and the slates. Recommendation: page identity through the **ground light** (SPEC §1.2 lights 1–3 already differ in hue) and the 2px rule, not through a new hue per page.

**Urgency groups (Do now / Before lock / This week).** No cross-product convention; the products signal urgency with the injury red and iOS signals it with red badges. Keep weight + the gold rule (existing). If one hue is spent here, only "Do now" gets it, and it should be the same warm orange as Q/D (`#FF9A3D`) so the app has one "heads-up" hue rather than two.

**Streak states (HOT / COLD).** Fire/orange for hot and ice/blue for cold is a cultural convention (heat maps, "on fire"), not one any of the six products ships for fantasy rosters; Sleeper's trending arrows are green (adds) / red (drops) per its League Legend. Safe as a tint on a glyph: ember `#FF8C42` (23°, 5.6 on worst) and ice `#8FB8E8` (212°, 6.3). Ice collides with WR blue at 12px, so the streak must carry a glyph (flame/snowflake) and the word, never the tint alone.

**Status pills Q/D/O/IR** — §4. **League identity** — §2. **Positions** — §1. **Matchup grades** — §3.

**The widget.** From iOS 18, Home Screen widgets can be rendered in *accented* mode, which flattens the whole view to the user's tint plus alpha (https://developer.apple.com/documentation/widgetkit/widgetrenderingmode/accented ; https://developer.apple.com/documentation/widgetkit/optimizing-your-widget-for-accented-rendering-mode-and-liquid-glass). Every hue above disappears there. The widget must therefore carry position, status and verdict as **letters and weight** (which the verdict chips already do) and treat colour as decoration it can lose — the same rule as §5.1, enforced by the OS.

---

## 7. Adopt / weak / noise

| Convention | Verdict | What to ship |
|---|---|---|
| QB in the red-violet band | **Adopt** | `#F06CC2` as 12px code ink / ring; fill only under `chip-ink` |
| RB in the teal band | **Adopt** (needs a 1° tolerance or a category carve-out in the hue rule) | `#3ED7C1` |
| WR blue / TE orange | **Weak — follow Sleeper** because the alternative is nobody | `#6FB4FF` / `#FFA857`; TE never as a fill beside gold |
| K, DST hues | **Noise** | `dim`; FantasyPros-style neutral |
| Platform tag: ESPN red, Yahoo purple, Sleeper cyan | **Adopt** as an 8px dot / 2px rule + plain name | `#F0605F` (**flag: red band**; fallback `coral` stone), `#B48CFF`, `#4FE0E8` |
| Matchup green→red | **Do not adopt** (the rejected traffic light) | Count + word + weight (SPEC §5.4); warm→cool tint as a wash only, with the metaphor made consistent (§3.3) |
| Status two-tier (Q/D warm, O/IR hot) | **Adopt as a hint** on top of weight | Q/D `#FF9A3D` text or 2px underline; O/IR weight (+ brick `#E0705A` underline **only if** the red ban is lifted) |
| Letter always present on a status | **Adopt** (universal) | `<abbr>` letter in `text`, as today |
| Colour in a fixed carrier, ink never changes | **Adopt** (universal) | Two carriers app-wide: 12px code ink, 2px rule |
| Source category = platform colour | **Weak** | Glyph/ring tint only; YouTube red flagged |
| Page identity hue | **No convention** | Ground light + rule, not a new hue |
| Urgency hue | **No convention** | Weight + gold rule; one warm "heads-up" hue at most |
| HOT/COLD fire/ice | **Cultural, medium** | Glyph + word + tint; never tint alone |
| Widget colour | **OS constraint** | Meaning in letters/weight; colour is droppable |

---

## Appendix A — contrast of the surveyed values on Obsidian (why they cannot be used as-is)

| Shipped value | On `canvas` | On worst `#2A3145` | Verdict for 12px text |
|---|---|---|---|
| Sleeper QB `#FC2B6D` | 5.3 | 3.5 | fails at the worst pixel |
| Sleeper RB `#20CEB8` | 9.9 | 6.5 | passes |
| Sleeper WR `#59A7FF` | 7.8 | 5.2 | passes |
| Sleeper TE `#FEAE58` | 10.6 | 7.0 | passes |
| Underdog QB `#9647B8` | 3.6 | 2.4 | fails (it is a fill under white in Underdog's dark UI) |
| Underdog RB `#15997D` | 5.5 | 3.6 | fails |
| Underdog TE `#297FB9` | 4.5 | 3.0 | fails |
| FantasyPros QB `#C8A1FF` | 9.3 | 6.2 | passes (designed as a fill under dark ink) |
| ESPN `#C00` | 3.3 | 2.2 | fails — ESPN's red only works on white |
| Yahoo `#6001D2` | 2.3 | 1.5 | fails — brand purple is for light UI |
| Sleeper status orange `#FF7A00` | 7.5 | 4.9 | passes |
| Sleeper status red `#D54033` | 4.3 | 2.8 | fails |

Which is why §1.3 and §2 lift values: the *hues* transfer, the *hexes* do not.

## Appendix B — files fetched (for a rerun)

- Sleeper web bundle chunks, `dpl=0-2-0-1294--ae02e55`: `2c7a3r5pyddzv.js` (position colour function), `2b7avkr6fu8y5.css` (DLS tokens). Public pages read: `/nfl/scores/ne-patriots-sea-seahawks-2026-09-09`, `/nfl/players/jeremiyah-love-13287`, `/nfl/players/aj-brown-5859`, `/nfl/players/jordyn-tyson-13281`, `/nfl/players/zach-charbonnet-9753`. Injured-player IDs came from https://api.sleeper.app/v1/players/nfl (`injury_status`).
- ESPN Fantasy: `cdn1.espn.net/kona/5a90d30cd38d-1.490/_next/static/commons/main-82d208d52efd2b467c49.js`, `…/page/football/players/projections.js`; ESPN.com: `cdn1.espn.net/fitt-v3/bbad313c521d-2.0.5531/client/espnfitt/injuries-2dcab3bb.css`, `…/css/fusion-db0c8d23.css`.
- Yahoo: computed styles on `football.fantasysports.yahoo.com/f1/draftanalysis`; help pages SLN6390, SLN9034.
- Underdog: `app.underdogsports.com/css/entry.app.b5f2e70389f37dbb.css` (via browser; curl is Cloudflare-blocked); App Store screenshots via `itunes.apple.com/search?term=underdog+fantasy&entity=software`.
- FantasyPros: `dwcdnstatic.fantasypros.com/assets/css/min/base/mcu-player-positions-f5a107ebcc9fe6bdf72ac0b08e31c979.css`; computed styles on `/nfl/rankings/ppr-cheatsheets.php` and `/nfl/rankings/ppr-flex.php`; support article 360038154454.
- NFL Fantasy (Wayback 2024-09-19): `fantasy.nfl.com/research/players` HTML, its bundled CSS, and `iconSpritePlayers_1726509901.png` (30×500 sprite; dominant colours sampled per 20px row).
- Shutdown of NFL Fantasy: https://espnpressroom.com/feature/nfl-fantasy-is-moving-to-espn-fantasy-your-questions-answered/ ; https://cordcuttersnews.com/the-nfl-is-phasing-out-its-fantasy-app-and-handing-fantasy-football-to-espn-heres-what-players-need-to-know/
- Trademark: https://supreme.justia.com/cases/federal/us/514/159/ ; https://harriganip.com/blog/nominative-fair-use-trademark-law/ ; https://www.worldtrademarkreview.com/article/united-states-how-use-third-party-mark-without-infringing-it
- Widgets: https://developer.apple.com/documentation/widgetkit/widgetrenderingmode/accented ; https://developer.apple.com/documentation/widgetkit/optimizing-your-widget-for-accented-rendering-mode-and-liquid-glass
