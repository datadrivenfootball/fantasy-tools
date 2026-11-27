"""EDDF (JEG-1735): the alternate value version built from the charts plus individual rankers.

Pins Jeremy's 2026-11-27 rules (every stable ranker its own equal-weight source, stale
sources excluded, each FantasyPros staff ranker separate, more rankers by registry row),
the stale and QB switches, DDF Value unchanged, EDDF off by default, and Python/JS parity.
"""
import json
import shutil
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
import eddf  # noqa: E402

CFG = {"stale_days": 14, "anchor_weeks": 3, "anchor_stability": 0.10, "anchor_floor_frac": 0.05,
       "min_anchors": 3, "exclude_positions": ["QB"], "rescale_to_ddf_total": False,
       "rankers": [{"id": "a", "scoring": ["half_ppr"]}, {"id": "b", "scoring": ["half_ppr"]},
                   {"id": "c", "scoring": ["ppr"]}]}
POS = {1: "RB", 2: "WR", 3: "WR", 4: "TE", 5: "RB", 6: "QB", 7: "RB"}
TODAY = date(2026, 11, 27)
HIST = [{1: 100, 2: 80, 3: 60, 4: 40, 5: 20, 6: 90, 7: 5}] * 3
CHARTS = {"x": {1: 100, 2: 80, 3: 60, 4: 40, 5: 20, 6: 90}, "y": {1: 98, 2: 82, 3: 58, 4: 42, 5: 22, 6: 88}}
RANKS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 2.5, 7: 6}


def run(cfg=CFG, charts=CHARTS, vint=None, lists=None, scoring="half_ppr"):
    vint = vint if vint is not None else {"a": "2026-11-25", "b": "2026-11-20"}
    lists = lists if lists is not None else {"a": RANKS, "b": RANKS}
    return eddf.eddf(charts, lists, vint, HIST, POS, cfg, TODAY, scoring)


class Curve(unittest.TestCase):
    def test_pools_violations_and_is_non_increasing(self):
        f = eddf.isotonic_nonincreasing([1, 2, 3, 4], [10, 20, 5, 4])
        self.assertEqual([f(x) for x in (1, 2, 3, 4)], [15, 15, 5, 4])
        self.assertEqual(f(0), 15)      # clipped below the anchors
        self.assertEqual(f(99), 4)      # and above
        self.assertAlmostEqual(f(2.5), 10)  # linear between block ends
        xs = [f(x / 4) for x in range(4, 17)]
        self.assertTrue(all(a >= b for a, b in zip(xs, xs[1:])))

    def test_anchors_need_every_pull_and_a_small_spread(self):
        hist = [{1: 100, 2: 100, 3: 50}, {1: 105, 2: 60, 3: 50}, {1: 98, 2: 100}]
        self.assertEqual(eddf.stable_anchors(hist, 0.10, 0.05), {1: 100})  # 2 moved, 3 missing a pull


class Rules(unittest.TestCase):
    def test_every_ranker_is_its_own_equal_weight_source(self):
        res = run()
        v = res["values"][1]
        self.assertEqual(v["count"], 4)  # two charts + two rankers, not two charts + one pooled source
        self.assertEqual(v["sources"], ["a", "b", "x", "y"])
        self.assertAlmostEqual(v["value"], (100 + 98 + 100 + 100) / 4)
        self.assertAlmostEqual(res["report"]["chart_weight_share"], 0.5)

    def test_stale_list_is_out_at_fifteen_days_not_fourteen(self):
        keep = run(vint={"a": "2026-11-13", "b": "2026-11-12"})  # 14 and 15 days
        status = {s["id"]: s for s in keep["report"]["rankers"]}
        self.assertTrue(status["a"]["in"])
        self.assertFalse(status["b"]["in"])
        self.assertIn("stale", status["b"]["reason"])
        self.assertEqual(keep["values"][1]["sources"], ["a", "x", "y"])

    def test_weekly_tuesday_reset_makes_older_lists_stale(self):
        cfg = {**CFG, "stale_weekday": 1}   # 27 Nov 2026 is a Friday: the reset was Tue 24 Nov
        res = run(cfg=cfg, vint={"a": "2026-11-24", "b": "2026-11-23"})  # both inside the 14-day backstop
        status = {s["id"]: s for s in res["report"]["rankers"]}
        self.assertTrue(status["a"]["in"])
        self.assertFalse(status["b"]["in"])
        self.assertIn("weekly reset", status["b"]["reason"])

    def test_the_reset_day_itself_counts_the_new_week(self):
        cfg = {**CFG, "stale_weekday": 1}
        tue = eddf.ranker_status({"id": "a", "scoring": ["half_ppr"]}, "2026-11-24", date(2026, 11, 24), 14, "half_ppr", 1)
        mon_list = eddf.ranker_status({"id": "a", "scoring": ["half_ppr"]}, "2026-11-23", date(2026, 11, 24), 14, "half_ppr", 1)
        self.assertTrue(tue["in"])
        self.assertFalse(mon_list["in"])  # the Monday list predates Tuesday's reset
        self.assertEqual(eddf.week_reset(date(2026, 11, 24), 1), date(2026, 11, 24))
        self.assertEqual(eddf.week_reset(date(2026, 11, 23), 1), date(2026, 11, 17))

    def test_ranker_without_this_scoring_is_out_with_a_reason(self):
        s = {x["id"]: x for x in run(vint={"c": "2026-11-26"}, lists={"c": RANKS}, scoring="half_ppr")["report"]["rankers"]}
        self.assertFalse(s["c"]["in"])
        self.assertIn("half_ppr", s["c"]["reason"])

    def test_all_rankers_stale_gives_the_chart_mean(self):
        res = run(vint={"a": "2026-09-01", "b": "2026-09-01"})
        self.assertEqual(res["values"][1]["value"], eddf.chart_only(CHARTS, POS)[1])

    def test_a_chart_down_still_prices_from_the_rankers(self):
        res = run(charts={})
        self.assertEqual(res["values"][1]["sources"], ["a", "b"])

    def test_qb_switch(self):
        self.assertNotIn("a", run()["values"][6]["sources"])
        with_qb = run(cfg={**CFG, "exclude_positions": []})
        self.assertIn("a", with_qb["values"][6]["sources"])

    def test_ranked_player_no_chart_prices_is_priced_by_rankers_alone(self):
        res = run()
        self.assertEqual(res["values"][7]["sources"], ["a", "b"])

    def test_too_few_anchors_drops_the_ranker(self):
        res = run(cfg={**CFG, "min_anchors": 99})
        self.assertEqual([s["in"] for s in res["report"]["rankers"]], [False, False, False])

    def test_superflex_and_other_team_counts_are_unavailable(self):
        self.assertEqual(eddf.available({"teams": 12, "superflex": 0}), (True, None))
        self.assertFalse(eddf.available({"teams": 12, "superflex": 1})[0])
        self.assertFalse(eddf.available({"teams": 10, "superflex": 0})[0])


class CurveMode(unittest.TestCase):
    """Jeremy, 2026-11-27: per-position curves (QBs still excluded); pooled stays as the option."""
    POS2 = {i: ("RB" if i <= 6 else "TE") for i in range(1, 13)}
    ANCH = {i: (100.0 - 5 * i if i <= 6 else 90.0 - 2 * (i - 6)) for i in range(1, 13)}  # TEs sit above the RBs ranked ahead of them
    RK = {i: float(i) for i in range(1, 13)}
    CFG = {"exclude_positions": ["QB"], "min_anchors": 4, "min_position_anchors": 3}

    def test_per_position_fits_each_position_on_its_own_anchors(self):
        iv = eddf.implied_values(self.RK, self.ANCH, self.POS2, {**self.CFG, "curve_mode": "per_position"})
        for i, v in self.ANCH.items():
            self.assertAlmostEqual(iv[i], v, places=9)  # each position's anchors are already monotone

    def test_pooled_curve_is_one_curve_for_every_position(self):
        iv = eddf.implied_values(self.RK, self.ANCH, self.POS2, {**self.CFG, "curve_mode": "pooled"})
        self.assertAlmostEqual(iv[7], iv[7])
        self.assertNotAlmostEqual(iv[7], self.ANCH[7], places=3)  # pooled pulls the TE off its own anchor
        self.assertTrue(all(iv[a] >= iv[b] for a, b in zip(range(1, 12), range(2, 13))))

    def test_default_is_per_position_and_few_anchors_fall_back_to_the_pooled_curve(self):
        iv = eddf.implied_values(self.RK, self.ANCH, self.POS2, self.CFG)
        self.assertAlmostEqual(iv[8], self.ANCH[8], places=9)
        few = eddf.implied_values(self.RK, self.ANCH, self.POS2, {**self.CFG, "min_position_anchors": 7})
        pooled = eddf.implied_values(self.RK, self.ANCH, self.POS2, {**self.CFG, "curve_mode": "pooled"})
        self.assertEqual(few, pooled)

    def test_qb_stays_excluded_in_both_modes(self):
        pos = {**self.POS2, 1: "QB"}
        for mode in ("pooled", "per_position"):
            self.assertNotIn(1, eddf.implied_values(self.RK, self.ANCH, pos, {**self.CFG, "curve_mode": mode}))

    def test_per_position_removes_most_of_the_rb_and_wr_bias_on_real_values(self):
        sys.path.insert(0, str(ROOT / "tools/research"))
        import eddf_evidence as E
        import value_reference as vr
        cfg = eddf.load_config()
        self.assertEqual(cfg["curve_mode"], "per_position")
        inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
        hist = vr.History(vr.REPO / "data/history")
        wm, charts, pos_of, _, _ = E.adjusted_by_week(inp, hist, "half_ppr", [12, 11, 10])
        lists, vint = E.load_lists("half_ppr")
        ddf = eddf.chart_only({c: wm[12][c] for c in charts}, pos_of)
        top = sorted(ddf, key=lambda p: -ddf[p])[:100]
        bias = {}
        for mode in ("pooled", "per_position"):
            res = E.run_eddf({**cfg, "curve_mode": mode}, charts, wm, lists, vint, pos_of, date(2026, 11, 27), "half_ppr", [12, 11, 10])
            e = {pk: v["value"] for pk, v in res["values"].items()}
            bias[mode] = {pos: sum(e[p] - ddf[p] for p in top if pos_of[p] == pos) / sum(1 for p in top if pos_of[p] == pos)
                          for pos in ("RB", "WR")}
        for pos in ("RB", "WR"):
            self.assertLess(abs(bias["per_position"][pos]), abs(bias["pooled"][pos]), pos)


class Variants(unittest.TestCase):
    CFGV = {**CFG, "rankers": [{"id": "a", "scoring": ["half_ppr"], "group": "G"},
                               {"id": "b", "scoring": ["half_ppr"], "group": "G"},
                               {"id": "d", "scoring": ["half_ppr"], "group": "H"}]}

    def go(self, variant):
        return eddf.eddf(CHARTS, {"a": RANKS, "b": RANKS, "d": RANKS},
                         {"a": "2026-11-25", "b": "2026-11-25", "d": "2026-11-25"}, HIST, POS, self.CFGV, TODAY,
                         "half_ppr", variant)

    def test_per_expert_is_the_default_and_every_list_votes(self):
        self.assertEqual(self.go("per_expert")["report"]["chart_weight_share"], 2 / 5)
        self.assertEqual(self.go("per_expert")["values"], eddf.eddf(
            CHARTS, {"a": RANKS, "b": RANKS, "d": RANKS}, {"a": "2026-11-25", "b": "2026-11-25", "d": "2026-11-25"},
            HIST, POS, self.CFGV, TODAY, "half_ppr")["values"])

    def test_site_once_shares_one_vote_per_group(self):
        w = eddf.source_weights({"x": 1, "a": 1, "b": 1, "d": 1}, {"a": "G", "b": "G", "d": "H"}, "site_once")
        self.assertEqual(w, {"x": 1.0, "a": 0.5, "b": 0.5, "d": 1.0})
        self.assertAlmostEqual(self.go("site_once")["report"]["chart_weight_share"], 2 / 4)

    def test_grouped_is_one_source_beside_the_charts(self):
        self.assertAlmostEqual(self.go("grouped")["report"]["chart_weight_share"], 2 / 3)
        v = self.go("grouped")["values"][1]
        self.assertAlmostEqual(v["value"], (100 + 98 + 100) / 3)

    def test_chart_floor_keeps_the_charts_at_half_when_rankers_would_outweigh_them(self):
        parts = {"x": 1, "y": 1, "a": 1, "b": 1, "d": 1, "e": 1}
        groups = {k: k for k in "abde"}
        w = eddf.source_weights(parts, groups, "chart_floor", 0.5)
        self.assertAlmostEqual(w["x"] + w["y"], sum(w[k] for k in "abde"))  # charts hold half
        self.assertAlmostEqual(w["a"], 0.5)
        few = eddf.source_weights({"x": 1, "y": 1, "a": 1}, {"a": "a"}, "chart_floor", 0.5)
        self.assertEqual(few, {"x": 1.0, "y": 1.0, "a": 1.0})  # already above the floor: one vote each

    def test_unknown_variant_is_refused(self):
        with self.assertRaises(ValueError):
            self.go("loudest")


class Rescale(unittest.TestCase):
    """Jeremy, 2026-11-28: EDDF is rescaled to the league value total DDF Value holds."""

    ON = {**CFG, "rescale_to_ddf_total": True,
          "rankers": [{"id": "a", "scoring": ["half_ppr"], "group": "G"}, {"id": "b", "scoring": ["half_ppr"], "group": "G"}]}

    def go(self, variant="per_expert", cfg=None):
        return eddf.eddf(CHARTS, {"a": RANKS, "b": {k: v + 1 for k, v in RANKS.items()}},
                         {"a": "2026-11-25", "b": "2026-11-25"}, HIST, POS, cfg or self.ON, TODAY, "half_ppr", variant)

    def test_every_variant_sums_to_the_ddf_total(self):
        ddf_total = sum(eddf.chart_only(CHARTS, POS).values())
        for variant in eddf.VARIANTS:
            res = self.go(variant)
            self.assertAlmostEqual(sum(v["value"] for v in res["values"].values()), ddf_total, delta=1e-6)
            self.assertAlmostEqual(res["report"]["rescale"]["ddf_total"], ddf_total, delta=1e-9)

    def test_rescale_is_one_factor_so_order_is_unchanged(self):
        on, off = self.go(), self.go(cfg={**self.ON, "rescale_to_ddf_total": False})
        self.assertEqual(sorted(on["values"], key=lambda k: -on["values"][k]["value"]),
                         sorted(off["values"], key=lambda k: -off["values"][k]["value"]))
        f = on["report"]["rescale"]["factor"]
        for k, v in on["values"].items():
            self.assertAlmostEqual(v["value"], off["values"][k]["value"] * f, places=9)
        self.assertIsNone(off["report"]["rescale"])

    def test_sum_holds_on_real_values_for_every_scoring_and_team_count(self):
        import value_reference as vr
        inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
        cfg = eddf.load_config()
        self.assertTrue(cfg["rescale_to_ddf_total"])
        raw = json.loads((ROOT / "docs/research/data/jeg1735/lists.json").read_text())
        for scoring in ("ppr", "half_ppr", "standard"):
            lists = {r: {int(k): v for k, v in d[scoring]["ranks"].items()} for r, d in raw.items() if scoring in d}
            vint = {r: d[scoring]["vintage"] for r, d in raw.items() if scoring in d}
            for teams in (8, 10, 12, 14, 16):
                s = vr.Setting(inp, scoring, teams, 0)
                st, rows = s.state(), s.result()["rows"]
                charts = [k for k in st["included"] if vr.FAMILY[k] == "chart" and k not in st["hidden"]]
                adj = {c: {pk: r["adjusted"][c] for pk, r in rows.items() if r["adjusted"].get(c) is not None} for c in charts}
                hist = [eddf.chart_only(adj, rows)] * 3
                res = eddf.eddf(adj, lists, vint, hist, {pk: r["pos"] for pk, r in rows.items()}, cfg, date(2026, 11, 27), scoring)
                ddf_total = sum(r["ddf"]["blended"]["value"] for r in rows.values() if r["ddf"]["blended"]["value"] is not None)
                self.assertGreater(len(res["report"]["rankers"]), 0)
                self.assertAlmostEqual(sum(v["value"] for v in res["values"].values()), ddf_total, delta=1e-6,
                                       msg=f"{scoring} {teams} teams")


class EnabledCandidates(unittest.TestCase):
    """The registry as shipped: enabled rows only at the scorings they support, disabled rows out."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools/research"))
        import eddf_evidence as E
        cls.E, cls.cfg = E, eddf.load_config()

    def status(self, scoring):
        lists, vint = self.E.load_lists(scoring)
        return {r["id"]: eddf.ranker_status(r, vint.get(r["id"]), date(2026, 11, 27), self.cfg["stale_days"], scoring,
                                            self.cfg.get("stale_weekday")) for r in self.cfg["rankers"]}

    def test_enabled_sources_appear_only_at_their_scorings(self):
        s = {sc: self.status(sc) for sc in ("ppr", "half_ppr", "standard")}
        self.assertTrue(s["ppr"]["cand-rotoballer"]["in"] and s["half_ppr"]["cand-rotoballer"]["in"])
        self.assertFalse(s["standard"]["cand-rotoballer"]["in"])
        self.assertIn("standard", s["standard"]["cand-rotoballer"]["reason"])
        self.assertTrue(s["ppr"]["cand-stm"]["in"])
        self.assertFalse(s["half_ppr"]["cand-stm"]["in"] or s["standard"]["cand-stm"]["in"])
        self.assertTrue(all(s[sc]["cand-razzball"]["in"] for sc in s))

    def test_disabled_rows_are_out_at_every_scoring(self):
        for sc in ("ppr", "half_ppr", "standard"):
            st = self.status(sc)
            for rid in ("cand-fanduel", "cand-rsj-wolf", "cand-footballguys-qb", "cand-gwttkb"):
                self.assertFalse(st[rid]["in"], f"{rid} {sc}")
                self.assertIn("disabled", st[rid]["reason"])

    def test_a_source_missing_a_scoring_has_no_list_there(self):
        lists, _ = self.E.load_lists("standard")
        self.assertNotIn("cand-rotoballer", lists)
        self.assertNotIn("cand-stm", lists)
        self.assertIn("cand-razzball", lists)

    def test_ties_share_the_average_rank_and_qbs_get_no_implied_value(self):
        import eddf_candidates as C
        self.assertEqual(C.rank_by_points([(1, 10.0), (2, 10.0), (3, 8.0)]), {1: 1.5, 2: 1.5, 3: 3.0})
        lists, vint = self.E.load_lists("half_ppr")
        # a model list prices players it ranks only, and a QB never gets an implied value
        pos = {1: "QB", 2: "RB", 3: "WR"}
        iv = eddf.implied_values({1: 1.0, 2: 2.0, 3: 3.0}, {2: 50.0, 3: 40.0, 1: 90.0}, pos,
                                 {**self.cfg, "min_anchors": 2})
        self.assertEqual(set(iv), {2, 3})

    def test_stage_off_leaves_value_reference_alone(self):
        text = (ROOT / "pipelines/value_reference.py").read_text()
        self.assertNotIn("eddf", text)

    def test_rescale_holds_with_the_enabled_registry_in_every_scoring_and_variant(self):
        import value_reference as vr
        inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
        for scoring in ("ppr", "half_ppr", "standard"):
            lists, vint = self.E.load_lists(scoring)
            s = vr.Setting(inp, scoring, 12, 0)
            st, rows = s.state(), s.result()["rows"]
            charts = [k for k in st["included"] if vr.FAMILY[k] == "chart" and k not in st["hidden"]]
            adj = {c: {pk: r["adjusted"][c] for pk, r in rows.items() if r["adjusted"].get(c) is not None} for c in charts}
            ddf_total = sum(r["ddf"]["blended"]["value"] for r in rows.values() if r["ddf"]["blended"]["value"] is not None)
            for variant in eddf.VARIANTS:
                res = eddf.eddf(adj, lists, vint, [eddf.chart_only(adj, rows)] * 3, {pk: r["pos"] for pk, r in rows.items()},
                                self.cfg, date(2026, 11, 27), scoring, variant)
                used = {s_["id"] for s_ in res["report"]["rankers"] if s_["in"]}
                self.assertIn("cand-razzball", used)
                self.assertNotIn("cand-fanduel", used)
                self.assertAlmostEqual(sum(v["value"] for v in res["values"].values()), ddf_total, delta=1e-6,
                                       msg=f"{scoring} {variant}")


class Registry(unittest.TestCase):
    def test_registry_has_the_three_staff_rankers_each_separate(self):
        cfg = eddf.load_config()
        ids = {r["id"] for r in cfg["rankers"]}
        for want in ("fp-andrew-erickson", "fp-derek-brown", "fp-pat-fitzmaurice"):
            self.assertIn(want, ids)
        self.assertEqual(len(cfg["rankers"]), len(ids))
        for r in cfg["rankers"]:
            self.assertTrue({"id", "outlet", "scoring", "url", "how_read"} <= set(r))

    def test_adding_a_ranker_is_one_row(self):
        more = {**CFG, "rankers": CFG["rankers"] + [{"id": "d", "scoring": ["half_ppr"]}]}
        res = run(cfg=more, vint={"a": "2026-11-25", "b": "2026-11-20", "d": "2026-11-26"},
                  lists={"a": RANKS, "b": RANKS, "d": RANKS})
        self.assertEqual(res["values"][1]["count"], 5)

    def test_a_disabled_row_is_excluded_with_a_reason(self):
        cfg = {**CFG, "rankers": [{"id": "a", "scoring": ["half_ppr"]},
                                  {"id": "b", "scoring": ["half_ppr"], "enabled": False}]}
        res = run(cfg=cfg)
        status = {s["id"]: s for s in res["report"]["rankers"]}
        self.assertFalse(status["b"]["in"])
        self.assertIn("disabled", status["b"]["reason"])
        self.assertNotIn("b", res["values"][1]["sources"])
        self.assertEqual(res["values"][1]["sources"], ["a", "x", "y"])

    def test_registry_enabled_and_disabled_candidates_as_ruled(self):
        # Jeremy, 2026-11-28: Razzball, Rotoballer and StickToTheModel on; FanDuel (scoring and date
        # not stated), Wolf (duplicate), Footballguys (QBs only), GWTTKB (stale) stay off.
        rows = {r["id"]: r for r in eddf.load_config()["rankers"]}
        for rid in ("cand-razzball", "cand-rotoballer", "cand-stm"):
            self.assertIs(rows[rid]["enabled"], True, rid)
        for rid in ("cand-fanduel", "cand-rsj-wolf", "cand-footballguys-qb", "cand-gwttkb"):
            self.assertIs(rows[rid]["enabled"], False, rid)
        self.assertEqual(rows["cand-razzball"]["scoring"], ["ppr", "half_ppr", "standard"])
        self.assertEqual(rows["cand-rotoballer"]["scoring"], ["ppr", "half_ppr"])
        self.assertEqual(rows["cand-stm"]["scoring"], ["ppr"])

    def test_duplicate_ids_are_refused(self):
        import tempfile
        p = Path(tempfile.mkdtemp()) / "c.json"
        p.write_text(json.dumps({**CFG, "rankers": [{"id": "a"}, {"id": "a"}]}))
        with self.assertRaises(ValueError):
            eddf.load_config(p)


class DdfUnchanged(unittest.TestCase):
    def test_ddf_value_is_the_equal_weight_mean_of_the_visible_charts_and_never_reads_eddf(self):
        import value_reference as vr
        text = (ROOT / "pipelines/value_reference.py").read_text()
        self.assertNotIn("eddf", text)  # off by default: the reference never loads it
        self.assertEqual(list(vr.DDF_VERSIONS), ["ddf_value", "ddf_value_charts", "ddf_value_projections"])
        inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
        s = vr.Setting(inp, "half_ppr", 12, 0)
        st, rows = s.state(), s.result()["rows"]
        charts = [k for k in st["included"] if vr.FAMILY[k] == "chart" and k not in st["hidden"]]
        mine = eddf.chart_only({c: {pk: r["adjusted"][c] for pk, r in rows.items() if r["adjusted"].get(c) is not None}
                                for c in charts}, rows)
        for pk, r in rows.items():
            ref = r["ddf"]["blended"]["value"]
            if ref is not None:
                self.assertAlmostEqual(mine[pk], ref, places=9)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class JsParity(unittest.TestCase):
    def test_js_twin_matches_the_python_module_on_the_pinned_fixture(self):
        fx = json.loads((ROOT / "tests/fixtures/eddf_parity.json").read_text())
        pyres = eddf.eddf({c: {int(k): v for k, v in m.items()} for c, m in fx["charts"].items()},
                          {r: {int(k): v for k, v in m.items()} for r, m in fx["lists"].items()}, fx["vintages"],
                          [{int(k): v for k, v in h.items()} for h in fx["history"]],
                          {int(k): v for k, v in fx["pos"].items()}, fx["config"], date.fromisoformat(fx["as_of"]), fx["scoring"])
        self.assertEqual({str(k): round(v["value"], 9) for k, v in pyres["values"].items()},
                         {k: round(v, 9) for k, v in fx["expected"].items()})
        code = ("const m=require(process.argv[1]);const fx=JSON.parse(require('fs').readFileSync(process.argv[2]));"
                "const r=m.eddf(fx.charts,fx.lists,fx.vintages,fx.history,fx.pos,fx.config,fx.as_of,fx.scoring);"
                "const o={};for(const k in r.values)o[k]=r.values[k].value;console.log(JSON.stringify(o));")
        out = subprocess.run(["node", "-e", code, str(ROOT / "pipelines/eddf_model.js"),
                              str(ROOT / "tests/fixtures/eddf_parity.json")], capture_output=True, text=True, check=True)
        js = json.loads(out.stdout)
        self.assertEqual(set(js), set(fx["expected"]))
        for k, v in fx["expected"].items():
            self.assertAlmostEqual(js[k], v, places=9)


if __name__ == "__main__":
    unittest.main()
