"""JEG-1691 v5: the chart chain on one snapshot week, and the Tier 1 chart tests T2-T8.

Spec: docs/research/jeg1691/preregistration.md (binding). Steps 1-4 are v4's, imported
unchanged from tools/research/jeg1611/v4.py (Week4.unwound: Adjusted A_i(s0), P_i(s0),
labels). Steps 5-6 are mix.py. Step 7: a pseudo projection source outside I, run through
the unmodified value_reference.run_pipeline (VP-1.4 path), in delta form:
    Av5_i(s) = max(0, A_i(s0) + Aps_i(s) - Aps_i(s0)).
The pseudo-source's list is the projections' mean ppg m_j(s) for every player, with the
chart's invertible players replaced by their assumed points P_i(s) (amendment 4), so its
waiver line comes out of the pipeline's own rule.
Research only; no pipeline code is modified.
"""
from __future__ import annotations

import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "research" / "jeg1611"))
sys.path.insert(0, str(HERE))

import v4  # noqa: E402
import mix as mx  # noqa: E402
import refs as rf  # noqa: E402
import history5 as h5  # noqa: E402
import stats5 as st  # noqa: E402

R3, uw, vr = v4.R3, v4.uw, v4.vr
SCORINGS = mx.SCORINGS
CHARTS5 = ("fantasycalc", "fantasypros")
REFERENCE_CHARTS = ("cbs", "usatoday")
POOL = ("RB", "WR", "TE")
TOP_N = {"RB": 24, "WR": 24, "TE": 12}
ANCHORS = {"primary": {"fantasycalc": "ppr", "fantasypros": "half_ppr"},
           "fc_half": {"fantasycalc": "half_ppr", "fantasypros": "half_ppr"},
           "fp_full": {"fantasycalc": "ppr", "fantasypros": "ppr"}}
T7_CELLS = (("fantasycalc", "standard"), ("fantasycalc", "half_ppr"),
            ("fantasypros", "standard"), ("fantasypros", "ppr"))
MIXKINDS = ("v5", "k0", "kinf", "v4share")


class Week5:
    def __init__(self, ctx, w, sel, hist):
        self.ctx, self.w, self.sel, self.hist = ctx, w, sel, hist
        self.wk = v4.Week4(ctx, w)
        self.refs = rf.Refs(w, ctx["name_of"], ctx["pos_of"])
        self._runs, self._mix = {}, {}

    # -- steps 1-4 (v4, unchanged) -------------------------------------------
    def unwound(self, chart, anchor="primary", drop=(), exclude=()):
        """exclude: projections left out of step 4's maps only (amendment 10); the pipeline
        runs, and so the references, keep every source."""
        s0 = ANCHORS[anchor][chart]
        if exclude:
            if chart == "fantasycalc" and anchor == "fc_half":
                dg, s00, _x, _t = self.wk.anchor4(chart, "fchalf", drop)
            elif chart == "fantasypros" and anchor == "fp_full":
                dg, s00, _x, _t = self.wk.anchor_at(chart, "ppr", drop)
            else:
                dg, s00, _x, _t = self.wk.anchor4(chart, "primary", drop)
            recs = dg["charts"][chart]
            priced = [k for k, r in recs.items() if r[1] > 0]
            mixes = self.wk.mixes("share", priced, s00, priced)
            pairs = {j: by for j, by in dg["pairs"].items() if j not in exclude}
            u = v4.unwind4(recs, uw.maps_by_position(pairs), mixes, dg["R"], s00)
            assert u.s0 == s0
            return u
        if chart == "fantasycalc" and anchor == "fc_half":
            u, _x, _dg, _t = self.wk.unwound(chart, variant="fchalf", drop=drop)
        elif chart == "fantasypros" and anchor == "fp_full":
            u, _x, _dg, _t = self.wk.unwound(chart, s0="ppr", drop=drop)
        else:
            u, _x, _dg, _t = self.wk.unwound(chart, drop=drop)
        assert u.s0 == s0, (chart, anchor, u.s0)
        return u

    # -- step 5 ---------------------------------------------------------------
    def mixes(self, keys, s0, kind="v5", u=None):
        """{key: (mix dict, label)} for the given keys at anchor s0."""
        out = {}
        pos_of = self.ctx["pos_of"]
        if kind == "v4share":
            for k in keys:
                sh = u.records[k]["mix"].sh if u is not None else 0.0
                r0 = mx.REC_W[s0]
                out[k] = ({"rec": sh / (1 + r0 * sh), "other": 1.0 / (1 + r0 * sh)}, "v4share")
            return out
        cut = (2026, self.w)
        for p in set(pos_of.get(k) for k in keys):
            if p not in mx_positions():
                continue
            t = self.sel[p]["t"]
            ck = (p, t, s0)
            if ck not in self._mix:
                hists = {k: mx.history_rates(h5.before(rows, cut), t)
                         for k, rows in self.hist.items() if pos_of.get(k) == p}
                hists = {k: h for k, h in hists.items() if h is not None}
                self._mix[ck] = (hists, mx.position_prior(hists, pos_of, s0)[p])
            hists, prior = self._mix[ck]
            kk = ({c: 0.0 for c in mx.CATS} if kind == "k0" else
                  {c: math.inf for c in mx.CATS} if kind == "kinf" else self.sel[p]["k"])
            for k in keys:
                if pos_of.get(k) == p:
                    m = mx.shrunk_mix(hists.get(k), prior, kk, s0)
                    out[k] = (m.m, m.label)
        return out

    # -- step 7 ---------------------------------------------------------------
    def base(self, s, drop=(), exclude=()):
        nat = R3.current_natives(self.wk.natives, s)
        nat = {k: v for k, v in nat.items() if k not in drop}
        pos_of = {i: p for i, p in self.ctx["pos_of"].items() if p in vr.POSITIONS}
        src = {k: vr.SourceInput(k, vr.FAMILY[k], {i: float(x) for i, x in nat[k].items()
                                                   if vr._finite(x) and i in pos_of})
               for k in vr.SOURCES if k in nat}
        inc = [k for k in self.ctx["inc_list"][s] if k in src]
        return nat, src, inc, vr.mean_ppg(src, [k for k in inc if k not in exclude])

    def run(self, s, extras: dict, tag, drop=()):
        """The unmodified pipeline at s with extra projection sources outside I."""
        key = (s, tag, tuple(sorted(drop)))
        if key not in self._runs:
            nat, _src, inc, _m = self.base(s, drop)
            sources = {k: vr.SourceInput(k, vr.FAMILY[k], dict(nat[k])) for k in vr.SOURCES if k in nat}
            for name, vals in extras.items():
                sources[name] = vr.SourceInput(name, "projection", dict(vals))
            live = self.ctx["live"][s]
            hidden = set(self.ctx["hidden"][s]) & set(inc)
            self._runs[key] = vr.run_pipeline(live.league, sources, self.ctx["pos_of"], inc, None,
                                              lineup=live.lineup, hidden=hidden, flex_bench_seats=True)
        return self._runs[key]

    def chain(self, anchor="primary", drop=(), kinds=("v5",), exclude=()):
        """Everything the tests read for one anchor variant and drop set."""
        pos_of = self.ctx["pos_of"]
        U, P, labels = {}, {}, {}
        for c in CHARTS5:
            if c in drop:
                continue
            u = self.unwound(c, anchor, drop, exclude)
            U[c] = u
            inv = [k for k, r in u.records.items() if r["label"] == "invertible" and r.get("P0") is not None
                   and pos_of.get(k) in vr.POSITIONS]
            for kind in kinds:
                mixes = self.mixes(inv, u.s0, kind, u)
                P[(c, kind)] = {k: (u.records[k]["P0"], mixes[k][0]) for k in inv if k in mixes}
                labels[(c, kind)] = {k: mixes[k][1] for k in inv if k in mixes}
            ref = {}
            for k in inv:
                rm = self.refs.ref_mix(k, u.s0)
                ref[k] = (u.records[k]["P0"], rm if rm is not None else P[(c, kinds[0])][k][1])
            P[(c, "ref")] = ref
        runs, ps_adj, ps_maps = {}, {}, {}
        for s in SCORINGS:
            # the pad (waiver pool) is the projections' mean ppg without the excluded ones
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
            res = self.run(s, extras, f"{anchor}|{','.join(kinds)}|x={','.join(exclude)}", drop)
            runs[s] = res
            for name in extras:
                pl = res["sources"][name]["players"]
                ps_adj[(name, s)] = {i: float(r["adjusted"]) for i, r in pl.items() if r.get("adjusted") is not None}
                ps_maps[(name, s)] = [(float(r["native"]), float(r["adjusted"])) for r in pl.values()
                                      if r.get("adjusted") is not None and r.get("native") is not None]
        return {"U": U, "P": P, "labels": labels, "runs": runs, "ps_adj": ps_adj, "ps_maps": ps_maps,
                "anchor": anchor, "drop": drop, "exclude": exclude}

    def av5(self, ch, c, kind, s):
        """{key: Av5_i(s)} for the invertible players (delta form)."""
        u = ch["U"][c]
        name = f"ps|{c}|{kind}"
        a_s, a_0 = ch["ps_adj"][(name, s)], ch["ps_adj"][(name, u.s0)]
        # difference first, so the identity at s = s0 is exact in floating point
        return {k: max(0.0, u.records[k]["A"] + (a_s.get(k, 0.0) - a_0.get(k, 0.0))) for k in ch["P"][(c, kind)]}

    def chart_list(self, ch, c, kind, s):
        """The chart's Adjusted at s: Av5 for invertible players, unchanged for the rest."""
        unch = self.unchanged(ch, c, s)
        out = dict(unch)
        out.update(self.av5(ch, c, kind, s))
        return out

    @staticmethod
    def unchanged(ch, c, s):
        rows = ch["runs"][s]["rows"]
        return {i: float(r["adjusted"][c]) for i, r in rows.items() if r["adjusted"].get(c) is not None}


def mx_positions():
    return ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# DDF Value (VP-6.3) from a run's rows with two charts replaced
# ---------------------------------------------------------------------------

def chart_keys(ctx, res, s):
    return [k for k in res["included"] if vr.FAMILY.get(k) == "chart" and k not in ctx["hidden"][s]]


def ddf_from_rows(res, keys, replace: dict | None = None) -> dict:
    out = {}
    for i, r in res["rows"].items():
        vals = []
        for k in keys:
            v = r["adjusted"].get(k)
            if replace and k in replace and i in replace[k]:
                v = replace[k][i]
            if v is not None:
                vals.append(float(v))
        out[i] = sum(vals) / len(vals) if vals else None
    return out
