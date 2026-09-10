# Yahoo setup — for the OWNER, once, for everybody

**This file is for you, not for your friends.** You register one app. Every
person who wants their Yahoo leagues read then grants *that* app read access
through Yahoo's own consent screen. They never see this file, never open a
developer portal, and never hand over a password or a cookie.

The note you send *them* is [`docs/CONNECT_YAHOO.md`](docs/CONNECT_YAHOO.md).

---

## What changed and why

The old version of this file told **each user** to register **their own** Yahoo
app as an *Installed Application* with redirect `oob`. That is the single-user
desktop model, and it is exactly why a friend could not connect — you cannot
ask someone to become a registered Yahoo developer to try your thing.

The mistake was never the `oob` redirect. `oob` is correct here and stays.
The mistake was *who owns the app*. In OAuth 2.0 the **app belongs to the
developer** and the **token belongs to the user** — one app, many tokens. Yahoo
expects exactly this: its Fantasy API access form asks you to state your
"intended user base" and offers *Small (< 1,000 users) / Medium (1,000 –
100,000) / Large (100,000+)*, and asks you to say so explicitly "where access
is limited to personal or single league use"
([Apply for Yahoo Fantasy Sports API](https://sports.yahoo.com/developer/access/)).
A form that asks how many thousands of users you expect is a form for an app
that serves many people.

---

## Step 1 — Register the app

Go to **<https://developer.yahoo.com/apps/create/>** and fill in, field by
field:

| Field | What to put | Why |
|---|---|---|
| **Application Name** | `War Room` | Your friends see this name on Yahoo's consent screen. Use something they will recognise as yours — a name they don't recognise is a name they should refuse. |
| **Application Type** | **Installed Application** | This is a program running on your Mac, not a website. There is no server, so there is nothing for Yahoo to call back to. |
| **Description** | `Read-only fantasy football advice tool. Reads league settings and rosters to generate draft, waiver and lineup recommendations. Never writes to Yahoo.` | Yahoo reviews this. Say read-only, because it is. |
| **Home Page URL** | your Cloudflare Pages URL, or leave blank | Optional. |
| **Redirect URI(s)** | `oob` — and if the form refuses it, `https://localhost:8080` | See "Which redirect URI" below. This one matters. |
| **API Permissions** | tick **Fantasy Sports**, then select **Read** | Read, never Read/Write. `Read` is the scope `fspt-r`; `fspt-w` is read/write and `engine/yahoo.py` refuses to request it. |

Yahoo then shows you a **Client ID** and a **Client Secret**. Both are yours,
not anyone else's. Keep the secret off chat, off git, off the published site.

### Which redirect URI

You have no server, so the code Yahoo issues has to reach you some other way.
Two options, both server-free:

**`oob` (out of band) — preferred.** Yahoo's OAuth 2.0 guide: *"If the user
should not be redirected to your server, you should specify the callback as
`oob` (out of band)."*
([Authorization Code Flow](https://developer.yahoo.com/oauth2/guide/flows_authcode/))
Yahoo's own worked example on that page uses `redirect_uri=oob`. The person
presses Allow and Yahoo prints a short code on screen for them to send you.
As of 2026-09-09 that is still documented and supported.

**`https://localhost:8080` — fallback.** Some versions of the app-creation
form insist on a real URL in the Redirect URI(s) box. If yours does, put
`https://localhost:8080` and set it in your secrets file (below). After the
person presses Allow, their browser tries to load `localhost:8080`, nothing is
listening, and the page fails — **that is fine and expected**. The code is
sitting in the address bar. They copy the whole address and send it; `./yahoo.sh
finish` parses the code out of it.

Be aware of the risk on `oob`: Google retired its out-of-band flow in 2023 over
phishing concerns, and Yahoo could follow. If Yahoo ever rejects `oob`, switch
to the localhost fallback — no code change, just the `redirect_uri` in your
secrets file.

---

## Step 2 — Apply for Fantasy API access

**Creating the app is no longer enough on its own.** Yahoo now gates the
Fantasy Sports API behind a review: *"Review the API Documentation and
requirements, then provide information about your organization, your product,
and use case(s)… We'll review your application and reach out with any
follow-up questions… If you're approved, we'll follow up with next steps."*
([Yahoo Fantasy Sports API](https://sports.yahoo.com/developer/))

Apply at **<https://sports.yahoo.com/developer/access/>**:

| Field | What to put |
|---|---|
| **Client ID** | the Client ID from step 1 — this is how they attach the approval to your existing app. (The form says new users without a YDN account may leave it blank and access is provisioned after approval; you have one, so fill it in.) |
| **Expected Users** | **Small (< 1,000 users)** |
| Product / use case / organization details | A personal, non-commercial fantasy football advice tool. It reads league settings, rosters and matchups for a handful of friends who each authorize it themselves via OAuth, and returns draft, waiver and lineup recommendations. It is read-only and never writes to Yahoo. Not a commercial product; no data is sold or redistributed. |
| Access level | Leave at read-only. The form says: *"Access to the Yahoo Fantasy Sports API is read-only by default."* |

Yahoo's own warning about this form: *"Given current request volume, incomplete
or insufficiently detailed submissions cannot be evaluated and will be closed
without further correspondence."* Write real sentences.

Until you are approved, expect HTTP 403 on Fantasy reads. `engine/yahoo.py`
raises `YahooAPIError` and says to check this step by name.

---

## Step 3 — Put the app credential on disk

Create `data/yahoo_secrets.json`:

```json
{
  "client_id": "PASTE_YOUR_CLIENT_ID_HERE",
  "client_secret": "PASTE_YOUR_CLIENT_SECRET_HERE",
  "redirect_uri": "oob",
  "scope": "fspt-r"
}
```

* `redirect_uri` must be **byte-identical** to what you registered in step 1.
  If you had to register `https://localhost:8080`, put that here.
* `scope` is the Fantasy Sports read-only scope. If Yahoo ever answers
  `invalid_scope`, set it to `""` — the app registration in step 1 already
  pins the permission to Read, so omitting the parameter is still read-only.
  Setting it to `fspt-w` is refused outright by the code.
* `consumer_key` / `consumer_secret` (the older spelling Yahoo sometimes shows)
  are accepted as aliases.

Then `chmod 600 data/yahoo_secrets.json`. It is already in `.gitignore`;
check that it stayed there.

---

## Step 4 — Prove it works on yourself first

You are a person too. Connect yourself before you send a friend anything:

```bash
./yahoo.sh authorize --person andrew     # prints a link — open it yourself
./yahoo.sh finish    --person andrew --code <the code Yahoo showed you>
./yahoo.sh leagues   --person andrew
./yahoo.sh import    --person andrew --league <league id from that list>
./yahoo.sh check     --person andrew     # proves the refresh token works
```

`check` is the one to re-run in a week. It forces a token refresh and tells you
whether the grant is still alive.

---

## What Yahoo's terms require of you

These are not optional and they shape the product.

**24-hour data retention.** Yahoo APIs Terms of Use §2.1: *"You may not retain
or use, and must immediately remove from any Application and any data
repository in your possession or under your control any Yahoo user data
obtained through the Yahoo APIs that is not explicitly identified as being
storable indefinitely in the API Documents within 24 hours after the time at
which you obtained the data"*
([Yahoo APIs Terms of Use](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html)).

So: every file `./yahoo.sh import` writes carries `yahoo_fetched_at` and
`yahoo_retention_expires_at`, and anything past its clock is deleted — swept
automatically at the start of the next import (reported as `PURGED`), or on
demand with `./yahoo.sh purge`. The sweep is automatic on purpose: a retention
rule you have to *remember* to run is one you will breach on a busy Sunday. **A multi-week roster history or a weekly accuracy ledger cannot
store the Yahoo data itself.** It can store *your* derived output — the pick
you recommended, the grade you gave it, a score — because that is yours. It
cannot store a copy of somebody's Yahoo roster from three weeks ago. Design the
ledger to keep verdicts, not payloads. (Details and the honest trade-off are in
`docs/CONNECT_YAHOO.md` and in the `engine/yahoo.py` module docstring.)

**No commercial use without written permission.** §1.7(d) forbids you to
*"Sell, lease, share, transfer, or sublicense the Yahoo APIs or access or
access codes thereto or derive income from the use or provision of the Yahoo
APIs… unless the API Documents specifically permit otherwise or Yahoo gives
prior, express, written permission."* Friends testing it: fine. Charging for
it: not without asking Yahoo first.

**You own the consent.** §1.8(b): *"You are solely responsible for securing
clear, express consent from the user, granting you permission to access such
user's Yahoo account using OAuth-enabled APIs… You will strictly comply with
the scope of express consent they granted you."* This is the whole reason the
design is OAuth and not "paste me your cookie."

**Rate limits are undocumented and discretionary.** Terms of Use preamble:
*"Yahoo's APIs may be subject to rate limits at Yahoo's absolute and sole
discretion."* The Fantasy portal adds that if usage "is excessive over short
periods or impacts performance, we may temporarily throttle or limit access."
There is no published number. `engine/yahoo.py` maps HTTP 429 and Yahoo's 999
to `YahooRateLimited`; if you see it, slow down — one import per league per
run, not a polling loop.

**Attribution.** Yahoo asks that displays of this data carry *"Fantasy data
provided by Yahoo Fantasy"* and the official logo. That belongs on the
published pages — it is a `publish.py` change, not a connector one.

---

## What can go wrong

**"Invalid redirect URI"** — the `redirect_uri` in `data/yahoo_secrets.json`
does not exactly match what is registered on the app. Not "basically the
same": identical.

**HTTP 403 on every Fantasy read** — step 2 (Fantasy API access approval) is
not done, or not attached to this Client ID.

**`YahooCodeError: … single-use and expire in minutes`** — the person sat on
the code too long, or it was already used. Send a fresh `authorize` link.

**`YahooTokenRevoked`** — they removed the app in their Yahoo account, or the
grant aged out. Send a fresh `authorize` link. Nothing is wrong on your end.

**`YahooSetupError: Yahoo rejected the app credential`** — the Client ID or
Secret is wrong, or the app was deleted in the developer console.

**Someone's leagues list is empty** — `game_keys=nfl` resolves to the season
Yahoo currently treats as live. An archived season needs its numeric game key;
ask and I will add the flag.

---

## What this tool will never do

It never asks for anyone's Yahoo password. It never accepts anyone's session
cookie. It never requests write access, and there is no add/drop/claim/trade
call anywhere in `engine/yahoo.py` — every Fantasy request is a GET, and
`tests/yahoo_test.py` asserts that. A bug here cannot cost anybody a player.
