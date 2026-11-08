"""JEG-1393 decision 4 (Jeremy, 2026-11-08): Team and Trading Partners never use fill-in estimates; no price is an implied 0.

"drop fill-in estimates on Team and Trading Partners for consistency; a team counts as complete when every starter is
priced; make sure Partners does not blank; add a test with the real 11-team case; keep the ranking metric otherwise
unchanged." Follow-up, option (a): "No price is an implied 0" — a dropped estimate counts as 0 on that chart, so no
partner blanks; a real null (a chart that does not run this week) stays null.

On the seeded league of tests.test_team_engine_parity (12 teams: my team and 11 partners), at all 12 settings, read on
partners.html against an independent recomputation in the same browser (engine rows, TradeValueFinder, the published
rules; not through DDF.league):
- a chart's fill-in estimate (row.estimated[k]) never counts: DDF.league.chartRows sets it to 0 on the Analyst charts
  and Live market, so an estimated player (Chris Godwin when the engine fills him in, else any) averages his real
  charts with 0 for the estimated one, and keeps his DDF Value;
- each partner's "Same starters on the Analyst charts" / "Live market" figure equals the recomputation with estimates
  at 0, and none of the 11 partners shows a dash (the fixture has no chart that does not run; e86255800 blanked all 11,
  the leave-out version of 870c73aa3 blanked 3 to 5);
- the partner order equals the unchanged ranking metric run on those inputs (tests.test_partners_rank_parity ORACLE);
- each partner row carries the line "A chart that doesn't price a starter counts him at zero."
- the fixture really exercises estimates: some partner's figure differs from the one estimates would give.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_partners_rank_parity import ORACLE as RANK_ORACLE
from tests.test_team_engine_parity import APPLY, READY, SETTINGS, _browser, _open, seeded_league

RECOMPUTE = r"""(league) => {
  const F = window.TradeValueFinder, C = window.TradeValueCurveControls;
  const POS = ['QB', 'RB', 'WR', 'TE'], AN = ['cbs', 'usatoday', 'fantasypros'], CH = AN.concat(['fantasycalc']);
  const fin = v => typeof v === 'number' && isFinite(v), fx = v => fin(v) ? v.toFixed(1) : '—';
  const rows = C.getAllRows().filter(r => POS.includes(r.pos));
  const byKey = new Map(rows.map(r => [String(r.player_key), r]));
  const shape = C.getRosterShape();
  const drop = r => { const est = r.estimated || {}; if (!CH.some(k => est[k])) return r;
    const v = {...r.values}; CH.forEach(k => { if (est[k]) v[k] = 0; }); return {...r, values: v}; };
  const partners = {};
  league.teams.forEach((t, i) => {
    if (i === league.me) return;
    const got = [];
    t.players.forEach(e => {
      let r = e.key ? byKey.get(String(e.key)) : null;
      if (!r && e.name) r = F.matchNames([{name: e.name, pos: e.pos || ''}], rows).matched[0] || null;
      if (r && !got.includes(r)) got.push(r);
    });
    if (!got.length) return;
    const L = F.lineupValue(got, shape, 'ddf_value');
    const chart = F.withChartAverage(got.map(drop), AN), raw = F.withChartAverage(got, AN);
    const side = (list, key) => {
      const ok = L.starters.every(r => fin(list[got.indexOf(r)].values[key]));
      return ok ? fx(F.lineupValue(list, shape, key).starterValue) : '—';
    };
    const estStarters = L.starters.filter(r => CH.some(k => (r.estimated || {})[k])).map(r => r.name);
    const estBench = got.filter(r => !L.starters.includes(r) && CH.some(k => (r.estimated || {})[k])).map(r => r.name);
    partners[t.name] = {analyst: side(chart, F.MARKET_KEY), live: side(chart, 'fantasycalc'),
      rawAnalyst: side(raw, F.MARKET_KEY), rawLive: side(raw, 'fantasycalc'),
      estStarters, estBench};
  });
  return partners;
}"""

READ = r"""() => {
  const out = {};
  document.querySelectorAll('#team-list .pt-row').forEach(r => {
    out[r.querySelector('.tn').textContent.trim()] = {analyst: r.querySelector('[data-v=analyst]').textContent.trim(),
      live: r.querySelector('[data-v=live]').textContent.trim(), zero: (r.querySelector('.zero-note') || {}).textContent || ''};
  });
  return out;
}"""

# An estimated player: Chris Godwin when the engine fills him in on an Analyst chart, else the first estimated one.
ESTIMATED = r"""() => {
  const C = window.TradeValueCurveControls, F = window.TradeValueFinder, AN = ['cbs', 'usatoday', 'fantasypros'];
  const est = C.getAllRows().filter(r => AN.some(k => (r.estimated || {})[k]) && AN.every(k => typeof (r.values || {})[k] === 'number'));
  const r = est.find(x => x.name === 'Chris Godwin') || est[0];
  if (!r) return null;
  const mine = DDF.league.chartRows([r])[0], raw = F.withChartAverage([r], AN)[0];
  const zeroAvg = AN.reduce((t, k) => t + ((r.estimated || {})[k] ? 0 : r.values[k]), 0) / AN.length;
  return {name: r.name, raw: raw.values[F.MARKET_KEY], listed: mine.values[F.MARKET_KEY], zeroAvg, ddf: mine.values.ddf_value === r.values.ddf_value,
    zeroed: AN.concat(['fantasycalc']).filter(k => (r.estimated || {})[k]).every(k => mine.values[k] === 0)};
}"""


class TeamPartnersEstimatesTest(unittest.TestCase):
    def test_eleven_partners_leave_estimates_out(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not all((DIST / p).exists() for p in ("partners.html", "ddf-league.js")):
            raise _render_env.unavailable("dist partners page is not built")
        league = seeded_league()
        errors: list[str] = []
        differs = bench_estimates = estimated_starters = 0
        with serve(DIST) as base, sync_playwright() as pw:
            browser = _browser(pw)
            try:
                page, page_errors = _open(browser, base, "partners.html", league)
                page.wait_for_function(READY, timeout=30000)
                est = page.evaluate(ESTIMATED)
                self.assertIsNotNone(est, "no estimated player in the engine rows")
                self.assertIsInstance(est["raw"], (int, float), f"{est['name']}: raw average should exist with the estimate")
                self.assertAlmostEqual(est["listed"], est["zeroAvg"], places=9, msg=f"{est['name']}: estimate not counted as 0")
                self.assertNotAlmostEqual(est["listed"], est["raw"], places=6, msg=f"{est['name']}: the estimate still counts")
                self.assertTrue(est["zeroed"] and est["ddf"], f"{est['name']}: chartRows changed DDF Value or kept an estimate")
                for scoring, teams, sf in SETTINGS:
                    label = f"{scoring}/{teams}/{'sf' if sf else 'no-sf'}"
                    page.evaluate(APPLY, [scoring, teams, sf])
                    want = page.evaluate(RECOMPUTE, league)
                    got = page.evaluate(READ)
                    if sorted(got) != sorted(want) or len(got) != 11:
                        errors.append(f"{label}: partners page={sorted(got)} want={sorted(want)}")
                        continue
                    for name, w in want.items():
                        g = got[name]
                        bench_estimates += bool(w["estBench"])
                        if (g["analyst"], g["live"]) != (w["analyst"], w["live"]):
                            errors.append(f"{label}: {name} page analyst/live={g['analyst'], g['live']} want={w['analyst'], w['live']}")
                        if "—" in (g["analyst"], g["live"]):
                            errors.append(f"{label}: {name} blank analyst/live={g['analyst'], g['live']} (estimated starters {w['estStarters']}, bench {w['estBench']})")
                        if g["zero"].strip() != "A chart that doesn’t price a starter counts him at zero.":
                            errors.append(f"{label}: {name} zero line missing: {g['zero']!r}")
                        estimated_starters += bool(w["estStarters"])
                        differs += (w["analyst"], w["live"]) != (w["rawAnalyst"], w["rawLive"])
                    order = [r["name"] for r in page.evaluate(RANK_ORACLE, league)]
                    shown = page.evaluate("() => [...document.querySelectorAll('#team-list .pt-row .tn')].map(n => n.textContent.trim())")
                    if shown != order:
                        errors.append(f"{label}: order page={shown} recomputed={order}")
                errors.extend(f"page error {e}" for e in page_errors)
                page.close()
            finally:
                browser.close()
        self.assertEqual(errors, [], "\n".join(errors[:20]))
        self.assertGreater(bench_estimates, 0, "fixture has no estimated bench player: the blanking case is not exercised")
        self.assertGreater(estimated_starters, 0, "fixture has no estimated starter: the implied-0 case is not exercised")
        self.assertGreater(differs, 0, "no partner figure moves when estimates are left out: the fixture does not exercise them")


if __name__ == "__main__":
    unittest.main()
