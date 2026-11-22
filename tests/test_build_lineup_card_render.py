"""Build a Trade lineup card (Jeremy, 2026-11-21/22, layout A "Changes first"), at 375px and 1440px.

On the USO league fixture (Yahoo 848938, Team 3 is you) with the trade Find ranks first with Team 9 (McCaffrey and
Boston for Cook and Henry), what we guard:
- One card, "Starting lineup after this trade", right under You give / You get and above the trade checks.
- Both teams' totals at the top: your starters on DDF Value and Team 9's on the Analyst charts, before, after and the
  change. The totals are recomputed here, independently of finder.js: the best lineup under the league's slots (QB, RB,
  WR, TE by value, then FLEX from RB/WR/TE, SUPERFLEX from QB/RB/WR/TE) from the engine's own rows.
- Changed slots open (every player who enters a starting slot, by that same independent lineup, has a changed row);
  unchanged starters and the bench are folded to one line each by default.
- K and DEF rows are listed, marked "not valued".
- The Why panel on Build keeps its sentences and loses its two lineup tables.
- Shopping a player (only your side picked) shows your lineup without him, one side only; Any players with the league
  loaded shows your side and asks for a team in My league for theirs; with no league, no card, and the Add your league
  card shows its faded slot rows.
- No horizontal scroll, and the site header is the same as on a page without the card.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import DIST, serve
from tests._served_weeks import route_pinned_weeks

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests/fixtures/league_levels/uso.json").read_text())
KEY = {p["name"]: p["key"] for t in FIXTURE["league"]["teams"] for p in t["players"] if p.get("key")}
APPLY = "() => { DDF.engine.apply({scoring: 'half_ppr', teams: 12, superflex: false, roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5}}); return true; }"
LIVE = "() => document.body.classList.contains('build-live')"


def seed(with_league: bool, partial: bool = False) -> str:
    """The USO league pasted on connect (sessionStorage ddf:pasted). partial: one team's roster left out, so the league is
    not full and Any players stays available (a full league opens Build in My league)."""
    if not with_league:
        return "(function(){ try { if (sessionStorage.getItem('t-seeded')) return; localStorage.clear(); sessionStorage.clear(); sessionStorage.setItem('t-seeded','1'); } catch(_){} })()"
    teams = [{"name": "Team " + t["id"], "players": [{"name": p["name"], "key": p["key"], "pos": p["pos"], "team": None, "id": None}
              for p in t["players"] if p.get("key") and not (partial and t["id"] == "12")], "unmatched": []} for t in FIXTURE["league"]["teams"]]
    me = next(i for i, t in enumerate(FIXTURE["league"]["teams"]) if t["id"] == "3")
    rec = {"v": 1, "source": "paste", "site": "yahoo", "me": me, "name": "USO Season XVIII", "teams": teams}
    return ("(function(){ try { if (sessionStorage.getItem('t-seeded')) return; localStorage.clear(); sessionStorage.clear();"
            " sessionStorage.setItem('t-seeded','1'); sessionStorage.setItem('ddf:pasted', " + json.dumps(json.dumps(rec)) + "); } catch(_){} })()")


def team_keys(team_id: str) -> list[str]:
    return [p["key"] for t in FIXTURE["league"]["teams"] if t["id"] == team_id for p in t["players"] if p.get("key")]


GIVE = [KEY["Christian McCaffrey"], KEY["Denzel Boston"]]
GET = [KEY["James Cook III"], KEY["Derrick Henry"]]

# The best lineup under the league's slots, written here on purpose (not finder.js pickStarters): values from the
# engine's rows, DDF Value for you, the mean of the analyst charts the page runs (CBS Sports, USA Today, FantasyPros:
# all that are available; a player missing one has no average) for them.
INDEPENDENT = r"""([mineKeys, theirKeys, give, get]) => {
  const C = window.TradeValueCurveControls, shape = C.getRosterShape();
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const analyst = ['cbs', 'usatoday', 'fantasypros'].filter(k => avail.has(k));
  const rows = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const val = {ddf: r => r.values.ddf_value, an: r => analyst.length >= 2 && analyst.every(k => typeof r.values[k] === 'number' && isFinite(r.values[k])) ? analyst.reduce((t, k) => t + r.values[k], 0) / analyst.length : null};
  const best = (keys, v) => {
    const pool = keys.map(k => rows.get(String(k))).filter(r => r && typeof v(r) === 'number' && isFinite(v(r)))
      .sort((a, b) => v(b) - v(a) || String(a.player_key).localeCompare(String(b.player_key)));
    const used = new Set(), starters = [];
    const take = (n, ok) => { for (const r of pool) { if (n <= 0) break; if (!used.has(r) && ok(r.pos)) { used.add(r); starters.push(r); n -= 1; } } };
    ['QB', 'RB', 'WR', 'TE'].forEach(p => take(shape[p] || 0, x => x === p));
    take(shape.FLEX || 0, x => ['RB', 'WR', 'TE'].includes(x));
    take(shape.SUPERFLEX || 0, x => ['QB', 'RB', 'WR', 'TE'].includes(x));
    return {total: starters.reduce((t, r) => t + v(r), 0), names: starters.map(r => r.name)};
  };
  const after = (keys, out, add) => keys.filter(k => !out.includes(k)).concat(add);
  const side = (keys, out, add, v) => { const b = best(keys, v), a = best(after(keys, out, add), v);
    const d = a.total - b.total, delta = Math.abs(d) < 0.05 ? '0.0' : (d > 0 ? '+' : '\u2212') + Math.abs(d).toFixed(1);
    return {before: b.total.toFixed(1), after: a.total.toFixed(1), delta, into: a.names.filter(n => !b.names.includes(n))}; };
  return {you: side(mineKeys, give, get, val.ddf), them: side(theirKeys, get, give, val.an), shape: {K: shape.K, DST: shape.DST}};
}"""

READ = r"""() => {
  const card = document.getElementById('lineup-card'), box = el => el ? el.getBoundingClientRect() : null;
  const shown = n => Math.abs(n) < 0.05 ? '0.0' : (n > 0 ? '+' : '−') + Math.abs(n).toFixed(1);
  const sum = who => { const el = card.querySelector('[data-lineup-sum="' + who + '"]'); if (!el) return null;
    return {before: el.dataset.before, after: el.dataset.after, delta: el.dataset.delta, missing: el.hasAttribute('data-missing'), text: el.textContent.replace(/\s+/g, ' ').trim(), top: box(el).top}; };
  const side = who => { const el = card.querySelector('[data-lineup-side="' + who + '"]'); if (!el) return null;
    const fold = name => { const d = el.querySelector('details[data-fold="' + name + '"]'); return d ? {open: d.open, summary: d.querySelector('summary').textContent.replace(/\s+/g, ' ').trim()} : null; };
    return {changed: [...el.querySelectorAll(':scope > [data-changed]')].map(r => ({slot: r.dataset.slot, name: (r.querySelector('.lu-nm') || {}).textContent, visible: r.checkVisibility()})),
      same: fold('same'), bench: fold('bench'), flags: [...el.querySelectorAll('.lu-flag')].map(f => f.textContent),
      unvalued: [...el.querySelectorAll('[data-unvalued]')].map(r => ({slot: r.dataset.slot, text: r.textContent.replace(/\s+/g, ' ').trim(), visible: r.checkVisibility()}))}; };
  const offer = box(document.querySelector('.offer-boxes')), checks = document.querySelector('.trade-checks');
  const header = document.querySelector('body > header');
  return {hidden: card.hidden, title: document.getElementById('lineup-title').textContent, cardTop: box(card).top, cardBottom: box(card).bottom,
    offerBottom: offer.bottom, checksTop: checks && !checks.hidden ? box(checks).top : null,
    sums: {you: sum('you'), them: sum('them')}, sides: {you: side('you'), them: side('them')},
    foot: (card.querySelector('.lu-foot') || {}).textContent || null,
    whyPanel: !!document.querySelector('#build-why details.why'), whyTables: document.querySelectorAll('#build-why .why-lus, #build-why .why-lt').length,
    noLeague: (() => { const c = document.querySelector('.lock-card[data-only=any-noleague]'); return c && !c.hidden && c.offsetParent !== null ? c.querySelectorAll('.lu-ghost span').length : null; })(),
    header: header ? header.outerHTML : null, headerBox: header ? [box(header).height, box(header).width] : null,
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 || document.body.scrollWidth > document.documentElement.clientWidth + 1};
}"""


class BuildLineupCardRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "build.html").exists() or not (DIST / "ddf-lineup.js").exists():
            raise _render_env.unavailable("dist/build.html or dist/ddf-lineup.js is not built")
        cls._serve = serve(DIST)
        cls.base = cls._serve.__enter__()
        cls._pw = sync_playwright().start()
        try:
            cls.browser = cls._pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(cls._pw))
        except Exception as exc:  # noqa: BLE001
            cls._pw.stop(); cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls._pw.stop(); cls._serve.__exit__(None, None, None)

    def open(self, width, query, with_league=True, partial=False):
        page = self.browser.new_page(viewport={"width": width, "height": 900})
        self.addCleanup(page.close)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith(self.base), lambda r: r.abort())
        route_pinned_weeks(page, DIST)   # every source on the newest served week, so the analyst charts all run
        page.add_init_script(seed(with_league, partial))
        page.goto(f"{self.base}/build.html?{query}", wait_until="load", timeout=60000)
        page.wait_for_function(LIVE, timeout=60000)
        page.evaluate(APPLY)
        page.wait_for_timeout(600)
        return page, errors

    def assert_side_matches(self, label, got_sum, got_side, want):
        self.assertEqual((got_sum["before"], got_sum["after"]), (want["before"], want["after"]), f"{label}: totals vs the independent lineup")
        # The change is the unrounded difference shown to one decimal, as on the Find card and in the Why.
        self.assertEqual(got_sum["delta"], want["delta"], label)
        changed = [r["name"] for r in got_side["changed"]]
        for name in want["into"]:
            self.assertIn(name, changed, f"{label}: {name} enters a starting slot but has no open row")
        self.assertTrue(all(r["visible"] for r in got_side["changed"]), f"{label}: a changed slot is hidden")

    def test_trade_card_at_375_and_desktop(self):
        q = "mode=league&partner=Team%209&" + "&".join([f"give={k}" for k in GIVE] + [f"get={k}" for k in GET])
        ref_header = None
        for width in (375, 1440):
            with self.subTest(width=width):
                page, errors = self.open(width, q)
                got = page.evaluate(READ)
                want = page.evaluate(INDEPENDENT, [team_keys("3"), team_keys("9"), GIVE, GET])
                label = str(width)
                self.assertFalse(got["hidden"], f"{label}: no lineup card")
                self.assertEqual(got["title"], "Starting lineup after this trade")
                # Right under You give / You get, above the trade checks.
                self.assertGreaterEqual(got["cardTop"], got["offerBottom"] - 1, label)
                self.assertIsNotNone(got["checksTop"], f"{label}: trade checks hidden")
                self.assertLessEqual(got["cardBottom"], got["checksTop"] + 1, label)
                # Both totals at the top, then the sides.
                you, them = got["sums"]["you"], got["sums"]["them"]
                self.assertIn("on DDF Value", you["text"])
                self.assertIn("Team 9 starters", them["text"])
                self.assertIn("on Analyst charts", them["text"])
                self.assert_side_matches(f"{label} you", you, got["sides"]["you"], want["you"])
                self.assert_side_matches(f"{label} them", them, got["sides"]["them"], want["them"])
                self.assertTrue(want["you"]["into"] and want["them"]["into"], f"{label}: the fixture trade changes no lineup")
                # Folded by default: unchanged starters and the bench, one line each.
                for who in ("you", "them"):
                    s = got["sides"][who]
                    self.assertEqual((s["same"]["open"], s["bench"]["open"]), (False, False), f"{label} {who}: folds open by default")
                    self.assertRegex(s["same"]["summary"], r"^\d starters? unchanged, plus K and DEF$", f"{label} {who}")
                    self.assertRegex(s["bench"]["summary"], r"^Bench · .+?\s*\d+\.\d → to \d+\.\d$", f"{label} {who}")
                    # K and DEF rows, marked not valued (inside the unchanged fold).
                    self.assertEqual([r["slot"] for r in s["unvalued"]], ["K", "DEF"], f"{label} {who}")
                    self.assertTrue(all("not valued" in r["text"] and not r["visible"] for r in s["unvalued"]), f"{label} {who}: {s['unvalued']}")
                self.assertEqual((want["shape"]["K"], want["shape"]["DST"]), (1, 1))
                # Opening the fold shows them.
                page.click('[data-lineup-side="you"] details[data-fold="same"] > summary')
                self.assertTrue(page.evaluate("() => [...document.querySelectorAll('[data-lineup-side=you] [data-unvalued]')].every(r => r.checkVisibility())"))
                # The Why keeps its sentences, not its lineup tables.
                self.assertTrue(got["whyPanel"], f"{label}: Why panel missing")
                self.assertEqual(got["whyTables"], 0, f"{label}: Why still draws lineup tables on Build")
                self.assertFalse(got["overflow"], f"{label}: horizontal scroll")
                self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"), f"{label}: horizontal scroll with a fold open")
                self.assertEqual(errors, [])
                # The header is the page's own: the same markup and size as on a page with no card.
                bare, _ = self.open(width, "mode=league")
                ref = bare.evaluate(READ)
                self.assertTrue(ref["hidden"], f"{label}: card shows with no players picked")
                self.assertEqual((got["header"], got["headerBox"]), (ref["header"], ref["headerBox"]), f"{label}: header changed")
                ref_header = ref_header or got["header"]

    def test_shop_any_and_no_league_states(self):
        for width in (375, 1440):
            with self.subTest(width=width):
                label = str(width)
                # Shopping a player: your lineup without him, your side only.
                page, errors = self.open(width, f"mode=league&partner=Team%209&give={KEY['Denzel Boston']}")
                got = page.evaluate(READ)
                want = page.evaluate(INDEPENDENT, [team_keys("3"), team_keys("9"), [KEY["Denzel Boston"]], []])
                self.assertFalse(got["hidden"], f"{label}: shop")
                self.assertEqual(got["title"], "Your lineup without Denzel Boston")
                self.assertIsNone(got["sums"]["them"], label)
                self.assert_side_matches(f"{label} shop", got["sums"]["you"], got["sides"]["you"], want["you"])
                self.assertEqual(got["foot"], "Add a player to receive to see the full trade.")
                self.assertFalse(got["overflow"], label)
                self.assertEqual(errors, [])
                # Any players with the league loaded (11 of 12 rosters): your side, and a line for theirs.
                page, errors = self.open(width, "mode=any&" + "&".join([f"give={k}" for k in GIVE] + [f"get={k}" for k in GET]), partial=True)
                got = page.evaluate(READ)
                want = page.evaluate(INDEPENDENT, [team_keys("3"), team_keys("9"), GIVE, GET])
                self.assertFalse(got["hidden"], f"{label}: any players")
                self.assert_side_matches(f"{label} any", got["sums"]["you"], got["sides"]["you"], want["you"])
                self.assertTrue(got["sums"]["them"]["missing"], f"{label}: {got['sums']} {got['title']}")
                self.assertIn("Pick a team in My league to see their lineup too.", got["sums"]["them"]["text"])
                self.assertIsNone(got["sides"]["them"], label)
                self.assertFalse(got["overflow"], label)
                self.assertEqual(errors, [])
                # No league: no card; the Add your league card shows its faded slot rows.
                page, errors = self.open(width, "&".join([f"give={k}" for k in GIVE] + [f"get={k}" for k in GET]), with_league=False)
                got = page.evaluate(READ)
                self.assertTrue(got["hidden"], f"{label}: card shows with no league")
                self.assertEqual(got["noLeague"], 3, f"{label}: Add your league card or its slot rows missing")
                self.assertFalse(got["overflow"], label)
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
