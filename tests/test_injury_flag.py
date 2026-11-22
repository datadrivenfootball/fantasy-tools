"""Injury flag severity mapping and display rules (Jeremy, 2026-11-22: "It is a flag, not a stopper").

The rule lives in app/next/injury-flag.js (window.DDFInjury), the one function every trade page uses:

  * severity: Sleeper's injury_status (and Yahoo's one-letter tags) -> label and level. Out, IR, PUP and Suspended
    are level "out"; Doubtful "doubtful"; Questionable "questionable". Anything else (Active, Inactive, NA, DNR, empty,
    not text) gets no flag, never a guess.
  * flagOf: the status comes only through the Waivers rule (TradeValueWaivers.statusOf): a dated copy at most 6 days
    old, the same Sleeper id, team and position. The body part is the same copy's injury_body_part, when present.
  * the chip's aria-label ("Injury: Out, hamstring"), the card line ("Injury flag on 1 player") and the Why line
    ("Injury flag: X is Out (hamstring). A flag, not a stopper: the trade may not work as planned.").
  * display only: flagOf never changes the row it reads.

The pages are covered by tests/test_injury_flag_render.py.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
const assert = require('assert');
globalThis.DDFStatusRule = require('./app/v2/player-status-rule.js');
const I = require('./app/next/injury-flag.js');
const W = globalThis.DDFStatusRule;
// The Waivers tab reads the same rule (waivers.js re-exports it).
assert.strictEqual(require('./app/v2/waivers.js').statusOf, W.statusOf);

// The severity map.
const want = {Out: ['Out', 'out'], IR: ['IR', 'out'], PUP: ['PUP', 'out'], Sus: ['Suspended', 'out'],
  Doubtful: ['Doubtful', 'doubtful'], Questionable: ['Questionable', 'questionable']};
for (const [s, [label, level]] of Object.entries(want)) {
  const got = I.severity(s);
  assert.deepStrictEqual([got.status, got.label, got.level], [s, label, level], s);
}
assert.strictEqual(I.severity('O').status, 'Out');
assert.strictEqual(I.severity('q').status, 'Questionable');
assert.strictEqual(I.severity(' D ').status, 'Doubtful');
assert.strictEqual(I.severity('Injured Reserve').status, 'IR');
for (const none of ['Active', 'Inactive', 'NA', 'DNR', '', null, undefined, 3, 'Healthy']) assert.strictEqual(I.severity(none), null, String(none));
assert(I.severity('Out').rank < I.severity('Doubtful').rank && I.severity('Doubtful').rank < I.severity('Questionable').rank);

// flagOf through the Waivers freshness rule.
const daily = {as_of: '2026-11-22T13:10:00Z', by_sleeper_id: {
  '1': {team: 'SF', pos: 'RB', injury_status: 'Out', injury_body_part: 'Hamstring'},
  '2': {team: 'KC', pos: 'WR', injury_status: 'Questionable'},
  '3': {team: 'LAR', pos: 'WR', injury_status: 'IR', injury_body_part: '  Ankle   - High '},
  '4': {team: 'KC', pos: 'TE', injury_status: null, injury_body_part: 'Knee'},
  '5': {team: 'KC', pos: 'QB', injury_status: 'NA', injury_body_part: 'Illness'}
}};
const now = Date.parse(daily.as_of) + 3600000;
const fresh = W.statusFreshness(daily, now);
const row = {player_key: '10', sleeper_id: '1', name: 'Christian McCaffrey', team: 'SF', pos: 'RB', values: {ddf_value: 30.1}};
const before = JSON.stringify(row);
const f = I.flagOf(row, fresh);
assert.deepStrictEqual([f.status, f.label, f.level, f.body, f.aria], ['Out', 'Out', 'out', 'hamstring', 'Injury: Out, hamstring']);
assert(f.title.includes('Sleeper status as of Nov 22') && f.title.includes('not a stopper'), f.title);
assert.strictEqual(JSON.stringify(row), before, 'flagOf changed the row');
assert.strictEqual(I.flagOf({...row, sleeper_id: '2', team: 'KC', pos: 'WR', name: 'A'}, fresh).aria, 'Injury: Questionable');
assert.strictEqual(I.flagOf({...row, sleeper_id: '3', team: 'LA', pos: 'WR', name: 'B'}, fresh).body, 'ankle - high');
assert.strictEqual(I.flagOf({...row, sleeper_id: '4', team: 'KC', pos: 'TE'}, fresh), null, 'no status is no flag, even with a body part');
assert.strictEqual(I.flagOf({...row, sleeper_id: '5', team: 'KC', pos: 'QB'}, fresh), null, 'NA is not a flag');
assert.strictEqual(I.flagOf({...row, team: 'KC'}, fresh), null, 'team mismatch');
assert.strictEqual(I.flagOf({...row, pos: 'WR'}, fresh), null, 'position mismatch');
assert.strictEqual(I.flagOf({...row, sleeper_id: null}, fresh), null);
assert.strictEqual(I.flagOf(row, W.statusFreshness(daily, Date.parse(daily.as_of) + 7 * 86400000)), null, 'stale copy');
assert.strictEqual(I.flagOf(row, W.statusFreshness({...daily, as_of: null}, now)), null, 'undated copy');
assert.strictEqual(I.flagOf(row, null), null);

// Lines.
const rows = [row, {...row, player_key: '11', sleeper_id: '2', team: 'KC', pos: 'WR', name: 'Rashee Rice'}, {...row, player_key: '12', sleeper_id: '4', team: 'KC', pos: 'TE', name: 'Healthy Guy'}];
const flags = I.flagsOf(rows.concat([row]), fresh);
assert.deepStrictEqual(flags.map(x => x.name), ['Christian McCaffrey', 'Rashee Rice'], 'input order, one per player, healthy left out');
assert.strictEqual(I.summary(flags), 'Injury flag on 2 players');
assert.strictEqual(I.summary(flags.slice(0, 1)), 'Injury flag on 1 player');
assert.strictEqual(I.summary([]), '');
assert.strictEqual(I.whyLine(flags[0]), 'Injury flag: Christian McCaffrey is Out (hamstring). A flag, not a stopper: the trade may not work as planned.');
assert.strictEqual(I.whyLine(flags[1]), 'Injury flag: Rashee Rice is Questionable. A flag, not a stopper: the trade may not work as planned.');
assert.strictEqual(I.whyLine(I.flagOf({...row, sleeper_id: '3', team: 'LAR', pos: 'WR', name: 'Puka Nacua'}, fresh)),
  'Injury flag: Puka Nacua is on IR (ankle - high). A flag, not a stopper: the trade may not work as planned.');
const chip = I.chip(flags[0]);
assert(chip.includes('aria-label="Injury: Out, hamstring"') && chip.includes('data-level="out"') && chip.includes('>Out</span>'), chip);
assert.strictEqual(I.chip(null), '');
assert(I.note(rows, fresh).includes('data-injury-summary="2"') && I.note(rows, fresh).includes('not a stopper'));
assert.strictEqual(I.note([rows[2]], fresh), '');
assert.strictEqual(I.whyHtml([rows[2]], fresh), '');
assert.strictEqual((I.whyHtml(rows, fresh).match(/<p>/g) || []).length, 2);
// Names are escaped.
assert(!I.chip(I.flagOf({...row, name: '<b>x</b>'}, fresh)).includes('<b>'));
assert(!I.whyHtml([{...row, name: '<b>x</b>'}], fresh).includes('<b>'));
console.log('ok');
"""


class InjuryFlagTest(unittest.TestCase):
    def test_severity_mapping_and_lines(self):
        out = subprocess.run(["node", "-e", SCRIPT], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        self.assertEqual(out.stdout.strip(), "ok")

    def test_every_trade_page_loads_the_shared_module(self):
        # One function on every page: the pages that show trade players load injury-flag.js after the status copy
        # and the status rule (app/v2/player-status-rule.js), and no page reimplements the map. Build and Values load
        # the small rule file, not the whole Waivers script (review of #1519: page weight).
        for page in ("find.html", "build.html", "values.html"):
            html = (ROOT / "app" / "next" / page).read_text()
            order = [html.find(s) for s in ('src="v2/player-status.js"', 'src="v2/player-status-rule.js"', 'src="injury-flag.js"')]
            self.assertTrue(all(i >= 0 for i in order) and order == sorted(order), f"{page}: {order}")
        for page in ("build.html", "values.html"):
            self.assertNotIn('src="v2/waivers.js"', (ROOT / "app" / "next" / page).read_text(), page)
        for page in ("find.html", "team.html", "waivers.html"):
            html = (ROOT / "app" / "next" / page).read_text()
            self.assertLess(html.find('src="v2/player-status-rule.js"'), html.find('src="v2/waivers.js"'), f"{page}: the rule loads after waivers.js")
        for js in ("find-page.js", "build-trade.js", "ddf-why.js", "ddf-lineup.js", "values-buysell.js"):
            src = (ROOT / "app" / "next" / js).read_text()
            self.assertIn("DDFInjury", src, js)
            self.assertNotIn('"Questionable"', src, f"{js} carries its own status list")
        self.assertIn('"injury-flag.js"', (ROOT / "pipelines" / "build_root_pages.py").read_text())


if __name__ == "__main__":
    unittest.main()
