"""Builds the v6 walkthrough page (one self-contained HTML file) from out/*.json.

  python3 build_page.py <output.html>

Text lives here; numbers in the examples and the level chart are read from the outputs so the
page cannot drift from them. The page saves Jeremy's answers to the artifact db (collection
"verdicts", one document per card) and falls back to browser storage.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def esc(s):
    return html.escape(str(s), quote=True)


def f1(x):
    return "n/a" if x is None else f"{x:.1f}"


STEPS = [
    ("s1", "Pick the charts", "Adjust only the two charts that print one list for every scoring: FantasyCalc (read as Full PPR) and FantasyPros (read as Half PPR). CBS Sports and USA Today are used as published.",
     "Both anchors are assumed; neither publisher states them. Every value carries a range over the four anchor pairs instead of hiding this."),
    ("s2", "Start from the value DDF already gives the chart", "Each chart's Adjusted value at its anchor scoring, from the unmodified pipeline. This is exactly what DDF Value uses today.",
     "Checked exact on all six weeks: the start point equals today's Adjusted value, and DDF Value is reproduced to within 1e-9."),
    ("s3", "Read that value as a points level", "Find the points per game at which DDF's own projection pricing (ESPN, CBS ROS, Razzball) gives the same Adjusted value. The chart's math is never inverted; only DDF's is.",
     "A chart value can be read as a points level. It is not a calibrated forecast (issue 16). The test in the numbers section shows the scoring change barely depends on it: using only the chart's rank, or no chart points at all, gives the same player-by-player change at 0.84 to 0.99 correlation."),
    ("s4", "How the player earns his points: his catch share", "From his 2024 to 2026 game logs: catches per Half point. Pull it toward his position's average by n / (n + k), with k chosen on 2015 to 2025 outcomes: RB 8 games, WR 24, TE 16. QBs use the position share. On Standard, Half and Full only catches are weighted differently, so this one number drives the scoring change.",
     "Exploratory backtest, 2017 to 2025: calibration slope WR 0.94 [0.80, 1.08], TE 0.99 [0.59, 1.18], RB 0.98, against the locked light pull's WR 0.59. It beats the position average at RB, WR and TE. Caveat: the wider grid was chosen after the locked v5.1 result was seen."),
    ("s5", "Assumed stat line", "Split the chart's points into a per-game stat line: catches from the share, and the rest over yards and touchdowns in the player's own historical proportions. By construction the line scores exactly the chart's points at the anchor.",
     "The chart's points split the way the player's history does. The split of the non-catch points is untested and only matters for custom scoring."),
    ("s6", "Price the line exactly the way DDF prices ESPN", "Rescore the line at Standard, Half and Full (stat line times the scoring) and run it through DDF's projection path: waiver line, value above waivers, Adjusted. Keep the chart's own starting value and add only the change DDF's pricing gives (delta form).",
     "DDF's ESPN-style pricing is the right response. Result: the two re-priced charts now move like DDF's own projection sources (a top-24 WR keeps 0.64 to 0.65 of his Full value at Standard, ESPN 0.63)."),
    ("s7", "Average as DDF does", "Scoring-aware DDF = the mean of the four charts' Adjusted values: CBS Sports and USA Today as published, FantasyCalc and FantasyPros re-priced. Shown beside DDF Value, never instead of it.",
     "Equal weights, as DDF Value. At Full the metric differs from DDF Value only through FantasyPros, at Half only through FantasyCalc (tested)."),
]

LOCKED = [
    ("v5 decisive run, weeks 8-10 (PR #1472, outcome B)", [
        "T1 player mix beats position mix on real games: +0.041 [0.026, 0.056].",
        "T2 exactness pass; T4 direction pass (FantasyCalc 0.730, FantasyPros 0.582).",
        "T5 size fail at FantasyPros: 0.640 overall, WR 0.26 (week 10 alone 0.19). FantasyCalc 0.804 passed only because of zero-value ties.",
        "T6 fail by a hair (FantasyCalc TE/RB 0.645 vs envelope edge 0.644). T7 and T8 inconclusive; week 10 alone FantasyPros at Standard HARM -0.019."]),
    ("v5.1 backtest, 2017-2025 (PR #1478, outcome A)", [
        "Own catch history beats the position average: RB 9 of 9 seasons (+0.558), WR 8 of 9 (+0.082); TE inconclusive (+0.199 [-0.006, 0.542]).",
        "Calibration slope with the light pull (at most 8 games): RB 0.997 pass, WR 0.588 fail (band 0.67 to 1.5), TE 0.783 pass. Raw history WR 0.24; v5's heavy pull 3.08.",
        "The light pull chose the cap of 8 in every season, so a heavier pull was never tested."]),
]

EXPLORATORY = [
    ("Catch-share backtest with a wide grid (2017-2025, already seen)", [
        "Forward choice of the pull: RB 8 games every season, WR 24 (48 and 32 in the first two seasons), TE 12 to 24.",
        "Calibration slope: RB 0.98 [0.89, 1.08], WR 0.94 [0.80, 1.08], TE 0.99 [0.59, 1.18]. All inside 0.67 to 1.5.",
        "Error gain over the position average: RB +0.540 [0.309, 0.784], WR +0.113 [0.063, 0.168], TE +0.230 [0.035, 0.548]. Against the light pull: not shown either way (WR +0.016 [-0.003, +0.035]). The gain is calibration, not error.",
        "Harness check: with all history, the light pull rows reproduce the locked v5.1 figures exactly (WR 0.588, TE 0.783, RB 0.997)."]),
    ("Response against ESPN and Sleeper rescoring, weeks 5-10 (all seen)", [
        "Spread ratio (1.0 = moves as far): FantasyCalc 0.93 [0.88, 1.04], FantasyPros 0.76 [0.71, 0.92]. Direction 0.63 and 0.49, far above the shuffle control.",
        "Receivers: 0.57 at FantasyPros, and 0.58 at both charts once FantasyCalc's zero-value ties are removed. Up from 0.25 in v5, but below v5's band of 0.67. This is the weakest number.",
        "Position levels: the re-priced charts keep 0.64 to 0.65 of a top WR's Full value at Standard, ESPN 0.63. The metric keeps 0.75, because CBS Sports and USA Today keep 0.84 to 0.86."]),
    ("Calibration on 2026 outcomes (snapshot weeks 5-7, truth to week 10, small)", [
        "WR (66 players): v6 slope 1.47 [0.69, 2.24], ESPN 0.63 [0.17, 1.05], Sleeper 0.82 [0.34, 1.28]. v6 has the lowest weighted error of the five rules.",
        "So the projectors' own WR catch shares look over-spread against outcomes, which is why moving less than ESPN at WR may be the right size. The sample is far too small to settle it.",
        "TE (19 players): v6 slope -0.45 [-2.13, 0.67] and a higher error than ESPN. A warning, not a result."]),
    ("Does the answer depend on the chart's math? (weeks 5-10)", [
        "Each player's Standard-to-Full change with only the chart's rank: correlation 0.93 to 0.99 with v6. With no chart points at all: 0.84 to 0.96.",
        "Reading: the chart contributes its anchor value, as in DDF Value today. The scoring change comes from the player's history and DDF's pricing."]),
    ("Rankings and no-harm (weeks 5-10)", [
        "Within position the metric hardly reorders (0.99 to 1.00 against DDF Value). It mostly moves levels: at Standard the median top WR moves 10.7%, TE 10.2%, RB 5.6%, QB 1.9%.",
        "Agreement with the projectors' own lists equals DDF Value's within 0.02 everywhere. Against DDF Value (T8): Full +0.003 [+0.0001, +0.009], others inconclusive.",
        "No-harm against unchanged (T7): FantasyPros at Standard HARM -0.008 [-0.021, -0.001]; the other cells inconclusive."]),
    ("Anchor range", [
        "Median width of the four-anchor range, relative to the value: Standard WR 7.3%, RB 4.2%, TE 3.9%, QB 1.7%; 2 to 6% at Half and Full."]),
]

ISSUES = [
    (1, "Labelled gate G1: the rebuild loses to unchanged on CBS Sports and USA Today", "done", "Failed v1 to v4 (locked). Not used as the target in v6, because the publishers' columns barely move and disagree (issue 4)."),
    (2, "Size: moves too far", "open", "Sign changed. No overshoot now; receivers move 0.58 as far as ESPN/Sleeper rescoring. Position levels match DDF's projection sources. Open at WR (new issue N1)."),
    (3, "No-harm tests, tight ends", "open", "FantasyPros at Standard HARM -0.008 [-0.021, -0.001] on weeks 5 to 10. TE weak on 2026 outcomes (N4)."),
    (4, "Is the target valid?", "open", "v6 is judged on ESPN/Sleeper rescoring and on real outcomes, not on the publishers. The projectors are not ground truth either: their WR catch shares look over-spread in 2026."),
    (5, "Chart-to-chart response (G2)", "open", "Reported only: correlation FantasyCalc 0.27, FantasyPros 0.25 against the CBS/USA Today mean move."),
    (6, "The \"closer\" statistic", "done", "Resolved; not used."),
    (7, "Better than DDF Value?", "open", "Not shown and not claimed. T8 within plus or minus 0.01. The metric is separate."),
    (8, "Invertibility: the charts don't do strong math", "open", "Mitigated by design: the chart contributes only its anchor value; the scoring change is nearly the same without the chart's points (0.84 to 0.99). Still open as a premise."),
    (9, "Adjusted erases each chart's own position levels", "open", "Accepted by design: the start point is DDF's own Adjusted value, as in DDF Value."),
    (10, "Anchors unknown", "open", "Shown as a range on every value (median width 2 to 7%)."),
    (11, "FantasyCalc is pegged to one list", "done", "Resolved; Full anchor, disclosed."),
    (12, "History and stat data limits", "open", "2024 on per-stat history for chart players; the pull chosen with the same window; no fumbles or 2-pt."),
    (13, "Small sample; weeks already seen", "open", "Everything in v6 is exploratory. Weeks 11 and later are the first unseen chart weeks."),
    (14, "No tuning to the publishers", "open", "Held: the pull comes from outcomes. But the grid was widened after the locked v5.1 cap was seen (N6)."),
    (15, "Realized points cannot separate methods", "open", "Not tested for the metric."),
    (16, "Chart points are not a calibrated forecast", "open", "Still true. They only size the stat line, and the answer barely depends on them."),
    (17, "FantasyPros as published tracked actuals better", "open", "Untested."),
    (18, "Catches carry usage signal", "done", "Resolved: the rescoring keeps catches through the share."),
    (19, "Leakage and independence", "open", "v6's selection is forward only; the seasons were seen. Independence of references open."),
    (20, "Re-deriving the allocation moves levels", "open", "Re-derived as your step 7; levels land with ESPN and Sleeper (WR/RB 0.713 vs 0.710 and 0.687)."),
    (21, "v1 implementation errors", "done", "Resolved."),
    (22, "Open review findings", "open", "v6 has had no adversarial review yet."),
    ("N1", "Receivers move 0.58 as far as ESPN/Sleeper rescoring", "new", "Calibrated on 2017 to 2025 outcomes, but below v5's band. Decision D1."),
    ("N2", "Zero floor", "new", "At Standard 17 to 23 FantasyCalc WRs sit at 0 (DDF today already zeroes 15 of them); FantasyPros zeroes none where today's FantasyPros zeroes 8. Ties are dropped from the statistics."),
    ("N3", "CBS Sports and USA Today move little", "new", "Used as published they pull the metric halfway back toward DDF Value (WR 0.75 vs 0.63). Decision D3."),
    ("N4", "Tight ends on 2026 outcomes", "new", "v6 slope -0.45 [-2.13, 0.67], 19 players; the backtest TE is fine (0.99)."),
    ("N5", "Assumed lines look high at the top", "new", "Smith-Njigba 112 receiving yards a game at FantasyPros. A consequence of issue 16; shown as an assumption."),
    ("N6", "The wide grid came after seeing the v5.1 cap", "new", "And 2017 to 2025 were seen. Needs an unseen check (weeks 11 and later, season-end shares)."),
    ("N7", "The non-catch split is untested", "new", "Matters only for custom scoring."),
]

DECISIONS = [
    ("d1", "D1. How far should receivers move?", [("A", "Size to outcomes (v6): about 0.58 of ESPN/Sleeper (recommended)"), ("B", "Size to the projectors: light pull, about 0.86, over-reacts on outcomes"), ("C", "Halfway, pull about 12 games")]),
    ("d2", "D2. How to show the unknown anchors?", [("A", "Show the four-anchor range beside the value (recommended)"), ("B", "Average the four anchors into the value"), ("C", "Primary anchors only")]),
    ("d3", "D3. CBS Sports and USA Today", [("A", "As published, labelled as moving little (recommended for now)"), ("B", "Re-price them too, from their own anchor column"), ("C", "Leave them out of the metric")]),
    ("d4", "D4. Next check", [("A", "Freeze v6 and score it once on weeks 11-14 and season-end shares, rules written first (recommended)"), ("B", "Adversarial review first, then freeze")]),
]

DRIVERS = {
    "Jaxon Smith-Njigba": "About a fifth of his Half points are catches (8.5 a game), so at Standard he sits 11% below DDF Value; the two re-priced charts drop him as far as ESPN's own line does. CBS Sports and USA Today barely move him, so the metric moves about half as far as ESPN.",
    "Christian Watson": "His own catch share (0.31) is low for a WR; 31 games are not enough to trust it fully, so it is pulled up to 0.37. He still loses less than the catch-heavy receivers.",
    "Christian McCaffrey": "A pass-catching back: 4 catches a game, so unlike most RBs he does not gain at Standard (2% below DDF Value).",
    "Derrick Henry": "About 1 catch a game: almost nothing to lose at Standard, and RBs gain as a position, so at Standard he sits 13.5% above DDF Value.",
    "Trey McBride": "The most catch-heavy TE: at Standard he sits 16% below DDF Value.",
    "George Kittle": "Yards and touchdowns more than catches (own share 0.40), so he loses about half as much as McBride.",
    "Josh Allen": "No catches in his line; the small moves are position levels only.",
    "Jonah Coleman": "4 games of history; his share is close to the RB average anyway, so he moves like a typical back.",
    "Jordyn Tyson": "1 game of history (0.80 catches per point): the pull puts weight 0.04 on it, so he is priced almost at the WR average share.",
    "Mike Evans": "No game rows in weeks 7 to 9. History does not know he is out; the chart's anchor value carries that and v6 leaves it alone.",
}


def example_cards(ex):
    out = []
    for b in ex:
        fp = b["lines"]["fantasypros"]
        sh, ln = fp["share"], fp["line_per_game"]
        td = ln.get("rec_td", 0) + ln.get("rush_td", 0) + ln.get("pass_td", 0)
        rows = "".join(
            f"<tr><th scope=\"row\">{lab}</th><td>{f1(b['ddf'][s])}</td><td>{f1(b['metric'][s])}</td>"
            f"<td>{f1(b['band'][s][0])} to {f1(b['band'][s][1])}</td><td>{f1(b['adjusted_v6'][s]['fantasycalc'])}</td>"
            f"<td>{f1(b['adjusted_v6'][s]['fantasypros'])}</td></tr>"
            for s, lab in (("standard", "Standard"), ("half_ppr", "Half"), ("ppr", "Full")))
        parts = [f"{ln['rec']:.1f} catches", f"{ln['rec_yds']:.0f} rec yds"]
        if ln.get("rush_yds", 0) >= 5:
            parts.append(f"{ln['rush_yds']:.0f} rush yds")
        if ln.get("pass_yds", 0) >= 20:
            parts.append(f"{ln['pass_yds']:.0f} pass yds")
        parts.append(f"{td:.1f} TD")
        if b["pos"] == "QB":
            parts = [p for p in parts if not p.endswith("catches") and not p.endswith("rec yds")]
        proj = "n/a" if fp["proj_share"] is None else f"{fp['proj_share']:.3f}"
        share = (f"QB: position share" if b["pos"] == "QB" else
                 f"{sh['n']} games of history; own {sh['q_hist']:.3f}, weight {sh['a']:.2f}, used {sh['q']:.3f} (ESPN+Sleeper {proj})")
        pub = b["published"]
        out.append(
            f'<article class="ex"><header><h3>{esc(b["name"])}</h3><span class="tag">{esc(b["pos"])}</span></header>'
            f'<p class="why">{esc(b["why_chosen"])}</p>'
            f'<div class="tw"><table><thead><tr><th></th><th>DDF Value</th><th>Scoring-aware</th><th>Anchor range</th><th>FC re-priced</th><th>FP re-priced</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<dl class="kv"><dt>Chart values as published</dt><dd>FantasyPros {pub["fantasypros"]["half_ppr"]}, FantasyCalc {pub["fantasycalc"]["ppr"]:.0f} (Full), CBS {pub["cbs"]["standard"]} / {pub["cbs"]["ppr"]}, USA Today {pub["usatoday"]["standard"]} / {pub["usatoday"]["ppr"]} (Standard / Full)</dd>'
            f'<dt>Catch share</dt><dd>{esc(share)}</dd>'
            f'<dt>Assumed line (FantasyPros, per game)</dt><dd>{fp["P0"]:.1f} Half points: {esc(", ".join(parts))}</dd>'
            f'<dt>What drives the change</dt><dd>{esc(DRIVERS.get(b["name"], ""))}</dd></dl></article>')
    return "\n".join(out)


def level_chart(levels):
    s = levels["summary"]["WR"]
    items = [("ESPN (DDF projection source)", "espn", "proj"), ("Projections mean", "projections_mean", "proj"),
             ("FantasyCalc re-priced (v6)", "fantasycalc_v6", "v6"), ("FantasyPros re-priced (v6)", "fantasypros_v6", "v6"),
             ("Scoring-aware DDF", "scoring_aware_ddf", "metric"), ("CBS Sports as published", "cbs", "pub"),
             ("DDF Value today", "ddf_value", "ddf"), ("USA Today as published", "usatoday", "pub"),
             ("FantasyPros today", "fantasypros", "pub")]
    rows = []
    for lab, key, cls in items:
        v = s[key]["mean"]
        rows.append(f'<div class="bar {cls}"><span class="bl">{esc(lab)}</span><span class="bt"><span class="bf" style="width:{v * 100:.1f}%"></span></span><span class="bv">{v:.2f}</span></div>')
    return "\n".join(rows)


CSS = r"""
/* Layout: one reading column; each step, issue and decision is a card with answer buttons and a note. */
:root{--bg:#f6f7f4;--fg:#17201b;--muted:#566159;--line:#cdd4cc;--card:#ffffff;--accent:#1d6b4a;--accent-bg:#e3f1ea;--warn:#9a5b00;--warn-bg:#fbefd9;--bad:#a3262a;--bad-bg:#fbe4e4;--ok:#1d6b4a;--info:#2f5f8f;--info-bg:#e5edf6;--serif:"Source Serif 4",Georgia,serif;--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1713;--fg:#e8efe9;--muted:#9bab9f;--line:#2f3d34;--card:#17221c;--accent:#58c08e;--accent-bg:#143324;--warn:#f0b35a;--warn-bg:#3a2a10;--bad:#f08a8d;--bad-bg:#3b1a1c;--ok:#58c08e;--info:#8db8e8;--info-bg:#16263a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0f1713;--fg:#e8efe9;--muted:#9bab9f;--line:#2f3d34;--card:#17221c;--accent:#58c08e;--accent-bg:#143324;--warn:#f0b35a;--warn-bg:#3a2a10;--bad:#f08a8d;--bad-bg:#3b1a1c;--ok:#58c08e;--info:#8db8e8;--info-bg:#16263a;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:16px/1.55 var(--sans);padding-block:24px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--bg)}
main{max-width:760px;margin:0 auto;display:flex;flex-direction:column;gap:28px}
section{display:flex;flex-direction:column;gap:12px;min-width:0}
h1{font:700 30px/1.15 var(--serif);margin:0 0 8px;text-wrap:balance}
h2{font:700 21px/1.25 var(--serif);margin:0;text-wrap:balance}
h3{font:600 16px/1.35 var(--sans);margin:0;text-wrap:balance}
p{margin:0;max-width:68ch}
ul{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:5px;max-width:68ch}
.meta{font:500 12px var(--mono);color:var(--muted);letter-spacing:.05em;text-transform:uppercase;margin-bottom:8px}
.lede{background:var(--accent-bg);border:1px solid var(--accent);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
.isnot{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.isnot>div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0}
.isnot h3{margin-bottom:6px}
@media (max-width:620px){.isnot{grid-template-columns:1fr}}
.progress{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 0;font:500 13px var(--mono);color:var(--muted);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;min-width:0}
.num{font:500 12px var(--mono);color:var(--muted);letter-spacing:.05em}
.tags{display:flex;gap:6px;flex-wrap:wrap}
.tag{font:500 12px var(--mono);padding:2px 8px;border-radius:999px;background:var(--bg);border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.tag.open{background:var(--warn-bg);color:var(--warn);border-color:var(--warn)}
.tag.done{background:var(--accent-bg);color:var(--ok);border-color:var(--ok)}
.tag.new{background:var(--info-bg);color:var(--info);border-color:var(--info)}
.tag.locked{background:var(--info-bg);color:var(--info);border-color:var(--info)}
.tag.expl{background:var(--warn-bg);color:var(--warn);border-color:var(--warn)}
.k{font:600 12px var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.verdict{display:flex;gap:8px;flex-wrap:wrap}
.verdict button{flex:1 1 140px;min-height:44px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:8px;font:500 14px var(--sans);cursor:pointer;padding:8px 10px;text-align:center}
.verdict.opts button{flex:1 1 100%;text-align:left}
.verdict button:focus-visible,textarea:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.verdict button[aria-pressed="true"]{border-color:var(--accent);background:var(--accent-bg);box-shadow:inset 0 0 0 1px var(--accent)}
.verdict button.no[aria-pressed="true"]{border-color:var(--bad);background:var(--bad-bg);box-shadow:inset 0 0 0 1px var(--bad)}
.verdict button.unsure[aria-pressed="true"]{border-color:var(--warn);background:var(--warn-bg);box-shadow:inset 0 0 0 1px var(--warn)}
textarea{width:100%;min-height:56px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:15px/1.4 var(--sans);padding:8px 10px;resize:vertical}
.saved{font:500 12px var(--mono);color:var(--muted);min-height:16px}
.banner{font-size:14px;color:var(--warn);background:var(--warn-bg);border-radius:8px;padding:8px 12px}
.ex{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;min-width:0}
.ex header{display:flex;gap:8px;align-items:center;justify-content:space-between}
.why{color:var(--muted);font-size:15px}
.tw{overflow-x:auto;min-width:0}
table{border-collapse:collapse;font:14px/1.35 var(--sans);font-variant-numeric:tabular-nums;width:100%;min-width:520px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{font:600 12px var(--mono);color:var(--muted);letter-spacing:.03em}
tbody th{font-weight:600}
.kv{display:grid;grid-template-columns:minmax(0,1fr);gap:2px;margin:0}
.kv dt{font:600 12px var(--mono);letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin-top:6px}
.kv dd{margin:0;max-width:68ch}
.numblock{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:8px;min-width:0}
.numblock.locked{border-left:4px solid var(--info)}
.numblock.expl{border-left:4px solid var(--warn)}
.bars{display:flex;flex-direction:column;gap:6px}
.bar{display:grid;grid-template-columns:minmax(0,13em) minmax(0,1fr) 3em;gap:8px;align-items:center;font-size:14px}
.bl{min-width:0}
.bt{height:12px;background:var(--bg);border:1px solid var(--line);border-radius:3px;position:relative;overflow:hidden}
.bf{position:absolute;inset:0 auto 0 0;background:var(--muted)}
.bar.proj .bf{background:var(--info)}.bar.v6 .bf{background:var(--accent)}.bar.metric .bf{background:var(--warn)}
.bar.metric .bl{font-weight:600}
.bv{font:500 13px var(--mono);text-align:right;font-variant-numeric:tabular-nums}
@media (max-width:520px){.bar{grid-template-columns:minmax(0,1fr) 3em}.bl{grid-column:1/-1}}
.small{font-size:14px;color:var(--muted)}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

SCRIPT = r"""
var STEP_LABELS=[["ok","Sound"],["no","Not sound"],["unsure","Unsure"]];
var ISSUE_LABELS=[["ok","Handling is sound"],["no","Not sound"],["unsure","Unsure"]];
var OVERALL=[["ok","Sound enough to freeze and test"],["no","Not sound: change the approach"],["unsure","Not sure yet"]];
var state={};var dbc=null;var LS="ddf-v6-verdicts";
function lsGet(){try{return JSON.parse(localStorage.getItem(LS)||"{}")}catch(_){return{}}}
function lsSet(){try{localStorage.setItem(LS,JSON.stringify(state))}catch(_){}}
function save(id){var rec=state[id];rec.at=new Date().toISOString();var s=document.getElementById("saved-"+id);
 if(dbc){dbc.doc(id).set(rec).then(function(){if(s)s.textContent="Saved"}).catch(function(){if(s)s.textContent="Could not save for Claude; kept in this browser";lsSet()})}
 else{lsSet();if(s)s.textContent="Kept in this browser only"}
 progress()}
function wire(c){var id=c.dataset.id,kind=c.dataset.kind;var v=c.querySelector(".verdict");var labels=kind==="step"?STEP_LABELS:kind==="issue"?ISSUE_LABELS:kind==="overall"?OVERALL:JSON.parse(c.dataset.opts);
 labels.forEach(function(l){var b=document.createElement("button");b.type="button";b.textContent=l[1];b.className=l[0]==="no"?"no":(l[0]==="unsure"?"unsure":"");b.dataset.v=l[0];b.setAttribute("aria-pressed","false");
  b.onclick=function(){state[id]=state[id]||{kind:kind};state[id].verdict=l[0];paint(id);save(id)};v.appendChild(b)});
 var t=c.querySelector("textarea");var timer;t.oninput=function(){state[id]=state[id]||{kind:kind};state[id].note=t.value;clearTimeout(timer);timer=setTimeout(function(){save(id)},700)}}
function paint(id){var c=document.querySelector('[data-id="'+id+'"]');if(!c)return;var r=state[id]||{};
 c.querySelectorAll(".verdict button").forEach(function(b){b.setAttribute("aria-pressed",String(r.verdict===b.dataset.v))});
 var t=c.querySelector("textarea");if(t&&document.activeElement!==t)t.value=r.note||""}
function count(kind){var n=0,d=0;document.querySelectorAll('[data-kind="'+kind+'"]').forEach(function(c){n++;var r=state[c.dataset.id];if(r&&r.verdict)d++});return[d,n]}
function progress(){var s=count("step"),i=count("issue"),d=count("decision");
 document.getElementById("prog-steps").textContent="Steps "+s[0]+"/"+s[1];document.getElementById("prog-issues").textContent="Issues "+i[0]+"/"+i[1];
 document.getElementById("prog-dec").textContent="Decisions "+d[0]+"/"+d[1];var o=state.overall&&state.overall.verdict;
 document.getElementById("prog-overall").textContent="Overall: "+(o?(o==="ok"?"sound":o==="no"?"not sound":"not sure"):"not answered")}
function paintAll(){document.querySelectorAll("[data-id]").forEach(function(c){paint(c.dataset.id)});progress()}
document.querySelectorAll("[data-id]").forEach(wire);state=lsGet();paintAll();
if(window.claude&&claude.use){claude.use("db").then(function(db){
 if(!db){document.getElementById("dbnote").hidden=false;return}
 dbc=db.collection("verdicts");
 var local=lsGet();Object.keys(local).forEach(function(k){var v=local[k];if(v&&(v.verdict||v.note)){dbc.doc(k).get().then(function(s){if(!s.exists){return dbc.doc(k).set(v)}}).catch(function(){})}});
 dbc.onSnapshot(function(snap){snap.docs.forEach(function(d){var v=d.data&&d.data();if(v&&(v.verdict||v.note)){state[d.id]=v}});paintAll()},function(){document.getElementById("dbnote").hidden=false;dbc=null});
}).catch(function(){document.getElementById("dbnote").hidden=false})}else{document.getElementById("dbnote").hidden=false}
"""


def answer_block(id_, kind, opts=None, placeholder="Your note (optional)"):
    extra = f" data-opts='{esc(json.dumps(opts))}'" if opts else ""
    cls = "verdict opts" if opts else "verdict"
    return id_, kind, extra, (f'<div class="{cls}" role="group" aria-label="Your answer"></div>'
                             f'<textarea id="note-{id_}" placeholder="{esc(placeholder)}" aria-label="Note"></textarea>'
                             f'<div class="saved" id="saved-{id_}"></div>')


def card(id_, kind, inner, opts=None):
    _i, _k, extra, ans = answer_block(id_, kind, opts)
    return f'<div class="card" data-id="{id_}" data-kind="{kind}"{extra}>{inner}{ans}</div>'


def build(path):
    ex = json.loads((OUT / "examples.json").read_text())
    levels = json.loads((OUT / "levels.json").read_text())
    steps = "\n".join(card(sid, "step", f'<div class="num">STEP {i + 1} OF {len(STEPS)}</div><h3>{esc(t)}</h3><p>{esc(m)}</p>'
                                         f'<div class="k">Assumption and evidence</div><p class="small">{esc(a)}</p>')
                      for i, (sid, t, m, a) in enumerate(STEPS))
    num = lambda blocks, cls, tag: "\n".join(  # noqa: E731
        f'<div class="numblock {cls}"><div class="tags"><span class="tag {cls}">{tag}</span></div><h3>{esc(t)}</h3><ul>'
        + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul></div>" for t, items in blocks)
    tagname = {"open": ("open", "open"), "done": ("done", "resolved"), "new": ("new", "new in v6")}
    issues = "\n".join(card(f"i{n}", "issue", f'<div class="num">ISSUE {n}</div><h3>{esc(t)}</h3><div class="tags"><span class="tag {tagname[s][0]}">{tagname[s][1]}</span></div>'
                                              f'<div class="k">Where v6 stands</div><p>{esc(txt)}</p>')
                       for n, t, s, txt in ISSUES)
    decisions = "\n".join(card(did, "decision", f"<h3>{esc(t)}</h3>", opts=[[k, f"{k}: {lab}"] for k, lab in opts])
                          for did, t, opts in DECISIONS)
    overall = card("overall", "overall", "<h3>Is this the right end-to-end approach for a separate scoring-aware metric?</h3>"
                                         '<p class="small">Your answer here decides whether v6 is frozen and tested on weeks 11 and later, or reworked.</p>')
    page = f"""<title>Scoring-aware DDF v6</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap">
<style>{CSS}</style>
<main>
<header>
<div class="meta">Data Driven Football · JEG-1597 · v6 · prepared 2026-11-17</div>
<h1>Scoring-aware DDF v6</h1>
<div class="lede">
<p><b>What this is.</b> My best end-to-end version of a new, separate metric that responds to your league's scoring. It sits beside DDF Value and never replaces it. Nothing here changes DDF Value, the charts, the pipeline or the live site.</p>
<p><b>Your method, as built.</b> Take the two charts that ignore scoring (FantasyCalc, FantasyPros), start from the value DDF already gives them, read it as a points level, split those points into a stat line using each player's own history, then price that line at Standard, Half and Full exactly the way DDF prices ESPN, and average the four charts as DDF does. CBS Sports and USA Today are used as published.</p>
<p><b>How to use it.</b> Every step, issue and decision has buttons and a note box. Answers save as you tap, and I can read them back.</p>
<p><b>Status.</b> Everything new here is exploratory: it was built after the locked v5 and v5.1 results, on weeks and seasons already seen. The numbers section keeps the locked results apart.</p>
</div>
<div id="dbnote" class="banner" hidden>Answers are not being saved for Claude in this view (kept in this browser only).</div>
</header>
<div class="progress" aria-live="polite"><span id="prog-steps">Steps 0/0</span><span id="prog-issues">Issues 0/0</span><span id="prog-dec">Decisions 0/0</span><span id="prog-overall">Overall: not answered</span></div>

<section>
<h2>What this metric is and is not</h2>
<div class="isnot">
<div><h3>It is</h3><ul>
<li>DDF Value's own four-chart average, with FantasyCalc and FantasyPros re-priced for your scoring.</li>
<li>Driven by each player's real catch history and DDF's own ESPN-style pricing.</li>
<li>Shown with a range for the scoring FantasyCalc and FantasyPros might assume, since neither says.</li>
<li>A research column, labelled as such.</li></ul></div>
<div><h3>It is not</h3><ul>
<li>A replacement for DDF Value.</li>
<li>A claim that the charts hold stat lines inside them. The chart only supplies its anchor value, as in DDF Value today.</li>
<li>Tuned to CBS Sports or USA Today.</li>
<li>Tested against outcomes at the chart level: no chart snapshots exist before 2026.</li></ul></div>
</div>
<p class="small">Suggested label for users: "Scoring-aware DDF (research). DDF Value with FantasyCalc and FantasyPros re-priced for your scoring from each player's catch history. Not a replacement for DDF Value."</p>
</section>

<section>
<h2>The method, step by step</h2>
{steps}
</section>

<section>
<h2>Worked examples (week 10)</h2>
<p class="small">Values are DDF's Adjusted-value units. "Anchor range" is the lowest and highest Scoring-aware value over the four anchor pairs. FC and FP re-priced are the two charts' own new values. Ten players: four positions, a pass-catching and an early-down back, two rookies, and one player with no games in weeks 7 to 9.</p>
{example_cards(ex)}
</section>

<section>
<h2>How far a top receiver's value moves</h2>
<p class="small">Share of a top-24 WR's Full PPR value kept at Standard (median, weeks 5 to 10). Lower means a bigger response to scoring. Exploratory.</p>
<div class="numblock"><div class="bars">{level_chart(levels)}</div>
<p class="small">The two re-priced charts now move like DDF's own projection sources. CBS Sports and USA Today, as published, move about as little as an unadjusted FantasyPros does inside DDF, so the metric lands halfway (decision D3).</p></div>
</section>

<section>
<h2>The numbers</h2>
<p class="small">Locked results were pre-registered and run once; they are quoted, not re-run. Exploratory results are mine from today, on data already seen, with 95% intervals in brackets.</p>
{num(LOCKED, "locked", "locked, pre-registered")}
{num(EXPLORATORY, "expl", "exploratory")}
<p class="small"><b>Strongest evidence:</b> the catch-share pull is now calibrated on nine seasons of outcomes at every position. <b>Weakest:</b> receivers move only 0.58 as far as ESPN and Sleeper rescoring would; whether that is right rests on a small 2026 sample.</p>
</section>

<section>
<h2>Issues: the 22 carried over, and new ones</h2>
{issues}
</section>

<section>
<h2>Decisions for you</h2>
{decisions}
</section>

<section>
<h2>Overall</h2>
{overall}
</section>
<p class="small">Design doc: docs/research/jeg1597/v6-design.md on branch claude/JEG-1597-v6. Code: tools/research/jeg1597v6/.</p>
</main>
<script>{SCRIPT}</script>
"""
    Path(path).write_text(page, encoding="utf-8")
    print("wrote", path, len(page))


if __name__ == "__main__":
    build(sys.argv[1])
