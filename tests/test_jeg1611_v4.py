"""JEG-1611 v4: property tests of the chain (iteration 3 of
docs/research/jeg1611/iteration-log.md). Synthetic tests first; the real-data
tests use development weeks 5-7 only (never 8 or 9)."""
from __future__ import annotations

import copy
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "research" / "jeg1611"))
import v4  # noqa: E402

uw = v4.uw
DEV_WEEKS = (5, 6, 7)


# ---------------------------------------------------------------------------
# Synthetic
# ---------------------------------------------------------------------------

def synth_maps(rng):
    out = {}
    for j in ("espn", "cbsros", "razzball"):
        ppg = sorted(rng.uniform(1, 25) for _ in range(40))
        out[j] = uw.build_map([(p, max(0.0, p - 6.0) ** 1.3) for p in ppg])
    return out


def synth_case(seed=1, pos="WR"):
    rng = random.Random(seed)
    maps = synth_maps(rng)
    xs = sorted(rng.uniform(1, 100) for _ in range(30))
    recs = {i: (pos, x, max(0.0, x - 20) ** 1.1, 0.0) for i, x in enumerate(xs)}
    mixes = {i: v4.Mix4("share", rng.uniform(0.0, 1.2)) for i in recs}
    R0 = {p: 6.0 for p in v4.POSITIONS}
    return recs, {pos: maps}, mixes, R0


def test_points_at_identity_and_monotone_in_A():
    recs, maps, mixes, R0 = synth_case()
    u = v4.unwind4(recs, maps, mixes, R0, "ppr")
    inv = sorted((r["A"], r["P0"]) for r in u.records.values() if r["label"] == "invertible")
    assert len(inv) >= 10
    assert all(b[1] >= a[1] - 1e-12 for a, b in zip(inv, inv[1:]))
    for r in u.records.values():
        if r["P0"] is not None:
            for kind in (r["mix"], v4.Mix4("rec", rec_hat=3.0), v4.Mix4("hist", std=5.0, rec=2.0),
                         v4.Mix4("q", q=0.3)):
                assert v4.points_at(r["P0"], kind, "ppr", "ppr") == r["P0"]


def test_identity_synthetic_and_below_waiver_keeps_x():
    recs, maps, mixes, R0 = synth_case(2)
    x = {i: r[1] for i, r in recs.items()}
    x[999] = 0.0                                   # listed at 0: untouched, not unwound
    u = v4.unwind4(recs, maps, mixes, R0, "ppr")
    assert 999 not in u.records
    for form in v4.FORMS:
        assert v4.rebuild4(u, "ppr", x, dict(R0), form) == x
    out = v4.rebuild4(u, "standard", x, {p: 4.0 for p in v4.POSITIONS})
    below = [i for i, r in u.records.items() if r["label"] == "below_waiver"]
    assert below and all(out[i] == x[i] for i in below)
    assert out[999] == 0.0


def test_delta_is_b_times_vorp_change():
    recs, maps, mixes, R0 = synth_case(3)
    x = {i: r[1] for i, r in recs.items()}
    u = v4.unwind4(recs, maps, mixes, R0, "ppr")
    Rs = {p: 4.5 for p in v4.POSITIONS}
    out = v4.rebuild4(u, "standard", x, Rs)
    b = u.b["WR"]["b"]
    assert b is not None and u.b["WR"]["method"] == "ols"
    for i, r in u.records.items():
        if r["label"] == "invertible":
            Ps = r["P0"] / (1 + r["mix"].sh)
            want = max(0.0, r["x"] + b * ((Ps - 4.5) - (r["P0"] - 6.0)))
            assert abs(out[i] - want) < 1e-9


def test_pure_receiver_move():
    """A pure receiver (raw history std = 0) anchored at Full loses all his
    implied points to Standard: x moves by b (-(P0) - (R_s - R_0))."""
    recs, maps, mixes, R0 = synth_case(4)
    i0 = max(recs, key=lambda i: recs[i][1])
    mixes[i0] = v4.Mix4("hist", std=0.0, rec=4.0)
    u = v4.unwind4(recs, maps, mixes, R0, "ppr")
    r = u.records[i0]
    assert v4.points_at(r["P0"], r["mix"], "standard", "ppr") == 0.0
    assert v4.points_at(r["P0"], r["mix"], "half_ppr", "ppr") == pytest.approx(r["P0"] / 2)
    x = {i: rr[1] for i, rr in recs.items()}
    out = v4.rebuild4(u, "standard", x, dict(R0))
    assert out[i0] == pytest.approx(max(0.0, r["x"] - u.b["WR"]["b"] * r["P0"]))
    # share model: a high share loses P0 sh / (1 + sh) points, Full -> Standard
    sh = 0.9
    assert v4.points_at(10.0, v4.Mix4("share", sh), "standard", "ppr") == pytest.approx(10.0 / 1.9)


def test_qb_untouched_synthetic():
    recs, maps, mixes, R0 = synth_case(5, pos="QB")
    x = {i: r[1] for i, r in recs.items()}
    u = v4.unwind4(recs, maps, mixes, R0, "ppr")
    assert all(r["mix"] is v4.QB_MIX for r in u.records.values())
    assert v4.rebuild4(u, "standard", x, dict(R0)) == x


def test_b_fallback_top_player():
    recs, maps, mixes, R0 = synth_case(6)
    top3 = dict(sorted(recs.items(), key=lambda kv: -kv[1][1])[:3])
    u = v4.unwind4(top3, maps, mixes, R0, "ppr")
    b = u.b["WR"]
    assert b["method"] == "top_player" and b["n"] == 3
    top = max(u.records.values(), key=lambda r: r["x"])
    assert b["b"] == pytest.approx(top["x"] / (top["P0"] - 6.0))


def test_share_model_fallback_label_and_window():
    model = v4.sm.load_model()
    assert v4.share_mix([], "WR", 5, model).label == "fallback_prior"
    assert v4.share_mix(None, "QB", 5, model) is v4.QB_MIX
    rows = [(2026, wk, 7, 10.0, 5.0) for wk in range(1, 10)] + [(2025, 3, 7, 8.0, 1.0)]
    by = v4.rows_by_key(rows, 5)
    assert sorted((r["season"], r["week"]) for r in by[7]) == [(2025, 3), (2026, 1), (2026, 2), (2026, 3), (2026, 4)]


# ---------------------------------------------------------------------------
# Real data (weeks 5-7 only)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world():
    ctx = v4.R3.load_world()
    model = v4.sm.load_model()
    return ctx, {w: v4.Week4(ctx, w, model) for w in DEV_WEEKS}


def test_fixed_allocation_reproduces_anchor_run(world):
    ctx, weeks = world
    for w, wk in weeks.items():
        for s in v4.R3.SCORINGS:
            cur = wk.current(s)
            assert len(cur["mix"]) > 1          # the anchor run is a blend of seat vertices
            fx = wk.fixed(cur, f"current_{s}", s)
            assert fx["ddf"] == cur["ddf"], (w, s)
            assert fx["adj"] == cur["adj"], (w, s)
            assert fx["waiver"] == cur["waiver"] and fx["R"] == cur["R"], (w, s)
        fh = wk.fc_half_anchor()
        assert wk.fixed(fh, "fc_half_anchor", "half_ppr")["R"] == fh["R"]
        nat = v4.R3.current_natives(wk.natives, "half_ppr")
        nat["fantasycalc"] = dict(wk.natives["fantasycalc"]["ppr"])
        got = v4.digest4(ctx, v4.run_fixed(ctx, nat, "half_ppr", fh["mix"]), "half_ppr")
        assert got["adj"] == fh["adj"] and got["ddf"] == fh["ddf"]


def test_identity_every_chart_week(world):
    ctx, weeks = world
    n = 0
    for w, wk in weeks.items():
        cases = [(c, s0, "primary") for c in ("cbs", "usatoday", "fantasycalc", "fantasypros")
                 for s0 in v4.R3.SCORINGS] + [("fantasycalc", None, "fchalf")]
        for c, s0, var in cases:
            for kind in v4.MIX_MODELS:
                u, x, dg, tag = wk.unwound(c, s0, var, (), kind)
                for form in v4.FORMS:
                    out, _, _ = wk.v4_list(c, u.s0, s0, var, (), kind, form)
                    assert out == x, (w, c, s0, var, kind, form)
                    n += 1
    assert n == 3 * 13 * 4 * 3


def test_current_ddf_reproduced_at_anchor(world):
    ctx, weeks = world
    for w, wk in weeks.items():
        for s in v4.R3.SCORINGS:
            nat = v4.R3.current_natives(wk.natives, s)
            for c in v4.R3.CHARTS:
                nat[c] = wk.v4_list(c, s, s0=s)[0]
            got = v4.digest4(ctx, v4.R3.run_at(ctx, nat, s), s)["ddf"]
            assert got == wk.current(s)["ddf"], (w, s)
        # the rescaled charts' own anchors
        assert wk.v4_list("fantasycalc", "ppr")[0] == wk.natives["fantasycalc"]["ppr"]
        assert wk.v4_list("fantasypros", "half_ppr")[0] == wk.natives["fantasypros"]["half_ppr"]


def test_qb_untouched_and_non_invertible_keep_x_real(world):
    ctx, weeks = world
    for w, wk in weeks.items():
        for c in ("fantasycalc", "fantasypros"):
            for s in ("standard", "ppr"):
                out, u, _ = wk.v4_list(c, s)
                for i, r in u.records.items():
                    if r["pos"] == "QB" or r["label"] != "invertible":
                        assert out[i] == r["x"], (w, c, s, i)


def test_P_monotone_in_A_real(world):
    ctx, weeks = world
    for w, wk in weeks.items():
        for c in ("fantasycalc", "fantasypros", "cbs", "usatoday"):
            u = wk.unwound(c, None if c in ("fantasycalc", "fantasypros") else "standard")[0]
            for p in v4.POSITIONS:
                inv = sorted((r["A"], r["P0"]) for r in u.records.values()
                             if r["pos"] == p and r["label"] == "invertible")
                assert all(b[1] >= a[1] - 1e-9 for a, b in zip(inv, inv[1:])), (w, c, p)


def test_v4_independent_of_games(world):
    ctx, weeks = world
    base = {(c, s): weeks[5].v4_list(c, s)[0] for c in ("fantasycalc", "fantasypros") for s in ("standard", "ppr")}
    ctx2 = dict(ctx)
    rng = random.Random(1611)
    ctx2["gp"] = {w: {k: rng.randint(0, 9) for k in d} for w, d in copy.deepcopy(ctx["gp"]).items()}
    ctx2["byes"] = {t: rng.randint(5, 14) for t in ctx["byes"]}
    wk2 = v4.Week4(ctx2, 5)
    for (c, s), v in base.items():
        assert wk2.v4_list(c, s)[0] == v
