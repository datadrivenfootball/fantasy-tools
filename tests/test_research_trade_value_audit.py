"""JEG-1565: the trade value audit draft is reproducible and stays private.

- the page's data file equals a fresh run of pipelines/research_trade_value_audit.py;
- every number quoted in the page text (data-n spans) equals the script output;
- the page is noindex, unlisted (not in Learn's list, not a root page) and no other page links to it;
- the framework's banned words stay off the page.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import research_trade_value_audit as audit  # noqa: E402

PAGE = ROOT / "app" / "next" / "research" / "trade-value-audit.html"
DATA = ROOT / "app" / "next" / "research" / "trade-value-audit-data.json"
SCRIPT = ROOT / "app" / "next" / "research" / "trade-value-audit.js"


def fmt(v) -> str:
    """Same as the page's fmt(): the script's value as written."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


class Spans(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.found, self.text = [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.stack.append(a.get("data-n"))
        if a.get("data-n"):
            self.found.append([a["data-n"], ""])

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)
        if self.stack and self.stack[-1] and self.found:
            self.found[-1][1] += data


def lookup(data, path):
    cur = data
    for key in path.split("."):
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    return cur


class AuditData(unittest.TestCase):
    """The article is one snapshot (week 9). Once the weekly refresh replaces
    data/fixtures/current, a fresh run describes a different week: the
    reproduction test then skips (check out the commit that published the
    snapshot to reproduce it), and the page-vs-data checks keep running."""

    @classmethod
    def setUpClass(cls):
        cls.saved = json.loads(DATA.read_text(encoding="utf-8"))
        cls.html = PAGE.read_text(encoding="utf-8")
        fixture = json.loads(audit.vr.FIXTURE.read_text(encoding="utf-8"))
        cls.same_snapshot = fixture.get("built_at") == cls.saved["fixture_built_at"]
        cls.fresh = json.loads(audit.dump(audit.build())) if cls.same_snapshot else cls.saved

    def test_data_file_equals_a_fresh_run(self):
        if not self.same_snapshot:
            self.skipTest("fixture moved past the week 9 snapshot; reproduce at the publishing commit")
        self.assertEqual(self.fresh, self.saved, "run: python3 pipelines/research_trade_value_audit.py")

    def test_every_quoted_number_equals_the_script(self):
        p = Spans()
        p.feed(self.html)
        self.assertGreater(len(p.found), 60)
        for path, text in p.found:
            with self.subTest(path=path):
                self.assertEqual(fmt(lookup(self.fresh, path)), text.strip())

    def test_headline_facts(self):
        h = self.fresh["headline"]
        self.assertEqual(0, h["fantasypros_numbers_changed_pct"])
        self.assertEqual(0, h["fantasycalc_top_flex_reordered"])
        f = self.fresh["fantasycalc_scoring_factors"]
        self.assertLessEqual(f["RB"]["spread"], 0.002)
        self.assertLessEqual(f["WR"]["spread"], 0.002)
        for k in audit.CHARTS:
            self.assertGreaterEqual(h["pairs_raw"][k], h["pairs_after_waiver"][k])

    def test_scorecard_levels_follow_the_rules(self):
        card = self.fresh["scorecard"]
        self.assertEqual("Weak", card["fantasypros"]["scoring"]["label"])
        self.assertEqual("OK", card["fantasycalc"]["scoring"]["label"])
        self.assertEqual("Weak", card["cbs"]["depth"]["label"])
        self.assertEqual(set(audit.CHARTS), set(card))  # the four redraft charts only; DDF Value is never graded
        self.assertEqual("Strong", card["cbs"]["curve"]["label"])   # close to the reference curve
        self.assertEqual("Weak", card["usatoday"]["curve"]["label"])
        self.assertEqual("Weak", card["usatoday"]["depth"]["label"])  # reaching past counts like stopping short
        self.assertEqual("Strong", card["cbs"]["superflex"]["label"])  # coverage: superflex values for 24+ QBs
        self.assertEqual("Weak", card["cbs"]["qb_sf"]["label"])        # but its QB share is Far from DDF Value
        self.assertEqual("Strong", card["fantasypros"]["qb_sf"]["label"])
        for k in audit.CHARTS:
            listed, ros = self.fresh["sources"][k]["listed"], self.fresh["sources"][k]["rostered"]
            gap = sum(abs(listed[p] - ros[p]) / ros[p] for p in ("QB", "RB", "WR", "TE")) / 4
            self.assertEqual(round(100 * gap), card[k]["depth"]["value"])

    def test_scoring_claims_come_from_the_publishers_raw_output(self):
        prov = self.fresh["scoring_provenance"]
        self.assertEqual([100] * 5, prov["identical_std_vs_ppr_pct_by_week"]["fantasypros"])
        caps = prov["fantasycalc_captures"]
        self.assertEqual("week 4 cache", caps[0]["capture"])
        self.assertGreater(caps[0]["RB"]["reordered"], 0)
        for cap in caps[1:]:  # every capture from 2026-10-04 on, live pull included
            for p in ("RB", "WR", "TE"):
                self.assertEqual(0, cap[p]["reordered"], cap["capture"])
        self.assertTrue(all("ppr=0" in c["urls"][0] and "ppr=1" in c["urls"][1] for c in caps if "urls" in c))

    def test_depth_against_the_waiver_line(self):
        dv = self.fresh["depth_vs_waiver"]
        for p in ("QB", "RB", "WR", "TE"):
            cbs = dv["sources"]["cbs"]["12"][p]
            self.assertEqual("short", cbs["class"])
            self.assertEqual(cbs["rostered"] - cbs["listed"], cbs["unpriced"])
            self.assertEqual("past", dv["sources"]["usatoday"]["12"][p]["class"])
        past = {k: v["12"]["value_past_line_pct"] for k, v in dv["sources"].items()}
        self.assertEqual("usatoday", max(past, key=past.get))

    def test_page_data_carries_no_chart_tables(self):
        """The article publishes derived measures (shares, ranks, percent of each chart's #1), not the charts' tables."""
        text = DATA.read_text(encoding="utf-8")
        self.assertNotIn('"published"', text)
        self.assertNotIn('"last_value"', text)
        for row in self.fresh["players"]:
            for v in row["pct_of_top"].values():
                self.assertTrue(v is None or 0 <= v <= 100)

    def test_every_source_link_is_listed_and_alive(self):
        links = {l["url"] for l in self.fresh["source_links"]["links"]}
        hrefs = {h.replace("&amp;", "&") for h in re.findall(r'href="(https?://[^"]+)"', self.html)}
        self.assertEqual(set(), hrefs - links, "every external link on the page must be in SOURCE_LINKS")
        self.assertEqual(set(), links - hrefs, "every SOURCE_LINKS entry must appear on the page")
        check = {row["url"]: row for row in json.loads((ROOT / "data/research/jeg1565/link-check.json").read_text(encoding="utf-8"))}
        for url in links:
            self.assertIn(url, check, "run pipelines/check_trade_value_audit_links.py")
            status = check[url]["status"]
            self.assertTrue(status == "not_checked_robots" or (isinstance(status, int) and 200 <= status < 400), (url, status))
        self.assertEqual(len(re.findall(r'href="https?://', self.html)), len(re.findall(r'target="_blank" rel="noopener noreferrer"', self.html)))

    def test_no_projection_sources_or_self_grading_on_the_page(self):
        p = Spans()
        p.feed(self.html)
        text = " ".join(p.text)
        for word in ("ESPN", "Razzball", "DynastyProcess", "our model gives", "Our model on the same scorecard"):
            self.assertNotIn(word, text)
        self.assertNotIn("ddf", self.fresh["scorecard"])

    def test_realized_scoring_benchmark(self):
        rs = self.fresh["realized_scoring"]
        self.assertEqual((2015, 2025), (rs["first_season"], rs["last_season"]))
        self.assertLessEqual(rs["min"], rs["season_min"])
        self.assertLessEqual(rs["season_max"], rs["max"])
        self.assertIn("about %d%%" % rs["pooled"], self.fresh["rules"]["scoring"])
        for k in ("cbs", "usatoday", "fantasypros", "fantasycalc"):  # every chart reorders less than real outcomes
            self.assertLess(self.fresh["headline"]["reorder_avg_pct"][k], rs["pooled"])

    def test_reorder_spread_logic(self):
        h = self.fresh["headline"]
        r = h["reorder_avg_pct"]
        self.assertEqual(0, r["fantasypros"])
        self.assertEqual(0, r["fantasycalc"])
        self.assertEqual(max(r[k] for k in audit.CHARTS) - min(r[k] for k in audit.CHARTS), h["reorder_chart_spread"])
        self.assertEqual(abs(r["usatoday"] - r["cbs"]), h["reorder_cbs_usatoday_gap"])
        self.assertEqual(h["reorder_cbs_usatoday_gap"] / 2, h["reorder_half_gap"])

    def test_pie_shares_in_depth(self):
        dv = self.fresh["depth_vs_waiver"]
        cbs = dv["sources"]["cbs"]["12"]
        self.assertEqual(round(100 * 22 / 65), cbs["RB"]["unpriced_players_pct"])  # 22 of 65 backs, as in the prose
        self.assertEqual(0, cbs["value_past_line_pct"])                            # it never reaches past the line
        for k, v in dv["sources"].items():
            row = v["12"]
            self.assertAlmostEqual(row["value_past_line_pct"], sum(row[p]["past_value_pct"] for p in ("QB", "RB", "WR", "TE")), delta=0.25)
            self.assertLessEqual(row["unpriced_value_pct"], 100)

    def test_curve_readout_names_line_up_with_values(self):
        for sc, lines in self.fresh["curves"].items():
            for k, vals in lines.items():
                self.assertEqual(len(vals), len(self.fresh["curve_players"][sc][k]), (sc, k))

class ChartsOnlyVariant(unittest.TestCase):
    """The post-flip variant (JEG-1569 charts-only position split): page numbers equal its data
    file, which is produced by running the script on a value model with DDF_VALUE_SPLIT=charts:
    AUDIT_ENGINE_DIR=<checkout>/pipelines DDF_VALUE_SPLIT=charts python3 pipelines/research_trade_value_audit.py
        --out app/next/research/trade-value-audit-data-chartsonly.json"""
    PAGE = ROOT / "app" / "next" / "research" / "trade-value-audit-chartsonly.html"
    DATA = ROOT / "app" / "next" / "research" / "trade-value-audit-data-chartsonly.json"

    def test_numbers_equal_its_data(self):
        data = json.loads(self.DATA.read_text(encoding="utf-8"))
        p = Spans()
        p.feed(self.PAGE.read_text(encoding="utf-8"))
        self.assertGreater(len(p.found), 60)
        for path, text in p.found:
            with self.subTest(path=path):
                self.assertEqual(fmt(lookup(data, path)), text.strip())

    def test_split_is_the_four_charts(self):
        data = json.loads(self.DATA.read_text(encoding="utf-8"))
        sf = [data["superflex"][k]["qb_share_sf"] for k in audit.CHARTS]
        self.assertAlmostEqual(sum(sf) / 4, data["superflex"]["ddf_value"]["qb_share_sf"], delta=0.15)
        text = self.PAGE.read_text(encoding="utf-8")
        self.assertNotIn("three sevenths", text)
        self.assertIn('noindex, nofollow', text)


class StaysPrivate(unittest.TestCase):
    def test_page_is_noindex(self):
        self.assertIn('<meta name="robots" content="noindex, nofollow">', PAGE.read_text(encoding="utf-8"))

    def test_not_listed_or_linked(self):
        posts = (ROOT / "app" / "next" / "learn" / "posts.json").read_text(encoding="utf-8")
        self.assertNotIn("trade-value-audit", posts)
        import build_root_pages
        self.assertFalse(any("research" in f for f in (*build_root_pages.ROOT_PAGES, *build_root_pages.ROOT_FILES)))
        for path in (ROOT / "app").rglob("*"):
            if path.is_file() and path.suffix in {".html", ".js", ".json", ".md", ".txt"} and "research" not in path.parts:
                self.assertNotIn("trade-value-audit", path.read_text(encoding="utf-8", errors="ignore"), str(path))


class Wording(unittest.TestCase):
    def test_banned_words(self):
        p = Spans()
        p.feed(PAGE.read_text(encoding="utf-8"))
        text = " ".join(p.text) + " " + SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(text, re.compile(r"player pool", re.I))
        bare = [m.start() for m in re.finditer(r"\bmarket\b", text, re.I) if text[max(0, m.start() - 5):m.start()].lower() != "live "]
        self.assertEqual([], bare, "the bare word 'market' is banned; use 'Live market' or 'Analyst charts'")
        self.assertNotRegex(text, re.compile(r"\b(demo|illustrative|mock)\b", re.I))


if __name__ == "__main__":
    unittest.main()
