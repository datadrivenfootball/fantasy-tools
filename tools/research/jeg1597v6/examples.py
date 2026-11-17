"""v6 worked examples on chart week 10 (EXPLORATORY). Out: out/examples.json.

  python3 examples.py --list          # candidate pool (to choose the players)
  python3 examples.py                 # the chosen players (EXAMPLES below)

For each player: published chart values, DDF Value and the new metric at three scorings, the
anchor band (four anchor pairs), the assumed stat line from each adjusted chart, the history
behind the catch share, and the parts of the change (FantasyCalc and FantasyPros).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v6  # noqa: E402
import evidence as EV  # noqa: E402
import history5 as h5  # noqa: E402
import mix as mx  # noqa: E402

W10 = 10
# chosen 2026-11-17 from the --list pool (see the design doc, choice log): a mix of RB, WR, TE,
# QB, a pass-catching RB, a rookie / thin history, and an injured player
EXAMPLES = (
    ("Jaxon Smith-Njigba", "WR, catch-heavy top receiver"),
    ("Christian Watson", "WR with a low catch share (big-play receiver), pulled up toward the average"),
    ("Christian McCaffrey", "RB, pass-catching back"),
    ("Derrick Henry", "RB, early-down back with few catches"),
    ("Trey McBride", "TE, very catch-heavy"),
    ("George Kittle", "TE, yards and TDs more than catches"),
    ("Josh Allen", "QB: on the three presets a QB's own line barely changes"),
    ("Jonah Coleman", "RB rookie: 4 games of history"),
    ("Jordyn Tyson", "WR rookie: 1 game of history, so the position share does most of the work"),
    ("Mike Evans", "WR with no game rows in weeks 7-9 (out); the chart value already prices that"),
)


def games_2026(hist, k, w0, w1):
    return sum(1 for (s, w), ln in hist.get(k, []) if s == 2026 and w0 <= w <= w1 and v6.is_game(ln))


def seasons_of(hist, k):
    return sorted({s for (s, _w), ln in hist.get(k, []) if v6.is_game(ln)})


def build(W, chains):
    ch = chains["primary"]
    anchors = EV.anchor_lists(W, chains)
    ctx = W.ctx
    return ch, anchors, ctx


def player_block(W, chains, ch, anchors, k):
    ctx = W.ctx
    nat = W.wk.natives
    out = {"key": k, "name": ctx["name_of"].get(k), "pos": ctx["pos_of"].get(k), "team": ctx["team"].get(k),
           "history_seasons": seasons_of(W.hist, k), "games_2026_w1_9": games_2026(W.hist, k, 1, 9),
           "games_2026_w7_9": games_2026(W.hist, k, 7, 9), "published": {}, "adjusted_unchanged": {},
           "adjusted_v6": {}, "ddf": {}, "metric": {}, "band": {}, "lines": {}, "share": {}}
    for c in ("fantasycalc", "fantasypros", "cbs", "usatoday"):
        out["published"][c] = {s: nat[c][s].get(k) for s in mx.SCORINGS}
    for s in mx.SCORINGS:
        new, cur = W.metric(ch, s)
        out["metric"][s], out["ddf"][s] = new.get(k), cur.get(k)
        vs = [anchors[n][s][0].get(k) for n in EV.ANCHOR_PAIRS]
        vs = [v for v in vs if v is not None]
        out["band"][s] = (min(vs), max(vs)) if vs else None
        out["adjusted_unchanged"][s] = {c: W.unchanged(ch, c, s).get(k) for c in ("fantasycalc", "fantasypros", "cbs", "usatoday")}
        out["adjusted_v6"][s] = {c: W.av5(ch, c, "v5", s).get(k) for c in v6.CHARTS}
    for c in v6.CHARTS:
        u = ch["U"][c]
        rec = u.records.get(k)
        if rec is None or (c, "v5") not in ch["P"] or k not in ch["P"][(c, "v5")]:
            out["lines"][c] = {"label": None if rec is None else rec["label"], "A0": None if rec is None else rec.get("A")}
            continue
        P0, m = ch["P"][(c, "v5")][k]
        line = v6.assumed_line(P0, m)
        info = W.info.get((u.s0, k), {})
        out["lines"][c] = {"label": ch["labels"][(c, "v5")][k], "anchor": u.s0, "A0": rec["A"], "P0": P0,
                           "line_per_game": line, "points": {s: mx.F(line, s) for s in mx.SCORINGS},
                           "share": info}
        ref = W.refs.ref_mix(k, u.s0)
        out["lines"][c]["proj_share"] = None if ref is None else ref["rec"]
    e = W.refs.espn.get(k)
    out["espn_ros_line"] = e
    return out


def candidates(W, ch):
    ctx = W.ctx
    new, cur = W.metric(ch, "half_ppr")
    rows = []
    for k, v in cur.items():
        p = ctx["pos_of"].get(k)
        if not v or p not in v6.POSITIONS:
            continue
        rows.append((p, -v, k))
    rows.sort()
    by = {}
    for p, nv, k in rows:
        by.setdefault(p, []).append(k)
    lo, hi = W.metric(ch, "standard"), W.metric(ch, "ppr")
    for p, ks in by.items():
        print("==", p)
        for k in ks[:40]:
            info = W.info.get(("half_ppr", k)) or W.info.get(("ppr", k)) or {}
            print(f"  {k:>6} {ctx['name_of'].get(k)!s:24} ddf {cur[k]:6.1f}  std {lo[0][k] - lo[1][k]:+6.2f} "
                  f"ppr {hi[0][k] - hi[1][k]:+6.2f}  n {info.get('n')} q {info.get('q') and round(info['q'], 3)} "
                  f"hist {info.get('q_hist') and round(info['q_hist'], 3)} seasons {seasons_of(W.hist, k)} "
                  f"g2026 {games_2026(W.hist, k, 1, 9)} g7-9 {games_2026(W.hist, k, 7, 9)}")


def main():
    ctx, Ws = v6.load((W10,))
    W = Ws[0]
    chains = {"primary": W.chain(), "fc_half": W.chain(anchor="fc_half", kinds=("v5",)),
              "fp_full": W.chain(anchor="fp_full", kinds=("v5",))}
    ch = chains["primary"]
    if "--list" in sys.argv:
        candidates(W, ch)
        return
    anchors = EV.anchor_lists(W, chains)
    names = {v: k for k, v in ctx["name_of"].items()}
    out = []
    for name, why in EXAMPLES:
        k = names[name]
        b = player_block(W, chains, ch, anchors, k)
        b["why_chosen"] = why
        out.append(b)
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "examples.json").write_text(json.dumps(EV.jsonable(out), indent=1))
    print("wrote", len(out))


if __name__ == "__main__":
    main()
