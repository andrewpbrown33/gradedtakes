# The Library — notes

Companion to `design/model/library.yaml` (78 entries, built and verified 2026-09-10).
The library is a **directory of real sources with links and metadata** that a Graded
Takes user can add to their own model on the Sources page. It is not a content list:
every third-party entry is `consent_status: link-only` until a creator signs the
one-page licence described in `design/plan/platform.md`.

## What "top" meant, and how each tier was ranked

There is no single ranking of fantasy sources, so "top" was built from four
signals, in this order of trust:

1. **Alive in September 2026.** Every podcast feed was resolved through Apple's
   iTunes lookup/search API (which returns the canonical `feedUrl` and the last
   `releaseDate`) and then the RSS itself was fetched and parsed. Anything whose last
   episode predates the 2026 season is flagged `dormant` or excluded (see below).
   Every YouTube channel page was fetched for its own `externalId`, and the
   subscriber count was read from YouTube's channel-search renderer (the number on
   the channel page's HTML is unreliable — it often belongs to a "related" channel;
   Harris Football reads 461K that way and 37.6K the correct way).
2. **Reach.** YouTube subscribers where a channel exists; Substack's own subscriber
   claims (Stealing Signals: 12,000+); Fantasy Life's "400,000+ readers" claim. Reach
   decides the order inside a tier, not whether a source gets in.
3. **Gradeability.** A source earns weight in this product only if it makes explicit,
   dated, checkable calls (start X over Y; add Z; "under" on a total). That is why
   the projection houses (4for4, Fantasy Points, ETR, CBS/Cummings, ESPN/Clay), the
   usage writers (McFarland, Gretch, Hribar) and the daily rankings shows sit at
   10–12, the football-first entertainment shows at 5–6, and the news wires at 0–2.
4. **Independence from each other.** FantasyPros' podcast and ECR both re-aggregate
   the same 130 rankers; consensus-flavoured sources were weighted down so a user's
   "room" does not accidentally count the same opinion three times.

`suggested_default_weight` uses the same 0–100 relative scale as `data/sources.yaml`
(the owner's engine sits at 17). The owner's own weights were left in place on the
`owner-uses` entries and the library suggests a *stranger's* default next to them —
e.g. Sharp or Square 17 → 8, because RSS blurbs from a betting show yield few
gradeable fantasy calls unless you paste the takes.

## Category-by-category decisions

**(a) Podcasts — 24.** The show-linked YouTube channels are attached to their podcast
entry (`youtube_channel`, `youtube_channel_id`) rather than listed twice. Several of
the requested shows changed networks in 2026 and the feed URLs in the library are the
*current* ones:

| Show | What changed in 2025–26 | Source |
|---|---|---|
| Fantasy Football Happy Hour (Berry) | Left NBC; audio now via Audacy from 2026-08-03, video on Berry's own YouTube | barrettmedia.com 2026-08-03 |
| Yahoo Fantasy Football with Josh & Hayden | Underdog shut its content network; Norris & Winks signed with Yahoo, show relaunched July 2026 | awfulannouncing.com |
| Fantasy Focus (ESPN) | Stephania Bell laid off 2026-07-21 after ESPN absorbed NFL Network; RSS author tag still lists her | awfulannouncing.com |
| Fantasy Football with Ian Hartitz | Hartitz left Fantasy Life for RotoWire, July 2026; new show | x.com/Ihartitz status 2072304757264314445 |
| Sharp or Square | Millman left Action Network; launched on The Volume/iHeart 2025-09-02 | barrettmedia.com 2025-09-02 |
| The Favorites | Relaunched 2025-09-10 with Kendra Middleton, Brandon Kravitz, Stuckey | actionnetwork.com |
| The Athletic Fantasy Football Podcast | Feed last published 2024-01-04 — **excluded as defunct** | iTunes lookup id 1477537533 |

**(b) YouTube — 6 stand-alone.** Flock Fantasy (329K), The Fantasy Headliners (281K),
Sal Vetri (219K), Fantasy Football Advice (122K), Fantasy Football Counselor (105K),
The Fantasy Football Show (39K). By subscribers the biggest fantasy-first channels are
The Fantasy Footballers (425K), Flock, FantasyPros (293K), Headliners, PFF (229K,
mostly non-fantasy), Sal Vetri, Josh & Hayden (179K). Two traps were caught and left
out: `@sharpfootball` ("Sharp Football Channel", 450K) is **not** Warren Sharp
(`@SharpFootballAnalysis`, 14.4K), and `@ringerfantasyfootball` (10 subscribers) is an
impostor of `@RingerFFS`.

**YouTube feeds are broken in 2026.** `youtube.com/feeds/videos.xml?channel_id=…`
returned 404 for every channel tested, from two networks, even though each channel
page still advertises that link. This is the platform-wide outage documented on
Google's own developer forum (Dec 2025–May 2026, no fix) and by thecodersblog.com
(2026-05-06). So every `youtube` entry carries `feed_readable: false` and
`machine_path: youtube-data-api-v3`: `channels.list` → uploads playlist →
`playlistItems.list`, 1 quota unit per call against 10,000/day. That path yields
titles and links only, which is exactly what the data-rights plan allows; the
transcript pipeline is not part of it.

**(c) Newsletters and free tiers — 12.** Substack feeds (`/feed`) all verified live:
Stealing Signals, Unexpected Points, The FF Newsletter, Thinking About Thinking. Site
feeds verified for 4for4 (`/rss.xml`, ~1,000 items), PFF (`/feed`, all-PFF so
filter by title), RotoBaller, Sharp Football Analysis (site-level; the fantasy
sub-feed is empty). No public RSS could be found for Fantasy Life
(`/rss` = 404), Footballguys (`/rss`, `/news/rss` = 404), Fantasy Points (`/rss` =
404) or Late Round (`/feed` answers but is empty) — those are page-link entries.

**(d) Analysts — 17.** Only people whose rankings or data stand apart from a show
entry (Mike Clay's projections, McFarland's Utilization Report, Harmon's Reception
Perception, Cummings' projection tiers, Barrett's rankings page) plus the four news
breakers and the two injury voices. Pelissero, Rapoport, Bell and Berry all changed
platforms in 2026 and carry `moved`.

**(e) Data feeds — 12**, each with the data-rights plan's verdict in
`public_status` and the licence text quoted in `licensing`:

| Feed | Status | Basis |
|---|---|---|
| engine, house-research | free (owned) | — |
| nflverse | free | CC-BY-4.0; exclude the FTN charting release (ShareAlike) |
| Fantasy Football Calculator ADP | free | "free for personal and commercial use", attribution requested |
| The Odds API | free tier (500 credits/mo) | commercial terms not on homepage — read T&C |
| Sleeper projections / trending | needs-deal | docs: free non-commercial; "reach out … to discuss licensing" |
| Yahoo Fantasy API | needs-deal | OAuth; API Access and Use Agreement + approval |
| FantasyCalc | needs-deal | open JSON, no terms anywhere → unlicensed until asked |
| **FantasyPros ECR** | **needs-deal (was "dies")** | FantasyPros now sells a self-serve API: Free (sample), Premium $8.99/mo personal-only, Commercial custom-priced with "commercial license & redistribution rights" |
| ESPN projections | cannot-use-publicly | Disney terms bar automated access and commercial use |
| Boris Chen tiers | cannot-use-publicly | "All data exclusively from FantasyPros.com" — restrictions travel |

The FantasyPros row is the one change to the plan's table: ECR is purchasable, and
therefore a *cost* decision rather than a legal wall. Chen's tiers remain blocked
because they inherit the FantasyPros terms without a licence of their own.

**(f) News wires — 7.** Working public RSS: RotoWire NFL news, ProFootballTalk, ESPN
NFL news, Yahoo NFL. Page-only: NBC/Rotoworld player news (three feed URLs tried, all
404), FantasyPros player news (its RSS answers with zero items), NFL.com injuries.
All are weighted 0–2: they inform, they do not vote.

## Excluded, and why

- **Defunct:** The Athletic Fantasy Football Podcast (last episode 2024-01-04); Jake
  Ciely's All In Football (2024-07-17); Underdog's content network (shut in 2026 — its
  hosts are in the library under Yahoo); PlayerProfiler's Waiver Wired sub-feed
  (2025-12-03); the "FTN Fantasy Football Podcast" feed (2025-12-26 — The Rant is
  FTN's live show); "Five Minute Fantasy Football" (marked INACTIVE by its own
  network).
- **Dormant but kept with a flag:** PFF Fantasy Football Podcast (last audio
  2026-03-13). Kept because Jahnke's snap-count work is valuable and PFF may simply
  have moved the show to video.
- **Paywalled-only, no public calls to grade:** RotoViz, Draft Sharks' Injury
  Predictor, ETR's written In-Season product (ETR is in via its free podcast; Silva
  is in as an analyst with `paid` noted), The Athletic's fantasy writing, Reception
  Perception's paid tiers (Harmon is in via Yahoo).
- **Low signal for a weekly ledger:** dynasty-only shows beyond Dynasty Nerds
  (Dynasty Points, Dynasty Degens, FantasyPros Dynasty, Footballers Dynasty, CBS FFT
  Dynasty) — dynasty calls take a season to grade. Regional/one-person channels under
  ~35K subscribers unless they had a distinct method (Late Round, Warren Sharp).
- **Cannot be attributed safely:** "Sharp Football Channel" (unrelated to Warren
  Sharp); impostor Ringer channel; "Underdog Fantasy" YouTube result with 2
  subscribers.
- **X/Twitter lists** as a "source type": no public feed exists, so news breakers are
  listed as link-only analysts instead.

## Unverified items (flagged in the YAML, do not treat as fact)

- Hosts of the FantasyPros podcast, the NFL Fantasy Football Show and Dynasty Nerds
  for 2026 — the feeds credit the network, not people.
- ESPN Fantasy's YouTube subscriber count (hidden on the channel page).
- Fantasy Points' subscription prices (pricing page returned HTTP 402 to a fetch).
- Whether `x.com/Stephania_Bell` is Stephania Bell's account (it resolves; her old
  `@Stephania_ESPN` is gone) and where she is publishing after the July layoff.
- Fantasy Points' Injury Insights index URL (the one search engines return is 404).
- The Odds API's commercial-use terms (homepage only shows pricing).
- The FantasyPros player-news RSS (answers as RSS, zero items on the day checked).

## The five entries most likely to be wrong in six months

1. **Fantasy Focus (ESPN)** — ESPN just absorbed NFL Network and cut Bell and
   Pelissero; the host slate and the ESPN Fantasy YouTube presence will keep
   shifting through the 2027 offseason. The RSS metadata is already stale.
2. **Stephania Bell** — laid off in July 2026 with no verified new platform; her
   entry will need a URL, a cadence and probably a new employer.
3. **Fantasy Football Happy Hour (Berry)** — one month into an Audacy deal, off NBC;
   feed URLs on this show have changed with every network move.
4. **PFF Fantasy Football Podcast** — audio feed dormant since March; either it is
   quietly finished or it lives on video now. Check before Week 1 2027.
5. **The Favorites** — relaunched with a new cast a year ago; betting-podcast
   lineups turn over annually, and the feed's publisher tag already reads
   "Playmaker and iHeartPodcasts" rather than Action Network.

Honourable mentions: Ian Hartitz (two months into RotoWire), Josh & Hayden (two
months into Yahoo), Tom Pelissero (Netflix + The Ringer, new this season), and any
YouTube `feed_readable` value if Google restores the RSS endpoint.

## Maintenance rhythm — the "suggest new ones" queue

The Sources page should write suggestions to a plain YAML queue
(`data/library_suggestions.yaml`; one record per suggestion: url-or-handle, the
user's one-line reason, who suggested it, when, and a `status` of
`new | reviewing | added | declined`). Review it on this cadence:

- **Weekly, Tuesday, 15 minutes (in-season).** Read new suggestions. For each: resolve
  the feed the same way this library was built (iTunes lookup for podcasts, channel
  page `externalId` for YouTube, `/feed` for Substacks). Add anything that is alive,
  makes explicit calls, and is not a duplicate of an existing entry's network.
  Decline duplicates with a one-line reason the suggester can see. Tuesday because
  waiver-day traffic produces most suggestions.
- **Monthly, first Monday.** Re-run the liveness check across the whole library
  (`last_episode` / `last_post` older than 45 days in-season → flag `dormant`;
  older than 180 days → propose removal). Re-check the `unverified` list above.
- **Twice a year — the week after the Super Bowl, and the last week of July.** The
  network-move season. Re-verify every `hosts`, `network` and feed URL for the
  podcasts, and every `publishes_at` for the analysts. July is when 2026's moves
  (Hartitz, Bell, Pelissero, Josh & Hayden, Berry) all landed.
- **Whenever a licence changes.** The `feeds` block mirrors the data-rights table in
  `design/plan/platform.md`; when Sleeper or Yahoo answers, or a FantasyPros
  commercial quote arrives, update `public_status` and `licensing` here first and let
  the Sources page read the status from the YAML so the UI never claims a feed the
  product cannot legally use.

Promotion rule for the queue: a suggested creator becomes a library entry as
`link-only`; they become quotable only when the signed one-pager is on file, at which
point `consent_status` flips to `licensed` and nothing else about the entry changes.

## Verification record

All URLs in the YAML were fetched on 2026-09-10 (UTC evening); each entry's
`source_of_truth` is the page the facts were read from. Tools: iTunes
lookup/search API for podcast feeds; direct RSS fetch and parse for item counts and
latest `pubDate`; YouTube channel pages and channel search for ids and subscriber
counts; site and author pages for HTTP status; 2026 press coverage (Barrett Media,
Awful Announcing, Yahoo Sports, Pro Football Network) for personnel moves.
