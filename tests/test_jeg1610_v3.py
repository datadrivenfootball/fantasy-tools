"""JEG-1610: unit and property tests of the v3 chain
(docs/research/jeg1610/preregistration.md section 3, "Unit and property tests").
Synthetic tests first; the real-data identity runs every chart-week."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "research" / "jeg1610"))
import history as hs  # noqa: E402
import unwind as uw  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic helpers
# ---------------------------------------------------------------------------

def synth_map(rng, n=40, scale=1.0):
    """A projection priced by a convex increasing map with a zero region."""
    ppg = sorted(rng.uniform(1, 25) for _ in range(n))
    return [(p, scale * max(0.0, (p - 6.0)) ** 1.3) for p in ppg]


def synth_chart(rng, maps_p, n=30, scale=1.0):
    """Chart players whose Adjusted values are monotone in x."""
    xs = sorted(rng.uniform(1, 100) for _ in range(n))
    return {i: ("WR", x, scale * max(0.0, x - 20) ** 1.1, 0.0) for i, x in enumerate(xs)}


# ---------------------------------------------------------------------------
# Steps 2-4
# ---------------------------------------------------------------------------

def test_inverse_exact_at_nodes():
    rng = random.Random(1)
    pairs = synth_map(rng)
    m = uw.build_map(pairs)
    for p, a in pairs:
        if a > 0:
            assert abs(uw.inverse(m, a) - p) < 1e-9
            assert abs(uw.forward(m, p) - a) < 1e-9


def test_inverse_round_trip_between_nodes_and_above_top():
    m = uw.build_map([(5.0, 0.0), (10.0, 10.0), (15.0, 30.0), (20.0, 50.0)])
    assert abs(uw.inverse(m, 20.0) - 12.5) < 1e-12
    # top-3 OLS slope over (10,10),(15,30),(20,50) = 4
    assert abs(uw.inverse(m, 70.0) - 25.0) < 1e-12
    assert abs(uw.forward(m, 25.0) - 70.0) < 1e-12
    assert uw.inverse(m, -1.0) is None


def test_running_max_makes_map_monotone():
    m = uw.build_map([(5.0, 0.0), (10.0, 12.0), (11.0, 9.0), (15.0, 30.0)])
    assert list(m.adj) == [0.0, 12.0, 12.0, 30.0]
    assert uw.inverse(m, 12.0) == 10.0        # lowest ppg reaching the value


def test_P_non_decreasing_in_A():
    rng = random.Random(2)
    maps_p = {j: uw.build_map(synth_map(rng)) for j in ("espn", "cbsros", "razzball")}
    a_vals = sorted(rng.uniform(0.01, 400) for _ in range(500))
    ps = [uw.expected_points(a, maps_p)[0] for a in a_vals]
    ps = [p for p in ps if p is not None]
    assert len(ps) == len(a_vals)
    assert all(b >= a - 1e-12 for a, b in zip(ps, ps[1:]))


def test_scaling_pie_or_W_leaves_P_unchanged():
    rng = random.Random(3)
    base = {j: synth_map(random.Random(10 + n)) for n, j in enumerate(("espn", "cbsros", "razzball"))}
    for c in (0.37, 2.0, 11.0):
        m1 = {j: uw.build_map(p) for j, p in base.items()}
        mc = {j: uw.build_map([(x, c * a) for x, a in p]) for j, p in base.items()}
        for _ in range(200):
            a = rng.uniform(0.01, 300)
            p1, n1 = uw.expected_points(a, m1)
            pc, nc = uw.expected_points(c * a, mc)
            assert n1 == nc and abs(p1 - pc) < 1e-9 * max(1.0, abs(p1))


def test_g_map_identity_and_monotone():
    nodes = [(5.0, 10.0), (8.0, 20.0), (8.0, 22.0), (12.0, 40.0), (20.0, 80.0)]
    g = uw.build_g(nodes)
    assert g.tied_nodes == 1 and g.x[1] == 21.0
    xs = [uw.g_eval(g, p / 10) for p in range(0, 300)]
    assert all(b >= a for a, b in zip(xs, xs[1:])) and min(xs) >= 0.0


# ---------------------------------------------------------------------------
# Steps 5-7 on synthetic charts
# ---------------------------------------------------------------------------

def make_unwound(rng, mix_of, s0="ppr"):
    maps_p = {"WR": {j: uw.build_map(synth_map(random.Random(20 + n))) for n, j in enumerate(uw.PROJ)}}
    recs = synth_chart(rng, maps_p)
    mixes = {i: mix_of(i) for i in recs}
    return uw.unwind(recs, maps_p, mixes, s0), recs


def test_identity_synthetic():
    rng = random.Random(4)
    u, recs = make_unwound(rng, lambda i: hs.Mix(5.0 + i % 3, 2.0 + i % 4, 20, "history", None))
    x = {i: r[1] for i, r in recs.items()}
    assert uw.rebuild(u, "ppr", x) == x


def test_pure_receiver_full_anchor():
    """std_h = 0 at a Full anchor: nothing gained at Full; Full to Standard he
    loses exactly his implied receptions per game (P falls by k x rec_h = P0)."""
    rng = random.Random(5)
    u, recs = make_unwound(rng, lambda i: hs.Mix(0.0, 4.0, 30, "history", None))
    for i, rec in u.records.items():
        if rec["label"] != "invertible":
            continue
        P0 = rec["P0"]
        assert P0 * uw.ratio_for(rec, u.q, "ppr", "ppr") == P0
        Ps = P0 * uw.ratio_for(rec, u.q, "standard", "ppr")
        implied_rec = rec["k"] * rec["rec_h"]
        assert abs((P0 - Ps) - implied_rec) < 1e-12 and Ps == 0.0
    x = {i: r[1] for i, r in recs.items()}
    assert uw.rebuild(u, "ppr", x) == x


def test_unlisted_and_zero_get_no_v3_value_below_waiver_keeps_native():
    rng = random.Random(6)
    maps_p = {"WR": {j: uw.build_map(synth_map(random.Random(20 + n))) for n, j in enumerate(uw.PROJ)}}
    recs = synth_chart(rng, maps_p)
    recs[999] = ("WR", 0.0, 0.0, 0.0)                     # listed at 0
    mixes = {i: hs.Mix(6.0, 1.0, 20, "history", None) for i in recs}
    u = uw.unwind(recs, maps_p, mixes, "ppr")
    assert 999 not in u.records
    x = {i: r[1] for i, r in recs.items()}
    out = uw.rebuild(u, "standard", x)
    assert out[999] == 0.0 and 12345 not in out            # unlisted stays unlisted
    bw = [i for i, r in u.records.items() if r["label"] == "below_waiver"]
    assert bw and all(out[i] == x[i] for i in bw)
    moved = [i for i, r in u.records.items() if r["label"] == "invertible"]
    assert any(out[i] != x[i] for i in moved)


def test_fallback_ratio_and_reasons():
    rows = [(2026, 1, 1, 10.0, 0.0)] * 3 + [(2025, w, 2, 5.0, 3.0) for w in range(1, 10)] \
        + [(2025, w, 3, -1.0, 0.0) for w in range(1, 10)]
    st = hs.player_stats(rows)
    assert hs.history_mix(st, 1, 1.0).reason == "under_6_games"
    assert hs.history_mix(st, 2, 1.0).basis == "history"
    assert hs.history_mix(st, 3, 1.0).reason == "nonpositive_anchor_points"
    assert hs.history_mix(st, 4, 1.0).reason == "rookie_no_rows"
    assert abs(hs.fallback_ratio(0.4, 0.0, 1.0) - 0.6) < 1e-12
    assert hs.fallback_ratio(0.4, 1.0, 1.0) == 1.0


def test_window_excludes_current_and_later_weeks():
    rows = [(2026, w, 1, 1.0, 1.0) for w in range(1, 10)] + [(2024, 3, 1, 1.0, 1.0), (2023, 3, 1, 1.0, 1.0)]
    assert {r[1] for r in hs.window_rows(rows, 6) if r[0] == 2026} == {1, 2, 3, 4, 5}
    assert all(r[0] != 2023 for r in hs.window_rows(rows, 6))
    assert all(r[0] == 2026 for r in hs.window_rows(rows, 6, "2026_only"))
    assert len(hs.window_rows(rows, 6, "2015_2026", [(2020, 1, 1, 1.0, 1.0)])) == 7


# ---------------------------------------------------------------------------
# Real data: identity every chart-week, current DDF reproduced, games-free
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world():
    import run_v3 as R
    ctx = R.load_world()
    return R, ctx, {w: R.Week(ctx, w) for w in R.WEEKS}


def test_identity_real_every_chart_week(world):
    R, ctx, weeks = world
    worst, n = 0.0, 0
    for w, wk in weeks.items():
        lists = [(c, s0, "primary") for c in ("cbs", "usatoday") for s0 in R.SCORINGS] + \
                [("fantasycalc", "ppr", "primary"), ("fantasypros", "half_ppr", "primary"),
                 ("fantasycalc", "half_ppr", "fchalf")]
        for c, s0, var in lists:
            if var == "fchalf":
                dg, x = wk.fc_half_anchor(), dict(wk.natives["fantasycalc"]["ppr"])
            else:
                dg, x = wk.current(s0), dict(wk.natives[c][s0])
            u = R.unwind_chart(ctx, dg, c, s0, w)
            out = uw.rebuild(u, s0, x)
            assert out.keys() == x.keys()
            worst = max(worst, max(abs(out[k] - x[k]) for k in x))
            n += 1
    assert n == 5 * 9 and worst < 1e-9


def test_pipeline_at_anchor_reproduces_current_ddf(world):
    R, ctx, weeks = world
    for w, wk in weeks.items():
        for s in R.SCORINGS:
            nat = R.current_natives(wk.natives, s)
            for c in R.CHARTS:
                u = R.unwind_chart(ctx, wk.current(s), c, s, w)
                nat[c] = uw.rebuild(u, s, dict(wk.natives[c][s]))
            got = R.digest(ctx, R.run_at(ctx, nat, s), s)["ddf"]
            cur = wk.current(s)["ddf"]
            assert got.keys() == cur.keys()
            assert all(got[k] == cur[k] for k in cur), (w, s)


def test_v3_lists_do_not_depend_on_games(world):
    R, ctx, weeks = world
    import response_test as rtest
    espn = rtest.espn_games()
    wk = weeks[9]
    base = {(c, s): R.Week.v3_list(wk, c, s)[0] for c in ("fantasycalc", "fantasypros") for s in ("standard", "ppr")}
    # the v3 chain takes no games input; changing the world's games rule changes nothing it reads
    for rule in ("G1", "G2"):
        g = rtest.week_world(ctx, 9, rule=rule, espn=espn)["games"]
        assert g != rtest.week_world(ctx, 9)["games"]
        wk2 = R.Week(ctx, 9)
        wk2.games = g
        for (c, s), v in base.items():
            assert wk2.v3_list(c, s)[0] == v
