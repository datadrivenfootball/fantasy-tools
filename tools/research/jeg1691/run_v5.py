"""JEG-1691 v5 runner.

  python3 tools/research/jeg1691/run_v5.py --weeks 5 6 7                 # dev: debug only
  python3 tools/research/jeg1691/run_v5.py --weeks 8 9 10 --decisive <sha>  # the one decisive run
  python3 tools/research/jeg1691/run_v5.py --weeks 11 12 13 14 --replication <sha>  # later, non-blocking

Guards (preregistration 3.1): weeks 8-10 run only with --decisive equal to the checked-out
HEAD and a clean tree under tools/research/jeg1691 and docs/research/jeg1691, and only
once (out/decisive/ must not exist). T1's test origins run only in decisive mode. Dev mode
runs the step 5 selection (selection origins only) and the chart chain on weeks 5-7, and
freezes the T6 widening from those weeks.
Out: tools/research/jeg1691/out/<mode>/{selection,battery,sensitivity,t1,verdict}.json
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

import history5 as h5  # noqa: E402
import t1 as T1  # noqa: E402
import tests5 as TS  # noqa: E402
import v5  # noqa: E402

DEV, DECISIVE, REPLICATION = {5, 6, 7}, {8, 9, 10}, {11, 12, 13, 14}
OUT = HERE / "out"
SENSITIVITY = (("S-FC-Half", "fc_half", ()), ("S-FP-Full", "fp_full", ()),
               ("S-drop-ESPN", "primary", ("espn",)), ("S-drop-CBSROS", "primary", ("cbsros",)),
               ("S-drop-RZ", "primary", ("razzball",)))


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    if isinstance(x, float):
        return round(x, 6)
    return x


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=True).stdout.strip()


def guard(args):
    weeks = set(args.weeks)
    if weeks <= DEV and not args.decisive and not args.replication:
        return "dev"
    mode = "decisive" if weeks <= DECISIVE else "replication" if weeks <= REPLICATION else None
    sha = args.decisive if mode == "decisive" else args.replication
    if mode is None or not sha:
        sys.exit(f"weeks {sorted(weeks)}: dev is {sorted(DEV)}; {sorted(DECISIVE)} needs --decisive <sha>; "
                 f"{sorted(REPLICATION)} needs --replication <sha>")
    if git("rev-parse", "HEAD") != git("rev-parse", sha):
        sys.exit("HEAD is not the registered commit")
    if git("status", "--porcelain", "tools/research/jeg1691", "docs/research/jeg1691").replace(
            "?? tools/research/jeg1691/out/", "").strip():
        sys.exit("tree not clean under the registered paths")
    if mode == "decisive" and (OUT / "decisive").exists():
        sys.exit("the decisive run already exists; it runs once")
    return mode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, nargs="+", required=True)
    ap.add_argument("--decisive")
    ap.add_argument("--replication")
    ap.add_argument("--no-sensitivity", action="store_true")
    ap.add_argument("--quick", action="store_true", help="dev only: 50 bootstrap draws and shuffles")
    args = ap.parse_args()
    mode = guard(args)
    if args.quick and mode != "dev":
        sys.exit("--quick is dev only")
    nb, ns = (50, 50) if args.quick else (TS.st.N_BOOT, TS.st.N_SHUFFLE)
    out = OUT / mode
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    H = h5.load()
    ctx = v5.R3.load_world()
    sel = T1.select(H["by_player"], ctx["pos_of"])
    (out / "selection.json").write_text(json.dumps(jsonable({"selection": sel, "history": {
        "meta": H["meta"], "players": len(H["by_player"]), "unkeyed_rows_with_stats": H["unkeyed_rows_with_stats"],
        "qualifying_2026_weeks": h5.qualifying_2026_weeks(H["nonzero_rows"])}}), indent=1))
    weeks = [v5.Week5(ctx, w, sel, H["by_player"]) for w in sorted(args.weeks)]
    widening_path = OUT / "t6_widening.json"
    widening = json.loads(widening_path.read_text()) if widening_path.exists() else None
    chains = {W.w: W.chain(kinds=("v5", "k0", "kinf", "v4share")) for W in weeks}
    bat = TS.battery(weeks, chains, nb, ns, widening)
    if mode == "dev":
        import statistics
        wd = {}
        for r in ("WR/RB", "TE/RB"):
            # ESPN's own moves do not depend on the chart; read them from the first chart's block
            per_week = bat["T6"][v5.CHARTS5[0]][r]["espn_per_week"]
            wd[r] = statistics.stdev([x for x in per_week if x is not None]) if len(per_week) >= 2 else None
        widening_path.write_text(json.dumps({**wd, "_from_weeks": sorted(args.weeks),
                                             "_rule": "week-to-week SD of ESPN's own Standard-to-Full log level moves, dev weeks"}, indent=1))
    (out / "battery.json").write_text(json.dumps(jsonable(bat), indent=1))
    sens = {}
    if not args.no_sensitivity:
        for kind in ("k0", "kinf", "v4share"):
            sens[f"V-mix-{kind}"] = {c: {"T4": TS.corr_sd(TS.moves_week(W, chains[W.w], c, kind))[0]}
                                     for W in weeks for c in chains[W.w]["U"]}
        for name, anchor, drop in SENSITIVITY:
            chs = {W.w: W.chain(anchor=anchor, drop=drop) for W in weeks}
            sens[name] = TS.battery(weeks, chs, nb, ns, widening)
        (out / "sensitivity.json").write_text(json.dumps(jsonable(sens), indent=1))
    t1res = None
    if mode == "decisive":
        sel_int = T1.select(H["by_player"], ctx["pos_of"], cats=T1.mx.CATS_INT)
        t1res = T1.t1(H["by_player"], ctx["pos_of"], H["nonzero_rows"], sel, sel_int)
        (out / "t1.json").write_text(json.dumps(jsonable(t1res), indent=1))
    (out / "verdict.json").write_text(json.dumps(jsonable({"mode": mode, "weeks": sorted(args.weeks),
        "head": git("rev-parse", "HEAD"), "tier1": TS.verdict(bat, t1res),
        "seconds": round(time.time() - t0, 1), "quick": args.quick}), indent=1))
    print(f"{mode} run done in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
