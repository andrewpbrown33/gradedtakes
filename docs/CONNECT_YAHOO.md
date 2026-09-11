# Connecting your Yahoo league

*This is the note to send to whoever wants their Yahoo leagues read. It is
written to be pasted as-is. Nothing in it asks them to install anything, sign
up for anything, or trust anything they can't check.*

---

## The short version

1. I send you a link.
2. You open it and press **Allow** on Yahoo's own page.
3. Yahoo shows you a short code. You send me that code.
4. Done.

There is no app to install, no account to make, no developer anything. It
takes about a minute.

---

## What you are actually agreeing to

The link opens **Yahoo's** consent screen — the real one, on
`api.login.yahoo.com`, with your Yahoo login and Yahoo's branding. You should
check the address bar; if it isn't Yahoo, don't type anything.

That screen will tell you two things:

* **which app is asking** — it'll be named *Graded Takes*, which is mine
  (an older registration may still show its earlier name, *War Room*)
* **what it's asking for** — **Fantasy Sports: Read**

Read means read. The tool can see your league settings, your roster, your
matchups, and the other teams in your league. It **cannot** add, drop, claim,
trade, or set your lineup. That isn't a promise about how carefully I coded
it — Yahoo enforces it at their end, because I registered the app for read
access only. There is no write permission to misuse.

---

## What I never get

**Not your password.** You type it into Yahoo, on Yahoo's page, the same as
always. It never comes near me or my computer.

**Not your session cookie.** Some fantasy tools ask you to dig a cookie out of
your browser's developer tools and paste it to them. Don't do that — for this
tool or any other. That hands over your whole logged-in Yahoo session, not just
fantasy, it can't be scoped, it usually can't be revoked without changing your
password, and it breaks Yahoo's terms for *you*. This tool will never ask.

**Not a blank cheque.** What I get is a token that only works for reading
Fantasy Sports, only for the app you approved, and only until you turn it off.

The short code you send me is a one-time authorization code. On its own it's
useless — it expires in minutes, works exactly once, and can only be redeemed
by someone holding my app's secret. It is not a password and not a login.

---

## How to turn it off

Any time, without asking me, without telling me:

**Yahoo → Account Info → Recent activity → "Apps connected to your account" →
find *Graded Takes* (or *War Room*) → Remove.**

(Yahoo also lists third-party connections under **Account Security → External
connections**. Either route works.)

The moment you do that, my next attempt to read your league fails with
"revoked" and I get nothing further. No stored copy keeps working — see below.

---

## What gets stored, and for how long

Yahoo's developer terms cap this, and I follow the cap rather than working
around it. Yahoo APIs Terms of Use §2.1:

> "You may not retain or use, and must immediately remove from any Application
> and any data repository in your possession or under your control any Yahoo
> user data obtained through the Yahoo APIs that is not explicitly identified
> as being storable indefinitely in the API Documents within **24 hours** after
> the time at which you obtained the data"

So, concretely:

* Every file the tool writes from your league — settings, roster — is stamped
  with the time it was fetched and the time it expires, 24 hours later.
* Expired files are deleted, not just marked. Every import sweeps anything
  already past its 24 hours, and `./yahoo.sh purge` does it on demand.
  Re-running the import pulls a fresh copy.
* **Your fantasy data is not accumulated.** There is no growing archive of your
  rosters. What persists across weeks is my own output — "here is what the tool
  recommended, here is whether it was right" — which is a record of my
  advice, not a copy of your league.

That last point is a real constraint on the product, not a nicety: it means the
weekly accuracy ledger scores *predictions*, and can't be built by warehousing
your Yahoo data week over week. If you ever want that trade-off explained
further, ask.

Your tokens live in one file on my Mac, readable only by my user account
(`chmod 600`), and are never printed to a screen, written into a log, or
included in any published page. There's a test that asserts exactly that.

---

## Step by step

### 1. Open the link I send you

It looks like this (yours will have a different `state`):

```
https://api.login.yahoo.com/oauth2/request_auth?client_id=...&scope=fspt-r&redirect_uri=oob&response_type=code&state=...
```

`scope=fspt-r` is Yahoo's code for **Fantasy Sports, read-only**. (`fspt-w`
would be read *and write*. You will not see that, ever.)

### 2. Sign in to Yahoo if it asks, and press Allow

Same Yahoo account that owns the fantasy team. If you have more than one Yahoo
login, this is the moment to get it right — I can only see leagues belonging to
whichever account you approve with.

### 3. Send me the code

**If you see a page with a short code on it:** that's it. Send me that code —
the code alone, nothing else.

**If instead your browser tries to load `localhost:8080` and fails** with
something like "can't connect" — that is expected, not an error. The code is in
the address bar. Copy the **whole address** and send me that; my end pulls the
code out of it.

Send it reasonably promptly. These codes expire in minutes. If it's gone stale,
just say so and I'll send a fresh link — there's no limit on retries.

### 4. Nothing else

I run two commands and tell you which leagues came through. If one is missing,
tell me its name.

---

## If you'd rather not

Then don't. Say no and nothing happens — you can also just close the consent
page, or press Deny, and I'll see "declined" rather than silence. Sleeper
leagues need no authorization at all (a username is enough, because Sleeper's
data is public), so if you have one of those we can start there instead and you
can decide about Yahoo later.

---

## Questions worth asking me

* *"Can you see my email / contacts / anything outside fantasy?"* No. The grant
  is scoped to Fantasy Sports read. Yahoo shows you the scope before you agree;
  if that screen ever asks for more than fantasy, refuse and tell me.
* *"Can you change my lineup?"* No. Read-only, enforced by Yahoo. And there is
  no lineup-setting code in the tool at all.
* *"What happens when the season ends?"* Remove the app from your Yahoo account
  and it's over. Or tell me and I'll delete the token from my end too — though
  you should do the Yahoo-side removal regardless, since that's the half that's
  actually under your control.
