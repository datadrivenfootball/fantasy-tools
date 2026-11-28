#!/usr/bin/env python3
"""JEG-1735: turn a pull_ros_rankings snapshot into EDDF's compact ranker lists.

Research input builder. Reads a snapshot.json written by pipelines/pull_ros_rankings.py
(fantasypros_expert_ros rows), resolves names to player_key through the offline resolver
(tools/research/ros_rank_keys.py, no Supabase), and writes
docs/research/data/jeg1735/lists.json: {ranker_id: {scoring: {vintage, ranks: {pk: rank}}}}.
Rankers come from config/eddf_sources.json (`analyst` field matches the snapshot's analyst).
Usage: eddf_prepare.py <snapshot.json> [--out docs/research/data/jeg1735/lists.json]
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ros_rank_keys as K  # noqa: E402


def build(snap: dict, cfg: dict) -> dict:
    by_analyst = {r["analyst"]: r["id"] for r in cfg["rankers"] if r.get("analyst")}
    out: dict = {}
    for row in snap["rows"]:
        rid = by_analyst.get(row["analyst"])
        if rid is None:
            continue  # a ranker not in the registry is not read: adding one is a registry row
        lst = out.setdefault(rid, {}).setdefault(row["scoring"], {"vintage": row["source_vintage"], "ranks": {}})
        pk = K.pk(row["player_name"], row["pos"], f"{rid}:{row['scoring']}")
        if pk is not None and str(pk) not in lst["ranks"]:
            lst["ranks"][str(pk)] = row["overall_rank"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--out", type=Path, default=REPO / "docs/research/data/jeg1735/lists.json")
    args = ap.parse_args(argv)
    cfg = json.loads((REPO / "config/eddf_sources.json").read_text())
    lists = build(json.loads(args.snapshot.read_text()), cfg)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(lists, separators=(",", ":"), sort_keys=True))
    rep = K.join_report()
    miss = sum(len(v["not_joined"]) for v in rep.values())
    print(f"{len(lists)} rankers, {sum(len(v) for v in lists.values())} lists, {miss} unjoined names -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
