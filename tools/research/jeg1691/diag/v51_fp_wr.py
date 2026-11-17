"""JEG-1691 v5.1 diagnosis (dev weeks 5-7 only, read-only): why FantasyPros WR moves are small.

Prints per chart, week and position: the common set size, the SD of receptions per anchor point
for the v5 mix and the reference mix, their correlation, the SD of the Standard-to-Full percentile
moves for v5, the reference-mix rebuild and the position-mix rebuild (kinf: level-only), the share
of exact ties in the chart's Adjusted at the anchor, and the spread of P_i(s0).
Never loads weeks 8+ (DEV only).
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import history5 as h5  # noqa: E402
import stats5 as st  # noqa: E402
import t1 as T1  # noqa: E402
import tests5 as TS  # noqa: E402
import v5  # noqa: E402

DEV = (5, 6, 7)


def main():
    H = h5.load()
    ctx = v5.R3.load_world()
    sel = T1.select(H["by_player"], ctx["pos_of"])
    print("WR selection", sel["WR"]["t"], sel["WR"]["k"]["rec"], "RB", sel["RB"]["t"], sel["RB"]["k"]["rec"],
          "TE", sel["TE"]["t"], sel["TE"]["k"]["rec"])
    for w in DEV:
        W = v5.Week5(ctx, w, sel, H["by_player"])
        for anchor in ("primary", "fc_half", "fp_full"):
            ch = W.chain(anchor=anchor, kinds=("v5", "kinf", "k0"))
            for c in v5.CHARTS5:
                u = ch["U"][c]
                keys = TS.common_set(W, ch, c)
                lo = {k: W.chart_list(ch, c, k, "standard") for k in ("v5", "ref", "kinf", "k0")}
                hi = {k: W.chart_list(ch, c, k, "ppr") for k in ("v5", "ref", "kinf", "k0")}
                for p in ("RB", "WR", "TE"):
                    ks = [k for k in keys if ctx["pos_of"][k] == p]
                    if len(ks) < 5:
                        continue
                    qv = [ch["P"][(c, "v5")][k][1]["rec"] for k in ks]
                    q0 = [ch["P"][(c, "k0")][k][1]["rec"] for k in ks]
                    qr = [W.refs.ref_mix(k, u.s0)["rec"] for k in ks]
                    sdm = {k: st.sd(list(st.moves(lo[k], hi[k], ks).values())) for k in lo}
                    A = [u.records[k]["A"] for k in ks]
                    P0 = [u.records[k]["P0"] for k in ks]
                    ties = 1 - len(set(A)) / len(A)
                    print(f"w{w} {anchor:7s} {c:11s} {p} n={len(ks):3d} sd_q v5={st.sd(qv):.4f} raw={st.sd(q0):.4f} "
                          f"ref={st.sd(qr):.4f} corr(q_v5,q_ref)={st.pearson(qv, qr):.2f} | sd_move v5={sdm['v5']:.4f} "
                          f"ref={sdm['ref']:.4f} kinf={sdm['kinf']:.4f} raw={sdm['k0']:.4f} | ties(A)={ties:.2f} "
                          f"P0 sd={statistics.pstdev(P0):.2f} range={min(P0):.1f}-{max(P0):.1f}")


if __name__ == "__main__":
    main()
