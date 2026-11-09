"""Guard: the CI speed-up settings stay in place (JEG-1169).

  - every workflow that installs Playwright browsers caches ~/.cache/ms-playwright
    with a key carrying the pinned Playwright version, and that version matches
    the python pin and tests/rendered_gate/package.json (both share one build);
  - Chromium is installed once per job: no `playwright-core install` after the
    python `playwright install`;
  - every preview job has a timeout (default is 6 hours) and v2-render has room for a
    slow browser install;
  - the docs-only skip on pull requests never skips a tests-only PR and keeps
    the docs the build reads.

Plain-text parsing on purpose (PyYAML is not on the CI runner). Each rule is
negative-tested against a mutated copy of the real file.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
BROWSER_WORKFLOWS = ("preview.yml", "pages.yml", "v2-render-test.yml", "full-suite.yml")
PR_FILTERED = ("preview.yml", "v2-render-test.yml")
BUILD_DOCS = ("docs/methodology.md", "docs/math-review-agenda.md", "docs/use-ddf-in-claude-chatgpt.md", "app/llm/**")
NPM_VERSION = json.loads((ROOT / "tests/rendered_gate/package.json").read_text(encoding="utf-8"))["dependencies"]["playwright-core"]

# The pre-shard browser gate's complete command inventory, including verbose mutation receipts.
RENDER_COMMANDS = (
    "tests.test_v2_contract_render",
    "tests.test_v2_finder_guardrails_render",
    "tests.test_interactive_trades_release_render",
    "tests.test_jeg1213_import tests.test_jeg1213_logic tests.test_jeg1213_summary_fields tests.test_jeg1213_acceptance_render",
    "tests.test_v2_finder_teams tests.test_v2_finder_teams_render",
    "-v tests.test_v2_waterfall_render",
    "tests.test_jeg1231_opponent_inclusion tests.test_jeg1231_opponent_inclusion_render tests.test_jeg1231_league_inclusion_render tests.test_jeg1263_simplified_site tests.test_jeg1263_simplified_site_render",
    "tests.test_week_stale_deadline tests.test_week_selector_render",
    "tests.test_jeg1380_finder_week_render",
    "-v tests.test_v2_compare_rosters_render",
    "tests.test_uso_site_journey_render tests.test_jeg1249_league_site_render",
    "tests.test_jeg1389_switch_redraw_render tests.test_jeg1389_link_settings_reload_render",
    "tests.test_jeg1266_ai_connection_panel tests.test_jeg1266_ai_connection_panel_render",
)


def render_schedule_problems(text):
    body = re.search(r"^  render-tests:\n(.*?)(?=^  [\w-]+:|\Z)", text, re.M | re.S)
    if not body:
        return ["missing render-tests job"]
    body = body.group(1)
    out = []
    matrix = re.search(r"^        lane: \[([^\]]+)\]$", body, re.M)
    lanes = [s.strip() for s in matrix.group(1).split(",")] if matrix else []
    if sorted(lanes) != ["contract", "journey", "league"]:
        out.append("incomplete or duplicate render matrix")
    if "      fail-fast: false" not in body or re.search(r"continue-on-error: true", body):
        out.append("render failures must stay visible")
    commands = []
    used = set()
    for step in re.split(r"^      - ", body, flags=re.M)[1:]:
        runs = re.findall(r"(?:^|\n)\s*run: python3 -m unittest ([^\n]+)", step)
        if runs:
            route = re.search(r"^if: matrix.lane == '([^']+)'", step)
            if not route or route.group(1) not in lanes:
                out.append("test command has no reachable unique lane")
            else:
                used.add(route.group(1))
            commands.extend(runs)
        for artifact, lane in (("jeg-1231-opponent-inclusion-shots", "league"), ("ai-panel-previews", "journey")):
            if f"name: {artifact}\n" in step and f"if: always() && matrix.lane == '{lane}'" not in step:
                out.append(f"artifact {artifact} must have one owner even on failure")
    if sorted(commands) != sorted(RENDER_COMMANDS):
        out.append("browser command coverage changed or duplicated")
    if used != set(lanes):
        out.append("empty render lane")
    return out


def read(name):
    return (WF / name).read_text(encoding="utf-8")


def browser_problems(name, text):
    out = []
    pins = set(re.findall(r"pip install --quiet playwright==([0-9.]+)", text))
    if len(pins) != 1:
        out.append(f"{name}: expected one python playwright pin, found {sorted(pins)}")
        return out
    pin = pins.pop()
    if pin != NPM_VERSION:
        out.append(f"{name}: python playwright {pin} != playwright-core {NPM_VERSION} (one browser build)")
    m = re.search(r"uses: actions/cache@v\d+\n\s+with:\n\s+path: ~/\.cache/ms-playwright\n\s+key: (.+)$", text, re.M)
    if not m:
        out.append(f"{name}: no actions/cache step for ~/.cache/ms-playwright")
    elif pin not in m.group(1):
        out.append(f"{name}: cache key {m.group(1)} does not carry playwright {pin}")
    elif text.index("~/.cache/ms-playwright") > text.index("playwright install"):
        out.append(f"{name}: the cache step must come before the browser install")
    if re.search(r"^\s+npx [^\n#]*playwright-core install", text, re.M):
        out.append(f"{name}: Chromium installed twice (playwright-core install after the python install)")
    return out


def job_timeout(text, job):
    m = re.search(rf"^  {re.escape(job)}:\n((?:    .*\n)+)", text, re.M)
    t = re.search(r"^    timeout-minutes: (\d+)$", m.group(1), re.M) if m else None
    return int(t.group(1)) if t else None


def pr_paths(text):
    m = re.search(r"^  pull_request:\n((?:    .*\n)+)", text, re.M)
    if not m:
        return None
    p = re.search(r"^    paths:\n((?:      - .*\n)+)", m.group(1), re.M)
    return re.findall(r"-\s+[\"']?([^\"'\n]+?)[\"']?\s*$", p.group(1), re.M) if p else []


def matches(pattern, path):
    rx = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(rx, path) is not None


def triggers(patterns, path):
    """GitHub `paths` semantics: last matching pattern wins, `!` excludes."""
    hit = False
    for p in patterns:
        neg = p.startswith("!")
        if matches(p[1:] if neg else p, path):
            hit = not neg
    return hit


def filter_problems(name, text):
    out = []
    if re.search(r"^    paths-ignore:", text, re.M):
        out.append(f"{name}: use `paths` with ! patterns, not paths-ignore")
    pats = pr_paths(text)
    if pats is None:
        return [f"{name}: no pull_request trigger"]
    if not pats:
        return out
    for path in ("tests/test_example.py", "pipelines/x.py", ".github/workflows/preview.yml",
                 "app/llm/skill/SKILL.md", "Makefile"):
        if not triggers(pats, path):
            out.append(f"{name}: a PR changing only {path} would skip the check")
    for path in BUILD_DOCS:
        probe = path.replace("**", "skill/SKILL.md")
        if not triggers(pats, probe):
            out.append(f"{name}: {probe} feeds the build but a PR changing it would skip the check")
    for path in ("README.md", "docs/claude-log/x.md", "docs/runbook.txt"):
        if triggers(pats, path):
            out.append(f"{name}: a docs-only PR ({path}) still runs the check")
    return out


def docs_only_job_problems(name, text):
    """JEG-1593: check that the docs-only detection job replaces the former paths filter.

    The pull_request trigger must have no paths filter. The docs-only job must
    exist and must classify BUILD_DOCS files as non-docs (they trigger the full
    check). A catch-all case must mark every other non-docs file as non-docs so
    tests-only PRs are never silently skipped.
    """
    out = []
    if pr_paths(text):  # non-empty => paths filter still present
        out.append(f"{name}: pull_request still has a paths filter; remove it (JEG-1593)")
    if not re.search(r"^  docs-only:\n", text, re.M):
        out.append(f"{name}: missing docs-only job")
        return out
    for path in BUILD_DOCS:
        # Strip glob suffix to get a matchable string in the shell case statement.
        probe = path.replace("/**", "").replace("**", "")
        if probe not in text:
            out.append(f"{name}: {path} not in docs-only job (would be mis-classified as docs)")
    if "*) docs_only=false" not in text:
        out.append(f"{name}: docs-only job has no catch-all for non-docs files (tests-only PRs would be skipped)")
    return out


class CiSpeedupTest(unittest.TestCase):
    def test_render_matrix_runs_the_complete_gate_once(self):
        self.assertEqual([], render_schedule_problems(read("v2-render-test.yml")))

    def test_render_matrix_catches_lost_coverage_and_hidden_failures(self):
        text = read("v2-render-test.yml")
        for old, new in (
            ("lane: [contract, league, journey]", "lane: [contract, league]"),
            ("lane: [contract, league, journey]", "lane: [contract, league, journey, journey]"),
            ("matrix.lane == 'contract'", "matrix.lane == 'absent'"),
            ("fail-fast: false", "fail-fast: true"),
            ("fail-fast: false", "fail-fast: false\n    continue-on-error: true"),
            ("        run: python3 -m unittest tests.test_v2_contract_render\n", ""),
            ("        run: python3 -m unittest tests.test_v2_contract_render\n",
             "        run: python3 -m unittest tests.test_v2_contract_render\n"
             "      - if: matrix.lane == 'contract'\n        run: python3 -m unittest tests.test_v2_contract_render\n"),
            ("if: always() && matrix.lane == 'league'", "if: always()"),
        ):
            with self.subTest(mutation=new):
                broken = text.replace(old, new, 1)
                self.assertNotEqual(text, broken)
                self.assertTrue(render_schedule_problems(broken))

    def test_real_workflows_cache_and_install_once(self):
        for name in BROWSER_WORKFLOWS:
            self.assertEqual([], browser_problems(name, read(name)))

    def test_real_timeouts(self):
        # JEG-1170: preview-build carries the ~45-minute budget; each test-core shard
        # and the aggregate `preview` check have their own, shorter one.
        self.assertTrue(45 < (job_timeout(read("preview.yml"), "preview-build") or 0) <= 90)
        self.assertTrue(15 < (job_timeout(read("preview.yml"), "preview-shard") or 0) <= 45)
        self.assertIsNotNone(job_timeout(read("preview.yml"), "preview"))
        self.assertGreaterEqual(job_timeout(read("v2-render-test.yml"), "render-tests") or 0, 25)
        self.assertIsNotNone(job_timeout(read("v2-render-test.yml"), "v2-render"))

    def test_real_docs_only_filter(self):
        # JEG-1593: the paths filter is gone; the docs-only job replaces it.
        for name in PR_FILTERED:
            self.assertEqual([], docs_only_job_problems(name, read(name)))

    def test_pages_has_no_path_filter(self):
        self.assertIsNone(re.search(r"paths", read("pages.yml")))

    def test_missing_cache_is_caught(self):
        text = read("preview.yml").replace("path: ~/.cache/ms-playwright", "path: ~/.cache/other")
        self.assertTrue(any("no actions/cache" in p for p in browser_problems("preview.yml", text)))

    def test_stale_cache_key_is_caught(self):
        text = read("pages.yml").replace("ms-playwright-${{ runner.os }}-1.49.1", "ms-playwright-${{ runner.os }}-1.48.0")
        self.assertTrue(any("does not carry" in p for p in browser_problems("pages.yml", text)))

    def test_second_install_is_caught(self):
        text = read("pages.yml").replace("npm ci --prefix tests/rendered_gate\n",
                                         "npm ci --prefix tests/rendered_gate\n"
                                         "          npx --prefix tests/rendered_gate playwright-core install --with-deps chromium\n", 1)
        self.assertTrue(any("installed twice" in p for p in browser_problems("pages.yml", text)))

    def test_version_drift_is_caught(self):
        text = read("v2-render-test.yml").replace("playwright==1.49.1", "playwright==1.50.0")
        self.assertTrue(any("one browser build" in p for p in browser_problems("v2-render-test.yml", text)))

    def test_missing_preview_timeout_is_caught(self):
        for job, minutes in (("preview-build", 60), ("preview-shard", 30), ("preview", 5)):
            text = re.sub(rf"    timeout-minutes: {minutes}\n", "", read("preview.yml"))
            self.assertIsNone(job_timeout(text, job), job)

    def test_filter_skipping_tests_is_caught(self):
        # JEG-1593: removing the catch-all case would silently skip tests-only PRs.
        text = read("preview.yml").replace("*) docs_only=false", "*) : # catch-all removed")
        self.assertNotEqual(read("preview.yml"), text)
        self.assertTrue(any("catch-all" in p for p in docs_only_job_problems("preview.yml", text)))

    def test_filter_dropping_build_docs_is_caught(self):
        # JEG-1593: removing a BUILD_DOCS path from the docs-only job would
        # mis-classify that file as docs and skip the check on PRs that change it.
        text = read("v2-render-test.yml").replace("docs/methodology.md", "docs/REMOVED.md")
        self.assertNotEqual(read("v2-render-test.yml"), text)
        self.assertTrue(any("docs/methodology.md" in p for p in docs_only_job_problems("v2-render-test.yml", text)))

    def test_matcher_semantics(self):
        self.assertTrue(matches("**/*.md", "README.md"))
        self.assertTrue(matches("**/*.md", "a/b/c.md"))
        self.assertTrue(matches("docs/**", "docs/a/b.txt"))
        self.assertFalse(matches("docs/**", "app/docs/x"))


if __name__ == "__main__":
    unittest.main()
