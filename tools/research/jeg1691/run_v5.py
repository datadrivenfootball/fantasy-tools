"""JEG-1691 v5 runner.

  python3 tools/research/jeg1691/run_v5.py --weeks 5 6 7                      # dev: debug only
  python3 tools/research/jeg1691/run_v5.py --weeks 8 9 10 --decisive <sha>    # the one decisive run
  python3 tools/research/jeg1691/run_v5.py --weeks 11 12 13 14 --replication <sha>  # later, non-blocking

Guards for decisive and replication runs (preregistration 3.1, amendment 11):
- APPROVAL.json (committed, unmodified) names the reviewed commit; --decisive/--replication
  must equal it.
- The executed tree (MANIFEST_ROOTS: the pipeline, v4's lane code, the harness, its caches,
  the history, the inputs and the pre-registration) must be blob-for-blob identical to the
  reviewed commit, with no untracked file in it.
- Once only: refused if a lock exists in the worktree, in any commit of any ref, or in the
  record outside the repository (~/.local/state/jeg1691/). The lock is written before any
  week 8-10 value is computed; commit it with the outputs.
T1's test origins run only in decisive mode.
Out: tools/research/jeg1691/out/<mode>/{selection,battery,sensitivity,week10_only,t1,verdict}.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

import history5 as h5  # noqa: E402
import outcome as oc  # noqa: E402
import t1 as T1  # noqa: E402
import tests5 as TS  # noqa: E402
import v5  # noqa: E402

DEV, DECISIVE, REPLICATION = {5, 6, 7}, {8, 9, 10}, {11, 12, 13, 14}
OUT = HERE / "out"
APPROVAL = HERE / "APPROVAL.json"
LOCKS = {"decisive": HERE / "DECISIVE.lock", "replication": HERE / "REPLICATION.lock"}
STATE = Path(os.path.expanduser("~/.local/state/jeg1691"))
MANIFEST_ROOTS = ("pipelines", "config", "data/history", "data/inputs", "data/fixtures",
                  "tools/research/jeg1597", "tools/research/jeg1605", "tools/research/jeg1610",
                  "tools/research/jeg1611", "tools/research/jeg1691", "docs/research/jeg1691")
MANIFEST_EXCLUDE = ("tools/research/jeg1691/out/", "tools/research/jeg1691/APPROVAL.json",
                    "tools/research/jeg1691/DECISIVE.lock", "tools/research/jeg1691/REPLICATION.lock")
KEEP_IN_OUT = ("tools/research/jeg1691/out/t6_widening.json",)
# sensitivity runs (section 4); exclusions touch step 4 and the waiver pool only
SENS_CHAINS = (("S-FC-Half", "fc_half", ()), ("S-FP-Full", "fp_full", ()),
               ("S-noESPN-step4", "primary", ("espn",)), ("S-noCBSROS-step4", "primary", ("cbsros",)),
               ("S-noRZ-step4", "primary", ("razzball",)))
SENS_CHART_DROPS = ("fantasycalc", "fantasypros", "cbs", "usatoday")


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


def git(*a, check=True):
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=check).stdout.strip()


def in_manifest(path: str) -> bool:
    if path in KEEP_IN_OUT:
        return True
    return path.startswith(tuple(r + "/" for r in MANIFEST_ROOTS)) and not path.startswith(MANIFEST_EXCLUDE)


def tree_blobs(commit: str) -> dict:
    out = {}
    for line in git("ls-tree", "-r", commit, "--", *MANIFEST_ROOTS).splitlines():
        meta, path = line.split("\t", 1)
        if in_manifest(path):
            out[path] = meta.split()[2]
    return out


def worktree_problems(commit: str) -> list:
    """Paths where the worktree differs from `commit` inside the manifest."""
    want = tree_blobs(commit)
    probs = [p for p in git("ls-files", "--others", "--exclude-standard", "--", *MANIFEST_ROOTS).splitlines()
             if in_manifest(p)]
    for path, blob in want.items():
        f = REPO / path
        if not f.exists():
            probs.append(f"missing {path}")
        elif git("hash-object", str(f)) != blob:
            probs.append(f"changed {path}")
    return probs


def tree_id(commit: str) -> str:
    h = hashlib.sha256()
    for p, b in sorted(tree_blobs(commit).items()):
        h.update(f"{p}\0{b}\n".encode())
    return h.hexdigest()


def guard(args):
    weeks = set(args.weeks)
    if weeks <= DEV and not args.decisive and not args.replication:
        return "dev", None
    mode = "decisive" if weeks == DECISIVE else "replication" if weeks <= REPLICATION else None
    sha = args.decisive if mode == "decisive" else args.replication
    if mode is None or not sha:
        sys.exit(f"weeks {sorted(weeks)}: dev is {sorted(DEV)}; {sorted(DECISIVE)} (all three) needs "
                 f"--decisive <reviewed sha>; {sorted(REPLICATION)} needs --replication <reviewed sha>")
    if not APPROVAL.exists():
        sys.exit("no APPROVAL.json: the reviewed commit must be named in a committed approval file")
    rel = str(APPROVAL.relative_to(REPO))
    if not git("ls-files", rel) or git("status", "--porcelain", rel):
        sys.exit("APPROVAL.json must be committed and unmodified")
    appr = json.loads(APPROVAL.read_text(encoding="utf-8"))
    reviewed = git("rev-parse", appr["reviewed_commit"], check=False)
    if not reviewed or git("rev-parse", sha, check=False) != reviewed:
        sys.exit("the given sha is not the reviewed commit named in APPROVAL.json")
    probs = worktree_problems(reviewed)
    if probs:
        sys.exit("executed tree differs from the reviewed commit: " + "; ".join(probs[:10]))
    lock = LOCKS[mode]
    lrel = str(lock.relative_to(REPO))
    if lock.exists() or git("log", "--all", "--format=%H", "--", lrel) or (STATE / f"{mode}.json").exists():
        sys.exit(f"the {mode} run already happened (lock in the worktree, in git history or in {STATE})")
    record = {"mode": mode, "weeks": sorted(weeks), "reviewed_commit": reviewed, "tree_id": tree_id(reviewed),
              "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{mode}.json").write_text(json.dumps(record, indent=1))
    lock.write_text(json.dumps(record, indent=1))
    return mode, record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, nargs="+", required=True)
    ap.add_argument("--decisive")
    ap.add_argument("--replication")
    ap.add_argument("--no-sensitivity", action="store_true")
    ap.add_argument("--quick", action="store_true", help="dev only: 50 bootstrap draws and shuffles")
    args = ap.parse_args()
    if args.quick and (args.decisive or args.replication):
        sys.exit("--quick is dev only")
    mode, record = guard(args)
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
    if mode != "dev" and not widening_path.exists():
        sys.exit("t6_widening.json (frozen by the dev run) is missing")
    widening = json.loads(widening_path.read_text()) if widening_path.exists() else None
    chains = {W.w: W.chain(kinds=("v5", "k0", "kinf", "v4share")) for W in weeks}
    bat = TS.battery(weeks, chains, nb, ns, widening)
    if mode == "dev" and not widening_path.exists():
        import statistics
        wd = {}
        for r in ("WR/RB", "TE/RB"):
            # ESPN's own moves do not depend on the chart; read them from the first chart's block
            per_week = [x for x in bat["T6"][v5.CHARTS5[0]][r]["espn_per_week"] if x is not None]
            wd[r] = statistics.stdev(per_week) if len(per_week) >= 2 else None
        widening_path.write_text(json.dumps({**wd, "_from_weeks": sorted(args.weeks),
                                             "_rule": "week-to-week SD of ESPN's own Standard-to-Full log level moves, dev weeks"}, indent=1))
    (out / "battery.json").write_text(json.dumps(jsonable(bat), indent=1))
    sens = {}
    if not args.no_sensitivity:
        for name, anchor, exclude in SENS_CHAINS:
            chs = {W.w: W.chain(anchor=anchor, exclude=exclude) for W in weeks}
            sens[name] = TS.battery(weeks, chs, nb, ns, widening)
        for c in SENS_CHART_DROPS:
            sens[f"S-drop-{c}"] = TS.battery(weeks, chains, nb, ns, widening, drop_charts=(c,))
        if 10 in args.weeks and len(weeks) > 1:
            W10 = [W for W in weeks if W.w == 10]
            sens["W10-only (fresh Sleeper)"] = TS.battery(W10, chains, nb, ns, widening)
        mixv = {f"V-mix-{kind}": {c: TS.corr_sd(TS.moves_week(W, chains[W.w], c, kind))
                                  for W in weeks for c in chains[W.w]["U"]} for kind in ("k0", "kinf", "v4share")}
        (out / "sensitivity.json").write_text(json.dumps(jsonable({"batteries": sens, "mix_variants": mixv}), indent=1))
    t1res = None
    if mode == "decisive":
        sel_int = T1.select(H["by_player"], ctx["pos_of"], cats=T1.mx.CATS_INT)
        t1res = T1.t1(H["by_player"], ctx["pos_of"], H["nonzero_rows"], sel, sel_int)
        (out / "t1.json").write_text(json.dumps(jsonable(t1res), indent=1))
    decision = oc.decide(bat, sens, t1res) if not args.no_sensitivity else None
    (out / "verdict.json").write_text(json.dumps(jsonable({
        "mode": mode, "weeks": sorted(args.weeks), "head": git("rev-parse", "HEAD"), "record": record,
        "decision": decision, "note": None if mode == "decisive" else "not a decision: dev or replication run",
        "seconds": round(time.time() - t0, 1), "quick": args.quick}), indent=1))
    print(f"{mode} run done in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
