"""JEG-1393 round 1, lane A: the Full value logic explainer's presentation of
DDF Value membership, hidden sources and the value-above-waivers factor.

Builder helpers are tested on synthetic engine bundles; template rules are
checked on the source. The rendered page is checked by `make values-explainer`
plus the render checks in the JEG-1393 handback.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_values_explainer as bve  # noqa: E402

TEMPLATE = (ROOT / "app" / "values-explainer" / "template.html").read_text(encoding="utf-8")


def bundle(**extra):
    sources = {"espn": {"vorpFactor": 0.5 * (10 / 4) + 0.5 * (10 / 5)},
               "cbs": {"vorpFactor": 10 / 8}}
    raw = {
        "inspection": {
            "valuePipeline": {"sources": sources},
            "rows": {
                "1": {"ddfByVersion": {"blended": {"sources": ["cbs"]}, "projections": {"sources": ["cbsros"]}}},
                "2": {"ddfByVersion": {"blended": {"sources": ["cbs", "usatoday"]}}},
            },
        },
        "diagnostics": {"excluded": [
            {"key": "espn", "reason": "held: fidelity: scrape_validity", "holdLevel": "red", "hidden": True},
            {"key": "usatoday", "reason": "held: lagging", "holdLevel": "amber"},
            {"key": "espn", "reason": "duplicate", "hidden": True},
        ]},
        "extra": {
            "compositeByVersion": {
                "ddf_value_projections": {"inputs": ["espn", "cbsros", "razzball"], "series": ["cbsros"]},
            },
            "vorpRuns": [
                {"weight": 0.5, "sources": {"espn": [4.0, 10 / 4], "cbs": [8.0, 10 / 8]}},
                {"weight": 0.5, "sources": {"espn": [5.0, 10 / 5], "cbs": [8.0, 10 / 8]}},
            ],
        },
    }
    raw.update(extra)
    return raw


class BuilderHelpersTest(unittest.TestCase):
    def test_hidden_lists_red_holds_once_and_skips_amber(self):
        self.assertEqual(bve.hidden_sources(bundle()),
                         [{"key": "espn", "reason": "held: fidelity: scrape_validity", "level": "red"}])

    def test_version_sources_reads_inputs_series_and_used(self):
        vs = bve.version_sources(bundle())
        self.assertEqual(vs["projections"], {"inputs": ["espn", "cbsros", "razzball"], "series": ["cbsros"],
                                             "used": ["cbsros"]})
        self.assertEqual(vs["blended"]["used"], ["cbs", "usatoday"])
        self.assertIsNone(vs["charts"]["series"])

    def test_vorp_runs_kept_only_when_they_reproduce_the_factor(self):
        runs = bve.vorp_runs(bundle())
        self.assertEqual(sorted(runs), ["cbs", "espn"])
        # The blended factor is the weighted mean of pie / raw surplus per run,
        # not pie / the averaged surplus (10 / 4.5 = 2.222 != 2.25).
        espn = runs["espn"]
        self.assertAlmostEqual(sum(w * f for w, _, f in espn), 2.25)
        self.assertNotAlmostEqual(10 / (0.5 * 4 + 0.5 * 5), 2.25)
        broken = bundle()
        broken["inspection"]["valuePipeline"]["sources"]["espn"]["vorpFactor"] = 9.0
        self.assertNotIn("espn", bve.vorp_runs(broken))

    def test_single_allocation_has_no_runs(self):
        raw = bundle()
        raw["extra"]["vorpRuns"] = None
        self.assertEqual(bve.vorp_runs(raw), {})

    def test_trim_keeps_the_raw_surplus_total(self):
        src = {"surplusTotal": 889.6, "totalVorp": 568.4, "family": "projection"}
        row = bve.trim_pipeline({"sources": {"espn": src}}, full=False)["sources"]["espn"]
        self.assertEqual((row["surplusTotal"], row["totalVorp"]), (889.6, 568.4))


class TemplateRulesTest(unittest.TestCase):
    def test_ddf_value_is_the_trade_charts(self):
        self.assertIn("DDF Value = mean(Adjusted value of each included, non-hidden trade chart that prices the player's "
                      "position; a chart that does not list the player counts 0)", TEMPLATE)
        self.assertIn("DDF Value = mean(Adjusted over included, non-hidden trade charts that price the player's "
                      "position; a chart that does not list the player counts 0)", TEMPLATE)
        self.assertNotIn("non-hidden source that prices the player", TEMPLATE)
        # The trace averages each version's own sources, not every counted source.
        self.assertIn('chain("blended", "ddf_value")', TEMPLATE)
        self.assertNotIn("if (COUNTED.includes(src) && av !== null", TEMPLATE)

    def test_hidden_is_read_per_version(self):
        self.assertIn("D.hidden", TEMPLATE)
        self.assertIn("heldIn(v)", TEMPLATE)

    def test_no_false_single_division_for_the_display_factor(self):
        self.assertNotIn("(${fmt(PIE, 0)} ÷ ${fmtN(s.totalVorp)})", TEMPLATE)
        self.assertIn("Expected-start-weighted parts total", TEMPLATE)

    def test_order_claim_is_qualified(self):
        self.assertNotIn("while keeping its own player order", TEMPLATE)
        self.assertIn("Indexed keeps the published order.", TEMPLATE)

    def test_fill_in_comes_before_the_waiver_line(self):
        self.assertLess(TEMPLATE.index('["Fill in what a chart doesn\'t list"'),
                        TEMPLATE.index('["Native to value above waivers, per source"'))
        self.assertIn("an estimate can set a chart's waiver line", TEMPLATE)

    def test_wording_rules(self):
        self.assertNotIn("Player pool", TEMPLATE)
        self.assertIn("chart's own curve", TEMPLATE)


METHODOLOGY = (ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")


class Round2Test(unittest.TestCase):
    """JEG-1393 round 2: CX-01, CX-03, CX-04, OP-06, OP-07, OP-08."""

    def test_bench_discount_constants_match_the_engine_and_python(self):
        bd = bve.bench_discount()
        self.assertAlmostEqual(bd["bye"], 1 / 17)
        self.assertEqual(bd["miss"], {"QB": 0.12, "RB": 0.14, "WR": 0.11, "TE": 0.15})

    def test_trim_keeps_availability_inputs(self):
        vp = {"lineup": {"bye": 0.0625}, "chartSigma": {"RB": {"sigma_rel": 0.4}},
              "sources": {"espn": {"positions": {"RB": {"avail": 0.8, "lineup": {"m": 0.14, "sigmaRel": 0.29}}}}}}
        out = bve.trim_pipeline(vp)
        self.assertEqual(out["lineup"], {"bye": 0.0625})
        self.assertEqual(out["chartSigma"]["RB"]["sigma_rel"], 0.4)
        self.assertEqual(out["sources"]["espn"]["positions"]["RB"]["avail"], 0.8)
        self.assertEqual(out["sources"]["espn"]["positions"]["RB"]["lineup"]["m"], 0.14)

    def test_bench_seats_state_the_usage_discount(self):
        self.assertNotIn("bench seats are shared the same way;", TEMPLATE)
        self.assertIn("usage discount = c^(1 + floor(k ÷ t1))", TEMPLATE)
        self.assertIn("The alternative, not used at this setting", TEMPLATE)

    def test_availability_includes_missed_games(self):
        self.assertNotIn("a healthy player", TEMPLATE)
        self.assertIn("after byes and missed games", TEMPLATE)

    def test_header_bench_share_one_decimal(self):
        # R4 (OP-01): named as the bench groups' share of the pie.
        self.assertIn("bench groups' share of the pie <b>${pct(BS, 1)}</b>", TEMPLATE)

    def test_methodology_display_factor_uses_raw_surplus(self):
        self.assertNotIn("6. **VORP vs waivers (display)**: `V_i = v_i x Pie / G_s`", METHODOLOGY)
        self.assertIn("`V_i = v_i x Pie / sum_j v_j`", METHODOLOGY)

    def test_methodology_order_claim_is_current(self):
        self.assertNotIn("so a source's own\n     order within a position never inverts", METHODOLOGY)
        self.assertIn("**Adjusted does not guarantee it.**", METHODOLOGY)

    def test_methodology_marks_retired_rules(self):
        self.assertNotIn("6.4% of the pie", METHODOLOGY)
        # Jeremy's quotes stay verbatim, annotated.
        self.assertIn('"15% is right. There is no way 35% is rational math." (OC-2)\n  *Superseded', METHODOLOGY)
        self.assertIn("(OC-4)\n  *Partly superseded:*", METHODOLOGY)


class Round3Test(unittest.TestCase):
    """JEG-1393 round 3, lane A: R3-OP-02, R3-OP-03, R3-OP-05, R3-CX-04."""

    @staticmethod
    def heavy_bundle():
        # One WR position: 2 teams x 1 starter each (n = 1), q = 0.2, three
        # players; the band and parts follow value-model.js esPositionParts.
        bands = [[1, 10.0, 50.0, 0.2]]
        players = {"1": [80.0, 0.0, 0.0], "2": [40.0, 0.0, 0.0]}
        avail = 0.75
        for pk, row in players.items():
            row[1] = bve.band_fill(row[0], 0.5 * row[0], 10.0, avail, bands)
        players["3"] = [30.0, 999.0, 0.0]  # off: the check reports it
        raw = bundle()
        raw["inspection"]["valuePipeline"]["sources"] = {
            "fantasycalc": {"family": "chart", "included": True}, "ktc": {"family": "chart", "included": True}}
        raw["inspection"]["rows"] = {k: {"pos": "WR"} for k in players}
        raw["diagnostics"]["excluded"] = []
        raw["extra"]["heavyRun"] = {"weight": 0.49, "sources": {
            "fantasycalc": {"positions": {"WR": {"starters": 2, "rostered": 4, "waiver": 10.0, "starterLine": 50.0,
                                                  "avail": avail, "bands": bands,
                                                  "lineup": {"nPerTeam": 1, "unavailable": 0.2, "sigmaRel": 0.5,
                                                             "sigmaFloor": 0}}},
                            "players": players}}}
        return raw

    def test_band_fill_matches_the_engine_formula(self):
        # avail x v x P(>= 1 out) x P(10 < X <= 50), X ~ N(40, 20)
        phi = bve._phi
        want = 0.75 * 30 * 0.2 * (phi((50 - 40) / 20) - phi((10 - 40) / 20))
        self.assertAlmostEqual(bve.band_fill(40.0, 20.0, 10.0, 0.75, [[1, 10.0, 50.0, 0.2]]), want)
        self.assertEqual(bve.band_fill(5.0, 2.0, 10.0, 0.75, [[1, 10.0, 50.0, 0.2]]), 0.0)

    def test_heavy_run_exports_n_q_bands_and_checks_them(self):
        hr = bve.heavy_run(self.heavy_bundle())
        self.assertEqual(hr["source"], "fantasycalc")
        wr = hr["positions"]["WR"]
        self.assertEqual((wr["n"], wr["q"], wr["bands"]), (1, 0.2, [[1, 10.0, 50.0, 0.2]]))
        self.assertGreater(hr["check"], 900)  # player 3's 999 is caught
        raw = self.heavy_bundle()
        del raw["extra"]["heavyRun"]["sources"]["fantasycalc"]["players"]["3"]
        self.assertEqual(bve.heavy_run(raw)["check"], 0.0)

    def test_heavy_run_skips_hidden_and_null_guards(self):
        raw = self.heavy_bundle()
        raw["diagnostics"]["excluded"] = [{"key": "fantasycalc", "hidden": True, "holdLevel": "red"}]
        self.assertIsNone(bve.heavy_run(raw))  # ktc has no heavy-run entry
        raw = self.heavy_bundle()
        raw["extra"]["heavyRun"] = None
        self.assertIsNone(bve.heavy_run(raw))
        raw = self.heavy_bundle()
        raw["extra"]["heavyRun"]["sources"]["fantasycalc"]["players"]["1"] = [None, 1, 2]
        raw["extra"]["heavyRun"]["sources"]["fantasycalc"]["positions"]["WR"]["lineup"] = None
        hr = bve.heavy_run(raw)
        self.assertNotIn("1", hr["players"])
        self.assertIsNone(hr["positions"]["WR"]["n"])

    def test_bands_and_binomial_are_defined(self):
        self.assertIn("band 1 runs from the starter line down to the value at rank starters + teams + 1", TEMPLATE)
        self.assertIn("q = bye share + (1 − bye share) × missed-game rate", TEMPLATE)
        self.assertIn("P(≥ k out) = Σ j ≥ k: C(n, j) × q^j × (1 − q)^(n − j)", TEMPLATE)
        self.assertIn('id="bandExample"', TEMPLATE)
        self.assertIn("D.heavyRun", TEMPLATE)

    def test_cutoff_and_decomposition_are_defined(self):
        self.assertIn("The <b>cutoff</b> is the PPG level τ at which the candidates' shares add up to exactly", TEMPLATE)
        self.assertIn("systematic rounding</i> (value-model.js vpDecompose)", TEMPLATE)
        self.assertIn('id="allocMixTable"', TEMPLATE)
        self.assertNotIn("(mean PPG − cutoff)", TEMPLATE)

    def test_two_rate_sets_are_explained(self):
        self.assertIn("These are <i>fixed</i> constants: a full-season bye rate (1/17)", TEMPLATE)
        self.assertIn("this window's own bye share", TEMPLATE)

    def test_methodology_live_links_use_the_current_host(self):
        self.assertNotIn("jb-barrel-droid.github.io", METHODOLOGY)
        self.assertIn("https://datadrivenfootball.github.io/fantasy-tools/modules/math-inspector.html", METHODOLOGY)


class Round4Test(unittest.TestCase):
    """JEG-1393 round 4, lane A: R4-OP-01, -03, -04/CX-01, -05, -06, -11."""

    @staticmethod
    def rate_bundle():
        # Two allocations, one source, one position (RB): rate_a = pie x W_a / group_a.
        pie = 100.0
        runs = []
        for w, wb, ws, gb, gs, parts in ((0.6, 0.1, 0.9, 20.0, 60.0, {"7": [4.0, 30.0]}),
                                         (0.4, 0.2, 0.8, 25.0, 50.0, {"7": [6.0, 20.0]})):
            groups = {"RB|bench": gb, "RB|starter": gs}
            rates = {"RB|bench": pie * wb / gb, "RB|starter": pie * ws / gs}
            runs.append({"weight": w, "pie": pie, "ddfWeights": {"RB|bench": wb, "RB|starter": ws},
                         "sources": {"cbs": [1.0, 1.0, groups, rates, parts, [], []]}})
        rate = {g: sum(r["weight"] * r["sources"]["cbs"][3][g] for r in runs) for g in ("RB|bench", "RB|starter")}
        shown = [sum(r["weight"] * r["sources"]["cbs"][3][g] * r["sources"]["cbs"][4]["7"][j] for r in runs) / rate[g]
                 for j, g in enumerate(("RB|bench", "RB|starter"))]
        raw = bundle()
        raw["inspection"]["valuePipeline"]["sources"] = {"cbs": {"rates": rate, "vorpFactor": 1.0}}
        raw["inspection"]["players"] = {"cbs": {"7": {"benchSlice": shown[0], "starterSlice": shown[1]}}}
        raw["inspection"]["rows"] = {"7": {"pos": "RB"}}
        raw["extra"]["vorpRuns"] = runs
        return raw

    def test_rate_runs_reproduce_the_averaged_rate_and_parts(self):
        rr = bve.rate_runs(self.rate_bundle())["cbs"]
        rb = rr["groups"]["RB|bench"]
        self.assertTrue(rb["budget"])
        self.assertAlmostEqual(sum(w * ra for w, _, _, ra in rb["runs"]), 0.6 * 0.5 + 0.4 * 0.8)
        # The averaged rate is not pie x averaged W / averaged group total.
        self.assertNotAlmostEqual(100 * (0.6 * 0.1 + 0.4 * 0.2) / (0.6 * 20 + 0.4 * 25), 0.62)
        self.assertEqual(rr["example"]["pk"], "7")
        self.assertEqual(rr["example"]["runs"], [[0.6, 4.0, 30.0], [0.4, 6.0, 20.0]])

    def test_rate_runs_drop_what_does_not_reproduce(self):
        raw = self.rate_bundle()
        raw["inspection"]["valuePipeline"]["sources"]["cbs"]["rates"]["RB|bench"] = 9.0
        rr = bve.rate_runs(raw)["cbs"]
        self.assertNotIn("RB|bench", rr["groups"])
        self.assertNotIn("example", rr)
        raw = self.rate_bundle()
        raw["inspection"]["players"]["cbs"]["7"]["starterSlice"] += 1
        self.assertNotIn("example", bve.rate_runs(raw)["cbs"])
        raw = self.rate_bundle()
        raw["extra"]["vorpRuns"] = raw["extra"]["vorpRuns"][:1]
        self.assertEqual(bve.rate_runs(raw), {})
        # Round-3 shaped runs (no groups or rates) give nothing, and vorp_runs still works.
        raw = bundle()
        self.assertEqual(bve.rate_runs(raw), {})
        self.assertEqual(sorted(bve.vorp_runs(raw)), ["cbs", "espn"])

    def test_three_bench_numbers_are_named_apart(self):
        self.assertNotIn("Own bench weight</th>", TEMPLATE)
        self.assertIn("Own bench group share</th>", TEMPLATE)
        self.assertIn("DDF bench group share</th>", TEMPLATE)
        self.assertIn('id="benchWeightTable"', TEMPLATE)
        self.assertIn("Bench weight (glossary)", TEMPLATE)
        self.assertNotIn("the Indexed basis and the bench-share readout", TEMPLATE)
        self.assertIn("includes hidden sources", TEMPLATE)

    def test_phi_and_chart_spread_are_defined(self):
        self.assertIn("Φ(z) = standard normal cumulative probability", TEMPLATE)
        self.assertIn("1 − Φ((L − x) ÷ σ)", TEMPLATE)
        self.assertIn('id="phiExample"', TEMPLATE)
        self.assertIn("Φ(0) = 0.5", TEMPLATE)
        self.assertIn("CHART_SIGMA_TXT", TEMPLATE)
        self.assertNotIn("(for a chart, the charts' own disagreement)", TEMPLATE)

    def test_waiver_line_names_the_allocation_average(self):
        self.assertIn("at the heaviest allocation; averaged over the ${MIX.length} allocations", TEMPLATE)

    def test_held_reason_in_plain_words(self):
        self.assertIn('"held: fidelity: scrape_validity": "its latest scrape failed validation"', TEMPLATE)
        self.assertIn("(projections never feed DDF Value), but still counted in the league allocation and the DDF weights",
                      TEMPLATE)
        self.assertNotIn("hidden: ${esc(hiddenReason(src)", TEMPLATE)

    def test_methodology_marks_vp4_fixed_share_and_phi(self):
        self.assertIn("**VP-4.1 to 4.3: fixed-share mode only (not live).**", METHODOLOGY)
        i = METHODOLOGY.index("### VP-4 DDF weights")
        self.assertLess(METHODOLOGY.index("fixed-share mode only (not live)", i), METHODOLOGY.index("1. `Sraw[p]`", i))
        self.assertIn("`P(lo < X <= hi) = Phi((hi - x) / s(x)) - Phi((lo - x) / s(x))`", METHODOLOGY)
        self.assertIn("hidden sources left out (as the Indexed\n   basis, which it reads)", METHODOLOGY)

    # Round 6.
    def test_weight_sets_are_per_allocation(self):
        self.assertNotIn("One weight set per setting and week, shared by all three DDF Value versions.`", TEMPLATE)
        self.assertIn("One weight set per allocation, shared by all three DDF Value versions.", TEMPLATE)
        self.assertIn("The DDF weights shown are their allocation-weighted average", TEMPLATE)
        self.assertEqual(TEMPLATE.count("${WEIGHT_SETS}${SPLIT_NOTE}"), 2)
        self.assertIn("A charts-only split (JEG-1569", TEMPLATE)

    def test_bench_weight_users_are_the_verified_ones(self):
        self.assertNotIn("Team, Build a Trade and Buy / Sell's natural fit", TEMPLATE)
        self.assertIn("Team's best-move size and the Natural fit check", TEMPLATE)
        self.assertIn("Team's \"Your roster\" and ROSTER DDF totals count every player in full", TEMPLATE)

    def test_methodology_expected_starts_is_fractional_and_dated(self):
        self.assertNotIn("greedy flex (OC-4 A)", METHODOLOGY)
        self.assertIn("fractional flex seats\n(VP-2.2g, JEG-1335", METHODOLOGY)
        self.assertNotIn("this week", METHODOLOGY[METHODOLOGY.index("**ES-1"):METHODOLOGY.index("**ES-5")])
        self.assertIn("At adoption (JEG-536, 2026-10-12) the rates were QB 58%", METHODOLOGY)

    # Round 7.
    def test_unlisted_chart_counts_zero_not_left_out(self):
        # R7-OP-02: value-model.js rowCell gives a chart that does not list him
        # (below_depth) Adjusted 0, which is averaged; only no_players is null.
        self.assertNotIn("a chart that does not price the player is left out", TEMPLATE)
        self.assertNotIn("A source that does not price a player is left out", TEMPLATE)
        self.assertIn("a chart whose list ends before this player counts 0 (an implied 0", TEMPLATE)
        self.assertIn("Only a chart that does not price the position at all (it lists nobody there) or is held is left out.",
                      TEMPLATE)

    def test_seth_mcgowan_mean_counts_the_zero(self):
        # R7-OP-02 live case: CBS does not list him, so it counts 0 over 4 charts.
        adjusted = {"cbs": 0, "usatoday": 4.5301, "fantasypros": 0.1647, "fantasycalc": 0.1812}
        self.assertAlmostEqual(sum(adjusted.values()), 4.876, places=4)
        self.assertAlmostEqual(sum(adjusted.values()) / len(adjusted), 1.219, places=3)

    def test_trace_prints_the_subtraction_only_when_it_holds(self):
        # R7-CX-02: Jalen Nailor CBS, 1.2 - 0.4271 != 0.1179 over 9 allocations.
        self.assertIn("const subtractionHolds = (nat, waiver, v)", TEMPLATE)
        self.assertIn("chain = (subtractionHolds(nat, x.waiver, v)", TEMPLATE)
        self.assertIn("v, restated surplus averaged over the allocations", TEMPLATE)
        self.assertIn("each allocation computes its own surplus and factor; an absent player contributes 0; "
                      "v is the averaged pie-scaled value ÷ the averaged factor", TEMPLATE)
        self.assertEqual(TEMPLATE.count('op("=") + step("v", fmtN(v))'), 1)


if __name__ == "__main__":
    unittest.main()
