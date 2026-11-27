"""JEG-1543 phase 2: the get-answers edge function (supabase/functions/get-answers) gives find.html's answers, no sources.

1. Parity with the real find.html (Playwright) on the seeded 12-team league (11 partners) of tests.test_team_engine_parity,
   at 3 settings (one superflex 10-team with held players, a skipped team and two overrides; one with sizes 1 only):
   - every group the page found (partner, fit class, players received) with every alternative trade in its order:
     players given and received, DDF edge, your starters' change, the waiver alternative (players, covered share,
     demoted) and the Why panel the page fills (your % roster better, the other side's word and percent, Natural fit,
     headline, net, reasons);
   - the order the page lists them in (DDF.findPage.visible(): default sort, repeat cap 20, page size 200), the
     natural / partner neutral / force sections;
   - the partner order (DDF.league.partnerRank(), what partners.html lists) and the opportunity tier
     (DDFOpportunity.computeTeam, what team.html shows; team.html's own tier at the first setting).
   The function runs as deployed (index.ts handler in node, fetching the built dist/), with the page's clock pinned to
   the same day.
2. The reply passes an explicit key/type allowlist (REPLY, kept here independently of core.ts) and
   answers_privacy.text_findings on the serialized reply; core.ts's banned list equals answers_privacy.BANNED.
3. Broken variants: a build whose reply carries each trade's per-chart nets, or the chart count behind the gate, is
   refused by the function's own allowlist (500, nothing sent), and what it would have sent fails the checks here.
4. Refusals: include, basis, a per-source field, sizes 3, an unknown field; plus CORS and the 30/min limiter.
Also reports CPU time per request (sizes 1-2, 11 partners), warm and cold.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_team_engine_parity import seeded_league

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import answers_privacy as ap  # noqa: E402

NODE = ["node", "--experimental-strip-types", "--no-warnings"]
DRIVER = ROOT / "tests" / "node" / "get_answers_driver.mjs"
FUNCTIONS = ROOT / "supabase" / "functions"

READY = "() => window.DDF && DDF.findPage && /^Searched|^$/.test(document.getElementById('search-status').textContent) && DDF.findPage.state.sig !== '' && !DDF.findPage.state.running"
APPLY = "async ([scoring, teams, sf]) => { await DDF.engine.ready; await DDF.league.ready; DDF.engine.apply({scoring, teams, superflex: sf}); return true; }"
SET = """([id, value]) => { const el = document.getElementById(id); el.value = value; el.dispatchEvent(new Event('change', {bubbles: true})); }"""
SIZES = """(want) => { document.querySelectorAll('.size').forEach(x => { const on = want.includes(+x.value); if (x.checked !== on) { x.checked = on; x.dispatchEvent(new Event('change', {bubbles: true})); } }); }"""

# The league as the page resolved it (priced players by key; my kicker as an unpriced special).
READ_LEAGUE = r"""() => { const c = DDF.league.current(); return {me: c.me, teams: c.teams.map(t => ({index: t.index, name: t.name,
  keys: t.players.filter(p => !p.unpriced).map(p => p.key),
  others: t.players.filter(p => p.unpriced && ['K', 'DEF', 'DST'].includes(p.pos)).map(p => ({pos: p.pos, name: p.name}))}))}; }"""

# Every group the page holds, every alternative, and the Why panel as whyFill() fills it; then the listed order.
READ_PAGE = r"""() => {
  const S = DDF.findPage.state, $ = id => document.getElementById(id);
  const r1 = v => (typeof v === 'number' && isFinite(v)) ? Math.round(v * 10) / 10 : null;
  const r2 = v => (typeof v === 'number' && isFinite(v)) ? Math.round(v * 100) / 100 : null;
  const keys = rows => rows.map(r => Number(r.player_key));
  const ctx = Object.assign({}, DDF.find.context(), {ourKey: DDF.find.valuation($('your-valuation').value).key, marketKey: DDF.find.valuation($('their-valuation').value).key});
  const trade = (g, t) => {
    const e = window.DDFWhy && t.fit ? DDFWhy.explain({mine: g.mineRows, theirs: g.theirRows, give: t.give, receive: t.receive, waiver: t.waiver || null}, ctx) : null;
    const p = e && e.pct ? e.pct : null;
    return {give: keys(t.give), receive: keys(t.receive), edge: r1(t.edge), starters: r1(t.you),
      roster_pct: p ? p.sender.shown : null, them: p ? {band: p.partner.band, pct: p.partner.shown} : null,
      waiver: t.waiver ? {players: t.waiver.players.map(x => Number(x.key)), covered: r2(t.waiver.covered), demoted: Boolean(t.waiver.demoted),
        line: t.waiver.demoted ? DDFWhy.waiverLine(t.waiver, t.give) : ''} : null,
      added: (t.addedThrowIns || []).map(a => ({key: Number(a.row.player_key), side: a.side === 'give' ? 'give' : 'receive'})),
      also: t.throwIns ? keys(t.throwIns.give.concat(t.throwIns.receive)) : [], unbalanced: Boolean(t.unbalanced),
      why: e ? {natural: Boolean(e.natural), headline: e.headline, net: e.table.net, reasons: e.reasons.map(r => [r.kind, r.text]),
        give: e.table.give.map(r => r.role), get: e.table.get.map(r => r.role), their_sentence: p ? (p.sentence || '') : '',
        you: [r1(e.you.starterDelta), r1(e.you.benchDelta), r1(e.you.net), ['QB', 'RB', 'WR', 'TE'].map(x => r1(e.you.posDelta[x]))]} : null};
  };
  const id = g => [g.partnerIndex, g.cls, g.key].join('|');
  return {groups: S.groups.map(g => ({id: id(g), trades: g.trades.map(t => trade(g, t))})), listed: DDF.findPage.visible().map(id)};
}"""
READ_RANK = r"""() => DDF.league.partnerRank().map(p => ({team: p.index, rank: p.rank, score: p.score === null ? null : Math.round(p.score * 100) / 100,
  get: p.get.map(x => x.pos), give: p.give.map(x => x.pos), two_way: Boolean(p.twoWay)}))"""
READ_TIER = r"""async () => { const o = await DDFOpportunity.computeTeam(DDF.league.current(), DDF.league.myTeam());
  return o ? {tier: o.tier, reason: o.reason || null, pct: o.shown, gain: Math.round(o.gain * 10) / 10, source: o.source || null, headline: o.headline, line: o.line} : null; }"""

# (scoring, teams, superflex, sizes, held: my roster positions, skipped: team indexes, overrides on (team, position)).
CASES = [
    ("ppr", 12, False, [1, 2], [], [], []),
    ("half_ppr", 10, True, [1, 2], [0], [5], [((0, 3), 40.0), ((4, 0), {"type": "adjustment", "delta": 6})]),
    ("standard", 12, False, [1], [], [], []),
]


def _node_driver(requests, raw=False, functions=None, today=None):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(requests, fh)
        path = fh.name
    try:
        cmd = NODE + [str(DRIVER), str(DIST), path] + (["--raw"] if raw else []) + (["--functions", str(functions)] if functions else [])
        env = {**os.environ, **({"DDF_TODAY": today} if today else {})}
        out = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        if out.returncode != 0:
            raise AssertionError(f"get-answers driver failed: {out.stderr[-2000:]}")
        return json.loads(out.stdout)
    finally:
        os.unlink(path)


def _today():
    from tests.test_week_history import _fixture_today
    return _fixture_today()


def _league():
    league = seeded_league()
    # My 2nd and 3rd round picks go back to the available players, so the waiver alternative has pickups (as find parity).
    del league["teams"][league["me"]]["players"][1:3]
    return league


def _seed(league, session=None, local=None):
    body = f"sessionStorage.setItem('ddf:pasted', {json.dumps(json.dumps(league))});"
    for k, v in (session or {}).items():
        body += f"sessionStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});"
    for k, v in (local or {}).items():
        body += f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});"
    return ("(function(){ try { if (sessionStorage.getItem('t-seeded')) return; localStorage.clear(); sessionStorage.clear();"
            f" sessionStorage.setItem('t-seeded','1'); {body} }} catch(_){{}} }})()")


def _ov_text(overrides):
    parts = []
    for key, v in overrides:
        parts.append(f"{key}:+{v['delta']}" if isinstance(v, dict) else f"{key}:{v:.1f}")
    return ",".join(parts)


def request_for(resolved, scoring, teams, sf, sizes, held, skipped, ov, alternatives=None):
    me = resolved["me"]
    mine = resolved["teams"][me]
    return {"league": {"scoring": scoring, "teams": teams, **({"roster": {"SUPERFLEX": 1}} if sf else {})},
            "me": {"index": me, "keys": mine["keys"], "others": mine["others"]},
            "opponents": [{"id": t["index"], "name": t["name"], "keys": t["keys"]} for t in resolved["teams"] if t["index"] != me],
            "skipped": skipped, "sizes": sizes, "held": held, **({"ov": ov} if ov else {}), **({"alternatives": alternatives} if alternatives else {})}


def capped(groups, cap=20, page_size=200):
    """find-page.js visible()'s display filters (repeat cap, page size) over the reply's order."""
    used, per, out = {}, {}, []
    for g in groups:
        t = g["trades"][0]
        ks = [str(k) for k in t["give"] + t["receive"]]
        if any(used.get(k, 0) >= cap for k in ks):
            continue
        for k in ks:
            used[k] = used.get(k, 0) + 1
        sec = "neutral" if g["fit"] == "unjudged" else g["fit"]
        per[sec] = per.get(sec, 0) + 1
        if per[sec] <= page_size:
            out.append(gid(g))
    return out


def gid(g):
    return f"{g['team']}|{g['fit']}|{','.join(str(k) for k in g['receive'])}"


def server_trade(t):
    return {k: t[k] for k in ("give", "receive", "edge", "starters", "roster_pct", "them", "waiver", "added", "also", "unbalanced")}


def server_why(w):
    if w is None:
        return None
    return {"natural": w["natural"], "headline": w["headline"], "net": w["net"], "reasons": [[r["kind"], r["text"]] for r in w["reasons"]],
            "give": [x["role"] for x in w["give"]], "get": [x["role"] for x in w["get"]], "their_sentence": w["their_sentence"],
            "you": [w["you"]["starters"], w["you"]["bench"], w["you"]["net"], [w["you"]["by_position"][p] for p in ("QB", "RB", "WR", "TE")]]}


# ----- 2. the reply allowlist, kept here on its own (not read from core.ts) -----
NUM, INT, STR, BOOL, ID = "num", "int", "str", "bool", "id"
TIERS = ("big", "medium", "marginal", "none")
FITS = ("natural", "neutral", "force", "unjudged")
BANDS = ("better", "unchanged", "slightly_worse", "clearly_worse")
POS = ("QB", "RB", "WR", "TE")


def nul(s):
    return ("nul", s)


def enum(*v):
    return ("enum", v)


def arr(s):
    return ("arr", s)


TRADE = {"give": arr(INT), "receive": arr(INT), "edge": NUM, "starters": nul(NUM), "roster_pct": nul(NUM),
         "them": nul({"band": enum(*BANDS), "pct": NUM}),
         "waiver": nul({"players": arr(INT), "covered": nul(NUM), "demoted": BOOL, "line": STR}),
         "added": arr({"key": INT, "side": enum("give", "receive")}), "also": arr(INT), "unbalanced": BOOL}
WHY = nul({"natural": BOOL, "headline": STR, "give": arr({"key": INT, "role": STR}), "get": arr({"key": INT, "role": STR}),
           "net": STR, "reasons": arr({"kind": STR, "text": STR}), "their_sentence": STR,
           "you": {"starters": nul(NUM), "bench": nul(NUM), "net": nul(NUM), "by_position": {p: nul(NUM) for p in POS}}})
GROUP = {"team": ID, "fit": enum(*FITS), "receive": arr(INT), "alternatives": INT, "trades": arr(TRADE)}
WHY_REPLY = {"v": INT, "found": BOOL, "team": ID, "fit": nul(enum(*FITS)), "trade": nul(TRADE), "why": WHY}
REPLY = {"v": INT, "as_of": nul(STR), "week": nul(INT), "setting": {"scoring": enum("standard", "half_ppr", "ppr"), "teams": INT, "superflex": INT},
         "sizes": arr(enum(1, 2)),
         "team": nul({"tier": enum(*TIERS), "reason": nul(enum("unsized", "unchecked", "small", "sharp")), "pct": nul(NUM), "gain": nul(NUM),
                      "source": nul(enum("trade", "waiver")), "headline": STR, "line": STR, "trade_team": nul(ID)}),
         "partners": arr({"team": ID, "rank": INT, "score": nul(NUM), "get": arr(enum(*POS)), "give": arr(enum(*POS)), "two_way": BOOL}),
         "natural": arr(GROUP), "neutral": arr(GROUP), "force": arr(GROUP),
         "notes": {"searched": arr(ID), "sanity_dropped": INT, "guardrail_dropped": INT, "partial": arr(ID), "unjudged": BOOL,
                   "searched_top": BOOL, "held": INT, "overrides": INT}}


def schema_findings(v, spec=REPLY, path="reply"):
    out = []
    if isinstance(spec, str):
        ok = {NUM: isinstance(v, (int, float)) and not isinstance(v, bool),
              INT: isinstance(v, int) and not isinstance(v, bool),
              STR: isinstance(v, str), BOOL: isinstance(v, bool),
              ID: (isinstance(v, str) and 0 < len(v) <= 64) or (isinstance(v, int) and not isinstance(v, bool) and v >= 0)}[spec]
        return [] if ok else [f"{path}: expected {spec}, got {v!r:.40}"]
    if isinstance(spec, tuple):
        kind, inner = spec
        if kind == "nul":
            return [] if v is None else schema_findings(v, inner, path)
        if kind == "enum":
            return [] if v in inner and not isinstance(v, bool) else [f"{path}: {v!r} not in {inner}"]
        if not isinstance(v, list):
            return [f"{path}: expected a list"]
        for i, x in enumerate(v):
            out += schema_findings(x, inner, f"{path}[{i}]")
            if len(out) > 20:
                break
        return out
    if not isinstance(v, dict):
        return [f"{path}: expected an object"]
    out += [f"{path}.{k}: not in the allowlist" for k in v if k not in spec]
    out += [f"{path}.{k}: missing" for k in spec if k not in v]
    for k, s in spec.items():
        if k in v:
            out += schema_findings(v[k], s, f"{path}.{k}")
    return out


def reply_findings(body, spec=REPLY):
    return schema_findings(body, spec) + ap.text_findings("get-answers reply", json.dumps(body))


def setUpModule():
    _render_env.ensure_built()


class GetAnswersParityTest(unittest.TestCase):
    """1. Same trades, order, fit class, Why words, tier and partner order as the real find.html."""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists():
            raise _render_env.unavailable("dist/find.html is not built")
        today = _today()
        league = _league()
        cls.cases = []
        with serve() as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except PlaywrightError as exc:
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                for n, (scoring, teams, sf, sizes, held_at, skipped, ov_at) in enumerate(CASES):
                    label = f"{scoring} {teams} sf={int(sf)} sizes={sizes}"
                    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                    ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                    ctx.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today)};")
                    # First the league as the page resolves it (the keys a client would send), then the seeded state.
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    ctx.add_init_script(_seed(league))
                    page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
                    page.evaluate(APPLY, [scoring, teams, sf])
                    page.wait_for_function(READY, timeout=120000)
                    resolved = page.evaluate(READ_LEAGUE)
                    me = resolved["teams"][resolved["me"]]
                    held = [me["keys"][i] for i in held_at]
                    overrides = [(resolved["teams"][t]["keys"][i], v) for (t, i), v in ov_at]
                    ctx.close()
                    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                    ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                    ctx.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today)};")
                    session = {"ddf:hold": held, "ddf:skip": [resolved["teams"][i]["name"] for i in skipped]}
                    local = {"ddf-v2-value-overrides": {"v": 2, "basis": {"mode": "default"}, "values": {str(k): v for k, v in overrides}, "names": {}}} if overrides else {}
                    ctx.add_init_script(_seed(league, session, local))
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
                    page.evaluate(APPLY, [scoring, teams, sf])
                    page.wait_for_timeout(300)
                    page.wait_for_function(READY, timeout=120000)
                    if sizes != [1, 2]:
                        page.evaluate(SIZES, sizes)
                        page.wait_for_timeout(300)
                        page.wait_for_function(READY, timeout=120000)
                    page.click('[data-page-size="200"]')
                    got = page.evaluate(READ_PAGE)
                    page.evaluate(SET, ["fit", "force"])
                    got["listed_force"] = page.evaluate(READ_PAGE)["listed"]
                    page.evaluate(SET, ["fit", "all"])
                    got["rank"] = page.evaluate(READ_RANK)
                    got["tier"] = page.evaluate(READ_TIER)
                    if n == 0:
                        tpage = ctx.new_page()
                        tpage.goto(f"{base}/team.html", wait_until="domcontentloaded", timeout=60000)
                        tpage.evaluate(APPLY, [scoring, teams, sf])
                        tpage.wait_for_function("() => document.getElementById('opp-tier') && document.getElementById('opp-tier').dataset.tier", timeout=120000)
                        got["team_html_tier"] = tpage.evaluate("() => document.getElementById('opp-tier').dataset.tier")
                    ctx.close()
                    req = request_for(resolved, scoring, teams, sf, sizes, held, skipped, _ov_text(overrides), alternatives=500)
                    cls.cases.append({"label": label, "page": got, "request": req, "errors": errors})
            finally:
                browser.close()
        out = _node_driver([{"body": c["request"]} for c in cls.cases], today=today)
        for c, r in zip(cls.cases, out["results"]):
            c["reply"] = r
        # Why mode: every group's shown trade (the first) and a spread of up to 12 alternatives per case.
        asks = []
        for n, c in enumerate(cls.cases):
            alts = [(g["id"], i) for g in c["page"]["groups"] for i in range(1, len(g["trades"]))]
            pick = [(g["id"], 0) for g in c["page"]["groups"]] + alts[:: max(1, len(alts) // 12)][:12]
            page = {g["id"]: g["trades"] for g in c["page"]["groups"]}
            for gk, i in pick:
                t = page[gk][i]
                asks.append((n, gk, i, {**c["request"], "why": {"team": int(gk.split("|")[0]), "give": t["give"], "receive": t["receive"]}}))
        cls.why_asks = asks
        cls.why_out = _node_driver([{"body": a[3], "ip": f"10.1.{k // 250}.{k % 250}"} for k, a in enumerate(asks)], today=today)["results"]

    def test_no_page_errors_and_replies_ok(self):
        for c in self.cases:
            self.assertEqual(c["errors"], [], c["label"])
            self.assertEqual(c["reply"]["status"], 200, (c["label"], c["reply"]["body"]))

    def test_same_groups_trades_fit_and_why(self):
        for c in self.cases:
            body = c["reply"]["body"]
            server = {gid(g): g for sec in ("natural", "neutral", "force") for g in body[sec]}
            page = {g["id"]: g["trades"] for g in c["page"]["groups"]}
            self.assertEqual(sorted(server), sorted(page), f"{c['label']}: the groups differ")
            for k, trades in page.items():
                g = server[k]
                self.assertEqual(g["alternatives"], len(trades), f"{c['label']} group {k}: alternatives")
                self.assertEqual(len(g["trades"]), len(trades), f"{c['label']} group {k}: alternatives listed")
                for i, (a, b) in enumerate(zip(g["trades"], trades)):
                    self.assertEqual(server_trade(a), {x: b[x] for x in server_trade(a)}, f"{c['label']} group {k} trade {i}")
            # Not vacuous: groups in two classes, the other side's word, Why panels.
            classes = {g.split("|")[1] for g in page}
            self.assertGreaterEqual(len(classes), 2, (c["label"], classes))
            self.assertTrue(any(t["them"] for ts in page.values() for t in ts), c["label"])
        self.assertTrue(any(t["waiver"] and t["waiver"]["demoted"] for c in self.cases for g in c["page"]["groups"] for t in g["trades"]),
                        "no demoted waiver alternative anywhere")
        self.assertTrue(any(g["id"].split("|")[1] == "natural" for c in self.cases for g in c["page"]["groups"]), "no natural fit anywhere")

    def test_why_mode_matches_the_page(self):
        self.assertGreaterEqual(sum(1 for a in self.why_asks if a[2] > 0), 20, "too few alternatives sampled")
        self.assertTrue(any(r["body"]["why"] for r in self.why_out), "no Why panel at all")
        for (n, gk, i, req), res in zip(self.why_asks, self.why_out):
            c = self.cases[n]
            want = next(g for g in c["page"]["groups"] if g["id"] == gk)["trades"][i]
            label = f"{c['label']} group {gk} alternative {i}"
            self.assertEqual(res["status"], 200, (label, res["body"]))
            body = res["body"]
            self.assertEqual(reply_findings(body, WHY_REPLY), [], label)
            self.assertTrue(body["found"], label)
            self.assertEqual(f"{body['team']}|{body['fit']}", "|".join(gk.split("|")[:2]), label)
            self.assertEqual(server_trade(body["trade"]), {x: want[x] for x in server_trade(body["trade"])}, label)
            self.assertEqual(server_why(body["why"]), want["why"], label)

    def test_default_reply_lists_ten_alternatives(self):
        c = self.cases[0]
        out = _node_driver([{"body": {k: v for k, v in c["request"].items() if k != "alternatives"}}], today=_today())["results"][0]
        self.assertEqual(out["status"], 200)
        groups = [g for s in ("natural", "neutral", "force") for g in out["body"][s]]
        self.assertTrue(any(g["alternatives"] > 10 for g in groups))
        self.assertTrue(all(len(g["trades"]) == min(10, g["alternatives"]) for g in groups))
        print(f"\nget-answers default reply: {len(out['text'])} bytes, {out['cpu_ms']} ms CPU (its own process, so it includes the cold load)")

    def test_same_order(self):
        for c in self.cases:
            body = c["reply"]["body"]
            self.assertEqual(capped(body["natural"] + body["neutral"]), c["page"]["listed"], f"{c['label']}: listed order (all offers)")
            self.assertEqual(capped(body["force"]), c["page"]["listed_force"], f"{c['label']}: listed order (force fits)")

    def test_same_partner_order_and_tier(self):
        for c in self.cases:
            body = c["reply"]["body"]
            self.assertEqual(body["partners"], c["page"]["rank"], f"{c['label']}: partner order")
            self.assertEqual(len(body["partners"]), 11, c["label"])
            want = c["page"]["tier"]
            got = {k: body["team"][k] for k in ("tier", "reason", "pct", "gain", "source", "headline", "line")}
            self.assertEqual(got, want, f"{c['label']}: opportunity tier")
            if "team_html_tier" in c["page"]:
                self.assertEqual(body["team"]["tier"], c["page"]["team_html_tier"], "team.html's tier")

    def test_reply_passes_the_allowlist_and_privacy_check(self):
        for c in self.cases:
            body = c["reply"]["body"]
            self.assertEqual(reply_findings(body), [], c["label"])
            self.assertNotIn("Access-Control-Allow-Origin", c["reply"]["headers"])  # no Origin sent

    def test_cpu_time_reported(self):
        # sizes 1-2, 11 partners: the first request also loads the site files; the others reuse them.
        rows = [(c["label"], c["reply"]["cpu_ms"], c["reply"]["wall_ms"]) for c in self.cases]
        print("\nget-answers CPU ms per request (first includes the cold load):", rows)
        self.assertTrue(all(cpu > 0 for _, cpu, _ in rows))


class GetAnswersContractTest(unittest.TestCase):
    """2-4. The allowlist, broken variants that leak per-chart fields, and refusals."""

    @classmethod
    def setUpClass(cls):
        league = _league()
        # Keys only (a client sends keys): even picks carry their key in the seeded league.
        resolved = {"me": 0, "teams": [{"index": i, "name": t["name"], "keys": [p["key"] for p in t["players"] if p.get("key")],
                                        "others": [{"pos": "K", "name": "Some Kicker"}] if i == 0 else []} for i, t in enumerate(league["teams"])]}
        cls.request = request_for(resolved, "ppr", 12, False, [1, 2], [], [], "")
        cls.today = _today()

    def test_banned_lists_agree(self):
        src = (FUNCTIONS / "get-answers" / "core.ts").read_text()
        block = src[src.index("export const BANNED = ["):]
        block = block[:block.index("];")]
        ts = [s.replace("\\\\", "\\") for s in re.findall(r'"((?:[^"\\]|\\.)*)"', block)]
        self.assertEqual(ts, ap.BANNED)

    def test_reply_is_allowlisted(self):
        out = _node_driver([{"body": self.request, "origin": "https://jb-barrel-droid.github.io"}], today=self.today)["results"][0]
        self.assertEqual(out["status"], 200, out["body"])
        self.assertEqual(reply_findings(out["body"]), [])
        self.assertEqual(out["headers"].get("access-control-allow-origin"), "https://jb-barrel-droid.github.io")
        self.assertEqual(len(out["body"]["partners"]), 11)
        self.assertTrue(out["body"]["neutral"] or out["body"]["natural"], "no offers at all: the check is vacuous")
        # The allowlist itself bites: an extra key or a chart-named value fails.
        bad = json.loads(json.dumps(out["body"]))
        bad["sources_included"] = ["x"]
        self.assertTrue(reply_findings(bad))
        bad = json.loads(json.dumps(out["body"]))
        bad["partners"][0]["ratio"] = 1.234
        self.assertTrue(reply_findings(bad))

    def _broken(self, anchor, patch):
        tmp = Path(tempfile.mkdtemp(prefix="get-answers-broken-"))
        try:
            for name in ("get-answers", "get-values"):
                shutil.copytree(FUNCTIONS / name, tmp / name)
            core = tmp / "get-answers" / "core.ts"
            src = core.read_text()
            self.assertIn(anchor, src, "broken-variant anchor not found in core.ts")
            core.write_text(src.replace(anchor, anchor + patch, 1))
            sent = _node_driver([{"body": self.request}], functions=tmp, today=self.today)["results"][0]
            leaked = _node_driver([{"body": self.request}], raw=True, functions=tmp, today=self.today)["results"][0]
            return sent, leaked
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_broken_variant_per_chart_nets_is_refused(self):
        sent, leaked = self._broken("give: keysOf(t.give), receive: keysOf(t.receive), ", "charts: t.charts, ")
        self.assertEqual(sent["status"], 500, "the function sent a reply carrying per-chart nets")
        self.assertEqual(sent["body"]["code"], "reply_not_allowed")
        problems = reply_findings(leaked["body"])
        self.assertTrue(any("charts: not in the allowlist" in p for p in problems), problems[:5])
        self.assertTrue(any("banned text" in p for p in problems), problems[:5])

    def test_broken_variant_chart_count_is_refused(self):
        sent, leaked = self._broken("give: keysOf(t.give), receive: keysOf(t.receive), ", "rivalOkCount: t.rivalOkCount, chartCount: t.chartCount, ")
        self.assertEqual(sent["status"], 500)
        self.assertEqual(sent["body"]["code"], "reply_not_allowed")
        problems = reply_findings(leaked["body"])
        self.assertTrue(any("rivalOkCount: not in the allowlist" in p for p in problems), problems[:5])

    def test_refusals(self):
        r = self.request
        cases = [
            ({**r, "include": "charts"}, 400, "not_in_answers"),
            ({**r, "basis": "fantasycalc"}, 400, "not_in_answers"),
            ({**r, "sources": ["cbs"]}, 400, "not_in_answers"),
            ({**r, "league": {**r["league"], "split": "charts"}}, 400, "not_in_answers"),
            ({**r, "sizes": [1, 2, 3]}, 400, "bad_sizes"),
            ({**r, "sizes": [3]}, 400, "bad_sizes"),
            ({**r, "extra": 1}, 400, "unknown_field"),
            ({**r, "skipped": [99]}, 400, "bad_skipped"),
            ({**r, "ov": "not an override"}, 400, None),
        ]
        out = _node_driver([{"body": b} for b, _, _ in cases] + [{"method": "GET"}], today=self.today)["results"]
        for (b, status, code), res in zip(cases, out):
            self.assertEqual(res["status"], status, (b.keys() - r.keys(), res["body"]))
            if code:
                self.assertEqual(res["body"]["code"], code, res["body"])
            self.assertEqual(ap.text_findings("refusal", json.dumps(res["body"])), [])
        self.assertEqual(out[-1]["status"], 405)

    def test_rate_limit_and_preflight(self):
        reqs = [{"body": {"bad": True}, "ip": "10.9.9.9"} for _ in range(31)] + [{"method": "OPTIONS", "origin": "http://localhost:3000"}]
        out = _node_driver(reqs, today=self.today)["results"]
        self.assertEqual([o["status"] for o in out[:30]], [400] * 30)
        self.assertEqual(out[30]["status"], 429)
        self.assertEqual(out[31]["status"], 204)
        self.assertEqual(out[31]["headers"].get("access-control-allow-origin"), "http://localhost:3000")


if __name__ == "__main__":
    unittest.main()
