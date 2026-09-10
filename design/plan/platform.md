# From your Mac to a platform

*Plan of record · 8 September 2026 · every number below was measured in your repository today, not estimated.*

## The one-line answer

**Infrastructure is not your constraint — data rights are.** Hosting this for ten thousand people costs about $230 a month. What you are *allowed to read*, and what you are allowed to *charge for*, is the whole game. Two beliefs this project was built on turned out to be wrong, and both are load-bearing.

**"Advise-only protects us" is false.** It solves the write side — no bot places your claims, no platform's fair-play rule is broken. But every prohibition that actually bites is about automated *reading* and *commercial use*. Disney's terms bar accessing ESPN by "robot, spider, script, or other automated means" and bar commercial use. Neither cares that we never write anything back. Advise-only remains a good product principle. It is not a legal answer.

**The line is money, not scale.** Sharing with eight known people, unpaid, with no brand and no discoverability, is near-zero enforcement risk. The day a pricing page exists, the commercial-use clauses activate, the App Store gate appears, and every high-risk item goes live at once. Plan for that day now; don't behave as though it has arrived.

## Two things I verified in your code today

**1. The YouTube pipeline impersonates the YouTube Android app.** In `engine/sources.py`, `ANDROID_UA` is set to `com.google.android.youtube/20.10.38` and posted to YouTube's internal player endpoint. The code's own comment says *"this UA matches the client context we claim."* That is not incidental scraping — it reaches an endpoint the public API deliberately closes, and YouTube's developer policy separately bars using API data "to create new or derived data or metrics," which is exactly what the consensus step does. There is no compliant version of this pipeline.

On your own Mac, for your own use, the practical risk is low. But it will be in the repository when a lawyer, an investor, or a creator's manager looks at it. **Recommendation: keep it local this season, delete it before anything is hosted.** I have not touched it — it powers one of your 17-weight sources, and killing a feature you asked for is your call, not mine.

**2. The page the plan wanted you to share with your league is empty.** The Receipts page says, in its own words: *"NO LIVE RECORD EXISTS YET… every CURRENT-form state below is NO-DATA by fact, not by failure."* I counted: **nine NO-DATA labels, 163 ledger rows, zero of them graded.** Both human voices — Sharp or Square and The Favorites, the ones your league actually argues about — have literally nothing, because we never recorded their past calls. The only three sources with any record are projection feeds graded against a 2025 reconstruction.

Drop that in the league chat and the first reply is *"so it's ESPN's projections grading themselves?"*

It gets worse before it gets better. The 2025 archive decays to zero by week 3, and a source needs 30 graded calls before it can be called hot or cold — about six weeks at your ledger's rate. **There is a death valley from roughly week 3 to week 6** where the archive has retired, the live sample is too thin to say anything, and the page honestly says so, weekly, to seven people whose habit you are trying to build. The product's integrity is what produces the emptiness. That is admirable, and it is still a bad thing to launch on.

## What survives, what needs a deal, what dies

| Source | Verdict | Notes |
|---|---|---|
| **nflverse** | Survives, free | CC-BY. Exclude the FTN charting set — ShareAlike is viral onto anything derived from it. |
| **FantasyFootballCalculator ADP** | Survives, free | Explicitly free for commercial use. A drop-in ADP replacement. |
| **Player names and stats** | Survives | Protected by *C.B.C. v. MLBAM* and *CBS v. NFLPA*. **Text only** — no headshots, no logos, no club colourways. |
| **Your own engine** | Survives | The only input you own outright. |
| **Sleeper** | One email | Their docs invite commercial licensing conversations. Just ask. |
| **Yahoo** | One application | A single app may serve many users. Get two answers in writing first: may you monetise, and how the 24-hour retention rule applies to your accuracy ledger. |
| **FantasyCalc** | One email | No terms retrievable anywhere. Unknown equals unlicensed. |
| **ESPN, server-side** | **Dies** | No sanctioned API since 2014. Storing a stranger's cookie instructs them to breach their own Disney agreement and builds an account-takeover honeypot. It also permanently blocks the App Store. |
| **YouTube transcripts** | **Dies** | See above. |
| **Boris Chen tiers · FantasyPros ECR** | **Dies** | Chen's inputs are FantasyPros; their restrictions travel with them. |

### The number that matters

The plan's first draft said half the built-in weight was at risk. The skeptic recomputed it against your actual registry, and it is worse: **72 of 100 points either die, need a signature, or are one person's hand-curation.** The clean survivor is your own engine at 17.

| Source | Weight | Survives? |
|---|---|---|
| War Room Engine | 17 | **Yes — the only clean survivor** |
| ESPN Projections | 17 | No |
| Sharp or Square | 17 | No, without a signed licence |
| The Favorites | 17 | No — the pipeline itself must go |
| Sleeper Projections | 11 | Conditional on a licence |
| Boris Chen Tiers | 11 | No |
| House Research | 10 | Yours, but hand-curated |

That reframes the strategic move, and it is not a concession: **build your own projections and your own tiers.** It removes FantasyPros, Chen and FantasyCalc from the dependency graph in one action, and it makes "your model" literally true rather than a weighting layer over other people's licensed work. The clustering method behind tiers is public; the inputs were the problem, and nflverse plus your own projections are inputs you can defend.

The second move: **flip the creator layer from extraction to consent.** A one-page licence — they grant their weekly calls and short quotes, you give attribution, a deep link, and their line in your accuracy ledger. Until a creator signs, they appear as headline-plus-link with no quoted text and no stored transcript. The ledger line is an offer nobody else can make: a public, graded scorecard.

## Phase 0 — your league, this season

The honest problem here is not access control. It is that **your league mates are your competitors.** Your home page, lineup, board and trade desk are your roster, your waiver plan and your named trade targets. In an eight-team league, publishing those hands seven rivals your sheet — and the trade desk is worse than the lineup page, because it names who you think is exploitable.

So Phase 0 is not "give my league the product." It is "give my league the one page with no strategy in it." That page is the Receipts — and the Receipts is empty until week 6.

**The correction:** publish a **methodology page** in weeks 1–5 — how a call gets graded, what the replacement line is, what the decay strip is doing, and the full 2025 archive presented explicitly as a retrospective — with the live ledger as a small, clearly-labelled strip that says "starts filling week 1." Ship the graded version in **week 6**, when it has something to say.

**Hosting, decided:** cron-push from your Mac to Cloudflare Pages, with Cloudflare Access on a custom domain. **$0/month plus about $10/year for the domain.** Eight email addresses, one-time PIN, revocable per person. A tunnel from your Mac was the faster option and it is overruled by one day of work: **a tunnel dies when the laptop sleeps**, and seven rivals hitting a dead link at 11am Sunday ends the pilot in week one.

Two traps worth naming. The Pages access toggle protects *preview* deployments only, not your custom domain — you need a separate Zero Trust application on the production hostname, or the receipts are public. And a failed cron is silent: the heartbeat must assert on **content**, not exit code. This system is built to degrade honestly and exit zero, so a page that renders "NO-DATA" successfully is the expected output right now. Fail loudly if the graded-call count didn't increase week over week.

**And the harder truth:** seven people who benefit from your failure are the wrong pilot audience. Your league gets the artifact. For the real experiment — does this product help someone? — recruit eight strangers who run multiple Sleeper leagues.

## Phase 1 — public beta

**The beachhead is Sleeper.** Not because it's biggest, but because it is the only platform where you can be fully compliant with a single email: public read-only API, no auth, no cookie, no OAuth app, no credential to store. The onboarding is *already written* — `engine/connections.py` resolves a username, lists leagues, and imports one. A Sleeper user signs up by typing their username. And Sleeper is where multi-league managers concentrate, which is the exact user this product is for.

Yahoo is second, gated on those two written answers. **ESPN is third and web-only forever** — manual import in beta, optionally a browser extension later that fetches in the user's own browser and posts derived roster JSON, never the cookie. Say plainly on the sign-up page that ESPN leagues don't get background digests.

**Architecture: one boring box.** A small FastAPI process for login and config that never calls a renderer synchronously, plus a scheduler that warms the shared feed cache *once for everybody* and then walks a tenant table calling your existing renderers. Cloudflare in front, rendered pages in R2, SQLite streamed to object storage.

The measurement that makes this cheap: **97 MB of shared feed cache versus 48 KB of per-tenant state — about 2,000 to 1.** User two through ten thousand each add ~50 KB and *zero upstream API calls*. That single fact keeps you off every rate limit and puts marginal cost near a nickel a season.

Cloudflare Containers is cheaper on paper and technically the better 2026 answer. Rejected for now: one droplet, one service, one cron is a system you can reason about at 11pm on a Sunday. Docker plus Wrangler plus a product that shipped in August is three new concepts buying $19 a month.

| Users | Infra/month |
|---|---|
| 100 | $12–25 |
| 1,000 | $40–70 |
| 10,000 | $110–200 |

**What carries over: everything that makes this good.** All 45 engine modules, the whole design system, all 31 test suites, every shell script as your local path. The seam already exists — the renderers already accept `--out`, and the scripts already warm caches as a separate step.

**What gets rewritten:** the settings panel's server half (about 1,900 lines bound to localhost, single-threaded, no sessions, no CSRF, no authorization, accepting session cookies as plaintext form input) — three to five weeks, and this is the work to hand a contractor, because a non-developer's mistake here is a breach, not a bug. Then path threading, a scheduler, and a Python upgrade off 3.9, which went end-of-life last October.

## Phase 2 — mobile

**Everything ships as web first.** Your pages already pass a measured iPhone-fit checklist at 375/390/430 with zero horizontal overflow, they have a phone tab bar and bottom sheets, and they're static HTML from a CDN — the fastest thing a phone can load. Install as a PWA for a home-screen icon and offline access to the last rendered week.

**The only thing that could force native is push quality.** iOS has supported web push for installed web apps since 16.4. That claim is the one thing the research did not verify, so treat it as open — and the experiment costs an afternoon: install the Phase 0 site to your own iPhone and send yourself one push. That single test decides whether Phase 2 costs nothing or three months.

Notifications are what turn this from a website you forget into a service. Four of them, capped at three a week, each carrying a verdict and a deep link:

- **Tuesday 7am** — *"3 lineup changes, $14 FAAB on Tucker Kraft."* Never "come look."
- **Wednesday, 3 hours before waivers** — the number.
- **Sunday 11:15am** — *"Two changes since Tuesday: Rice out, start Coleman."* This is the one that earns the subscription and the one that must never be wrong.
- **Monday night** — the ledger. *"Sharp or Square went 2-for-5 on your roster. Your model went 4-for-5."* Unique to you, and the retention loop.

Silence is a feature. If nothing changed, send nothing.

If you do build native: Sleeper and Yahoo only. Apple's guideline 5.2.2 requires authorization from third-party services "provided upon request." You will have Sleeper's letter and Yahoo's approval. You will never have ESPN's — an ESPN feature in a native binary is a rejection waiting to happen.

## The money

Data licensing on the recommended path is **$0/year**. The one-time costs are a lawyer's afternoon for the creator one-pager, terms of service and a privacy policy — budget $2,000–5,000 — plus a company shell.

Your closest published comparable is FantasyPros at $8.99/month. Price under it: **$6/month in season, or a $35 season pass, per user rather than per league** — the whole thesis is relief for people running several teams, and a per-league price would tax exactly the customer you want. One league free forever, multi-league paid, so the paywall lands precisely on the pain the product exists to solve.

At 1,000 paying users that is roughly $35,000 a season against about $90/month of infrastructure. **Infrastructure never appears in this arithmetic — stop optimising it.** The real cost line is a part-time engineer at $5,000–10,000/month, which puts breakeven for one around 850–1,700 paying users.

Ten thousand free users cost about $230/month, so **you can run an entirely free public beta for a year for under $3,000.** Do that rather than charging early, because the day you charge, every commercial-use clause activates.

Where the arithmetic breaks: buying licensed projections before you have revenue. The quotes run $1,200–7,200/year — one to two orders of magnitude above your entire infrastructure bill, for something you can build.

## How this most likely dies

Not law, not scale, not Apple. **It dies in October, quietly, from your bandwidth.** The evidence is already in your own runbook: item A4, "Yahoo OAuth — 5 min," is still unchecked. It unblocks the platform this plan names as beachhead number two, it takes five minutes, and it has been sitting there. That is not a criticism — it is what a day job does.

Now look at what the plan asks you to do simultaneously, in season: run the weekly loop, operate a publish pipeline, host a league pilot, cold-email three vendors and chase them, recruit creators, manage a contractor, learn enough infrastructure to own it on a Sunday night, and upgrade Python. Any one is fine. All of them, October through January, is not.

The death is undramatic: a week-five Sunday where the cron published a stale page, nobody mentions it because nobody was reading it, and the tab never gets opened again.

## Decisions only you can make

1. **Beachhead** → Sleeper first, Yahoo second, ESPN web-only. Costs you the largest platform at launch; buys you full compliance with one email and an onboarding flow that already works.
2. **ESPN at public launch** → manual import in beta, extension later, never a server-side cookie. Costs background digests for ESPN leagues; avoids a breach-shaped liability and a permanent App Store blocker.
3. **The YouTube pipeline** → keep local this season, delete before anything is hosted. Your creator sources weaken to headline-plus-link until someone signs.
4. **Own projections vs licensed rankings** → build your own, starting this off-season.
5. **Creator programme** → link-only by default, signed licence as the upgrade. If ten sign, you have a moat.
6. **Price** → free public beta through the 2027 draft, then $6/month or $35/season.
7. **Company shell and terms** → before strangers' data touches your server, not before the first dollar.
8. **Who writes Phase 1** → you and me for the engine work; a contractor for four to six weeks for the settings-panel rewrite and deployment.
9. **The name** → decide before you buy the domain, because the URL goes in the league chat and URLs are forever. Your navy-and-gold identity is already clear of every licensing trap: no shield, no logos, no club colourways. Keep it.

## What to build next week

1. **A `--public` render mode** — drop the localhost settings link and every nav entry except the published page, stamp the week and a generation timestamp. Half a day.
2. **`publish.sh` as an explicit allowlist with a file-count assertion.** Ten lines standing between you and publishing your trade desk to seven rivals. Half a day.
3. **Cloudflare: domain, Pages project, and a Zero Trust application on the production hostname** — not the preview toggle. Verify from a phone, on cellular, signed out. Half a day.
4. **The methodology page, published, with the 2025 archive as a retrospective** — not the empty ledger. Half a day, and it is the whole point of Phase 0.
5. **Run the real experiment: render week 1 with `engine` alone.** Not "minus two feeds" — the actual question is whether your model still feels right at 17 points of clean weight. If the verdicts hold, "your model" survives licensing. If they don't, you have found the true Phase 1 roadmap eleven months early. One afternoon.

**On day one, no code:** email Sleeper for a commercial licence, submit the Yahoo application declaring commercial intent, and email FantasyCalc for terms. Longest lead times, an hour of work, and the answers reshape everything downstream.
