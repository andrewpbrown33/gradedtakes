# DEPLOY — giving Graded Takes to other people

This is the whole procedure for putting a private copy of Graded Takes in front of
somebody who is **not in your league**: your brother, your sister-in-law, two
people at work. Each of them gets their own address, their own pages, their
own leagues. Nobody sees your rosters, and you do not see theirs beyond what
you render for them on this Mac.

It is written for somebody who is comfortable pasting a command into Terminal
and nothing more. Every command is exact. Run them from the project folder:

```bash
cd ~/Desktop/"War Room"
```

**The shape of the thing.** You run a command on your Mac. It writes a folder
called `public/` with one sub-folder per person, each named by a long random
string. You upload `public/` to Cloudflare. Cloudflare puts a login screen in
front of it that only lets in the email addresses you list. That is the whole
system — no server, no database, no monthly bill.

**Two locks, and you want both.**

| Lock | What it stops | Where it lives |
|---|---|---|
| The **token** — a long random folder name | Anyone guessing or stumbling onto a URL | `users.yaml` |
| **Cloudflare Access** — an email check at the door | Anyone who was *sent* a URL they should not have | Cloudflare Zero Trust |

The token alone is a secret URL, and secret URLs leak: they end up in group
chats, in browser history on a shared laptop, in a screenshot. Access alone
means everyone who can log in can try other people's paths. Together they are
fine.

---

## A. Add a person

### A1. Add their league

Each person's league needs a config in `leagues/`. Copy an existing one and
edit it:

```bash
cp leagues/espn-1.yaml leagues/sams-dynasty.yaml
open -e leagues/sams-dynasty.yaml
```

Set at least `id:` (it must match the filename — `sams-dynasty`), `name:`,
`platform:`, `teams:`, `my_slot:` and `roster_spots:`. See `docs/PER_LEAGUE.md`
for what else a new league needs before its numbers are trustworthy — in
particular a league whose scoring differs from an existing one needs its own
`rankings_csv`, and the engine will refuse to start and print the exact
command if it is missing.

League ids must be lowercase, at least three characters, and use only
`a-z 0-9 . _ -`. That is not fussiness: the publisher proves that no page in
one person's folder mentions another person's league id, and a one- or
two-character id would match inside ordinary words and make that proof
worthless. Short ids are refused rather than trusted.

### A2. Generate a token

**Run this. Do not make one up.**

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

or, which also checks it for you:

```bash
.venv/bin/python publish.py new-token
```

Either prints something like:

```
7mQx2Kd0pV9sLb4TnJc6RwYh1EuZaG3oFiN8vXtQrM0
```

`secrets.token_urlsafe(32)` takes 32 bytes from the operating system's
cryptographic random source — the same source that generates encryption keys —
and prints them as 43 URL-safe characters. That is about 256 bits: not
guessable by anybody, ever, including somebody firing millions of URLs at your
site.

Do **not** use Python's `random` module, a password you like, a birthday, a
surname, or anything you can remember. `publish.py` enforces a floor (24+
characters, 12+ distinct, real entropy, no dictionary words, nothing derived
from the person's own name or email, unique across everybody) and refuses the
entire run if any token fails it — but the floor is a backstop, not a
substitute for generating one properly.

**Generate a new token per person. Never reuse one.**

### A3. Add them to `users.yaml`

```bash
open -e users.yaml
```

```yaml
people:
  - name: Sam Rivera
    email: sam.rivera@example.com
    token: 7mQx2Kd0pV9sLb4TnJc6RwYh1EuZaG3oFiN8vXtQrM0
    leagues:
      - sams-dynasty
```

`leagues:` is a list — one person can hold several. Delete the `Example
Person` entry the template ships with; it exists so that a fresh checkout
refuses to publish rather than publishing something wrong.

`users.yaml` is a secrets file in practice: anybody holding it holds every
private URL. Keep it off shared drives and out of any repository.

**Do not add yourself.** You read your own pages from the project folder,
where they are already rendered and not on the internet. Adding your own
league here would publish your rosters, your trade desk and your strategy.

### A4. Look at it before it goes anywhere

```bash
.venv/bin/python publish.py --plan --person "Sam Rivera"
```

Instant, runs no renderer, and prints exactly which files are allowed to exist
in Sam's folder. Then the real rehearsal — this renders everything, runs every
safety assertion, prints the manifest, and **writes nothing**:

```bash
./publish.sh --dry-run --person "Sam Rivera"
```

Read the manifest. Every line is a file that is about to be reachable on the
internet. If a line surprises you, stop.

---

## B. Publish

```bash
./publish.sh
```

Everyone, current NFL week. Variations:

```bash
./publish.sh 7                        # a specific week
./publish.sh --person "Sam Rivera"    # one person
./publish.sh --dry-run                # rehearse, write nothing
./publish.sh --plan                   # just list the allowlist, instantly
./publish.sh --prune                  # also delete folders belonging to nobody
```

The result is `public/<token>/` per person, holding their index, their home
page, their lineup / board / ledger / trade desk for each of their leagues,
their sources page, an install page, and a `heartbeat.json`.

### What the exit code means

| Exit | Meaning |
|---|---|
| **0** | Published, everything rendered, every assertion passed. |
| **1** | Published, but something needs you — a page failed to render, or the heartbeat is stale. What did render is live and honest; what did not is **absent**, not blank, and the person's index says which and why. |
| **2** | **REFUSED. Nothing was published, for anybody.** A safety assertion failed. The reason is printed in full. |

Exit 2 is the important one. The commit is two-phase: every person is
rendered and checked first, and only if all of them pass does anything move
into `public/`. One bad file in one person's folder stops the whole run, so a
leak can never be half-published.

### What it refuses, and why

- **An unexpected file.** Each person has a computed allowlist — their
  leagues' pages at this week, and nothing else. Any other file found in
  staging stops the run. A file nobody listed is a file nobody has checked for
  somebody else's data.
- **Another person's league.** Every file is read and searched for every
  league id *and every league display name* the person does not own. The
  league switcher at the top of every page lists every league on this Mac, so
  this fires on real markup, not a hypothetical.
- **Your local settings panel.** `engine/ui.py` renders a link to
  `http://127.0.0.1:8787/` into every page. The publisher removes that anchor
  and then proves no published file contains `127.0.0.1` (or `localhost`, or
  the port). If the proof fails, nothing publishes.
- **A missing stamp.** Every published page carries the week and the build
  time, both visibly at the foot of the page and in a machine-readable
  comment. A page whose week cannot be checked later is not published.
- **A weak or duplicated token**, a league with no config, a person with no
  email — all before anything renders.

### Cross-league exposure — the leak, and the flag that closes it

**This was a blocker until the renderers took `--roster-dir`; it is closed
now.** It is documented in full because the assertion that caught it is still
armed, and you should know what it is for. Before the fix, a first real
`./publish.sh` stopped with exit 2 and a message like:

```
home.html for Sam Rivera contains the league name 'Kid&#x27;s Table', which
belongs to league 'yahoo-main' — a league this person does not own.
```

That was not a false alarm. It was the pipeline catching a genuine leak, and
here is where it came from.

Graded Takes has a **cross-league exposure** feature. On the home page, the board
and the trade desk it marks players you hold in your *other* leagues — "ALSO
YOURS", "starts in The Original 8; held in Kid's Table". It reads every file
in `data/rosters/` (`engine/exposure.py`) and prints the other leagues'
**names** onto the page.

In a one-owner Graded Takes that is exactly what you want. In a multi-tenant
publish it is a cross-tenant leak: a page built for Sam names *your* league,
or somebody else's, in plain English. So the pre-flight refuses and nothing is
published.

Verified on the pages currently in this project: rendering `espn-1` for a
reader who owns only `espn-1` leaks the name of `yahoo-main` into
`home.html`, `board-*.html` and `tradedesk-*.html`. `lineup-*`, `digest-*`
and `sources.html` are clean.

Two further traps worth knowing:

- The league is named **twice, differently**. `leagues/yahoo-main.yaml` says
  `Kid's Table (Yahoo)`; `data/rosters/yahoo-main.yaml` says `Kid's Table`,
  and it is the *shorter* one that lands on the page. The publisher treats
  both, plus their HTML-escaped forms, as leak markers. A check built only
  from `leagues/` would have let this through.
- The switcher at the top of every page lists every league on this Mac. That
  one the publisher can and does remove cleanly — it is markup, not prose.
  Exposure text is prose inside the page's own reasoning and cannot be edited
  out without changing what the page claims, so it is refused instead.

**The fix: one flag, in the three renderers that carry the ribbon.**
`engine/home.py`, `engine/board.py` and `engine/tradedesk.py` already accepted
a `roster_dir` argument internally and passed it to `Exposure.load`; none of
them exposed it on the command line. Each now does:

```
ap.add_argument("--roster-dir", default=None)
```

threaded to the existing parameter. The pipeline picks this up on its own: it
already builds a per-person copy of `data/rosters/` containing only that
person's leagues, and hands it to every renderer whose `--help` advertises
`--roster-dir`. `data/rosters/` itself is only ever read — never written,
moved or emptied.

Verified end to end on a two-person fixture (one owner of `espn-1`, one of
`yahoo-main`): exit 0, 16 files each, and zero occurrences of the other
person's league id, league name or token in either directory.

`engine.lineup_page`, `engine.digest` and `engine.sources_page` still do not
take the flag. They do not need it — each reads `data/rosters/<league>.yaml`
by id, or no roster at all, so none of them can name a stranger. The
pre-flight prints a NOTE naming them, and that NOTE is explicitly not a
prediction that the run will refuse.

What you must *not* do is take the assertion out. It is the only thing
standing between "Sam's private page" and "Sam's private page with your team
on it".

### Send them the link

```
https://<your-site>/7mQx2Kd0pV9sLb4TnJc6RwYh1EuZaG3oFiN8vXtQrM0/
```

The trailing slash matters. Send it however you would send them anything else
private. Tell them not to forward it.

To **rotate** a token (they forwarded it, they lost a phone): generate a new
one, paste it over the old one in `users.yaml`, then:

```bash
./publish.sh --person "Sam Rivera" && ./publish.sh --prune
```

The old folder stops existing. Until you prune it, it keeps serving, and
`check-heartbeat` reports it as an orphan on every run.

---

## C. Put it on the internet — Cloudflare Pages + Access

Free, no domain purchase needed, no server.

### C1. Account and CLI

Sign up at <https://dash.cloudflare.com/sign-up>. Then:

```bash
npm install -g wrangler
wrangler login
```

(`npm` comes with Node.js — <https://nodejs.org> if you do not have it. This
is the only thing in this document that is not already on your Mac.)

### C2. First upload — this creates the project

```bash
wrangler pages project create war-room --production-branch main
wrangler pages deploy public --project-name war-room --branch main
```

It prints your address:

```
https://war-room.pages.dev
```

**A `*.pages.dev` subdomain is a real, permanent, HTTPS address.** You do not
need to buy a domain to start, and you can attach one later without changing
anything else. Pick a project name that is not guessable-cute — `war-room` is
fine because the tokens are what protect the content, but there is no reason
to advertise.

Every later publish is one line:

```bash
wrangler pages deploy public --project-name war-room --branch main
```

**`--branch main` matters.** Deploying without it creates a *preview*
deployment on a different hostname, which — see the trap below — is protected
by a completely different setting.

Check it worked: open `https://war-room.pages.dev/<token>/` in a private
window. You should see the person's index. The bare
`https://war-room.pages.dev/` should 404 — there is deliberately no listing
page at the root.

### C3. THE TRAP: the Pages access toggle protects previews only

In the Cloudflare dashboard, under **Workers & Pages → war-room → Settings**,
there is an access-control setting. Read its wording: it protects **preview
deployments**. Turning it on does *nothing whatsoever* to
`https://war-room.pages.dev` — your production hostname, the one you just sent
to five people — and it is very easy to switch it on, see a login screen on a
preview URL, and conclude the whole site is protected.

**It is not.** Until you do C4, anybody with the URL can read the pages. The
tokens are still unguessable, so this is not a catastrophe, but it is one lock
where you meant to have two.

To protect production you must create a **separate Zero Trust self-hosted
application** on the production hostname. That is the next step, and it is not
optional.

### C4. Zero Trust: a self-hosted application on the production hostname

1. Go to <https://one.dash.cloudflare.com> (Zero Trust — a different dashboard
   from the main one).
2. First visit only: choose a team name (e.g. `andrew-warroom`). Your login
   page becomes `https://andrew-warroom.cloudflareaccess.com`. Choose the
   **Free** plan — it covers 50 users.
3. **Settings → Authentication → Login methods → Add new → One-time PIN.**
   This emails a six-digit code to the person. No Google account, no password,
   nothing for them to set up. Add Google or GitHub as well if you like, but
   One-time PIN is the one that works for everybody.
4. **Access → Applications → Add an application → Self-hosted.**
   - **Application name:** `Graded Takes`
   - **Session duration:** 1 month (they will not want to re-verify weekly)
   - **Public hostname:**
     - Subdomain: `war-room`
     - Domain: `pages.dev`
     - Path: leave empty (protects the whole site)
   - Save and continue.
5. **Add a policy:**
   - **Policy name:** `The list`
   - **Action:** Allow
   - **Include → Emails** → add every address from `users.yaml`, one per line.
     Use **Emails ending in** only if you genuinely mean everybody at a
     company; for family, list the addresses.
   - Save.

> If Cloudflare will not let you enter `pages.dev` as the domain — some
> accounts restrict Access to zones you own — attach a custom domain to the
> Pages project first (**Custom domains → Set up a domain**), then create the
> Access application on that hostname instead. Everything else is identical.

### C5. Verify it, from outside

Do this. It is the only step that actually proves the door is shut.

1. Open a **private/incognito window**.
2. Go to `https://war-room.pages.dev/<some-token>/`.
3. You should get **Cloudflare's login page**, not the Graded Takes page.
4. Enter an email that is **not** on the policy. You should be refused.
5. Enter one that is. You get a code by email, and then the pages.

If step 3 shows you the page instead of a login screen, the Access application
is not on the right hostname — go back to C4 step 4 and check the subdomain
and domain fields character by character.

Repeat this check after any change to the Pages project. It takes a minute.

---

## D. Schedule it with launchd

macOS's own scheduler. Two jobs: publish, and check that publishing actually
happened.

### D1. The script the scheduler runs

```bash
mkdir -p ~/bin
cat > ~/bin/warroom-publish.sh <<'EOF'
#!/bin/bash
cd ~/Desktop/"War Room" || exit 1
echo "=== $(date) publish ==="
./publish.sh
code=$?
echo "publish exit $code"
if [ $code -le 1 ]; then
  wrangler pages deploy public --project-name war-room --branch main
  echo "deploy exit $?"
fi
exit $code
EOF
chmod +x ~/bin/warroom-publish.sh
```

Note `-le 1`: it uploads on 0 (clean) and on 1 (published but incomplete —
partial honest pages are better than yesterday's pages), and never on 2, which
means the publisher refused and there is nothing new to upload.

### D2. The publish job — Tuesday and Saturday, 6:10am

```bash
cat > ~/Library/LaunchAgents/com.warroom.publish.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.warroom.publish</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string>
         <string>-lc</string>
         <string>$HOME/bin/warroom-publish.sh</string></array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>2</integer>
          <key>Hour</key><integer>6</integer>
          <key>Minute</key><integer>10</integer></dict>
    <dict><key>Weekday</key><integer>6</integer>
          <key>Hour</key><integer>6</integer>
          <key>Minute</key><integer>10</integer></dict>
  </array>
  <key>StandardOutPath</key><string>/tmp/warroom-publish.log</string>
  <key>StandardErrorPath</key><string>/tmp/warroom-publish.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
EOF

launchctl unload ~/Library/LaunchAgents/com.warroom.publish.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.warroom.publish.plist
```

Weekday 2 is Tuesday, 6 is Saturday (0 and 7 are both Sunday). Run it once by
hand to be sure:

```bash
launchctl start com.warroom.publish
tail -f /tmp/warroom-publish.log
```

### D3. THE CAVEAT: a sleeping Mac does not publish

`launchd` cannot wake a sleeping Mac. If the lid is shut at 6:10am on Tuesday,
nothing runs.

What it *does* do is run a missed `StartCalendarInterval` job **once, shortly
after the Mac wakes up**. So in practice: you open the laptop at 8am, it
publishes then. That is usually fine — but it means "it publishes every
Tuesday at 6:10" is not true, and a Mac that stays shut all week publishes
nothing at all while every exit code involved stays 0.

Three ways to deal with it, in order of effort:

1. **Accept it**, and rely on `check-heartbeat` (D4) to tell you when it has
   not happened. This is the honest minimum and you should do it regardless.
2. **Schedule a wake.** With the Mac plugged in:
   ```bash
   sudo pmset repeat wakeorpoweron TS 06:05:00
   pmset -g sched          # confirm
   ```
   Wakes it at 06:05 on Tuesdays and Saturdays, five minutes before the job.
   A closed lid on battery still will not wake; power and (for a laptop)
   an external display or clamshell power setup are what make this reliable.
3. **Move it off the Mac** — a small always-on machine, or GitHub Actions.
   Out of scope here; the Mac is where your ESPN and Yahoo cookies live.

### D4. The alert — a content check, not an exit code

**This is the part that matters, and it is the part people skip.**

Everything in Graded Takes is built to degrade honestly and exit 0. So does this
publisher: a week where three feeds are down still produces pages, still says
what it does not know, and still exits 0. Which means *"the cron job ran fine"
proves nothing at all*. The failure that actually bites is silent: the Mac was
asleep, or the deploy step failed, and your brother has been reading week 3's
lineup since October while every log line says success.

So the heartbeat does not check that the job ran. It **re-reads the HTML
sitting in `public/`** and asserts the week stamped inside it is the week it
should be:

```bash
.venv/bin/python publish.py check-heartbeat
```

Exit 0 means every person's pages are present, fresh and stamped for the
expected week. Non-zero, with a reason, when:

- a person in `users.yaml` has never been published;
- a publish is older than 26 hours (`--max-age-hours` to change it);
- the last publish reported itself incomplete;
- **the pages on disk are stamped for a different week than they should be** —
  the stale-content case, caught even when the heartbeat file itself claims
  the right week;
- pages the heartbeat claims are missing from disk;
- a published file contains `127.0.0.1` or another person's league;
- a folder is still serving that belongs to nobody in `users.yaml`.

Schedule it daily, an hour after the publish window, and have it shout:

```bash
cat > ~/bin/warroom-check.sh <<'EOF'
#!/bin/bash
cd ~/Desktop/"War Room" || exit 1
out=$(.venv/bin/python publish.py check-heartbeat 2>&1)
code=$?
echo "$out"
if [ $code -ne 0 ]; then
  osascript -e 'display notification "Graded Takes publish is stale — see /tmp/warroom-check.log" with title "Graded Takes" sound name "Basso"'
fi
exit $code
EOF
chmod +x ~/bin/warroom-check.sh

cat > ~/Library/LaunchAgents/com.warroom.check.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.warroom.check</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string>
         <string>-lc</string>
         <string>$HOME/bin/warroom-check.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/warroom-check.log</string>
  <key>StandardErrorPath</key><string>/tmp/warroom-check.log</string>
</dict>
</plist>
EOF

launchctl unload ~/Library/LaunchAgents/com.warroom.check.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.warroom.check.plist
```

The same caveat applies — a sleeping Mac does not run the check either. But
the check job catches up on wake, and *its* failure mode is loud: it will tell
you the pages are stale the moment the Mac is open, which is exactly when you
can do something about it.

`osascript` posts a Mac notification. Swap in anything that reaches you —
`curl` to a webhook, a `mail` command, a Pushover call. The only requirement
is that a non-zero exit turns into something you will actually see.

---

## E. Removing someone

```bash
open -e users.yaml            # delete their entry
./publish.sh --prune          # deletes their folder from public/
wrangler pages deploy public --project-name war-room --branch main
```

Then remove their email from the Access policy (Zero Trust → Access →
Applications → Graded Takes, or whatever you named it → Policies).

Do all three. Deleting the entry alone leaves the folder published; pruning
alone leaves them able to log in and try paths.

Note that Cloudflare keeps old deployments: the previous upload stays
reachable at its own `<hash>.war-room.pages.dev` preview URL. Access covers
the production hostname you configured, not those. If somebody's token needs
to be genuinely, immediately dead, rotate the token (B) rather than relying on
deletion — and if you need old deployments gone, delete them in the dashboard
under **Workers & Pages → war-room → Deployments**.

---

## F. When something is wrong

| Symptom | What it means |
|---|---|
| `exit 2: REFUSED` | A safety assertion failed. The full reason is printed above it. Nothing was published. Read it — it names the file and the string that caused it. |
| `token ... is 15 characters` | You typed a token instead of generating one. Go back to A2. |
| `no leagues/<id>.yaml` | The league config is missing or its filename does not match its `id:`. |
| `league id must be ... at least 3 characters` | Rename the league. Short ids cannot be checked for safely. |
| `unexpected file(s) in ...'s staging directory` | A renderer wrote something the allowlist does not know about. Do not widen the allowlist to make it go away without understanding what the file is. |
| `contains the league name '...'` | A page genuinely mentions another person's league — almost always cross-league exposure. See **Cross-league exposure** above. Nothing was published. |
| `NOTE - N renderer(s) are not confined to ...` | Printed before rendering starts: those renderers still read all of `data/rosters/`. Not a prediction of refusal — the renderer that prints league names is confined. |
| `still contains '127.0.0.1'` | A page links to your local settings panel somewhere the substitution does not reach. Nothing was published. |
| `THE PAGES ON DISK ARE STALE` | Publishing has not actually happened for a while — usually a sleeping Mac (D3) or a failed `wrangler` step. |
| `orphaned directory ... belongs to nobody` | Somebody was removed from `users.yaml` but their folder is still there. `./publish.sh --prune`. |
| Login screen never appears | The Zero Trust application is on the wrong hostname. C4, step 4. |
| `Offline install is not available in this copy` | `engine/pwa.py` was missing or failed. Everything else published; there is just no home-screen install page. |

---

## G. The one-page version

```bash
cd ~/Desktop/"War Room"

# add a person
.venv/bin/python publish.py new-token          # paste into users.yaml
open -e users.yaml

# rehearse
./publish.sh --dry-run

# publish + upload
./publish.sh
wrangler pages deploy public --project-name war-room --branch main

# prove it is still working
.venv/bin/python publish.py check-heartbeat
```

Cloudflare Access must be a **Zero Trust self-hosted application** on
`war-room.pages.dev`. The toggle in the Pages project settings covers preview
deployments only, and protects nothing that you have sent to anybody.
