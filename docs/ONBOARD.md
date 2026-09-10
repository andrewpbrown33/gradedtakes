# Onboarding one friend, end to end

This is **your** script — the owner's. It is what you run and what you send.

Two other docs are written for the friend, not for you, and are meant to be
sent as-is when the short message below is not enough:

* `docs/CONNECT_ESPN.md` — their ESPN league, both routes
* `docs/CONNECT_YAHOO.md` — the Yahoo consent link

Everything here assumes the friend is not sitting at your Mac and never will
be. That is the whole point: the panel used to assume the person at the
keyboard owned the account. Now it does not.

---

## The line you do not cross

**You never take custody of another person's password or session cookie.**
Not on your Mac, not on a server, not "just for testing".

ESPN's `espn_s2` and `SWID` are whole-account Disney session credentials —
mail, subscriptions, the lot. They are not fantasy-scoped. Asking a friend
for theirs breaks *their* terms with ESPN, cannot be un-shared, and is
refused by this tool by design. The ESPN card in the panel says so in as
many words, and `engine/espn_public.py` has no code path that sends a
cookie.

**OAuth consent is a different thing and is completely fine.** When your
friend opens a Yahoo link and presses Allow, they are telling Yahoo — on
Yahoo's own screen, with Yahoo's own login — to let your app read their
league. That is what OAuth is for. It is read-only, and they can revoke it
from their Yahoo account settings at any time.

If you ever find yourself typing someone else's credential into anything,
stop. There is another route, or there is an honest "not supported".

---

## The whole flow in one screen

```
1.  Add the person                    name + email
2.  Sleeper                           ask for their username
3.  ESPN                              ask for a league id, or a paste
4.  Yahoo                             send a link, get a code back
5.  Publish                           users.yaml + token + Access + the URL
```

Open the panel and work top to bottom:

```bash
./sources.sh          # then click the Leagues tab
```

Or do the whole thing from a terminal — every panel button is a function
call. Both write the same files.

```bash
.venv/bin/python -m engine.connections people      # who is where, what is next
.venv/bin/python -m engine.connections status      # your own plumbing too
```

`people` is the screen to trust. Every line ends in the one next thing to
do, phrased for a human, and it is computed from what is actually on disk —
not from what you remember doing.

---

## 1. Add the person

In the panel: **Leagues → Who you are onboarding → name, email, Add person.**

From a terminal:

```bash
.venv/bin/python -c "from engine.connections import add_person; \
  print(add_person('Sam Rivera', 'sam@example.com'))"
```

The email is not decoration. Cloudflare Access checks it at the door before
their pages load (`docs/DEPLOY.md`), so a person without a usable one cannot
be published to at all. It is required here for exactly that reason.

This writes `data/people.yaml` — the onboarding ledger. Who, where, and
when. It holds no credential of any kind and never will.

**It is not the publish list.** `users.yaml` is, and nothing in this flow
writes that file. Step 5 prints the block for you to paste.

---

## 2. Sleeper — ask for a username

The easy one. Sleeper's read API is public and read-only: a username is
genuinely the entire ask. No password, no cookie, nothing to install, and
nothing they have to change about their league.

**Send them this:**

> What's your Sleeper username? Not your display name — the @handle, in the
> app under Settings → Username. That's all I need; there's nothing to
> install and no password involved. Sleeper's league data is public to read.

**Then, in the panel:** Leagues → Sleeper → type it in → **Find my leagues**
→ **Import** next to the league they play in. Repeat for a second league.

**Or from a terminal:**

```bash
.venv/bin/python -c "
from engine.connections import sleeper_lookup, add_league_for
r = sleeper_lookup('their_handle')
for lg in r['leagues']:
    print(lg['league_id'], lg['name'], lg['teams'], 'teams')
"
.venv/bin/python -c "
from engine.connections import add_league_for
print(add_league_for('sam-rivera', 'sleeper',
                     username='their_handle', league_id='1234567890'))"
```

If the username comes back unknown, it is almost always the display name
rather than the handle. Ask again, naming the Settings screen.

---

## 3. ESPN — a league id, or a paste

Two routes. They are **equal**, and the second is not an apology: one
auto-refreshes, one does not, and a friend who does not want to change their
league settings is not being difficult.

### Route 1 — they make the league viewable

**Send them this:**

> Two things for your ESPN league: (1) in League Settings, turn on "Make
> League Viewable to Public" — that lets anyone with the league's ID read
> the rosters, nothing else, and you can switch it back off whenever. (2)
> Send me the number after `leagueId=` in your league's URL, and tell me
> which team is yours. I will never ask you for your ESPN password or those
> `espn_s2`/`SWID` cookies — anyone who does is asking for your whole Disney
> account.

**Then, in the panel:** Leagues → ESPN → league id → **Check if readable**.
That is an honest check: it either says ESPN will show it to a logged-out
reader, or it tells you exactly what to ask them to change. When it is
readable it lists every team, so you can confirm which is theirs, then
**Import for this person**.

```bash
.venv/bin/python -c "
from engine.connections import espn_public_check
r = espn_public_check('1234567')
print(r['readable'], r['detail'])
for t in r['roster']: print(t['team_id'], t['name'])
"
.venv/bin/python -c "
from engine.connections import add_league_for
print(add_league_for('sam-rivera', 'espn', league_id='1234567', team='3'))"
```

### Route 2 — they paste their roster

For a league that stays private. Same files land on disk; the league is
marked paste-fed, and every screen says out loud that it will not refresh on
its own — so you will need to ask again in a few weeks.

**Send them this:**

> No problem, leave the league private. Instead: open your team's roster
> page in ESPN, select the whole roster, copy it, and paste it into a
> message to me. Also send the number after `leagueId=` in the URL. Plain
> text is fine — I do not need a screenshot, and I still do not need your
> password.

**Then, in the panel:** Leagues → ESPN → Route 2 → paste it in, with their
league id and team name → **Import from paste**.

The league id is still required on this route. It names the files, so the
same league updates in place next time instead of piling up copies.

The parser never invents a player: every line it cannot match against the
player pool is reported back for you to fix, not guessed onto a roster.

Long version for them: `docs/CONNECT_ESPN.md`.

---

## 4. Yahoo — send a link, get a code back

Yahoo is the one that used to be impossible to share, because the old setup
told the *user* to register their own developer app. That was a single-user
desktop design. Now there is one app — yours — and each person authorises it
for themselves.

**Before any of this works, once:** do steps 1–2 of
[`SETUP_YAHOO.md`](../SETUP_YAHOO.md) — register the app, *and* apply for
Fantasy API access at <https://sports.yahoo.com/developer/access/>. **Yahoo
reviews that application by hand and it is not instant.** Until it is
approved, Fantasy reads come back 403 and no friend's import will work, no
matter how clean the consent round-trip looks. Register now so the clock
starts; the panel reports Yahoo as `unregistered` until `data/yahoo_secrets
.json` is on disk, and that status only covers the form, not the review.

**In the panel:** Leagues → Yahoo → **Generate consent link**. Copy it.

**Send them this, with the link:**

> Here's a link — open it, sign in to Yahoo as yourself, and press Agree.
> It's Yahoo's own page (check the address bar says api.login.yahoo.com).
> Yahoo will then show you a short code: send me that. It's read-only — I
> can see the league, I can't touch your team — and you can take the access
> away any time from your Yahoo account settings.

**When they send the code back:** paste it into the box, press **Finish &
list their leagues**, and press **Import** next to the league they play in.

From a terminal, the same four verbs:

```bash
./yahoo.sh authorize --person sam       # prints the link to send
./yahoo.sh finish    --person sam --code XXXX
./yahoo.sh leagues   --person sam
./yahoo.sh import    --person sam --league 428472
```

The code is single-use. It is exchanged and dropped: never stored in the
ledger, never echoed back into the page, never logged.

Long version for them: `docs/CONNECT_YAHOO.md`.

If they have no Yahoo league at all, say so and stop asking:

```bash
.venv/bin/python -c "from engine.connections import skip_platform; \
  skip_platform('sam-rivera', 'yahoo')"
```

That is the difference between "we have not done Yahoo yet" and "there is no
Yahoo", and the board stops nagging about the second one.

---

## 5. Publish to them

Connecting a league does not publish anything. `publish.py` reads
`users.yaml`, and this flow deliberately does not write that file — the
publish pipeline's format is the publish pipeline's business, and a bad
`users.yaml` is the one failure that leaks one person's pages to another.

**Get the block:**

```bash
.venv/bin/python -m engine.connections block sam-rivera
```

It prints their entry with every connected league filled in and the token
line left as a placeholder. **Generate the real token yourself** — never
invent one, never reuse one:

```bash
.venv/bin/python publish.py new-token
```

Paste the block into `users.yaml` under `people:`, with the real token.

**Then the usual publish checklist** (`users.yaml`'s own header has the
long form):

```bash
.venv/bin/python publish.py --dry-run --person "Sam Rivera"   # read the manifest
./publish.sh --person "Sam Rivera"
```

Add their email to the Cloudflare Access policy (`docs/DEPLOY.md`), then
send them `https://<your-site>/<token>/`.

The token is a secret URL, not a password. Send it over a channel they
already trust, and if it leaks: generate a new one, re-publish, and
`./publish.sh --prune` the old directory.

---

## Keeping it true

Rosters move every week. A page built from a three-day-old roster is wrong
in a way no exit code will tell you about, so the board calls it out:

```bash
.venv/bin/python -m engine.connections people
```

* **stale** — that league's files have not been rewritten in over 72 hours.
  Re-import it before you publish. Sleeper and public ESPN and Yahoo
  re-import in one press; a paste-fed ESPN league means asking again.
* **files missing** — a league is on someone's list but `leagues/<id>.yaml`
  is gone. Re-import it, or `forget_league_for(person, league_id)` to drop
  the ledger row. That never deletes league files.
* **not in users.yaml** — connected, but nothing is being published to them.
  Step 5.

---

## When it goes wrong

| What you see | What it means | What to do |
|---|---|---|
| Sleeper: "has no user named ..." | they sent their display name | ask for the @handle under Settings → Username |
| ESPN: "would not show that league" (401) | the league is not viewable | ask them to flip the setting, or use the paste route |
| ESPN: "no league ... in the 2026 season" (404) | wrong id, or the league has no 2026 season | re-check the `leagueId=` number; try the season they last played |
| ESPN: "Which team is yours?" | it will not guess | pass the team id from the listing it printed |
| Yahoo: consent denied | they pressed the wrong button | generate a fresh link and send it again |
| Yahoo: code rejected | the code expired, or it was pasted with the URL around it | generate a fresh link; the code is short and single-use |
| "engine/espn_public.py is not installed yet" | you are on an older tree | the other routes still work; nothing is broken |

Every one of these prints the same sentence in the panel and in the
terminal, because they are the same function.

---

## What this writes

| File | Written by | Holds |
|---|---|---|
| `data/people.yaml` | this flow | who is being onboarded, and which leagues are theirs. **Never a credential.** |
| `leagues/<id>.yaml` | the platform modules | one league's settings, scoring, roster spots |
| `data/rosters/<id>.yaml` | the platform modules | that person's own roster |
| `data/rankings-<id>.csv` | the rebuild | that league's own board, in its own format |
| `data/league-<id>.json` | ESPN public / paste | every team's roster, where it is known |
| `users.yaml` | **you, by hand** | the publish list. Nothing here writes it. |

The Leagues tab enforces that list in code: any write outside it is refused
with a 403, and a path that merely looks like a credential file is refused
even inside it.
