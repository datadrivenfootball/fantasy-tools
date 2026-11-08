#!/usr/bin/env python3
"""Build the values explainer: one self-contained HTML page showing how every
source's values are made, with the chart engine's own numbers.

    python3 pipelines/build_values_explainer.py [--out output/values-explainer/index.html]
    make values-explainer

Steps:
  1. `make sync`'s builder regenerates dist/ from app/ and the fixtures.
  2. dist/ is served locally and the chart engine is loaded headless
     (Playwright Chromium, hermetic: no outside hosts).
  3. app/values-explainer/extract.js reads the engine through its read-only
     accessors at the default setting (12 teams, Full PPR, standard roster),
     in all three views, plus a few other settings for the sensitivity table.
  4. The bundle is trimmed, stamped with the commit, build tag, logic-file
     hashes and the open math-review items, and written into
     app/values-explainer/template.html.

Nothing here computes a chart value. Every number on the page is the engine's
(value-pipeline/2, docs/methodology.md "Value Pipeline"), except labelled sums
and ratios. The builder checks that the per-source numbers it shows land on
the values the chart draws, and the page reports the result.

The narrative in the template was written against the logic files listed in
app/values-explainer/reviewed.json. When their hashes no longer match, the page
says which files changed so the explanation gets re-checked (CLAUDE.md,
"Values explainer").
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import math
import os
import re
import socketserver
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP = ROOT / "app" / "values-explainer"
DEFAULT_OUT = ROOT / "output" / "values-explainer" / "index.html"
PAGE = "modules/math-inspector.html"
HERMETIC_ARGS = ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"]

# The files whose logic the page explains. A hash change here flags the
# narrative for review.
LOGIC_FILES = [
    "app/trade-value-chart/assets/value-model.js",
    "app/trade-value-chart/assets/curve-widget.js",
    "pipelines/value_reference.py",
    "pipelines/spec_reference/value_pipeline.py",
    "docs/methodology.md",
]
SETTINGS = [["ppr", 8], ["ppr", 10], ["ppr", 12], ["ppr", 14], ["half_ppr", 12], ["standard", 12]]
POS = ("QB", "RB", "WR", "TE")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def build_tag() -> str:
    for p in (DIST / "index.html", DIST / "modules" / "status.html"):
        if p.exists():
            m = re.search(r"tv-\d{8}-\d{4}-[0-9a-f]{7}", p.read_text(errors="ignore"))
            if m:
                return m.group(0)
    return ""


def math_review_items() -> list[dict]:
    path = ROOT / "docs" / "math-review-agenda.md"
    if not path.exists():
        return []
    items = []
    for m in re.finditer(r"^## (MR-\d+) - (.+)$", path.read_text(), re.M):
        items.append({"id": m.group(1), "title": m.group(2).strip()})
    return items


# Read after extract.js has put the page back at the default setting (JEG-1393):
#  - each DDF Value version's composite inputs and display series, so the page
#    can say which sources a version holds back (inputs minus series);
#  - each source's raw surplus total and value-above-waivers factor in every
#    allocation of the fractional-seat mix, so the page can show the division
#    that is true per allocation (the final factor is their weighted average,
#    not pie / the averaged surplus). Read-only: runPipelineWith reruns the
#    engine on the page's own natives and changes nothing on the page.
EXTRA_JS = """() => {
  const C = window.TradeValueCurveControls, H = window.TradeValueCurveHarness;
  const clone = x => JSON.parse(JSON.stringify(x ?? null));
  const versions = {};
  for (const v of ["ddf_value", "ddf_value_charts", "ddf_value_projections"]) {
    try { versions[v] = clone(C.getCompositeInputs(v)); } catch (e) { versions[v] = null; }
  }
  let runs = null;
  try {
    const mix = (H && H.pipeline && H.pipeline().allocationMix) || [];
    if (mix.length > 1) {
      runs = mix.map(m => {
        const res = H.runPipelineWith({seatAllocation: m.allocation});
        const src = {};
        Object.entries(res.sources || {}).forEach(([k, s]) => { src[k] = [s.surplusTotal, s.vorpFactor]; });
        return {weight: m.weight, sources: src};
      });
    }
  } catch (e) { runs = null; }
  // JEG-1393 R3 (OP-02): the heaviest allocation's own run, per source and
  // position: the lines, n and q, the bench bands and each player's parts, so
  // the page can rebuild one player's fill-in part for one allocation.
  let heavy = null;
  try {
    const pl = H && H.pipeline && H.pipeline();
    const mix = (pl && pl.allocationMix) || [];
    let hi = 0;
    mix.forEach((m, j) => { if (m.weight > mix[hi].weight) hi = j; });
    const res = mix.length > 1 ? H.runPipelineWith({seatAllocation: mix[hi].allocation}) : pl;
    const sources = {};
    Object.entries((res && res.sources) || {}).forEach(([k, s]) => {
      const positions = {};
      Object.entries(s.positions || {}).forEach(([p, x]) => {
        const l = x.lineup || null;
        positions[p] = {starters: x.starters, rostered: x.rostered, waiver: x.waiver, starterLine: x.starterLine,
          avail: x.avail, lineup: l && {m: l.m, unavailable: l.unavailable, nPerTeam: l.nPerTeam,
                                        sigmaRel: l.sigmaRel, sigmaFloor: l.sigmaFloor},
          bands: (x.bands || []).map(b => [b.depth, b.lo, b.hi, b.fill])};
      });
      const players = {};
      Object.entries(s.players || {}).forEach(([pk, q]) => { players[pk] = [q.native, q.benchSlice, q.starterSlice]; });
      sources[k] = {positions, players};
    });
    heavy = {weight: mix.length ? mix[hi].weight : 1, sources};
  } catch (e) { heavy = null; }
  return {compositeByVersion: versions, vorpRuns: runs, heavyRun: heavy};
}"""
VERSION_OF = {"ddf_value": "blended", "ddf_value_charts": "charts", "ddf_value_projections": "projections"}
RUN_TOL = 1e-6  # relative: the weighted per-allocation factors must give the engine's factor


def vorp_runs(raw: dict) -> dict:
    """Per source: [[weight, raw surplus total, factor], ...] across the
    allocation mix, kept only when the weighted factors reproduce the
    engine's blended factor (else the page falls back to saying it is a blend)."""
    runs = (raw.get("extra") or {}).get("vorpRuns") or []
    vp_sources = raw["inspection"]["valuePipeline"]["sources"]
    out = {}
    if len(runs) < 2:
        return out
    tot = sum(run["weight"] for run in runs)
    for k, s in vp_sources.items():
        rows = [[run["weight"], *((run["sources"].get(k) or [None, None])[:2])] for run in runs]
        if any(x[1] is None or x[2] is None for x in rows):
            continue
        blended = sum(w * f for w, _, f in rows) / tot
        target = s.get("vorpFactor") or 0
        if target and abs(blended - target) <= RUN_TOL * abs(target):
            out[k] = [[r(w / tot, 6), r(st, 6), r(f, 9)] for w, st, f in rows]
    return out


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def band_fill(x: float, s: float, waiver: float, avail: float, bands: list) -> float:
    """The fill-in part of one player in one allocation (value-model.js
    esPositionParts): avail x v x sum over bands of P(>= depth of the team's
    starters out) x P(level in band). Used only to check the page's worked
    example against the engine's own number."""
    v = max(0.0, x - waiver)
    tot = 0.0
    for _depth, lo, hi, fill in bands:
        if hi <= lo:
            continue
        if s <= 0:
            p = 1.0 if lo < x <= hi else 0.0
        else:
            p = _phi((hi - x) / s) - _phi((lo - x) / s)
        tot += fill * p
    return avail * v * tot


def heavy_run(raw: dict) -> dict | None:
    """The heaviest allocation's run for one example trade chart (FantasyCalc
    when it is included and not hidden, else the first such chart): per
    position its lines, n, q and bands, and each player's [native, fill-in,
    start-worthy]. `check` is the worst gap between the band arithmetic and
    the engine's fill-in part over that chart's players."""
    hr = (raw.get("extra") or {}).get("heavyRun") or {}
    vp = raw["inspection"]["valuePipeline"]
    srcs = hr.get("sources") or {}
    hidden = {h["key"] for h in hidden_sources(raw)}
    charts = [k for k, s in (vp.get("sources") or {}).items()
              if s.get("family") == "chart" and s.get("included") and k not in hidden and k in srcs]
    if not charts:
        return None
    key = "fantasycalc" if "fantasycalc" in charts else charts[0]
    s = srcs[key]
    positions, worst = {}, 0.0
    for p, x in (s.get("positions") or {}).items():
        l = x.get("lineup") or {}
        bands = [b for b in (x.get("bands") or []) if isinstance(b, list) and len(b) == 4]
        positions[p] = {"starters": x.get("starters"), "rostered": x.get("rostered"), "waiver": x.get("waiver"),
                        "starterLine": x.get("starterLine"), "avail": x.get("avail"),
                        "n": l.get("nPerTeam"), "q": l.get("unavailable"), "sigmaRel": l.get("sigmaRel"),
                        "sigmaFloor": l.get("sigmaFloor"), "bands": bands}
    players = {}
    for pk, row in (s.get("players") or {}).items():
        nat, fill, start = (list(row) + [None, None, None])[:3]
        if not all(isinstance(v, (int, float)) for v in (nat, fill, start)):
            continue
        players[pk] = [r(nat, 4), r(fill, 4), r(start, 4)]
    pos_of = {pk: (raw["inspection"]["rows"].get(pk) or {}).get("pos") for pk in players}
    for pk, (nat, fill, _start) in players.items():
        x = positions.get(pos_of.get(pk)) or {}
        if not x.get("bands") or not all(isinstance(x.get(f), (int, float)) for f in ("waiver", "avail", "sigmaRel")):
            continue
        sd = max(x["sigmaRel"] * nat, x.get("sigmaFloor") or 0) if nat > 0 else (x.get("sigmaFloor") or 0)
        worst = max(worst, abs(band_fill(nat, sd, x["waiver"], x["avail"], x["bands"]) - fill))
    return {"source": key, "weight": hr.get("weight"), "positions": positions, "players": players,
            "check": r(worst, 4)}


def hidden_sources(raw: dict) -> list[dict]:
    """The sources the engine runs (allocation, weights, pie) but leaves out of
    every DDF Value blend: red holds and divergence excludes (curve-widget.js
    eligibilityReason, `hidden: true`)."""
    keys = set(raw["inspection"]["valuePipeline"]["sources"])
    seen, out = set(), []
    for e in (raw.get("diagnostics") or {}).get("excluded") or []:
        if e.get("hidden") and e.get("key") in keys and e["key"] not in seen:
            seen.add(e["key"])
            out.append({"key": e["key"], "reason": e.get("reason"), "level": e.get("holdLevel")})
    return out


def version_sources(raw: dict) -> dict:
    """Per DDF Value version: the composite inputs, the display series and the
    sources that actually price at least one player (from the engine rows)."""
    comp = (raw.get("extra") or {}).get("compositeByVersion") or {}
    used = {v: set() for v in VERSION_OF.values()}
    for row in raw["inspection"]["rows"].values():
        for ver, b in (row.get("ddfByVersion") or {}).items():
            used.setdefault(ver, set()).update(b.get("sources") or [])
    out = {}
    for key, ver in VERSION_OF.items():
        c = comp.get(key) or {}
        out[ver] = {"inputs": c.get("inputs"), "series": c.get("series"), "used": sorted(used.get(ver, ()))}
    return out


def extract() -> dict:
    from playwright.sync_api import sync_playwright

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(DIST)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    script = (APP / "extract.js").read_text()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=HERMETIC_ARGS, executable_path=os.environ.get("CHROMIUM_PATH") or None)
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.goto(f"http://127.0.0.1:{port}/{PAGE}", wait_until="load")
            page.wait_for_function(
                "window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=120000)
            data = page.evaluate(script, {"settings": SETTINGS})
            data["extra"] = page.evaluate(EXTRA_JS)
            browser.close()
    finally:
        srv.shutdown()
    return data


def r(x, nd=3):
    return None if x is None else round(float(x), nd)


ROLE = {"starter": "s", "bench": "b", "waiver": "w"}
CHECK_TOL = 0.01  # the page's per-source arithmetic must land on the row values


def trim_estimate(e: dict) -> dict:
    out = {"path": e.get("path"), "raw": r(e.get("raw")), "cap": r(e.get("cap")),
           "capped": bool(e.get("capped")), "value": r(e.get("value"))}
    peers = {}
    for k, pe in (e.get("peers") or {}).items():
        peers[k] = {"usable": pe.get("usable"), "n": len(pe.get("fitPlayers") or []),
                    "ratio": r(pe.get("ratio"), 6), "estimate": r(pe.get("estimate"))}
    if peers:
        out["peers"] = peers
    c = e.get("curve")
    if c:
        out["curve"] = {"kind": c.get("kind"), "n": len(c.get("points") or []), "slope": r(c.get("slope"), 6),
                        "intercept": r(c.get("intercept"), 6), "meanPpg": r(c.get("meanPpg"))}
    return out


def trim_pipeline(vp: dict, full: bool = True) -> dict:
    sources = {}
    for k, s in (vp.get("sources") or {}).items():
        row = {f: s.get(f) for f in ("family", "included", "totalVorp", "surplusTotal", "groups", "weights", "starterMix",
                                       "benchMix", "rates", "unfundedGroups", "unfundedMoved",
                                       "vorpFactor", "indexedFactor")}
        if full:
            row["positions"] = {}
            for p, pp in (s.get("positions") or {}).items():
                row["positions"][p] = {**{f: pp.get(f) for f in ("method", "waiver", "starterLine", "starters",
                                                                 "rostered", "listed", "nEstimated", "avail")},
                                       "lineup": {f: (pp.get("lineup") or {}).get(f)
                                                  for f in ("m", "unavailable", "nPerTeam", "sigmaRel", "sigmaFloor")}
                                       if pp.get("lineup") else None,
                                       "estimates": {pk: trim_estimate(e) for pk, e in (pp.get("estimates") or {}).items()}}
        sources[k] = row
    return {f: vp.get(f) for f in ("version", "pie", "benchShare", "benchShareApplied", "included", "excluded",
                                   "degenerate", "ddfWeights", "allocation", "allocationMix",
                                   "allocationExpected", "seatSigma", "lineup", "chartSigma")} | {"sources": sources}


# JEG-1393 R2 (CX-03): the bench usage discount the engine applies when it
# shares bench seats with no league loaded (value-model.js vpVorpBenchDiscount,
# JEG-1121). Its constants are read from the engine source and must match the
# Python twin (roster_convention.vorp_bench_discount), so the page prints the
# numbers the engine uses.
def bench_discount() -> dict:
    src = (ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js").read_text()
    miss = re.search(r"var VORP_MISS = \{([^}]*)\}", src)
    bye = re.search(r"var VORP_BYE = ([0-9.]+) / ([0-9.]+);", src)
    if not miss or not bye:
        raise SystemExit("bench discount constants not found in value-model.js")
    miss_rate = {k: float(v) for k, v in re.findall(r"(QB|RB|WR|TE): ([0-9.]+)", miss.group(1))}
    bye_rate = float(bye.group(1)) / float(bye.group(2))
    sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
    import roster_convention as rc
    if miss_rate != rc._BENCH_MISS_RATE or abs(bye_rate - rc._BYE_RATE) > 1e-12:
        raise SystemExit("bench discount constants differ between value-model.js and roster_convention.py")
    return {"bye": bye_rate, "miss": miss_rate}


def trim(raw: dict) -> dict:
    """Keep what the page draws; round floats so the page stays small."""
    insp = raw["inspection"]
    vp = insp["valuePipeline"]
    keys = list(vp["sources"])
    charts = [k for k in keys if vp["sources"][k]["family"] == "chart"]
    # Per source, per player on its work list (listed or estimated):
    # [native, estimated, rank, role, value above waivers, bench slice,
    #  starter slice, Adjusted, VORP vs waivers (display), Indexed]
    idx = insp["views"]["indexed"]
    src = {}
    for k in keys:
        out = {}
        for pk, p in (insp["players"].get(k) or {}).items():
            ix = idx.get(k, {}).get(pk) if k in charts else None
            out[pk] = [r(p.get("native"), 4), 1 if p.get("estimated") else 0, p.get("rank"),
                       ROLE.get(p.get("role"), "w"), r(p.get("vorp"), 4), r(p.get("benchSlice"), 4),
                       r(p.get("starterSlice"), 4), r(p.get("adjusted")), r(p.get("vorpDisplay")), r(ix)]
        src[k] = out

    # Check: the per-source numbers above are the ones the chart draws.
    rv = raw["rowValues"]
    worst = {}
    for k in keys:
        for pk, p in (insp["players"].get(k) or {}).items():
            pairs = [("adj", rv["adj"].get(k, {}).get(pk), p.get("adjusted"))]
            vkey = k if k in charts else k + "_vorp"
            pairs.append(("vorp", rv["vorp"].get(vkey, {}).get(pk), p.get("vorpDisplay")))
            if k in charts:
                pairs.append(("indexed", rv["indexed"].get(k, {}).get(pk), idx.get(k, {}).get(pk)))
            for view, shown, ours in pairs:
                if shown is None or ours is None:
                    continue
                d = abs(shown - ours)
                if d > worst.get(f"{k}:{view}", -1):
                    worst[f"{k}:{view}"] = d
    off = {kv: d for kv, d in worst.items() if d > CHECK_TOL}

    players = {}
    for pk, row in insp["rows"].items():
        meta = raw["rowMeta"].get(pk) or raw["rowMeta"].get(str(pk)) or {}
        ddf = {}
        for ver, b in (row.get("ddfByVersion") or {}).items():
            ddf[ver] = [r(b.get("value")), b.get("count"), 1 if b.get("lowConfidence") else 0,
                        r((meta.get("prior") or {}).get(ver))]
        players[pk] = {"n": row.get("name"), "t": meta.get("team"), "p": row.get("pos"), "m": r(row.get("meanPpg")),
                       "tier": row.get("tier"), "ddf": ddf, "est": row.get("estimated") or {},
                       "why": row.get("reasons") or {}}

    diag = raw["diagnostics"]
    fp = diag.get("fixedPie") or {}
    vi = diag.get("viewInvariants") or {}
    prior = insp.get("priorValuePipeline")
    return {
        "setting": insp["setting"], "versions": insp["versions"], "labels": insp["labels"],
        "publishedKeys": insp["publishedKeys"], "sourceKeys": keys, "charts": charts,
        "vp": trim_pipeline(vp),
        "prior": trim_pipeline(prior, full=False) if prior else None,
        "fillSets": {p: len(v) for p, v in (vp.get("fillSets") or {}).items()},
        "players": players, "src": src,
        "fixedPie": {"ok": fp.get("ok"), "pie": fp.get("pie"), "tolerance": fp.get("tolerance"),
                     "checks": [{f: c.get(f) for f in ("source", "n", "total", "target", "vorpTotal", "groupsOk",
                                                        "unpaid", "included", "ok")} for c in fp.get("checks") or []],
                     "indexed": fp.get("indexed")},
        "indexedCheck": (vi.get("indexed") or {}).get("sources"),
        "indexedOrder": diag.get("indexedOrder"),
        "sourcePeaks": diag.get("sourcePeaks"),
        "publishedDerivation": diag.get("publishedDerivation"),
        "priorAvailable": diag.get("priorAvailable"), "priorReason": diag.get("priorReason"),
        "info": [{f: s.get(f) for f in ("key", "label", "week", "stale", "waiverNote", "included", "excludedReason",
                                         "available", "paused")} for s in raw["info"]],
        "composite": raw["composite"], "positionWeights": raw["positionWeights"], "zones": raw["zones"],
        "sensitivity": raw["sensitivity"], "restored": raw["restored"],
        "benchDiscount": bench_discount(),
        "hidden": hidden_sources(raw), "versionSources": version_sources(raw), "vorpRuns": vorp_runs(raw),
        "heavyRun": heavy_run(raw),
        "reconstruction": {"tolerance": CHECK_TOL, "worst": {k: r(v, 6) for k, v in worst.items()}, "off": off},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--data-out", type=Path, default=None, help="also write the data bundle as JSON")
    ap.add_argument("--skip-sync", action="store_true", help="use the dist/ already built")
    ap.add_argument("--mark-reviewed", action="store_true",
                    help="record the current logic-file hashes as reviewed (after re-checking the narrative)")
    args = ap.parse_args(argv)

    if not args.skip_sync:
        subprocess.run([sys.executable, str(ROOT / "pipelines" / "sync_dashboard_artifacts.py")],
                       cwd=ROOT, check=True, capture_output=True)
    data = trim(extract())
    if args.mark_reviewed:
        (APP / "reviewed.json").write_text(json.dumps({
            "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "commit": git("rev-parse", "--short", "HEAD"),
            "hashes": {f: sha(ROOT / f) for f in LOGIC_FILES if (ROOT / f).exists()},
        }, indent=2) + "\n")
    reviewed = json.loads((APP / "reviewed.json").read_text()) if (APP / "reviewed.json").exists() else {}
    hashes = {f: sha(ROOT / f) for f in LOGIC_FILES if (ROOT / f).exists()}
    data["meta"] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "commit_date": git("log", "-1", "--format=%cI"),
        "commit_subject": git("log", "-1", "--format=%s"),
        "build_tag": build_tag(),
        "logic_hashes": hashes,
        "reviewed": reviewed,
        "logic_changed": sorted(f for f, h in hashes.items() if reviewed.get("hashes", {}).get(f) != h),
        "math_review": math_review_items(),
    }
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = (APP / "template.html").read_text().replace("/*__VALUES_DATA__*/null", blob)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html)
    if args.data_out:
        args.data_out.parent.mkdir(parents=True, exist_ok=True)
        args.data_out.write_text(json.dumps(data, indent=1))
    print(f"values explainer -> {args.out} ({len(html) // 1024} KB, commit {data['meta']['commit']}, "
          f"logic changed since review: {data['meta']['logic_changed'] or 'none'}, "
          f"off the drawn values: {data['reconstruction']['off'] or 'none'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
