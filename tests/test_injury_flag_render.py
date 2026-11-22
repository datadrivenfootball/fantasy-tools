"""Injury flags on Find and Build a Trade, at 375px and 1440px (Jeremy, 2026-11-22: "It is a flag, not a stopper").

On the USO league fixture (tests/fixtures/league_levels/uso.json: Yahoo rosters of 2026-10-29, Team 3 is you), with
the daily Sleeper status copy (v2/player-status.js) replaced by a dated test copy:

- A flag never changes the offers. Find's full offer list (every section, in page order: class, partner, both
  packages, both sides' values, the trade value, the fit label and tags, both lineup blocks, the section counts and the
  status line) is identical with no status file, with a fresh copy that flags nobody, and with a fresh copy that flags
  every other player in the offers (Out, IR, Doubtful, Questionable in turn; the rest stay healthy).
- With the flags on, every player in a card has one chip beside his name with an aria-label "Injury: <status>[, body
  part]", the card has one line "Injury flag on N player(s)", and the Why panel has one line per flagged player:
  "Injury flag: <name> is <status> (<body part>); the trade may not work as planned." Healthy players show nothing.
- Build a Trade (McCaffrey and Boston to Team 9 for Cook and Henry): chips beside the names in You give / You get and in
  the roster picker, one line under the boxes, chips on the flagged starters in the lineup card, the Why line; the
  lineup totals, the trade checks and the Why verdict are the same as without the flags.
- No horizontal scroll at 320, 360, 375 or 1440, chips inside their card, picker rows at least 44px.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from tests import _render_env
from tests._dist_server import DIST, serve
from tests._served_weeks import route_pinned_weeks
from tests.test_build_lineup_card_render import APPLY, GET, GIVE, LIVE, seed
from tests.test_find_engine_parity import READY

STATUSES = [("Out", "Hamstring"), ("IR", "Knee"), ("Doubtful", None), ("Questionable", "Ankle")]
LIST_ALL = r"""() => {
  const fit = document.getElementById('fit'); fit.value = 'all'; fit.dispatchEvent(new Event('change', {bubbles: true}));
  const b = document.querySelector('[data-page-size="200"]'); if (b) b.click();
  document.querySelectorAll('details.section').forEach(d => { d.open = true; });
  return true;
}"""
# Everything the offer list says, in page order, with the injury markup taken out.
OFFERS = r"""() => {
  const t = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : null;
  const strip = el => { if (!el) return null; const c = el.cloneNode(true); c.querySelectorAll('[data-injury-chip], [data-injury-summary], .inj-sub').forEach(x => x.remove()); return t(c); };
  const cards = [...document.querySelectorAll('[data-offer]')].map(a => ({
    section: a.closest('[id$="-table"]').id, cls: a.dataset.cls, partner: a.dataset.partner, give: a.dataset.give, receive: a.dataset.receive,
    you: a.dataset.you, them: a.dataset.them, edge: a.dataset.edge, label: t(a.querySelector('[data-fit-label]')),
    tags: [...a.querySelectorAll('[data-fit-tag]')].map(t), tv: t(a.querySelector('[data-trade-value]')),
    lineups: [...a.querySelectorAll('[data-lineup]')].map(l => [l.dataset.lineup, l.dataset.before, l.dataset.after, t(l)]),
    text: strip(a)}));
  return {cards, counts: ['natural-count', 'neutral-count', 'force-count'].map(id => t(document.getElementById(id))),
    status: t(document.getElementById('search-status')), force: t(document.getElementById('force-note'))};
}"""
PLAYERS = r"""() => { const out = {};
  DDF.findPage.visible().forEach(g => { const t = DDF.findPage.selected(g);
    t.give.concat(t.receive).forEach(r => { out[String(r.player_key)] = {name: r.name, sleeper_id: r.sleeper_id == null ? null : String(r.sleeper_id), team: r.team, pos: r.pos}; }); });
  return out; }"""
ROWS = r"""(keys) => { const rows = new Map(TradeValueCurveControls.getAllRows().map(r => [String(r.player_key), r]));
  return keys.map(k => { const r = rows.get(String(k)); return {key: String(k), name: r.name, sleeper_id: r.sleeper_id == null ? null : String(r.sleeper_id), team: r.team, pos: r.pos}; }); }"""
CHIPS = r"""() => [...document.querySelectorAll('[data-offer]')].map(a => { const box = a.getBoundingClientRect();
  return {give: a.dataset.give, receive: a.dataset.receive, partner: a.dataset.partner,
    chips: [...a.querySelectorAll('.pk-ex [data-injury-chip]')].map(c => ({label: c.textContent, aria: c.getAttribute('aria-label'), level: c.dataset.level,
      name: (c.previousElementSibling || {}).textContent, inside: c.getBoundingClientRect().right <= box.right + 0.5})),
    summary: (a.querySelector('[data-injury-summary]') || {}).textContent || null, select: !!a.querySelector('.pk-ex select')}; })"""
OVERFLOW = "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 || document.body.scrollWidth > document.documentElement.clientWidth + 1"


def status_js(flagged: dict[str, tuple[str, str | None, dict]]) -> str:
    """A dated, fresh Sleeper copy (the Waivers rule shows it for 6 days) flagging the given Sleeper ids."""
    as_of = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    by_id = {sid: {"team": p["team"], "pos": p["pos"], "injury_status": s, "injury_body_part": body} for sid, (s, body, p) in flagged.items()}
    return "window.TradeValueStatus = " + json.dumps({"source": "Sleeper", "as_of": as_of, "by_sleeper_id": by_id}) + ";\n"


def phrase(status: str) -> str:
    return {"IR": "on IR", "PUP": "on PUP"}.get(status, status)


class InjuryFlagRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists() or not (DIST / "injury-flag.js").exists():
            raise _render_env.unavailable("dist/find.html or dist/injury-flag.js is not built")
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

    def page(self, width, status):
        """status: None (no status file: 404), or the player-status.js body. Read at request time, so a reload after
        changing self.status serves the new copy."""
        self.status = status
        page = self.browser.new_page(viewport={"width": width, "height": 900})
        self.addCleanup(page.close)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith(self.base), lambda r: r.abort())
        route_pinned_weeks(page, DIST)

        def status_route(route):
            if self.status is None:
                route.fulfill(status=404, body="")
            else:
                route.fulfill(status=200, content_type="application/javascript", body=self.status)
        page.route("**/v2/player-status.js*", status_route)
        page.add_init_script(seed(True))
        return page, errors

    def open_find(self, width, status):
        page, errors = self.page(width, status)
        page.goto(f"{self.base}/find.html", wait_until="domcontentloaded", timeout=60000)
        self.find_ready(page)
        return page, errors

    def find_ready(self, page):
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.league", timeout=60000)
        page.evaluate("async () => { await DDF.engine.ready; await DDF.league.ready; return true; }")
        page.evaluate(APPLY)
        page.wait_for_timeout(300)
        page.wait_for_function(READY, timeout=180000)
        page.evaluate(LIST_ALL)
        page.wait_for_timeout(300)

    def test_find_flags_change_no_offer_and_show_on_every_flagged_player(self):
        base, errors = self.open_find(1440, None)
        no_file = base.evaluate(OFFERS)
        self.assertGreater(len(no_file["cards"]), 5, "the USO fixture lists too few offers to prove anything")
        self.assertTrue(any(c["cls"] == "natural" for c in no_file["cards"]), "no Natural offer on the fixture")
        players = base.evaluate(PLAYERS)
        self.assertEqual(base.evaluate("() => document.querySelectorAll('[data-injury-chip], [data-injury-summary]').length"), 0)
        keyed = {k: p for k, p in players.items() if p["sleeper_id"] and p["team"]}
        self.assertGreater(len(keyed), 0.8 * len(players), "offer players have no Sleeper id or team")
        flagged, by_key = {}, {}
        # Every other offer player is flagged (Out, IR, Doubtful, Questionable in turn), so a page that sorted, filtered
        # or relabelled by injury would move flagged offers against healthy ones and fail the comparison.
        for i, (key, p) in enumerate(sorted(keyed.items())):
            if i % 2:
                continue
            s, body = STATUSES[(i // 2) % len(STATUSES)]
            flagged[p["sleeper_id"]] = (s, body, p)
            by_key[key] = (s, body, p["name"])
        self.assertEqual(errors, [])

        for width in (375, 1440):
            with self.subTest(width=width):
                empty, e1 = self.open_find(width, status_js({}))
                self.assertEqual(empty.evaluate(OFFERS), no_file, f"{width}: a fresh copy with no flags changed the offers")
                self.assertEqual(empty.evaluate("() => document.querySelectorAll('[data-injury-chip], [data-injury-summary]').length"), 0)
                page, e2 = self.open_find(width, status_js(flagged))
                got = page.evaluate(OFFERS)
                # The proof: same offers, same order, same labels, counts and values, with every offer player flagged.
                self.assertEqual(got, no_file, f"{width}: injury flags changed the offer list")
                cards = page.evaluate(CHIPS)
                n_players = lambda c: len([k for k in c["give"].split(",") + c["receive"].split(",") if k])
                self.assertTrue(any(c["summary"] for c in cards), f"{width}: the test copy flags no card")
                self.assertTrue(any(len(c["chips"]) < n_players(c) for c in cards if not c["select"]), f"{width}: no healthy player left")
                for c in cards:
                    keys = [k for k in (c["give"].split(",") + c["receive"].split(",")) if k]
                    want = [by_key[k] for k in keys if k in by_key]
                    if not c["select"]:
                        self.assertEqual(len(c["chips"]), len(want), f"{width}: {c}")
                        for chip, (s, body, name) in zip(c["chips"], want):
                            self.assertEqual(chip["name"], name)
                            self.assertEqual(chip["aria"], f"Injury: {s}" + (f", {body.lower()}" if body else ""))
                    self.assertTrue(all(ch["inside"] for ch in c["chips"]), f"{width}: a chip runs out of its card: {c}")
                    n = len(want)
                    self.assertEqual(c["summary"], (f"Injury flag on {n} player" + ("" if n == 1 else "s")) if n else None, f"{width}: {c}")
                self.assertFalse(page.evaluate(OVERFLOW), f"{width}: horizontal scroll")
                # The Why panel of the first card: one line per flagged player.
                first = cards[0]
                page.click("[data-offer] details[data-why] > summary")
                page.wait_for_selector("[data-offer] [data-injury-why]", timeout=10000)
                lines = page.evaluate("() => [...document.querySelector('[data-offer] [data-injury-why]').querySelectorAll('p')].map(p => p.textContent)")
                keys = [k for k in first["give"].split(",") + first["receive"].split(",") if k in by_key]
                self.assertEqual(lines, [f"Injury flag: {by_key[k][2]} is {phrase(by_key[k][0])}" + (f" ({by_key[k][1].lower()})" if by_key[k][1] else "")
                                         + "; the trade may not work as planned." for k in keys])
                self.assertFalse(page.evaluate(OVERFLOW), f"{width}: horizontal scroll with the Why open")
                self.assertEqual(e1 + e2, [])

    def test_build_flags_names_picker_lineup_and_why(self):
        q = "mode=league&partner=Team%209&" + "&".join([f"give={k}" for k in GIVE] + [f"get={k}" for k in GET])
        READ = r"""() => { const t = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : null;
          const strip = el => { if (!el) return null; const c = el.cloneNode(true); c.querySelectorAll('[data-injury-chip]').forEach(x => x.remove()); return t(c); };
          return {give: strip(document.getElementById('give-names')), get: strip(document.getElementById('get-names')),
            giveChips: [...document.querySelectorAll('#give-names [data-injury-chip]')].map(c => c.getAttribute('aria-label')),
            getChips: [...document.querySelectorAll('#get-names [data-injury-chip]')].map(c => c.getAttribute('aria-label')),
            note: document.getElementById('injury-note').hidden ? null : t(document.getElementById('injury-note')),
            lineup: strip(document.getElementById('lineup-body')),
            lineupChips: [...document.querySelectorAll('#lineup-body [data-injury-chip]')].map(c => [c.closest('[data-lineup-side]').dataset.lineupSide, c.getAttribute('aria-label')]),
            sums: [...document.querySelectorAll('[data-lineup-sum]')].map(s => [s.dataset.before, s.dataset.after, s.dataset.delta]),
            checks: t(document.getElementById('checks')), pass: t(document.getElementById('check-pass')),
            why: strip(document.querySelector('#build-why .why-body') && (() => { const c = document.querySelector('#build-why .why-body').cloneNode(true); c.querySelectorAll('[data-injury-why]').forEach(x => x.remove()); return c; })()),
            whyLines: [...document.querySelectorAll('#build-why [data-injury-why] p')].map(p => p.textContent),
            pickerChips: [...document.querySelectorAll('#give-picker tr[data-key] [data-injury-chip]')].map(c => c.closest('tr').dataset.key),
            rowH: Math.min(...[...document.querySelectorAll('#give-picker tr[data-key]')].filter(r => !r.hidden).map(r => r.getBoundingClientRect().height))}; }"""
        for width in (320, 360, 375, 1440):
            with self.subTest(width=width):
                page, errors = self.page(width, status_js({}))
                page.goto(f"{self.base}/build.html?{q}", wait_until="load", timeout=60000)
                page.wait_for_function(LIVE, timeout=60000)
                page.evaluate(APPLY)
                page.wait_for_timeout(600)
                plain = page.evaluate(READ)
                self.assertEqual((plain["giveChips"], plain["getChips"], plain["note"], plain["whyLines"]), ([], [], None, []))
                rows = {r["name"]: r for r in page.evaluate(ROWS, GIVE + GET)}
                cmc, henry = rows["Christian McCaffrey"], rows["Derrick Henry"]
                self.assertTrue(cmc["sleeper_id"] and henry["sleeper_id"], rows)
                self.status = status_js({cmc["sleeper_id"]: ("Out", "Hamstring", cmc), henry["sleeper_id"]: ("Questionable", None, henry)})
                page.reload(wait_until="load", timeout=60000)
                page.wait_for_function(LIVE, timeout=60000)
                page.evaluate(APPLY)
                page.wait_for_timeout(600)
                got = page.evaluate(READ)
                label = str(width)
                self.assertEqual(got["giveChips"], ["Injury: Out, hamstring"], label)
                self.assertEqual(got["getChips"], ["Injury: Questionable"], label)
                self.assertEqual(got["note"], "Injury flag on 2 players", label)
                self.assertIn(cmc["key"], got["pickerChips"], label)
                self.assertGreaterEqual(got["rowH"], 44 - 0.5, f"{label}: picker rows under 44px")
                # McCaffrey starts for you before the trade, Henry for you after: both carry a chip in your lineup.
                self.assertIn(["you", "Injury: Out, hamstring"], got["lineupChips"], label)
                self.assertIn(["you", "Injury: Questionable"], got["lineupChips"], label)
                self.assertEqual(got["whyLines"], ["Injury flag: Christian McCaffrey is Out (hamstring); the trade may not work as planned.",
                                                   "Injury flag: Derrick Henry is Questionable; the trade may not work as planned."], label)
                # Nothing else moves: names, lineup, totals, checks, the Why's own words.
                for k in ("give", "get", "lineup", "sums", "checks", "pass", "why"):
                    self.assertEqual(got[k], plain[k], f"{label}: {k} changed with the flags")
                self.assertFalse(page.evaluate(OVERFLOW), f"{label}: horizontal scroll")
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
