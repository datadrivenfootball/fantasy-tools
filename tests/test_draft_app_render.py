"""Draft tool Phase 1 page (JEG-1667): app/draft/index.html in headless Chromium.

Gates covered here:
1. A full 12-team mock auction, end to end, from the keyboard only: arrow keys and "/" search pick the player,
   digits type the bid, W / P bid walk-away / push floor, M is my buy, S plus a team letter is a sale, U undoes.
2. Every sale recomputes and redraws the board in under 200 ms (the page's own timer).
3. A mid-draft link reopens in a new page to a deep-equal state and the same board.
4. The engine.md worked example is drawn on the board to the dollar.
5. The stale warning shows when the pull is older than a day, and not before.
6. Setup: a league ID loads a league (platform answered by fixtures); a private league falls back to the settings
   page link and the paste box; the values screen shows ours, market, platform, spread, tier and price source,
   and an override re-prices.
7. No horizontal scroll at 375 px.

The page is not live (hold of 2026-11-16): it is served from app/ here and is not copied to dist/.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve
from tests.draft_app_fixture import PULLED_AT, bundle

ROOT = Path(__file__).resolve().parents[1]
LINEUP = json.loads((ROOT / "config" / "lineup_parameters.json").read_text())
WORKED = json.loads((ROOT / "tests" / "fixtures" / "draft_worked_example.json").read_text())["auction"]
LEAGUE_FX = ROOT / "tests" / "fixtures" / "draft_league"
PAGE = "app/draft/index.html"
PULL_MS = "Date.parse(%s)" % json.dumps(PULLED_AT)

STATE_JS = """() => {
  const a = DraftApp.app, d = a.calc.derived;
  const visible = [...document.querySelectorAll('#rows tr[data-key]')].map(r => r.getAttribute('data-key'));
  return { me: a.state.me, picks: a.state.picks.length, sel: a.sel, visible, lastMs: a.lastMs, maxMs: a.maxMs,
    teams: d.teams.map(t => ({ open: t.open, left: t.budgetLeft, max: a.calc.board.maxBids[t.id], overflow: t.overflow })),
    avail: d.available.slice(0, 260).map(k => ({ k, pos: a.model.pos[k], name: a.model.players[k].name,
      market: a.calc.rows[k].marketInflated, walk: a.calc.rows[k].walkAway, push: a.calc.rows[k].pushFloor })) };
}"""


def preview_script(extra: str = "", hours_after_pull: float = 2) -> str:
    return ("window.DRAFT_PREVIEW = { bundle: %s, lineup: %s, now: %s + %s * 3600000 %s };"
            % (json.dumps(bundle()), json.dumps(LINEUP), PULL_MS, hours_after_pull, extra))


class DraftPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise _render_env.unavailable("playwright is not installed")
        cls._server = serve(ROOT)
        cls.base = cls._server.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except Exception as exc:  # no browser on this machine
            cls._pwcm.__exit__(None, None, None)
            cls._server.__exit__(None, None, None)
            raise _render_env.unavailable(f"chromium could not start: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._server.__exit__(None, None, None)

    def open(self, script=None, width=1280, fragment="", routes=None):
        ctx = self.browser.new_context(viewport={"width": width, "height": 900})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        for pattern, handler in (routes or {}).items():
            page.route(pattern, handler)
        page.add_init_script(script if script is not None else preview_script())
        page.goto(self.base.rstrip("/") + "/" + PAGE + fragment)
        page.wait_for_function("() => window.DraftApp && DraftApp.app.calc && document.querySelector('#app[data-view]')")
        return page

    # ------------------------------------------------------------------ 1, 2
    def test_full_12_team_auction_from_the_keyboard(self):
        page = self.open()
        self.assertEqual(page.get_attribute("#app", "data-view"), "setup")  # a new draft opens on Setup
        page.keyboard.press("b")
        self.assertEqual(page.get_attribute("#app", "data-view"), "board")
        kb = page.keyboard
        slots_per_team = 15
        total = 12 * slots_per_team
        want_order = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST", "BN"]
        used = {"arrow": 0, "search": 0, "walk": 0, "push": 0, "mine": 0, "sold": 0, "undo": 0}
        timings = []
        for n in range(total):
            st = page.evaluate(STATE_JS)
            self.assertEqual(st["picks"], n)
            # the team with the most open slots buys next, so every roster fills
            buyer = max(range(12), key=lambda i: (sum(st["teams"][i]["open"].values()), -i))
            team = st["teams"][buyer]
            slot = next(s for s in want_order if team["open"][s] > 0)
            fits = {"FLEX": ("RB", "WR", "TE"), "SUPERFLEX": ("QB", "RB", "WR", "TE"), "BN": ("QB", "RB", "WR", "TE")}.get(slot, (slot,))
            target = next(p for p in st["avail"] if p["pos"] in fits)
            # pick the player: arrows when he is near the selection, "/" search otherwise
            vis = st["visible"]
            if target["k"] in vis and st["sel"] in vis and abs(vis.index(target["k"]) - vis.index(st["sel"])) <= 6:
                step = vis.index(target["k"]) - vis.index(st["sel"])
                for _ in range(abs(step)):
                    kb.press("ArrowDown" if step > 0 else "ArrowUp")
                used["arrow"] += 1
            else:
                kb.press("/")
                kb.type(target["name"])
                kb.press("Enter")
                used["search"] += 1
            self.assertEqual(page.evaluate("DraftApp.app.sel"), target["k"])
            self.assertEqual(page.inner_text("#block-name"), target["name"])
            price = max(1, min(team["max"], round((target["market"] or 1) * 0.9)))
            mine = buyer == st["me"]
            if mine and target["walk"] >= 1 and (used["walk"] + used["push"]) % 2 == 0:
                kb.press("w")
                price = target["walk"]
                used["walk"] += 1
            elif mine and target["push"]:
                kb.press("p")
                price = target["push"]
                used["push"] += 1
            else:
                kb.type(str(price))
            self.assertEqual(page.input_value("#bid"), str(price))
            if mine:
                kb.press("m")
                used["mine"] += 1
            else:
                kb.press("s")
                self.assertTrue(page.is_visible("#buyers"))
                kb.press(chr(ord("a") + buyer))
                used["sold"] += 1
            after = page.evaluate("() => ({ picks: DraftApp.app.state.picks, ms: DraftApp.app.lastMs })")
            self.assertEqual(after["picks"][-1], [target["k"], buyer, price])
            timings.append(after["ms"])
            if n == 40:  # undo the sale and record it again
                kb.press("u")
                self.assertEqual(page.evaluate("DraftApp.app.state.picks.length"), n)
                self.assertEqual(page.evaluate("DraftApp.app.sel"), target["k"])
                self.assertEqual(page.input_value("#bid"), str(price))
                kb.press("m" if mine else "s")
                if not mine:
                    kb.press(chr(ord("a") + buyer))
                used["undo"] += 1
                self.assertEqual(page.evaluate("DraftApp.app.state.picks.length"), n + 1)
        end = page.evaluate(STATE_JS)
        self.assertEqual(end["picks"], total)
        for t in end["teams"]:
            self.assertEqual(sum(t["open"].values()), 0)
            self.assertEqual(t["overflow"], 0)
            self.assertGreaterEqual(t["left"], 0)
        self.assertIn("Pick %d of %d" % (total + 1, total), page.inner_text("#pick-count"))
        # every kind of key was used
        for kind, count in used.items():
            self.assertGreater(count, 0, kind)
        # gate 2: every sale recomputed and redrew in under 200 ms
        self.assertEqual(len(timings), total)
        self.assertLess(max(timings), 200, "slowest recompute %.1f ms" % max(timings))
        self.assertLess(end["maxMs"], 200)
        # the help overlay opens on "?"
        kb.press("?")
        self.assertTrue(page.evaluate("document.getElementById('help').open"))
        self.assertEqual(self.errors, [])

    # --------------------------------------------------------------------- 3
    def test_mid_draft_link_reopens_identical(self):
        page = self.open()
        page.keyboard.press("b")
        kb = page.keyboard
        for n in range(23):
            kb.press("ArrowDown")
            kb.type(str(3 + n))
            if n % 5 == 0:
                kb.press("m")
            else:
                kb.press("s")
                kb.press(chr(ord("b") + n % 11))
        page.wait_for_function("() => /#s=/.test(location.hash) && DraftApp.app.token && location.hash === '#s=' + DraftApp.app.token")
        before = page.evaluate("() => ({ state: DraftApp.app.state, hash: location.hash, walk: [...document.querySelectorAll('#rows td[data-f=walk]')].map(c => c.textContent), count: document.querySelector('#pick-count').textContent })")
        self.assertEqual(len(before["state"]["picks"]), 23)
        page2 = self.open(fragment=before["hash"])
        after = page2.evaluate("() => ({ state: DraftApp.app.state, view: DraftApp.app.view, walk: [...document.querySelectorAll('#rows td[data-f=walk]')].map(c => c.textContent), count: document.querySelector('#pick-count').textContent })")
        self.assertEqual(after["state"], before["state"])   # deep-equal state
        self.assertEqual(after["view"], "board")
        self.assertEqual(after["walk"], before["walk"])     # and the same board
        self.assertEqual(after["count"], before["count"])
        # a cut link is refused and says so
        page3 = self.open(fragment=before["hash"][:-9] + before["hash"][-8:])
        self.assertTrue(page3.is_visible("#link-error"))
        self.assertEqual(page3.evaluate("DraftApp.app.state.picks.length"), 0)

    # --------------------------------------------------------------------- 4
    def worked_script(self, factor):
        ids = ["A", "B", "C"]
        pos, ours, market, source, players = {}, {}, {}, {}, {}
        for k, p in WORKED["players"].items():
            pos[k], ours[k], market[k], source[k] = p["pos"], p["ours"], p["market"], "proj"
            players[k] = {"key": k, "name": k, "pos": p["pos"], "team": ""}
        for s in WORKED["sold"]:
            pos[s["key"]] = s["pos"]
            players[s["key"]] = {"key": s["key"], "name": s["key"], "pos": s["pos"], "team": ""}
        slots = {**dict(QB=0, RB=0, WR=0, TE=0, FLEX=0, SUPERFLEX=0, K=0, DST=0, BN=0), **WORKED["league"]["slots"]}
        league = {"name": "Worked example", "teams": [{"name": i, "budget": 30} for i in ids], "budget": 30, "minBid": 1, "slots": slots,
                  "scoring": {"pass_yds": 0.04, "pass_tds": 4, "ints": -2, "rush_yds": 0.1, "rush_tds": 6, "rec": 0.5, "rec_yds": 0.1, "rec_tds": 6, "fum_lost": -2}}
        model = {"league": {"teams": 3, "budget": 30, "minBid": 1, "slots": slots, "scoring": league["scoring"]},
                 "players": players, "pos": pos, "prices": {"ours": ours, "market": market, "source": source}, "values": {}, "tiers": {},
                 "order": list(WORKED["players"]) + [s["key"] for s in WORKED["sold"]], "counts": {}}
        state = {"v": 1, "league": league, "me": 0, "ourFactor": factor, "overrides": {},
                 "picks": [[s["key"], ids.index(s["team"]), s["price"]] for s in WORKED["sold"]]}
        return "window.DRAFT_PREVIEW = { model: %s, state: %s };" % (json.dumps(model), json.dumps(state))

    def board_cells(self, page):
        return page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#rows tr[data-key]')].map(r =>
          [r.getAttribute('data-key'), Object.fromEntries(['walk', 'push', 'buy'].map(f => [f, r.querySelector('td[data-f=' + f + ']').textContent]))]))""")

    def test_worked_example_on_the_board_to_the_dollar(self):
        cell = lambda v: "–" if not v else "$%d" % v
        for factor, expected in (("room", WORKED["expected"]["rows"]), ("personal", WORKED["expected_personal"]["rows"])):
            page = self.open(script=self.worked_script(factor))
            cells = self.board_cells(page)
            for key, exp in expected.items():
                self.assertEqual(cells[key], {"walk": cell(exp["walkAway"]), "push": cell(exp["pushFloor"]), "buy": cell(exp["buyLimit"])}, f"{key} ({factor})")
            bids = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#maxbids .mb')].map(r => [r.getAttribute('data-team'), r.querySelector('[data-f=maxbid]').textContent]))")
            self.assertEqual(bids, {"0": "$13", "1": "$13", "2": "$27"})
            self.assertEqual(page.inner_text("#infl-room"), "+25.0%")
            self.assertEqual(page.inner_text("#infl-main"), "+25.0%" if factor == "room" else "−20.0%")
            # the block leads with walk-away, then push floor and buy limit as separate numbers
            page.evaluate("DraftApp.select('P5')")
            lead = page.evaluate("() => [...document.querySelectorAll('#block .lead > div')].map(d => d.textContent)")
            p5 = expected["P5"]
            self.assertEqual(lead, ["Walk-away$%d" % p5["walkAway"], "Push floor$%d" % p5["pushFloor"], "Buy limit$%d" % p5["buyLimit"]])
            self.assertEqual(self.errors, [])

    # --------------------------------------------------------------------- 5
    def test_stale_warning(self):
        fresh = self.open(script=preview_script(hours_after_pull=20))
        fresh.keyboard.press("b")
        self.assertEqual(fresh.locator("#stale").count(), 0)
        self.assertEqual(fresh.inner_text("#updated"), "Updated 2026-11-28")
        fresh.keyboard.press("v")
        self.assertEqual(fresh.inner_text("#v-updated"), "Updated 2026-11-28")
        self.assertEqual(fresh.locator("#v-stale").count(), 0)
        stale = self.open(script=preview_script(hours_after_pull=50))
        stale.keyboard.press("b")
        self.assertIn("Stale: last pull 2026-11-28, 2 days old", stale.inner_text("#stale"))
        stale.keyboard.press("v")
        self.assertTrue(stale.is_visible("#v-stale"))

    # --------------------------------------------------------------------- 6
    def test_values_screen_and_override(self):
        page = self.open()
        page.keyboard.press("v")
        head = page.evaluate("() => [...document.querySelectorAll('#app thead th')].map(t => t.textContent)")
        for col in ("Ours", "Market", "Platform", "Spread", "Tier", "Source", "DDF Value (override)"):
            self.assertIn(col, head)
        sources = set(page.evaluate("() => [...document.querySelectorAll('#vrows td[data-f=source]')].map(t => t.textContent)"))
        self.assertTrue({"vegas", "vegas+proj", "proj"} <= sources, sources)
        self.assertIn("vegas 6", page.inner_text("#v-counts"))
        row = "#vrows tr:nth-child(30)"
        key = page.get_attribute(row, "data-key")
        before = page.evaluate("k => DraftApp.app.model.prices.ours[k]", key)
        ours, market = (float(page.inner_text(f"{row} td[data-f={f}]").replace("$", "")) for f in ("ours", "market"))
        self.assertAlmostEqual(float(page.inner_text(f"{row} td[data-f=spread]").replace("−", "-")), ours - market, delta=0.11)
        for _ in range(5):
            page.click(f"#vrows tr[data-key='{key}'] button[data-ovr='1']")
        after = page.evaluate("k => DraftApp.app.model.prices.ours[k]", key)
        self.assertGreater(after, before)
        self.assertEqual(page.inner_text("#v-overrides"), "1 override")
        self.assertTrue(page.evaluate("k => document.querySelector(`#vrows tr[data-key='${k}'] .stepper`).classList.contains('ovr')", key))
        # the override is in the link, and Reset restores the build
        page.wait_for_function("() => location.hash === '#s=' + DraftApp.app.token")
        page2 = self.open(fragment=page.evaluate("location.hash"))
        self.assertEqual(page2.evaluate("DraftApp.app.state.overrides"), page.evaluate("DraftApp.app.state.overrides"))
        page.click(f"#vrows tr[data-key='{key}'] button[data-ovr-reset]")
        self.assertAlmostEqual(page.evaluate("k => DraftApp.app.model.prices.ours[k]", key), before, places=6)
        self.assertEqual(self.errors, [])

    def test_roster_screen(self):
        page = self.open()
        page.keyboard.press("b")
        for price in ("31", "9", "4"):
            page.keyboard.type(price)
            page.keyboard.press("m")
        page.keyboard.press("r")
        self.assertEqual(page.get_attribute("#app", "data-view"), "roster")
        self.assertEqual(page.locator("#r-slots .slot[data-key]").count(), 3)
        self.assertEqual(page.locator("#r-slots .slot.open").count(), 12)
        self.assertIn("$44 spent · $156 left", page.inner_text("#r-money"))
        self.assertTrue(page.is_visible("#r-open"))
        self.assertTrue(page.is_visible("#r-byes"))
        self.assertGreater(float(page.inner_text("#r-roster-value")), 0)
        self.assertGreaterEqual(float(page.inner_text("#r-roster-value")), float(page.inner_text("#r-starter-value")))

    def test_league_id_import_and_paste_fallback(self):
        if not (ROOT / "app" / "draft" / "draft-league.js").exists():
            self.skipTest("draft-league.js is not built")
        fx = lambda name: (LEAGUE_FX / name).read_text()
        calls = []

        def sleeper(route):
            url = route.request.url
            calls.append((url, dict(route.request.headers)))
            body = fx("sleeper_drafts.json") if "/drafts" in url else fx("sleeper_users.json") if "/users" in url else fx("sleeper_league.json")
            route.fulfill(status=200, content_type="application/json", body=body, headers={"access-control-allow-origin": "*"})

        def espn(route):
            calls.append((route.request.url, dict(route.request.headers)))
            route.fulfill(status=401, content_type="application/json", body="{}", headers={"access-control-allow-origin": "*"})

        page = self.open(routes={"**/api.sleeper.app/**": sleeper, "**/lm-api-reads.fantasy.espn.com/**": espn})
        want = json.loads(fx("sleeper_league.json"))
        page.fill("#league-ref", "https://sleeper.com/leagues/%s" % want["league_id"])
        page.click("button[data-act=fetch-league]")
        page.wait_for_function("() => DraftApp.app.state.league.platform === 'sleeper'")
        league = page.evaluate("DraftApp.app.state.league")
        self.assertEqual(len(league["teams"]), want["total_rosters"])
        self.assertEqual(league["name"], want["name"])
        self.assertEqual(page.input_value("input[data-lg=teamCount]"), str(want["total_rosters"]))
        self.assertEqual(page.locator("#team-rows tr").count(), want["total_rosters"])
        # a private ESPN league: the settings page link and the paste box
        page.fill("#league-ref", "https://fantasy.espn.com/football/league?leagueId=123456")
        page.click("button[data-act=fetch-league]")
        page.wait_for_selector("#settings-link")
        self.assertIn("fantasy.espn.com/football/league/settings?leagueId=123456", page.get_attribute("#settings-link", "href"))
        self.assertIn("private", page.inner_text("#league-msg"))
        # no request carried a cookie, a token or a credential
        for url, headers in calls:
            for h in ("cookie", "authorization", "x-fantasy-filter", "espn_s2", "swid"):
                self.assertNotIn(h, headers, url)
        # Yahoo is paste only
        page.fill("#league-ref", "https://football.fantasysports.yahoo.com/f1/848938")
        page.click("button[data-act=fetch-league]")
        page.wait_for_function("() => (document.querySelector('#settings-link') || {}).href && document.querySelector('#settings-link').href.includes('yahoo')")
        pastes = sorted(LEAGUE_FX.glob("yahoo_settings_paste*.txt"))
        self.assertTrue(pastes)
        page.fill("#league-paste", pastes[0].read_text())
        page.click("button[data-act=read-paste]")
        page.wait_for_selector("#paste-read")
        self.assertEqual(page.evaluate("DraftApp.app.state.league.platform"), "yahoo")
        self.assertEqual(self.errors, [])

    # --------------------------------------------------------------------- 7
    def test_phone_width_has_no_horizontal_scroll(self):
        page = self.open(width=375)
        for key in ("l", "b", "v", "r"):
            page.keyboard.press(key)
            over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            self.assertLessEqual(over, 0, key)
        page.keyboard.press("b")
        # one tap per action on a phone: the five actions are buttons
        self.assertEqual(page.evaluate("() => [...document.querySelectorAll('#block .actions button')].map(b => b.getAttribute('data-act'))"),
                         ["walk", "push", "mine", "sold", "undo"])
        page.click("#rows tr:nth-child(2)")
        page.click("button[data-act=walk]")
        page.click("button[data-act=mine]")
        self.assertEqual(page.evaluate("DraftApp.app.state.picks.length"), 1)
        page.click("button[data-act=undo]")
        self.assertEqual(page.evaluate("DraftApp.app.state.picks.length"), 0)


if __name__ == "__main__":
    unittest.main()
