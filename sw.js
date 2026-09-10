'use strict';
/* War Room service worker - engine/pwa.py wrote this file; edit that.

   The whole contract in one line: this worker may make the app OPEN
   offline, and it may never make the app LIE. Anything it serves from the
   cache is rewritten with a banner that says so before it is handed over. */

var CACHE  = "warroom-v1-wk1-20260909T183024";
var PREFIX = "warroom-";
var WEEK   = 1;
var BUILT  = "Wed 9 Sep, 6:30 PM";
var START  = "./home.html";
var SHELL  = [
  "./home.html",
  "./sources.html",
  "./install.html",
  "./manifest.webmanifest",
  "./lineup-espn-1-week1.html",
  "./board-espn-1-week1.html",
  "./digest-espn-1-week1.html",
  "./tradedesk-espn-1-week1.html",
  "./lineup-yahoo-main-week1.html",
  "./board-yahoo-main-week1.html",
  "./digest-yahoo-main-week1.html",
  "./tradedesk-yahoo-main-week1.html",
  "./icons/icon.svg",
  "./icons/apple-touch-icon-180.png",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png"
];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) {
      return c.add(new Request(u, {cache: 'reload'}))['catch'](function () {});
    }));
  }).then(function () { return self.skipWaiting(); }));
});

/* A new publish supersedes the old one outright: every warroom- cache that
   is not this exact version goes, so a stale week cannot survive a
   deploy. */
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.map(function (k) {
      if (k !== CACHE && k.lastIndexOf(PREFIX, 0) === 0) {
        return caches['delete'](k);
      }
      return null;
    }));
  }).then(function () { return self.clients.claim(); }));
});

function isPage(req) {
  if (req.mode === 'navigate') { return true; }
  var a = req.headers.get('accept') || '';
  return a.indexOf('text/html') > -1;
}

/* THE BANNER. Not decoration - the reason the cache is allowed to exist.
   It names the week, names the build time, and refuses to imply anything
   in the page has been re-checked. Colours are the page's own tokens, so
   it lands in whichever theme the reader chose. */
function banner() {
  return '<div class="wr-offline" role="status" aria-live="polite">'
    + '<b>Offline &mdash; showing week ' + WEEK + ' as of ' + BUILT + '.</b> '
    + 'This is the saved copy your phone already had. Injuries, kickoffs, '
    + 'scores and every verdict below were true when it was built and have '
    + 'not been checked since. Reconnect and reload for the current read.'
    + '</div>'
    + '<style>.wr-offline{margin:0 0 16px;padding:12px 14px;'
    + 'border-left:3px solid var(--wr-rule);background:var(--wr-wash-hot);'
    + 'color:var(--wr-text);font-size:var(--wr-t3);line-height:1.45;'
    + 'border-radius:0 6px 6px 0;}'
    + '.wr-offline b{display:block;margin-bottom:2px;}</style>';
}

/* Rewrite on the way out. The banner goes just inside <main> so it sits
   under the sticky bar and inside the page's own gutters; <body> is the
   fallback for any document that ever stops using <main>. */
function stale(res) {
  return res.text().then(function (body) {
    var mark = banner();
    var out = body.replace(/<main\b[^>]*>/, function (m) { return m + mark; });
    if (out === body) {
      out = body.replace(/<body\b[^>]*>/, function (m) { return m + mark; });
    }
    if (out === body) { out = mark + body; }
    var h = new Headers();
    h.set('Content-Type', 'text/html; charset=utf-8');
    h.set('X-WarRoom-Offline', '1');
    return new Response(out, {status: 200, statusText: 'offline copy',
                              headers: h});
  });
}

function nothingSaved() {
  return new Response(
    '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
    + '<meta name="viewport" content="width=device-width,initial-scale=1">'
    + '<title>War Room &mdash; offline</title>'
    + '<body style="margin:0;padding:28px;background:#F4F2EC;'
    + 'color:#101B33;'
    + 'font:15px/1.5 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">'
    + '<h1 style="font-size:26px;margin:0 0 10px">Offline</h1>'
    + '<p>War Room has no saved copy of this page yet, so it has nothing to '
    + 'show you and will not guess. Reconnect and open it once; after that '
    + 'it opens without a signal.</p>',
    {status: 503, headers: {'Content-Type': 'text/html; charset=utf-8'}});
}

function keep(req, res) {
  if (res && res.ok && res.type !== 'opaque') {
    var copy = res.clone();
    caches.open(CACHE).then(function (c) {
      c.put(req, copy)['catch'](function () {});
    })['catch'](function () {});
  }
  return res;
}

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') { return; }
  var url;
  try { url = new URL(req.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) { return; }

  if (isPage(req)) {                       /* network-first, honest fallback */
    e.respondWith(
      fetch(req).then(function (res) { return keep(req, res); })
        ['catch'](function () {
          return caches.match(req, {ignoreSearch: true}).then(function (hit) {
            if (hit) { return stale(hit); }
            return caches.match(START).then(function (home) {
              return home ? stale(home) : nothingSaved();
            });
          });
        })
    );
    return;
  }

  /* icons and the manifest: cache-first - they cannot go stale inside a
     cache version, and they are what makes the app open without a flash */
  e.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) { return hit; }
      return fetch(req).then(function (res) { return keep(req, res); });
    })['catch'](function () { return fetch(req); })
  );
});
