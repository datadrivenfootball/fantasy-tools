"""JEG-1691 v5: the granular references (ESPN and Sleeper stat lines) per chart week.

Pairing (preregistration 2.1, amendment 3), all strictly no later than the week's DDF
ESPN snapshot, so nothing comes from a later vintage:
- ESPN, primary: data/inputs/espn_projections.csv at the commit DDF used for the week
  (its espn_snapshot_date equals the history snapshot's ESPN snapshot_date), seven
  categories, ROS over the CSV's weeks_covered.
- ESPN, cross-check (weeks 7-10): cache/espn_captures_ros.json, receptions only
  (full_ppr - standard points), target weeks w+1..18, latest batch before the snapshot.
- Sleeper, weeks 5-9: data/inputs/weekly_projections_sleeper.csv.gz (one vintage,
  2026-10-08/10; points only, receptions = ppr - std), the same target weeks as ESPN.
- Sleeper, week 10: cache/sleeper_ros_week10.json (warehouse run of 2026-11-16, full
  stat dict), target weeks 11-18.
A mix here is per anchor point: seven categories (ESPN CSV, Sleeper week 10) or two
buckets (receptions, other points) for points-only sources.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import re
import subprocess
from pathlib import Path

import mix as mx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CACHE = HERE / "cache"
SLEEPER_CSV = REPO / "data" / "inputs" / "weekly_projections_sleeper.csv.gz"
IDMAP = REPO / "data" / "inputs" / "sleeper_projection_idmap.csv"

# content week -> commit of data/inputs/espn_projections.csv DDF used (snapshot date)
ESPN_COMMITS = {5: ("71b5f891d", "2026-10-12"), 6: ("e5b571f78", "2026-10-19"),
                7: ("693c0ca4a", "2026-10-25"), 8: ("8a3855823", "2026-10-31"),
                9: ("284b7efac", "2026-11-09"), 10: ("24b3a6519", "2026-11-16")}
ESPN_COLS = {"r_pass_yds": "pass_yds", "r_pass_tds": "pass_td", "r_rush_yds": "rush_yds",
             "r_rush_tds": "rush_td", "r_receptions": "rec", "r_rec_yds": "rec_yds",
             "r_rec_tds": "rec_td"}
SLEEPER_KEYS = {"pass_yds": "pass_yds", "pass_td": "pass_td", "rush_yds": "rush_yds",
                "rush_td": "rush_td", "rec": "rec", "rec_yds": "rec_yds", "rec_td": "rec_td"}
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_name(s: str) -> str:
    s = re.sub(r"[^a-z ]", "", (s or "").lower().replace("-", " "))
    return " ".join(_SUFFIX.sub("", s).split())


def name_index(name_of: dict, pos_of: dict) -> dict:
    idx = {}
    for k, n in name_of.items():
        idx.setdefault((norm_name(n), pos_of.get(k)), []).append(k)
    return {kk: v[0] for kk, v in idx.items() if len(v) == 1}


def espn_csv_text(commit: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:data/inputs/espn_projections.csv"],
                          check=True, capture_output=True, text=True).stdout


def espn_lines(w: int, name_of: dict, pos_of: dict) -> dict:
    """{key: seven-category ROS line}, plus meta (window, unmatched)."""
    commit, snap = ESPN_COMMITS[w]
    idx = name_index(name_of, pos_of)
    out, unmatched, window = {}, 0, None
    rows = list(csv.DictReader(io.StringIO(espn_csv_text(commit))))
    for r in rows:
        if (r.get("eligible") or "").strip().lower() not in ("1", "true", "yes", "y"):
            continue
        window = r.get("weeks_covered") or window
        k = idx.get((norm_name(r.get("player")), (r.get("pos") or "").strip()))
        if k is None:
            unmatched += 1
            continue
        out[k] = {c: float(r.get(col) or 0.0) for col, c in ESPN_COLS.items()}
    snap_max = max((r.get("espn_snapshot_date") or "") for r in rows)
    return {"lines": out, "meta": {"commit": commit, "snapshot": snap_max, "expected_snapshot": snap,
                                   "weeks_covered": window, "unmatched": unmatched}}


def window_of(espn_meta: dict) -> tuple:
    a, b = espn_meta["weeks_covered"].split("-")
    return int(a), int(b)


def sleeper_csv(weeks: tuple) -> dict:
    """{key: {"std":, "half":, "ppr":, "n_weeks":}} summed over target weeks (2026)."""
    idm = {}
    with IDMAP.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("player_key") or "").isdigit():
                idm[r["sleeper_id"]] = int(r["player_key"])
    out = {}
    with gzip.open(SLEEPER_CSV, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["season"] != "2026" or not (weeks[0] <= int(r["week"]) <= weeks[1]):
                continue
            k = idm.get(r["sleeper_id"])
            if k is None:
                continue
            ppr = float(r["pts_ppr"] or 0)
            a = out.setdefault(k, {"std": 0.0, "half": 0.0, "ppr": 0.0, "n_weeks": 0})
            a["std"] += float(r["pts_std"] or 0)
            a["half"] += float(r["pts_half_ppr"] or 0)
            a["ppr"] += ppr
            a["n_weeks"] += ppr > 0
    return out


def sleeper_week10() -> dict:
    d = json.loads((CACHE / "sleeper_ros_week10.json").read_text(encoding="utf-8"))
    out = {}
    for k, v in d["players"].items():
        out[int(k)] = {"std": float(v["points_std"]), "half": float(v["points_half_ppr"]),
                       "ppr": float(v["points_ppr"]), "n_weeks": int(v["n_weeks"]), "line": {c: float(v[src]) for src, c in SLEEPER_KEYS.items()}}
    return out


def espn_captures(w: int) -> dict:
    d = json.loads((CACHE / "espn_captures_ros.json").read_text(encoding="utf-8"))
    wk = d["players"].get(f"w{w}")
    if wk is None:
        return {}
    return {int(k): {"std": float(v[0]), "half": float(v[1]), "ppr": float(v[2]), "n_weeks": int(v[3])}
            for k, v in wk.items() if None not in v[:4]}


class Refs:
    """The week's references: mixes at an anchor, and per-game points for own-list pricing."""

    def __init__(self, w: int, name_of: dict, pos_of: dict):
        self.w = w
        e = espn_lines(w, name_of, pos_of)
        self.espn, self.espn_meta = e["lines"], e["meta"]
        self.window = window_of(self.espn_meta)
        self.sleeper = sleeper_week10() if w == 10 else sleeper_csv(self.window)
        self.sleeper_source = "warehouse_2026-11-16" if w == 10 else "csv_vintage_2026-10-08"
        self.captures = espn_captures(w)

    def espn_mix(self, k, s0):
        ln = self.espn.get(k)
        if ln is None or not mx.F(ln, s0) > 0:
            return None
        return mx.normalise(ln, s0)

    def sleeper_mix(self, k, s0):
        v = self.sleeper.get(k)
        if v is None:
            return None
        if "line" in v and mx.F(v["line"], s0) > 0:
            return mx.normalise(v["line"], s0)
        return mx.two_bucket_mix(v["ppr"] - v["std"], v["std"], s0)

    def capture_mix(self, k, s0):
        v = self.captures.get(k)
        return None if v is None else mx.two_bucket_mix(v["ppr"] - v["std"], v["std"], s0)

    def ref_mix(self, k, s0):
        """ESPN+Sleeper mean as a two-bucket mix: receptions per anchor point = mean of the
        two; None unless both exist."""
        a, b = self.espn_mix(k, s0), self.sleeper_mix(k, s0)
        if a is None or b is None:
            return None
        q = 0.5 * (a["rec"] + b["rec"])
        return {"rec": q, "other": 1.0 - mx.REC_W[s0] * q}

    def sleeper_ppg(self, s):
        """Sleeper's own list as per-game natives at s (ROS points / projected weeks)."""
        f = {"standard": "std", "half_ppr": "half", "ppr": "ppr"}[s]
        return {k: v[f] / v["n_weeks"] for k, v in self.sleeper.items() if v["n_weeks"] > 0 and v[f] > 0}
