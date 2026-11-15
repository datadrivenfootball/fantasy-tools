"""JEG-1645: a Build a Trade link from an offer card carries the trade partner, and Build a Trade preselects it.

Max Logan's beta report (2026-11-15): a Natural fit offer said "Trade with Amazing Grace", but its Build a Trade link was
build.html?give=..&get=.. with no partner, so Build a Trade preselected another team and the players no longer belonged
to that roster.

Guarded here on the seeded 12-team league at 1440x900 and 390x844:
- every offer card's Build a Trade link and its chart-count link carry partner=<the card's partner>;
- clicking Build a Trade preselects that team, the give players are on my roster and the get players on that team's;
- a link whose partner is not in the league keeps the players but says so in the prefill note (no silent default).
"""
from __future__ import annotations

import unittest
from urllib.parse import parse_qsl, quote, urlsplit

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_ddf_why import _launch
from tests.test_find_engine_parity import APPLY, READY
from tests.test_team_engine_parity import seed_script, seeded_league

READ_CARDS = r"""() => [...document.querySelectorAll('[data-offer]')].map(card => ({
  partner: card.dataset.partner, cls: card.dataset.cls,
  build: card.querySelector('a[data-build]').getAttribute('href'),
  charts: (card.querySelector('a[data-charts]') || {getAttribute: () => null}).getAttribute('href')}))"""
READ_BUILD = r"""() => { const s = document.getElementById('partner'), n = document.getElementById('prefill-note');
  return {partner: s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : null, note: n.hidden ? '' : n.textContent,
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1}; }"""


def _rosters(league):
    return {t["name"]: {p["name"] for p in t["players"]} for t in league["teams"]}, league["teams"][league["me"]]["name"]


class BuildPartnerHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        _render_env.ensure_built()
        if not (DIST / "build.html").exists():
            raise _render_env.unavailable("dist/build.html is not built")
        cls.sync_playwright = staticmethod(sync_playwright)

    def _page(self, browser, base, size, url):
        page = browser.new_page(viewport=size)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.route(lambda u: not u.startswith(base), lambda r: r.abort())
        page.add_init_script(seed_script(seeded_league()))
        page.goto(f"{base}/{url}", wait_until="domcontentloaded", timeout=60000)
        return page

    def test_offer_links_carry_and_preselect_the_partner(self):
        rosters, me = _rosters(seeded_league())
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                for size in ({"width": 1440, "height": 900}, {"width": 390, "height": 844}):
                    page = self._page(browser, base, size, "find.html")
                    page.evaluate(APPLY, ["ppr", 12, False])
                    page.wait_for_function(READY, timeout=120000)
                    page.wait_for_selector("[data-offer]", timeout=120000)
                    cards = page.evaluate(READ_CARDS)
                    self.assertTrue(cards, "no offer cards for the seeded league")
                    for c in cards:
                        for href in (c["build"], c["charts"]):
                            q = parse_qsl(urlsplit(href).query)
                            self.assertEqual([v for k, v in q if k == "partner"], [c["partner"]], f"{c['cls']}: {href}")
                    for c in cards[:4]:
                        q = parse_qsl(urlsplit(c["build"]).query)
                        give, get = [v for k, v in q if k == "give"], [v for k, v in q if k == "get"]
                        self.assertTrue(set(give) <= rosters[me], f"give not on my roster: {give}")
                        self.assertTrue(set(get) <= rosters[c["partner"]], f"get not on {c['partner']}: {get}")
                        b = self._page(browser, base, size, c["build"])
                        b.wait_for_function("() => document.getElementById('partner') && document.getElementById('partner').options.length > 0", timeout=120000)
                        b.wait_for_timeout(400)
                        got = b.evaluate(READ_BUILD)
                        self.assertEqual(got["partner"], c["partner"], f"{size['width']}px {c['cls']}: {got}")
                        self.assertNotIn("not a trading partner", got["note"])
                        self.assertFalse(got["overflow"])
                        b.close()
                    self.assertEqual(self.errors, [])
                    page.close()
            finally:
                browser.close()

    def test_unknown_partner_is_named_not_swapped_silently(self):
        league = seeded_league()
        mine = [p["name"] for p in league["teams"][league["me"]]["players"] if p["pos"] == "WR"][0]
        url = f"build.html?partner={quote('Ghost Team')}&give={quote(mine)}"
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                for size in ({"width": 1440, "height": 900}, {"width": 390, "height": 844}):
                    b = self._page(browser, base, size, url)
                    b.wait_for_function("() => document.getElementById('partner') && document.getElementById('partner').options.length > 0", timeout=120000)
                    b.wait_for_timeout(400)
                    got = b.evaluate(READ_BUILD)
                    self.assertIn("Ghost Team", got["note"])
                    self.assertIn("not a trading partner", got["note"])
                    self.assertFalse(got["overflow"])
                    b.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
