"""JEG-1691 v5.1 backtest runner.

  <py> tools/research/jeg1691/v51/run_v51.py --mode dryrun
      Throwaway slice only: season 2015, k chosen on origin week 11 and evaluated on origin week 15
      (history from 2015 only). 2015 is never an evaluation season or selection fold of the
      registered backtest (only history), and weeks 11 and 15 are not registered origins. B5 is not run. No
      2017-2025 number is produced. Writes out51/dryrun/.
  <py> tools/research/jeg1691/v51/run_v51.py --mode backtest --approved <reviewed sha>
      The one registered backtest: primary plus every sensitivity run, always; writes
      out51/backtest/{battery,sensitivity,verdict}.json.

Guards for --mode backtest (carried from v5):
- v51/V51_APPROVAL.json (committed, unmodified) names the reviewed commit; --approved must equal it.
- The executed tree (MANIFEST_ROOTS) is blob-identical to the reviewed commit, with no untracked
  file in it.
- Once only: refused if v51/V51_BACKTEST.lock exists in the worktree or in any git ref, or the
  record ~/.local/state/jeg1691/v51-backtest.json exists. The lock is written before any number.
- No option that skips or shrinks anything is accepted (--n-boot, --n-shuffle and
  --no-sensitivity are dry-run only).
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
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))

import bt  # noqa: E402

OUT = HERE.parent / "out51"
APPROVAL = HERE / "V51_APPROVAL.json"
LOCK = HERE / "V51_BACKTEST.lock"
STATE = Path(os.path.expanduser("~/.local/state/jeg1691")) / "v51-backtest.json"
MANIFEST_ROOTS = ("data/inputs", "data/fixtures/current", "tools/research/jeg1691", "docs/research/jeg1691")
MANIFEST_EXCLUDE = ("tools/research/jeg1691/out51/", "tools/research/jeg1691/v51/V51_APPROVAL.json",
                    "tools/research/jeg1691/v51/V51_BACKTEST.lock")
DRY = replace(bt.PRIMARY, name="dryrun-2015", eval_seasons=(2015,), sel_start=2015, origins=(11, 15),
              dry_sel_origins=(11,), b1_needed=1, b5=False)


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
    return path.startswith(tuple(r + "/" for r in MANIFEST_ROOTS)) and not path.startswith(MANIFEST_EXCLUDE)


def tree_blobs(commit: str) -> dict:
    out = {}
    for line in git("ls-tree", "-r", commit, "--", *MANIFEST_ROOTS).splitlines():
        meta, path = line.split("\t", 1)
        if in_manifest(path):
            out[path] = meta.split()[2]
    return out


def worktree_problems(commit: str) -> list:
    probs = [f"untracked {p}" for p in git("ls-files", "--others", "--exclude-standard", "--",
                                           *MANIFEST_ROOTS).splitlines() if in_manifest(p)]
    for path, blob in tree_blobs(commit).items():
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
    if args.mode == "dryrun":
        return None
    if args.n_boot is not None or args.n_shuffle is not None or args.no_sensitivity:
        sys.exit("--n-boot, --n-shuffle and --no-sensitivity are dry-run only")
    if not args.approved:
        sys.exit("--mode backtest needs --approved <reviewed sha>")
    if not APPROVAL.exists():
        sys.exit("no V51_APPROVAL.json: the reviewed commit must be named in a committed approval file")
    rel = str(APPROVAL.relative_to(REPO))
    if not git("ls-files", rel) or git("status", "--porcelain", rel):
        sys.exit("V51_APPROVAL.json must be committed and unmodified")
    reviewed = git("rev-parse", json.loads(APPROVAL.read_text(encoding="utf-8"))["reviewed_commit"], check=False)
    if not reviewed or git("rev-parse", args.approved, check=False) != reviewed:
        sys.exit("--approved is not the reviewed commit named in V51_APPROVAL.json")
    probs = worktree_problems(reviewed)
    if probs:
        sys.exit("executed tree differs from the reviewed commit: " + "; ".join(probs[:10]))
    lrel = str(LOCK.relative_to(REPO))
    if LOCK.exists() or git("log", "--all", "--format=%H", "--", lrel) or STATE.exists():
        sys.exit("the v5.1 backtest already ran (lock in the worktree, in git history or in " + str(STATE) + ")")
    record = {"mode": "backtest", "reviewed_commit": reviewed, "tree_id": tree_id(reviewed),
              "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(record, indent=1))
    LOCK.write_text(json.dumps(record, indent=1))
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("dryrun", "backtest"), required=True)
    ap.add_argument("--approved")
    ap.add_argument("--n-boot", type=int)
    ap.add_argument("--n-shuffle", type=int)
    ap.add_argument("--no-sensitivity", action="store_true")
    args = ap.parse_args()
    record = guard(args)
    t0 = time.time()
    nb = args.n_boot if args.n_boot is not None else bt.N_BOOT
    ns = args.n_shuffle if args.n_shuffle is not None else bt.N_SHUFFLE
    players, integrity = bt.load_nflverse()
    v5p = bt.v5_params()
    out = OUT / args.mode
    out.mkdir(parents=True, exist_ok=True)
    if args.mode == "dryrun":
        primary = bt.battery(players, DRY, v5p, integrity, None, nb, ns)
        sens = {} if args.no_sensitivity else {
            n: bt.battery(players, replace(DRY, name=n, **kw), v5p, None, None, nb, ns)
            for n, kw in (("dry-anchor-Full", {"anchor": "ppr"}), ("dry-truth-ROS", {"truth": "ros"}))}
    else:
        pgs = {a: bt.load_pgs_twobucket(a) for a in ("half_ppr", "ppr")}
        primary = bt.battery(players, bt.PRIMARY, v5p, integrity, pgs["half_ppr"][0], nb, ns)
        primary["pgs_coverage"] = pgs["half_ppr"][1]
        sens = {c.name: bt.battery(players, c, v5p, None, pgs[c.anchor][0], nb, ns) for c in bt.SENSITIVITIES}
    decision = bt.decide(primary, sens)
    (out / "battery.json").write_text(json.dumps(jsonable(primary), indent=1, default=str))
    (out / "sensitivity.json").write_text(json.dumps(jsonable(sens), indent=1, default=str))
    (out / "verdict.json").write_text(json.dumps(jsonable({
        "mode": args.mode, "head": git("rev-parse", "HEAD"), "record": record,
        "decision": decision if args.mode == "backtest" else {"note": "dry run on a throwaway slice: not a decision",
                                                                "code_path_outcome": decision["outcome"]},
        "n_boot": nb, "n_shuffle": ns, "seconds": round(time.time() - t0, 1)}), indent=1))
    print(f"{args.mode} done in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
