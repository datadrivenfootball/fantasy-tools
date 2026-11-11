"""JEG-1621: the Values player table is compact, overrides sit in one end column, and "Group by position" toggles layout.

Default is one flat list sorted by DDF Value with a position chip per row; the toggle (persisted in localStorage) switches
to position group rows.

Drives the real page (grouped mode): no per-row "Set your own value" text or position pill in the Player cell, a position group row
per position, an Override column last, the button still opens the Overrides tab on the same player and an applied
override still shows on the table row; at 375px the page does not scroll sideways and the buttons stay tappable.
"""
from __future__ import annotations

import contextlib
import unittest

from tests import _render_env
from tests._dist_server import serve

LIVE = "() => document.body.classList.contains('values-live') && !!window.DDF && !!DDF.engine.player('2227')"
FACTS = """() => {
  const heads = [...document.querySelectorAll('#head th')].map(t => t.textContent.trim());
  const groups = [...document.querySelectorAll('#rows tr.pos-grp th')].map(t => t.textContent.trim().split(/\\s+/)[0]);
  const rows = [...document.querySelectorAll('#rows tr[data-i]')];
  const posOf = n => (DDFValues.D.find(r => r.n === n) || {}).pos;
  const blocks = []; let cur = null;
  document.querySelectorAll('#rows tr').forEach(tr => {
    if (tr.classList.contains('pos-grp')) {
      const th = tr.querySelector('th');
      cur = {pos: th.textContent.trim().split(/\\s+/)[0], scope: th.getAttribute('scope'), count: +th.querySelector('.pos-n').textContent, rowPos: []};
      blocks.push(cur);
    } else if (cur) cur.rowPos.push(posOf(tr.querySelector('.pn').textContent.replace('★', '').trim()));
  });
  const first = rows[0];
  const ddfOf = tr => { const r = DDFValues.D.find(r => r.n === tr.querySelector('.pn').textContent.replace('★', '').trim()); return r ? r.ddf : null; };
  const ddfs = rows.map(ddfOf);
  const own = first.querySelector('td.ovcol button[data-act=own]');
  return {
    heads, groups, blocks, ddfs,
    chips: rows.map(tr => { const c = tr.querySelector('td.pl .pos'); const r = DDFValues.D.find(r => r.n === tr.querySelector('.pn').textContent.replace('★', '').trim()); return c ? [c.textContent.trim(), r && r.pos] : null; }),
    pressed: document.getElementById('group-pos').getAttribute('aria-pressed'),
    toggleH: Math.round(document.getElementById('group-pos').getBoundingClientRect().height), nrows: rows.length,
    posPillInPlayerCell: !!document.querySelector('#rows td.pl .pos'),
    actsInPlayerCell: !!document.querySelector('#rows td.pl .vp-acts, #rows td.pl .vp-act'),
    ownButtons: document.querySelectorAll('#rows td.ovcol button[data-act=own]').length,
    ownText: own.textContent.trim(),
    rowH: Math.round(first.getBoundingClientRect().height),
    btnH: Math.round(own.getBoundingClientRect().height),
    btnW: Math.round(own.getBoundingClientRect().width),
    pageScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}"""


def setUpModule():
    _render_env.ensure_built()


class CompactValuesTableTest(unittest.TestCase):
    @contextlib.contextmanager
    def _session(self, width, height, grouped=False):
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
                if grouped:
                    ctx.add_init_script("try{localStorage.setItem('ddf:values:groupByPosition','1')}catch(e){}")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"{base}/values.html", wait_until="domcontentloaded", timeout=90000)
                page.wait_for_function(LIVE, timeout=60000)
                page.wait_for_timeout(500)
                yield page, page.evaluate(FACTS)
                self.assertEqual([], errors)
            finally:
                browser.close()

    def _check_common(self, f):
        self.assertEqual("Override", f["heads"][-1], "Override is the last column")
        self.assertEqual("Player", f["heads"][0])
        self.assertEqual(f["nrows"], f["ownButtons"], "one override button per player row")
        self.assertIn(f["ownText"], ("Set", "Edit"))

    def _check_flat(self, f):
        self._check_common(f)
        self.assertEqual("false", f["pressed"], "toggle is off by default")
        self.assertEqual([], f["groups"], "no position header rows in the mixed ranking")
        self.assertGreater(f["nrows"], 1)
        self.assertEqual(sorted(f["ddfs"], reverse=True), f["ddfs"], "one flat list sorted by DDF Value, high to low")
        self.assertTrue(all(c and c[0] == c[1] for c in f["chips"]), "every row shows its position chip")
        self.assertGreater(len({c[0] for c in f["chips"]}), 1, "positions are mixed in the list")

    def _check_layout(self, f):
        self._check_common(f)
        self.assertEqual("true", f["pressed"], "toggle is on")
        order = ["QB", "RB", "WR", "TE"]
        shown = f["blocks"]
        self.assertTrue(shown, "at least one position group is shown")
        heads = [b["pos"] for b in shown]
        self.assertEqual(len(heads), len(set(heads)), "one header per position")
        known = [h for h in heads if h in order]
        self.assertEqual(sorted(known, key=order.index), known, "groups follow QB, RB, WR, TE order")
        for b in shown:
            self.assertEqual("rowgroup", b["scope"])
            self.assertGreaterEqual(len(b["rowPos"]), 1, f"{b['pos']} header has no player rows")
            self.assertEqual({b["pos"]}, set(b["rowPos"]), f"rows under {b['pos']} are all {b['pos']}")
            self.assertEqual(b["count"], len(b["rowPos"]), f"{b['pos']} header count matches its rows")
        self.assertEqual(sum(len(b["rowPos"]) for b in shown), f["nrows"], "every player row sits under a header")
        self.assertFalse(f["posPillInPlayerCell"], "positions are group rows, not a pill per row")
        self.assertFalse(f["actsInPlayerCell"], "no per-row action links in the Player cell")

    def test_default_is_flat_mixed_ranking(self):
        with self._session(1440, 900) as (page, f):
            self._check_flat(f)
            self.assertFalse(f["actsInPlayerCell"])
            self.assertLessEqual(f["rowH"], 36, "compact row height")

    def test_toggle_groups_persists_and_ungroups(self):
        with self._session(1440, 900) as (page, f):
            self._check_flat(f)
            page.focus("#group-pos")
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            self._check_layout(page.evaluate(FACTS))
            self.assertEqual("1", page.evaluate("() => localStorage.getItem('ddf:values:groupByPosition')"))
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function(LIVE, timeout=60000)
            page.wait_for_timeout(500)
            self._check_layout(page.evaluate(FACTS))
            page.focus("#group-pos")
            page.keyboard.press("Space")
            page.wait_for_timeout(300)
            self._check_flat(page.evaluate(FACTS))
            self.assertEqual("0", page.evaluate("() => localStorage.getItem('ddf:values:groupByPosition')"))

    def test_desktop_grouped_layout(self):
        with self._session(1440, 900, grouped=True) as (page, f):
            self._check_layout(f)
            self.assertLessEqual(f["rowH"], 36, "compact row height")

    def test_phone_layout_and_tap_targets(self):
        for grouped in (False, True):
            with self._session(375, 812, grouped=grouped) as (page, f):
                (self._check_layout if grouped else self._check_flat)(f)
                self.assertEqual(0, f["pageScroll"], f"no horizontal page scroll at 375px (grouped={grouped})")
                self.assertGreaterEqual(f["toggleH"], 44)
                self.assertGreaterEqual(f["btnH"], 44)
                self.assertGreaterEqual(f["btnW"], 44)

    def test_sticky_override_cell_follows_row_highlight(self):
        with self._session(1440, 900) as (page, f):
            bg = "(sel) => getComputedStyle(document.querySelector(sel)).backgroundColor"
            row = "#rows tr[data-i]"
            page.hover(row)
            page.wait_for_timeout(300)
            self.assertEqual(page.evaluate(bg, row + " td.num"), page.evaluate(bg, row + " td.ovcol"), "hover")
            page.evaluate("() => document.querySelector('#rows tr[data-i]').classList.add('values-hl')")
            page.mouse.move(0, 0)
            page.wait_for_timeout(300)
            self.assertEqual(page.evaluate(bg, row + " td.num"), page.evaluate(bg, row + " td.ovcol"), "highlight")

    def test_override_button_opens_overrides_and_applies(self):
        for grouped in (False, True):
            self._override_roundtrip(grouped)

    def _override_roundtrip(self, grouped):
        with self._session(1440, 900, grouped=grouped) as (page, f):
            clicked = page.evaluate("() => document.querySelector('#rows tr[data-i] .pn').textContent.replace('★', '').trim()")
            page.click("#rows tr[data-i] td.ovcol button[data-act=own]")
            page.wait_for_function("() => !document.getElementById('panel-ov').hidden", timeout=15000)
            name = page.evaluate("() => document.getElementById('ov-name').textContent.trim()")
            self.assertEqual(clicked, name, "the Overrides tab opens on the clicked player")
            page.fill("#ov-num", "99")
            page.dispatch_event("#ov-num", "input")
            page.click("#ov-apply")
            page.wait_for_timeout(500)
            page.click("#tab-chart")
            page.wait_for_timeout(300)
            row = page.evaluate("(n) => { const t = [...document.querySelectorAll('#rows tr.ov-row')].find(r => r.textContent.includes(n)); return t ? t.querySelector('td.ovcol button[data-act=own]').textContent.trim() : null }", name)
            self.assertEqual("Edit", row, "an overridden row shows Edit and the ov-row marker")
            page.click("#tab-ov")
            page.click("#ov-reset")
            page.wait_for_timeout(300)
            page.click("#tab-chart")
            self.assertEqual(0, page.evaluate("() => document.querySelectorAll('#rows tr.ov-row').length"), "reset clears it")


if __name__ == "__main__":
    unittest.main()
