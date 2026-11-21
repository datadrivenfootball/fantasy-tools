"""Values: find a player and see comparably valued players (top of values.html, app/next/values-search.js).

Drives the real page at 375px and 1440px: type-ahead by name (initials and a typo through the shared matcher), team and
position; picking a player shows his DDF Value, rank, position rank and Trade chart average; the "Comparably valued"
list is recomputed here from the page's own rows (DDFValues.D, the engine records every tab reads) for each band and
position filter; the player=<key> hash round trips (pick writes it, a fresh load with it shows the player, Back
clears it); kickers and defenses never appear; empty, no-match and unknown-player states read plainly; the page does
not scroll sideways on a phone.
"""
from __future__ import annotations

import contextlib
import unittest

from tests import _render_env
from tests._dist_server import serve

LIVE = "() => document.body.classList.contains('values-live') && DDFValues.D.length > 0 && !!DDFValues.find"

# The page's rows, recomputed independently of values-search.js: skill positions with a DDF Value, sorted high to low.
EXPECT = """([key, band, scope]) => {
  const all = DDFValues.D.filter(p => ['QB','RB','WR','TE'].includes(p.pos) && typeof p.ddf === 'number' && isFinite(p.ddf))
    .slice().sort((a, b) => b.ddf - a.ddf);
  const me = all.find(p => p.key === key);
  const near = all.filter(p => p.key !== key && Math.abs(p.ddf - me.ddf) <= band + 1e-9);
  const pick = scope === 'same' ? near.filter(p => p.pos === me.pos) : scope === 'other' ? near.filter(p => p.pos !== me.pos) : near;
  const posRank = all.filter(p => p.pos === me.pos).findIndex(p => p.key === key) + 1;
  const charts = ['cbs','usat','fp','fc'].map(k => me[k]).filter(v => typeof v === 'number' && isFinite(v));
  return {
    n: me.n, pos: me.pos, ddf: me.ddf.toFixed(1), rank: all.findIndex(p => p.key === key) + 1, total: all.length, posRank,
    avg: charts.length ? (charts.reduce((a, b) => a + b, 0) / charts.length).toFixed(1) : '—',
    counts: {all: near.length, same: near.filter(p => p.pos === me.pos).length, other: near.filter(p => p.pos !== me.pos).length},
    keys: pick.map(p => p.key),
    gaps: Object.fromEntries(pick.map(p => [p.key, p.ddf - me.ddf])),
  };
}"""

SHOWN = """() => {
  const card = document.getElementById('vfind-card');
  const stats = [...card.querySelectorAll('.vfind-stats dd')].map(d => d.textContent.trim());
  const rows = [...card.querySelectorAll('.vfind-rows button[data-key]')].map(b => ({
    key: b.dataset.key, value: b.querySelector('.vfind-num').textContent.trim(), gap: b.querySelector('.vfind-gap').textContent.trim(),
    h: Math.round(b.getBoundingClientRect().height)}));
  const radios = sel => [...card.querySelectorAll(sel + ' [role=radio]')].map(b => [b.textContent.trim(), b.getAttribute('aria-checked')]);
  return {hidden: card.hidden, name: (card.querySelector('#vfind-name') || {}).textContent, stats, rows,
    self: !!card.querySelector('.vfind-self'), basis: (card.querySelector('#vfind-basis') || {}).textContent || '',
    band: radios('.vfind-ctrl:nth-child(1)'), scope: radios('.vfind-ctrl:nth-child(2)'),
    more: !!card.querySelector('#vfind-all'), empty: (card.querySelector('.vfind-empty') || {}).textContent || '',
    hash: location.hash, msg: document.getElementById('vfind-msg').textContent,
    pageScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""

OPTS = "() => ({hidden: document.getElementById('vfind-list').hidden, keys: [...document.querySelectorAll('#vfind-list button[data-key]')].map(b => b.dataset.key), text: document.getElementById('vfind-list').textContent})"


def setUpModule():
    _render_env.ensure_built()


def _gap_text(g: float) -> str:
    r = round(g * 10) / 10
    return "±0.0" if r == 0 else ("+" if r > 0 else "−") + f"{abs(r):.1f}"


class ValuesPlayerSearchTest(unittest.TestCase):
    @contextlib.contextmanager
    def _page(self, width, height, hash_=""):
        try:
            from playwright.sync_api import Error as PlaywrightError, sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        with serve() as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except PlaywrightError as exc:
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                ctx = browser.new_context(viewport={"width": width, "height": height})
                ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                ctx.add_init_script(_render_env.pin_data_week_script())
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"{base}/values.html{hash_}", wait_until="domcontentloaded", timeout=90000)
                page.wait_for_function(LIVE, timeout=60000)
                yield page
                self.assertEqual([], errors)
            finally:
                browser.close()

    def _type(self, page, text):
        page.fill("#vfind-q", "")
        page.click("#vfind-q")
        page.keyboard.type(text, delay=20)
        page.wait_for_function("() => !!window.TradeValueNameSearch", timeout=20000)
        page.wait_for_timeout(250)
        return page.evaluate(OPTS)

    def _check_card(self, page, key, band, scope):
        want = page.evaluate(EXPECT, [key, band, scope])
        got = page.evaluate(SHOWN)
        self.assertFalse(got["hidden"])
        self.assertIn(want["n"], got["name"])
        self.assertEqual([want["ddf"], f"#{want['rank']}", f"{want['pos']}{want['posRank']}", want["avg"]], got["stats"])
        self.assertIn(f"±{band} DDF Value points", got["basis"], "the band basis is stated in DDF Value points")
        self.assertIn(["±" + str(band), "true"], got["band"])
        self.assertEqual([f"All {want['counts']['all']}", f"{want['pos']} {want['counts']['same']}", f"Other {want['counts']['other']}"],
                         [t for t, _ in got["scope"]], "the position filter counts match the band")
        shown = [r["key"] for r in got["rows"]]
        if got["more"]:
            self.assertEqual(12, len(shown))
            self.assertTrue(set(shown) <= set(want["keys"]))
            closest = sorted(want["keys"], key=lambda k: abs(want["gaps"][k]))[:12]
            far_in = max(abs(want["gaps"][k]) for k in shown)
            self.assertLessEqual(far_in, abs(want["gaps"][closest[-1]]) + 1e-9, "the cut keeps the closest in value")
        else:
            self.assertEqual(sorted(want["keys"]), sorted(shown), "every player in the band, and only those")
        for r in got["rows"]:
            self.assertEqual(_gap_text(want["gaps"][r["key"]]), r["gap"])
        return want, got

    def _flow(self, width, height):
        with self._page(width, height) as page:
            # empty: nothing typed, no list, no card
            self.assertTrue(page.evaluate(OPTS)["hidden"])
            self.assertTrue(page.evaluate(SHOWN)["hidden"])
            # initials and a typo, through the shared matcher
            o = self._type(page, "jsn")
            self.assertFalse(o["hidden"])
            jsn = page.evaluate("() => DDFValues.D.find(p => p.n === 'Jaxon Smith-Njigba').key")
            self.assertEqual(jsn, o["keys"][0])
            o = self._type(page, "mcafrey")
            names = page.evaluate("keys => keys.map(k => DDFValues.D.find(p => p.key === k).n)", o["keys"])
            self.assertIn("Christian McCaffrey", names)
            # team + position words filter
            o = self._type(page, "dal wr")
            rows = page.evaluate("keys => keys.map(k => { const p = DDFValues.D.find(p => p.key === k); return [p.team, p.pos]; })", o["keys"])
            self.assertTrue(rows and all(r == ["DAL", "WR"] for r in rows))
            # no match
            o = self._type(page, "zzqxv")
            self.assertEqual([], o["keys"])
            self.assertIn("No players match", o["text"])
            # pick with the keyboard: the first match, hash written
            self._type(page, "jsn")
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            self._check_card(page, jsn, 3, "all")
            self.assertEqual(f"#player={jsn}", page.evaluate("location.hash"))
            # widen, then filter by position, each recomputed from the page's rows
            for band in (6, 10):
                page.click(f"#vfind-card [data-band='{band}']")
                self._check_card(page, jsn, band, "all")
            for scope in ("same", "other"):
                page.click(f"#vfind-card [data-scope='{scope}']")
                self._check_card(page, jsn, 10, scope)
            page.click("#vfind-card [data-scope='all']")
            want, got = self._check_card(page, jsn, 10, "all")
            self.assertTrue(got["rows"], "a ±10 band around a top-five player is not empty")
            self.assertTrue(got["self"], "the searched player is marked in the list")
            self.assertTrue(all(r["h"] >= 44 for r in got["rows"]), "rows are tappable")
            self.assertLessEqual(got["pageScroll"], 0, "no sideways scroll")
            # tap a comparable: it becomes the player, hash pushed; Back returns
            other = got["rows"][0]["key"]
            page.click(f"#vfind-card .vfind-rows button[data-key='{other}']")
            page.wait_for_timeout(300)
            self.assertEqual(f"#player={other}", page.evaluate("location.hash"))
            self._check_card(page, other, 10, "all")
            page.go_back()
            page.wait_for_timeout(400)
            self.assertEqual(f"#player={jsn}", page.evaluate("location.hash"))
            self._check_card(page, jsn, 10, "all")
            # dense bottom of the board: the list is cut to the 12 closest, then shows all
            low = page.evaluate("() => { const a = DDFValues.D.filter(p => p.ddf > 0); return a[a.length - 1].key; }")
            page.evaluate("k => DDFValues.find.pick(k, {push: true})", low)
            page.wait_for_timeout(200)
            want, got = self._check_card(page, low, 10, "all")
            if want["counts"]["all"] > 12:
                self.assertTrue(got["more"])
                page.click("#vfind-all")
                self.assertEqual(sorted(want["keys"]), sorted(r["key"] for r in page.evaluate(SHOWN)["rows"]))
            # Clear removes the player and the hash token
            page.click("#vfind-clear")
            page.wait_for_timeout(200)
            s = page.evaluate(SHOWN)
            self.assertTrue(s["hidden"])
            self.assertNotIn("player=", s["hash"])

    def test_phone_375(self):
        self._flow(375, 812)

    def test_desktop(self):
        self._flow(1440, 900)

    def test_hash_load_and_tab_tokens(self):
        with self._page(1440, 900) as page:
            key = page.evaluate("() => DDFValues.D[10].key")
        with self._page(375, 812, f"#buy-sell&player={key}") as page:
            page.wait_for_timeout(300)
            self._check_card(page, key, 3, "all")
            self.assertEqual("false", page.get_attribute("#tab-chart", "aria-selected"), "the tab token still applies")
            self.assertEqual("true", page.get_attribute("#tab-bs", "aria-selected"))
        with self._page(1440, 900, "#player=no-such-player") as page:
            page.wait_for_timeout(300)
            s = page.evaluate(SHOWN)
            self.assertTrue(s["hidden"])
            self.assertIn("no DDF Value", s["msg"])

    def test_kickers_and_defenses_never_listed(self):
        with self._page(1440, 900) as page:
            page.evaluate("() => DDFValues.find.loadMatcher()")
            page.wait_for_function("() => !!window.TradeValueNameSearch", timeout=20000)
            res = page.evaluate("""() => {
              const raw = DDF.engine.controls().getAllRows().filter(r => !['QB','RB','WR','TE'].includes(r.pos));
              const names = raw.map(r => r.name).filter(Boolean).slice(0, 25);
              const qs = names.concat(['Brandon Aubrey', 'Harrison Butker', 'Jake Bates', 'Cowboys', 'Ravens D/ST', 'k', 'def', 'dst', 'kicker', 'defense', 'a', 'j']);
              const hits = qs.flatMap(q => DDFValues.find.find(q).hits);
              const top = DDFValues.D.slice(0, 40).flatMap(p => (DDFValues.find.comparables(p.key, 10, 'all') || {list: []}).list);
              return {raw: raw.length, positions: [...new Set(hits.concat(top).map(p => p.pos))], kdefHits: hits.filter(p => names.includes(p.n) && !['QB','RB','WR','TE'].includes(p.pos)).length};
            }""")
            # The engine prices QB/RB/WR/TE only (no K/DEF rows at all); the search must keep it that way.
            self.assertTrue(set(res["positions"]) <= {"QB", "RB", "WR", "TE"}, res)
            self.assertEqual(0, res["kdefHits"])


if __name__ == "__main__":
    unittest.main()
