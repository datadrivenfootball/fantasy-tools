"""JEG-1548: the visit counter (app/next/analytics.js) sends only fixed, allow-listed labels, and nothing at all when off.

Every request the browser makes is recorded (context-level, so nothing is missed: fetch, images, beacons, navigations).
The counter is switched on for a test by serving analytics.js with a site code and 127.0.0.1 added to its hosts (the
real file ships with an empty code).

1. Off by default: the shipped file sends no request off the page's own host on any page, even with a full #s= link
   and a ?src= tag; the tag is still removed from the address bar and the hash is left exactly as it was.
2. On, every page in PAGES: each counter request is GET https://<code>.goatcounter.com/count with exactly p, e and rnd,
   p is the page's fixed label or an allow-listed event, no Referer and no cookie header, and no request to any host
   carries the league name, a team name, a player name, the #s= token, the query or the hash.
3. Do Not Track and Global Privacy Control: nothing is sent.
4. A failing or blocked counter never throws, no script logs a console error (Chrome's own "Failed to load resource"
   line for a blocked request cannot be stopped by any method), and the layout does not change.
5. 390 and 1440: the device event matches the width; no horizontal overflow with the footer note.
6. No cookies, and analytics.js never writes to localStorage, sessionStorage or document.cookie; the same storage keys
   exist with the counter on as off.
7. Key actions send their fixed event names (paste, link, override, bookmark, Start fresh); unknown names are dropped.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urlsplit

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "next" / "analytics.js"
FIXTURES = ROOT / "tests" / "fixtures" / "entry_paste"
CODE = "ddftest"
VENDOR = f"https://{CODE}.goatcounter.com/count"
# Static web fonts the pages already load (not analytics; fixed URLs). Every other off-host request must be the counter.
FONT_HOSTS = ("https://fonts.googleapis.com/", "https://fonts.gstatic.com/")
GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")
PAGES = {"index.html": "/", "connect.html": "/entry/connect", "setup.html": "/entry/setup",
         "settings.html": "/entry/settings", "team.html": "/workspace/team", "explore.html": "/workspace/explore",
         "partners.html": "/workspace/partners", "find.html": "/workspace/find", "waivers.html": "/workspace/waivers",
         "build.html": "/build", "values.html": "/values", "learn.html": "/learn", "ai.html": "/ai"}
LEAGUE = "Quokka Sentinel League"
TEAMS = ["Zebra Sentinel Squad", "Narwhal Sentinel Crew"]
PLAYERS = ["Josh Allen", "Jahmyr Gibbs"]
NO_DNT = "() => true"
DNT = "Object.defineProperty(Navigator.prototype, 'doNotTrack', {get: () => '1'});"
GPC = "Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {get: () => true});"
# Records every write to cookies and web storage with the calling script, so a write from analytics.js is caught.
WRITE_SPY = """(() => {
  window.__writes = [];
  const who = () => (new Error().stack || '').split('\\n').slice(2).join(' ');
  const set = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) { window.__writes.push(['storage', String(k), who()]); return set.apply(this, arguments); };
  const desc = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
  Object.defineProperty(Document.prototype, 'cookie', {configurable: true, get() { return desc.get.call(this); },
    set(v) { window.__writes.push(['cookie', String(v), who()]); return desc.set.call(this, v); }});
})();"""


def enabled_source() -> bytes:
    text = SOURCE.read_text(encoding="utf-8")
    assert "var GOATCOUNTER_CODE = '';" in text, "analytics.js must ship with an empty site code"
    text = text.replace("var GOATCOUNTER_CODE = '';", f"var GOATCOUNTER_CODE = '{CODE}';")
    text = text.replace("var HOSTS = ['datadrivenfootball.github.io'];", "var HOSTS = ['datadrivenfootball.github.io', '127.0.0.1'];")
    assert f"'{CODE}'" in text and "'127.0.0.1'" in text
    return text.encode("utf-8")


def setUpModule():
    _render_env.ensure_built()


class AnalyticsPrivacyTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._off = serve()
        cls.off_base = cls._off.__enter__()
        cls._on = serve(overrides={"analytics.js": enabled_source()})
        cls.on_base = cls._on.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except PlaywrightError as exc:
            cls._pwcm.__exit__(None, None, None)
            cls._on.__exit__(None, None, None)
            cls._off.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        cls.token = cls._make_token()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._on.__exit__(None, None, None)
        cls._off.__exit__(None, None, None)

    @classmethod
    def _make_token(cls) -> str:
        """A real #s= link with a named league, named teams and players, built by the site's own codec."""
        context = cls.browser.new_context()
        page = context.new_page()
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
        page.goto(f"{cls.off_base}/index.html", wait_until="load", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.link && DDF.link.encode", timeout=20000)
        url = page.evaluate("""([league, teams, players]) => DDF.link.encode({v: 1, view: 'team', name: league,
            settings: {scoring: 'ppr', teams: 12, superflex: false, slots: [1, 2, 2, 1, 1, 7]},
            teams: [{name: teams[0], players: [players[0]]}, {name: teams[1], players: [players[1]]}], me: 0},
            {context: false})""", [LEAGUE, TEAMS, PLAYERS])
        context.close()
        token = url.split("#", 1)[1]
        assert token.startswith("s="), url
        return token

    # ---- harness ----
    def page(self, width=1440, init=NO_DNT, vendor="ok", spy=False):
        context = self.browser.new_context(viewport={"width": width, "height": 900})
        self.addCleanup(context.close)
        if init != NO_DNT:
            context.add_init_script(init)
        if spy:
            context.add_init_script(WRITE_SPY)
        requests, console, errors = [], [], []
        context.on("request", lambda r: requests.append(r))

        def route(r):
            url = r.request.url
            if url.startswith("http://127.0.0.1"):
                return r.continue_()
            if url.startswith(VENDOR) and vendor == "ok":
                return r.fulfill(status=200, body=GIF, content_type="image/gif")
            return r.abort()
        context.route("**/*", route)
        page = context.new_page()
        # the static font requests are aborted here (hermetic run); their load errors are not the counter's
        page.on("console", lambda m: console.append(m) if m.type == "error"
                and not str((m.location or {}).get("url", "")).startswith(FONT_HOSTS) else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.requests, page.console, page.errors = requests, console, errors
        return page

    def open(self, page, base, path, wait=True):
        page.goto(f"{base}/{path}", wait_until="load", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF._analytics", timeout=20000)
        if wait:
            page.wait_for_timeout(400)

    def offsite(self, page, fonts=False):
        """Requests off the page's host; the static font requests only when fonts=True (the leak check reads them)."""
        return [r for r in page.requests if not r.url.startswith("http://127.0.0.1")
                and (fonts or not r.url.startswith(FONT_HOSTS))]

    def counts(self, page):
        """(p, e) for every counter request, after checking its shape."""
        out = []
        for r in self.offsite(page):
            self.assertTrue(r.url.startswith(VENDOR + "?"), f"request off the page's host that is not the counter: {r.url}")
            parts = urlsplit(r.url)
            q = parse_qs(parts.query, keep_blank_values=True)
            self.assertEqual(set(q), {"p", "e", "rnd"}, r.url)
            self.assertEqual(r.method, "GET")
            self.assertIsNone(r.post_data)
            self.assertEqual(parts.fragment, "")
            headers = {k.lower(): v for k, v in r.headers.items()}
            self.assertNotIn("referer", headers, r.url)
            self.assertNotIn("cookie", headers, r.url)
            self.assertIn(q["e"][0], ("true", "false"))
            self.assertRegex(q["rnd"][0], r"^[a-z0-9]{1,8}$")
            out.append((q["p"][0], q["e"][0] == "true"))
        return out

    def assert_no_league_data(self, page):
        secrets = [LEAGUE, *TEAMS, *PLAYERS, self.token[2:22], "leak", "Sentinel", "Gridiron", "Taco"]
        for r in self.offsite(page, fonts=True):
            blob = r.url + " " + " ".join(f"{k}:{v}" for k, v in r.headers.items()) + " " + (r.post_data or "")
            blob += " " + unquote_plus(blob)
            for s in secrets:
                for form in {s, s.replace(" ", "+"), s.replace(" ", "%20"), s.lower()}:
                    self.assertNotIn(form, blob, f"{s!r} left the browser in {r.url}")

    def allowed(self, page):
        return page.evaluate("() => ({pages: Object.values(DDF._analytics.PAGES), events: DDF._analytics.EVENTS})")

    # ---- 1. off by default ----
    def test_off_by_default_sends_nothing_and_still_cleans_the_tag(self):
        self.assertIn("var GOATCOUNTER_CODE = '';", SOURCE.read_text(encoding="utf-8"))
        for name in PAGES:
            page = self.page()
            self.open(page, self.off_base, f"{name}?src=claude-find_trades&leak=Quokka#{self.token}")
            self.assertEqual(self.offsite(page), [], f"{name}: a request left the page with the counter off")
            self.assertFalse(page.evaluate("() => DDF._analytics.on()"))
            self.assertNotIn("src=", page.evaluate("() => location.search"), name)
            self.assertFalse(page.evaluate("() => DDF.track('start-fresh')"))
            self.assertEqual(page.errors, [], name)

    # ---- 2. on: every page sends only allow-listed labels ----
    def test_every_page_sends_only_allowlisted_labels(self):
        for name, label in PAGES.items():
            for suffix in ("", f"?src=claude-find_trades&leak=Quokka+Sentinel#{self.token}"):
                page = self.page()
                self.open(page, self.on_base, name + suffix)
                page.wait_for_timeout(600)
                allowed = self.allowed(page)
                sent = self.counts(page)
                self.assert_no_league_data(page)
                views = [p for p, e in sent if not e]
                events = [p for p, e in sent if e]
                for p in views:
                    self.assertIn(p, allowed["pages"], name)
                for p in events:
                    self.assertIn(p, allowed["events"], name)
                if suffix:
                    self.assertIn("visit/claude/find_trades", events, name)
                    self.assertNotIn("src=", page.evaluate("() => location.search"))
                    self.assertTrue(page.evaluate("() => /(^|[#&])s=/.test(location.hash)"), f"{name}: the #s= hash must stay")
                else:
                    self.assertIn("visit/direct", events, name)
                    # a page that forwards (connect with a link, legacy routes) counts its landing page instead
                    self.assertEqual(views[:1], [label], f"{name}: {sent}")
                self.assertIn("device/desktop", events, name)
                self.assertEqual(page.errors, [], name)

    def test_saved_link_without_tag_and_bad_tags(self):
        page = self.page()
        self.open(page, self.on_base, f"team.html#{self.token}")
        self.assertIn(("visit/saved-link", True), self.counts(page))
        for bad in ("claude-steal_names", "Quokka", "claude-find_trades%20x", "chatgpt-"):
            page = self.page()
            self.open(page, self.on_base, f"values.html?src={bad}")
            events = [p for p, e in self.counts(page) if e]
            self.assertIn("visit/other-tag", events, bad)
            self.assertFalse([p for p in events if "Quokka" in p or "steal" in p], bad)
            self.assertNotIn("src=", page.evaluate("() => location.search"))

    def test_tag_removed_even_when_the_wrapper_is_blocked(self):
        """site.js takes the tag off at once, so a blocked analytics.js cannot leave it for a Bookmark link."""
        page = self.page()
        page.route("**/analytics.js*", lambda r: r.abort())
        page.goto(f"{self.on_base}/find.html?src=claude-find_trades&keep=a%20b&flag#{self.token}", wait_until="load", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.link", timeout=20000)
        self.assertEqual(page.evaluate("() => location.search"), "?keep=a%20b&flag")
        self.assertEqual(page.evaluate("() => location.hash"), "#" + self.token)
        self.assertEqual(self.offsite(page), [])

    def test_page_code_cannot_fake_a_source_or_device(self):
        page = self.page()
        self.open(page, self.on_base, "values.html")
        for name in ("visit/claude", "visit/claude/find_trades", "device/phone", "visit/direct"):
            self.assertFalse(page.evaluate("(n) => DDF.track(n)", name), name)

    def test_chatgpt_tag_through_connect_forwarding(self):
        page = self.page()
        self.open(page, self.on_base, f"connect.html?src=chatgpt-make_state#{self.token}")
        page.wait_for_function("() => /team\\.html/.test(location.pathname)", timeout=20000)
        page.wait_for_function("() => window.DDF && DDF._analytics", timeout=20000)
        page.wait_for_timeout(500)
        events = [p for p, e in self.counts(page) if e]
        self.assertIn("visit/chatgpt/make_state", events)
        self.assertTrue(page.evaluate("() => /(^|[#&])s=/.test(location.hash)"))
        self.assertEqual(page.evaluate("() => location.search"), "")
        self.assert_no_league_data(page)

    # ---- 3. DNT / GPC ----
    def test_do_not_track_and_gpc_send_nothing(self):
        for init in (DNT, GPC):
            for name in ("index.html", "team.html", "values.html"):
                page = self.page(init=init)
                self.open(page, self.on_base, f"{name}?src=claude#{self.token}")
                page.evaluate("() => DDF.track('start-fresh')")
                page.wait_for_timeout(300)
                self.assertEqual(self.offsite(page), [], f"{init[:40]} {name}")
                self.assertFalse(page.evaluate("() => DDF._analytics.on()"))

    # ---- 4. failure never throws, no console errors, no layout change ----
    def test_blocked_counter_never_throws_or_moves_the_page(self):
        sizes = {}
        for vendor in ("ok", "blocked"):
            page = self.page(vendor=vendor)
            self.open(page, self.on_base, "values.html")
            self.assertTrue(page.evaluate("() => DDF.track('value-override-set')"))
            self.assertFalse(page.evaluate("() => DDF.track('Quokka Sentinel League')"))
            self.assertFalse(page.evaluate("() => DDF.track({toString(){ throw new Error('x'); }})"))
            page.wait_for_timeout(400)
            self.assertEqual(page.errors, [], vendor)
            # Chrome itself logs "Failed to load resource" for any blocked request (fetch, image and beacon alike;
            # no script can stop it). That browser line for the counter URL is the only console error allowed.
            noise = [m.text for m in page.console
                     if not (m.text.startswith("Failed to load resource") and str(m.location.get("url", "")).startswith(VENDOR))]
            self.assertEqual(noise, [], vendor)
            sizes[vendor] = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
        self.assertEqual(sizes["ok"], sizes["blocked"])

    # ---- 5. phone and desktop ----
    def test_device_class_and_no_overflow(self):
        for width, device in ((390, "device/phone"), (1440, "device/desktop")):
            for name in ("index.html", "team.html", "learn.html", "connect.html"):
                page = self.page(width=width)
                self.open(page, self.on_base, name)
                events = [p for p, e in self.counts(page) if e]
                self.assertIn(device, events, f"{name} at {width}")
                self.assertNotIn("device/phone" if width > 390 else "device/desktop", events)
                note = page.locator(".ddf-count-note")
                self.assertGreaterEqual(note.count(), 1, name)
                self.assertNotRegex(note.first.inner_text(), r"(?i)player pool|DDF")
                over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
                self.assertLessEqual(over, 0, f"{name} at {width} overflows by {over}px")
                self.assertEqual(page.errors, [], name)

    def test_note_absent_when_off(self):
        page = self.page()
        self.open(page, self.off_base, "values.html")
        self.assertEqual(page.locator(".ddf-count-note").count(), 0)

    # ---- 6. no cookies, no storage ----
    def test_no_cookies_and_no_storage_writes(self):
        keys = {}
        for base in (self.off_base, self.on_base):
            page = self.page(spy=True)
            self.open(page, base, f"team.html?src=claude-get_values#{self.token}")
            page.evaluate("() => { DDF.track('bookmark-clicked'); DDF.track('value-override-set'); }")
            page.wait_for_timeout(400)
            self.assertEqual(page.evaluate("() => document.cookie"), "")
            self.assertEqual(page.context.cookies(), [])
            writes = page.evaluate("() => window.__writes")
            self.assertFalse([w for w in writes if "analytics.js" in w[2]], writes)
            self.assertFalse([w for w in writes if w[0] == "cookie"], writes)
            keys[base] = page.evaluate("() => [Object.keys(localStorage).sort(), Object.keys(sessionStorage).sort()]")
        self.assertEqual(keys[self.off_base], keys[self.on_base])

    # ---- 7. key actions ----
    def test_key_actions_send_fixed_names(self):
        page = self.page()
        self.open(page, self.on_base, "connect.html")
        page.wait_for_function("() => DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leaguePaste", timeout=60000)
        page.fill("#rosters", (FIXTURES / "03-espn.txt").read_text(encoding="utf-8"))
        page.click("#recognize-button")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        page.evaluate("(t) => DDF.link.decodeBlock('#' + t)", self.token)
        page.evaluate("() => DDF.overrides.set('Josh Allen', 99)")
        page.wait_for_timeout(500)
        events = [p for p, e in self.counts(page) if e]
        for name in ("league-added/paste", "league-added/link", "value-override-set"):
            self.assertIn(name, events)
        self.assert_no_league_data(page)

        page = self.page()
        self.open(page, self.on_base, f"team.html#{self.token}")
        page.wait_for_selector(".ddf-bm:visible", timeout=20000)
        page.click(".ddf-bm")
        page.wait_for_timeout(400)
        self.assertIn(("bookmark-clicked", True), self.counts(page))
        page.evaluate("() => DDF.startFresh.open()")
        page.click(".ddf-sf-go")
        page.wait_for_url(re.compile(r".*/connect\.html.*"), timeout=20000)
        page.wait_for_timeout(400)
        self.assertIn(("start-fresh", True), self.counts(page))
        self.assert_no_league_data(page)
        self.assertEqual(page.errors, [])


if __name__ == "__main__":
    unittest.main()
