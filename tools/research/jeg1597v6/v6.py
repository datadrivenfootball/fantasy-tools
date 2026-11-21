"""JEG-1597 v6: "Scoring-aware DDF", a separate research metric shown beside DDF Value.

Design: docs/research/jeg1597/v6-design.md. EXPLORATORY: not pre-registered, never published,
no pipeline, chart or DDF Value change. Prior lanes (v4 steps 1-4, v5 step 7 machinery) are
imported read-only from the pinned prior tree (prior.py).

Per snapshot week w, chart c in {FantasyCalc (anchor Full), FantasyPros (anchor Half)}:
  1-2  A_i(s0): the chart's Adjusted at its anchor, from the unmodified pipeline (v4).
  3-4  P_i(s0): chart-implied points per game, by inverting DDF's own projection pricing (v4).
  5    q_i: catches per anchor point = a q_hist + (1 - a) q_pos, a = n / (n + k_p), k_p chosen by
       forward CV on 2016-2025 actuals over a wide grid (share_bt.py -> params.json). The
       non-catch points are split over the six other ESPN categories by the player's history
       (pull k_other games), which matters only for custom scoring, never for the presets.
  6    assumed stat line = P_i(s0) x mix (catches q_i P_i(s0); F(line, s0) = P_i(s0) exactly).
  7    the line, rescored at s, priced through DDF's ESPN-style projection path as a pseudo-source
       outside I (v5 machinery), delta form: A6_i(s) = max(0, A_i(s0) + Aps_i(s) - Aps_i(s0)).
  avg  Scoring-aware DDF(s) = mean of the four charts' Adjusted (VP-6.3): CBS Sports and USA
       Today as published at s; FantasyCalc and FantasyPros A6(s).
Players without an assumed line (below waiver or no inverse at the anchor) keep the chart's
unchanged Adjusted at s, labelled.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prior  # noqa: E402

prior.activate()
import history5 as h5  # noqa: E402
import mix as mx  # noqa: E402
import v5  # noqa: E402

vr, uw, R3 = v5.vr, v5.uw, v5.R3
SCORINGS = mx.SCORINGS
CHARTS = v5.CHARTS5
POSITIONS = ("QB", "RB", "WR", "TE")
OTHER = tuple(c for c in mx.CATS if c != "rec")
PRIOR_MIN_GAMES = 8


def _f(x):
    return math.inf if x in ("inf", math.inf) else float(x)


def load_params(path: Path = HERE / "params.json") -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    return {"k_catch": {p: _f(v) for p, v in d["k_catch"].items()},
            "k_catch_cal_rule": {p: _f(v) for p, v in d["k_catch_cal_rule"].items()},
            "k_other": _f(d["k_other"])}


# ---------------------------------------------------------------------------
# Step 5-6 (pure functions)
# ---------------------------------------------------------------------------

def is_game(line: dict) -> bool:
    """A game = nonzero Standard or Full points (the v5.1 rule, so step 5 matches its backtest)."""
    return mx.F(line, "standard") != 0 or mx.F(line, "ppr") != 0


def catch_history(lines: list, s0: str) -> dict | None:
    """Ratio-of-totals history: q = receptions per anchor point; comp = other stats per Standard
    point (F(comp, standard) = 1); n = games."""
    games = [ln for ln in lines if is_game(ln)]
    if not games:
        return None
    rec = sum(float(ln.get("rec", 0.0)) for ln in games)
    pts = sum(mx.F(ln, s0) for ln in games)
    std = sum(mx.F(ln, "standard") for ln in games)
    if not pts > 0:
        return None
    comp = {c: sum(float(ln.get(c, 0.0)) for ln in games) / std for c in OTHER} if std > 0 else None
    return {"q": rec / pts, "comp": comp, "n": len(games), "rec_pg": rec / len(games), "pts_pg": pts / len(games)}


def position_prior(hists: dict, pos_of: dict) -> dict:
    """{pos: {"q":, "comp":}}: games-weighted means over players with >= 8 history games."""
    acc = {}
    for k, h in hists.items():
        p = pos_of.get(k)
        if h is None or p is None or h["n"] < PRIOR_MIN_GAMES or h["comp"] is None:
            continue
        a = acc.setdefault(p, {"q": 0.0, "comp": {c: 0.0 for c in OTHER}, "n": 0.0})
        a["q"] += h["n"] * h["q"]
        for c in OTHER:
            a["comp"][c] += h["n"] * h["comp"][c]
        a["n"] += h["n"]
    return {p: {"q": a["q"] / a["n"], "comp": {c: v / a["n"] for c, v in a["comp"].items()}}
            for p, a in acc.items() if a["n"] > 0}


def pull(own: float, pos: float, n: int, k: float) -> float:
    a = 0.0 if math.isinf(k) else n / (n + k)
    return a * own + (1.0 - a) * pos


def v6_mix(h: dict | None, prior_p: dict, k_catch: float, k_other: float, s0: str) -> tuple:
    """(seven-category mix per anchor point with F(mix, s0) = 1, label, info)."""
    r0 = mx.REC_W[s0]
    if h is None:
        q, comp, label, n = prior_p["q"], prior_p["comp"], "fallback_position", 0
    else:
        n = h["n"]
        q = pull(h["q"], prior_p["q"], n, k_catch)
        own_comp = h["comp"] if h["comp"] is not None else prior_p["comp"]
        comp = {c: pull(own_comp[c], prior_p["comp"][c], n, k_other) for c in OTHER}
        label = "own"
    fs = mx.F({**comp, "rec": 0.0}, "standard")
    comp = {c: v / fs for c, v in comp.items()} if fs > 0 else prior_p["comp"]
    std_share = 1.0 - r0 * q
    if not std_share > 0:
        raise ValueError("catch share at or above 1 / reception weight")
    m = {"rec": q, **{c: std_share * comp[c] for c in OTHER}}
    return m, label, {"n": n, "q": q, "q_hist": None if h is None else h["q"], "q_pos": prior_p["q"],
                      "a": 0.0 if (h is None or math.isinf(k_catch)) else n / (n + k_catch)}


def assumed_line(P0: float, m: dict) -> dict:
    return {c: P0 * v for c, v in m.items()}


# ---------------------------------------------------------------------------
# The chain on one week
# ---------------------------------------------------------------------------

class Week6(v5.Week5):
    """v5's Week5 with the v6 mix as the primary kind ("v5" slot, so v5's battery reads it)."""

    KINDS = ("v5", "light8", "heavy", "kinf", "calrule", "rankP", "projP")

    def __init__(self, ctx, w, sel, hist, params):
        super().__init__(ctx, w, sel, hist)
        self.params = params
        self._h6 = {}
        self.info = {}

    def hist6(self, s0):
        if s0 not in self._h6:
            cut = (2026, self.w)
            pos_of = self.ctx["pos_of"]
            hs = {k: catch_history(h5.before(rows, cut), s0) for k, rows in self.hist.items()
                  if pos_of.get(k) in POSITIONS}
            self._h6[s0] = (hs, position_prior(hs, pos_of))
        return self._h6[s0]

    def mixes(self, keys, s0, kind="v5", u=None):
        if kind in ("heavy", "kinf", "k0", "v4share"):
            return super().mixes(keys, s0, "v5" if kind == "heavy" else kind, u)
        hs, pri = self.hist6(s0)
        kc = dict(self.params["k_catch"])
        if kind == "light8":
            kc = {p: (math.inf if p == "QB" else 8.0) for p in POSITIONS}
        elif kind == "calrule":
            kc = dict(self.params["k_catch_cal_rule"])
        out = {}
        for k in keys:
            p = self.ctx["pos_of"].get(k)
            if p not in pri:
                continue
            m, label, info = v6_mix(hs.get(k), pri[p], kc[p], self.params["k_other"], s0)
            out[k] = (m, label)
            if kind in ("v5", "rankP", "projP"):
                self.info[(s0, k)] = info
        return out

    def points_variant(self, u, keys, kind, m0):
        """P_i(s0) by variant. chart: Jeremy's step 4 (v4 inversion). rankP: only the chart's
        within-position ORDER is used: the projections' consensus ppg at the same rank. projP:
        the projections' consensus ppg for the player (the chart contributes no points at all)."""
        P = {k: u.records[k]["P0"] for k in keys}
        if kind == "projP":
            return {k: (m0[k] if m0.get(k, 0) > 0 else P[k]) for k in keys}
        if kind == "rankP":
            pos_of = self.ctx["pos_of"]
            out = {}
            for p in POSITIONS:
                ks = sorted((k for k in keys if pos_of.get(k) == p), key=lambda k: -u.records[k]["A"])
                ladder = sorted((v for j, v in m0.items() if pos_of.get(j) == p and v > 0), reverse=True)
                for r, k in enumerate(ks):
                    out[k] = ladder[r] if r < len(ladder) else P[k]
            return out
        return P

    def chain(self, anchor="primary", drop=(), kinds=KINDS, exclude=(), anchors_by_chart=None):
        """v5's chain with v6 kinds and P_i(s0) variants. anchors_by_chart lets FantasyCalc and
        FantasyPros take different anchor variants (for the anchor sensitivity grid)."""
        pos_of = self.ctx["pos_of"]
        U, P, labels = {}, {}, {}
        for c in CHARTS:
            if c in drop:
                continue
            an = (anchors_by_chart or {}).get(c, anchor)
            u = self.unwound(c, an, drop, exclude)
            U[c] = u
            inv = [k for k, r in u.records.items() if r["label"] == "invertible" and r.get("P0") is not None
                   and pos_of.get(k) in vr.POSITIONS]
            _n, _s, _i, m0 = self.base(u.s0, drop, exclude)
            for kind in kinds:
                mixes = self.mixes(inv, u.s0, kind, u)
                Pk = self.points_variant(u, inv, kind, m0)
                P[(c, kind)] = {k: (Pk[k], mixes[k][0]) for k in inv if k in mixes}
                labels[(c, kind)] = {k: mixes[k][1] for k in inv if k in mixes}
            ref = {}
            for k in inv:
                rm = self.refs.ref_mix(k, u.s0)
                ref[k] = (u.records[k]["P0"], rm if rm is not None else P[(c, kinds[0])][k][1])
            P[(c, "ref")] = ref
        runs, ps_adj, ps_maps = {}, {}, {}
        tag = f"v6|{anchor}|{sorted((anchors_by_chart or {}).items())}|{','.join(kinds)}|x={','.join(exclude)}"
        for s in SCORINGS:
            _nat, _src, _inc, m = self.base(s, drop, exclude)
            extras = {}
            for (c, kind), pm in P.items():
                s0 = U[c].s0
                vals = dict(m)
                for k, (P0, mixd) in pm.items():
                    vals[k] = mx.points_at(P0, mixd, s, s0)
                extras[f"ps|{c}|{kind}"] = vals
            extras["sleeper_own"] = self.refs.sleeper_ppg(s)
            if "espn" in _nat:
                extras["espn_twin"] = dict(_nat["espn"])
            res = self.run(s, extras, tag, drop)
            runs[s] = res
            for name in extras:
                pl = res["sources"][name]["players"]
                ps_adj[(name, s)] = {i: float(r["adjusted"]) for i, r in pl.items() if r.get("adjusted") is not None}
                ps_maps[(name, s)] = [(float(r["native"]), float(r["adjusted"])) for r in pl.values()
                                      if r.get("adjusted") is not None and r.get("native") is not None]
        return {"U": U, "P": P, "labels": labels, "runs": runs, "ps_adj": ps_adj, "ps_maps": ps_maps,
                "anchor": anchor, "drop": drop, "exclude": exclude}

    def av5(self, ch, c, kind, s):
        """Delta form (v5's, unchanged). Kinds whose points differ from the chart's (rankP,
        projP) are still anchored on the chart's A_i(s0): only the scoring change is theirs."""
        return super().av5(ch, c, kind, s)

    def metric(self, ch, s, kind="v5", lists=None):
        """{key: Scoring-aware DDF at s} and {key: DDF Value at s} from the same run."""
        res = ch["runs"][s]
        keys = v5.chart_keys(self.ctx, res, s)
        rep = lists or {c: self.av5(ch, c, kind, s) for c in ch["U"]}
        return v5.ddf_from_rows(res, keys, rep), v5.ddf_from_rows(res, keys)


def as_primary(ch: dict, kind: str) -> dict:
    """A chain view in which `kind` sits in the "v5" slot, so v5's battery can score it."""
    if kind == "v5":
        return ch
    out = dict(ch)
    out["P"] = dict(ch["P"])
    out["labels"] = dict(ch["labels"])
    out["ps_adj"] = dict(ch["ps_adj"])
    out["ps_maps"] = dict(ch["ps_maps"])
    for c in ch["U"]:
        out["P"][(c, "v5")] = ch["P"][(c, kind)]
        out["labels"][(c, "v5")] = ch["labels"][(c, kind)]
        for s in SCORINGS:
            out["ps_adj"][(f"ps|{c}|v5", s)] = ch["ps_adj"][(f"ps|{c}|{kind}", s)]
            out["ps_maps"][(f"ps|{c}|v5", s)] = ch["ps_maps"][(f"ps|{c}|{kind}", s)]
    return out


def load(weeks=(5, 6, 7, 8, 9, 10)):
    """(ctx, [Week6]) for the given chart weeks."""
    H = h5.load()
    ctx = R3.load_world()
    sel = json.loads((prior.DEFAULT_TREE / "tools/research/jeg1691/out/decisive/selection.json").read_text())["selection"]
    sel = {p: {"k": {c: _f(x) for c, x in v["k"].items()}, "t": _f(v["t"])} for p, v in sel.items()}
    params = load_params()
    return ctx, [Week6(ctx, w, sel, H["by_player"], params) for w in weeks]
