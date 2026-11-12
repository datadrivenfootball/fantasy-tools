"""JEG-1485 decision A (Jeremy, 2026-11-08): publication checks DATA only.

Week 6, 8 and 9 of 2026 went live 16 to 54 hours after every source had
landed because the chain's gate was the whole of test-core: a code test that
failed on new data (or a merge that broke one) held the week. Since then the
rebuild chain runs `make validate-data` (validate-base + data-gate) and the
Pages build runs the same two. test-core keeps gating PRs (preview.yml
shards) and every deploy except an automated data commit ("Automated ..."). These guards pin that split so it cannot drift either way.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
CHAIN = (ROOT / ".github" / "workflows" / "rebuild-chain.yml").read_text(encoding="utf-8")
PAGES = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
PREVIEW = (ROOT / ".github" / "workflows" / "preview.yml").read_text(encoding="utf-8")
RUNBOOK = (ROOT / "docs" / "week-held-runbook.md").read_text(encoding="utf-8")


def recipe(target: str, text: str = MAKEFILE) -> list[str]:
    m = re.search(rf"^{re.escape(target)}:[^\n]*\n((?:\t[^\n]*\n|\s*#[^\n]*\n)*)", text, re.M)
    if not m:
        return []
    return [ln.strip() for ln in m.group(1).splitlines() if ln.startswith("\t") and not ln.strip().startswith("#")]


def prerequisites(target: str, text: str = MAKEFILE) -> list[str] | None:
    m = re.search(rf"^{re.escape(target)}:([^\n]*)$", text, re.M)
    return m.group(1).split() if m else None


def gate_ids(text: str = MAKEFILE) -> list[str]:
    """Every test id the data gate names (a module, a class or one test)."""
    return [name for ln in recipe("data-gate", text) for name in ln.split()[3:]]


def _defines(module: str, rest: list[str]) -> bool:
    """True when tests/<module>.py defines class rest[0] (and its method rest[1])."""
    import ast
    tree = ast.parse((ROOT / "tests" / f"{module}.py").read_text(encoding="utf-8"))
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    if rest[0] not in classes:
        return False
    if len(rest) == 1:
        return True
    return rest[1] in {n.name for n in classes[rest[0]].body if isinstance(n, ast.FunctionDef)}


# JEG-1628 (Jeremy, 2026-11-12): synthetic replays that build a scenario from the
# week's data are code tests (test-core: PRs and the nightly deploy), never data
# checks. Each of these held a new week on its own premise (retro of the Week 10
# rollover, 2026-11-12): transition replays (JEG-1606, JEG-1618, JEG-1626), seeded
# per-source holds and lags (test_fantasycalc_lagging, Tue 2026-11-10), and the view
# invariants' per-series coverage minimum (150 of 225, Tue 2026-11-10).
REPLAYS = (
    "tests.test_rank_guard.TestEngineKeepsOrderInTransition",
    "tests.test_rank_guard.TestEngineKeepsOrderWithHeldLaggingChart",
    "tests.test_rank_guard.TestEngineKeepsOrderWithLiveHolds",
    "tests.test_rank_guard.TestEngineKeepsOrderWhenTheDefaultFallsBack",
    "tests.test_seeded_hold_build.SeededHoldBuildTest",
    "tests.test_seeded_hold_build.SourceScenarioFixtureTest",
    "tests.test_seeded_hold_build.SourceScenarioRenderTest",
    "tests.test_view_invariants.ViewInvariants.test_every_unheld_series_is_measured",
    "tests.test_week_history.WeekTransitionSentinelTest",
    "tests.test_week_history.DeltaRecomputeTest.test_delta_guard_fails_on_broken_states",
    "tests.test_week_history.DeltaRecomputeTest.test_unmatched_served_week_is_a_warning_not_a_crash",
)


def runs(gate: list[str], test_id: str) -> bool:
    """True when a gate entry runs test_id (the entry is the id or one of its parents)."""
    return any(test_id == g or test_id.startswith(g + ".") for g in gate)


class DataGateDefinition(unittest.TestCase):
    def test_validate_data_is_validate_base_plus_data_gate(self):
        self.assertEqual(prerequisites("validate-data"), ["validate-base", "data-gate"])
        self.assertEqual(recipe("validate-data"), [])

    def test_every_data_check_is_also_a_code_gate_test(self):
        core = {name for ln in recipe("test-core") if ln.startswith("python3 -m unittest ")
                for name in ln.split()[3:]}
        lines = recipe("data-gate")
        self.assertGreaterEqual(len(lines), 15)
        for line in lines:
            self.assertTrue(line.startswith("python3 -m unittest tests."), line)
        ids = gate_ids()
        for test_id in ids:
            module = ".".join(test_id.split(".")[:2])
            # A class or test line is covered when test-core runs its whole module.
            self.assertTrue(test_id in core or module in core, f"{test_id} is in data-gate but not test-core")
            rest = test_id.split(".")[2:]
            if rest:
                self.assertTrue(_defines(module.split(".")[1], rest), f"{test_id} does not exist")
        self.assertEqual(len(ids), len(set(ids)), "data-gate runs a test twice")

    def test_synthetic_replays_are_not_data_checks(self):
        gate = gate_ids()
        for replay in REPLAYS:
            module, rest = ".".join(replay.split(".")[:2]), replay.split(".")[2:]
            self.assertTrue(_defines(module.split(".")[1], rest), f"{replay} no longer exists; update REPLAYS")
            self.assertFalse(runs(gate, replay), f"{replay} builds a scenario from the week's data: code lane only")
            self.assertIn(f"python3 -m unittest {module}", recipe("test-core"), f"{replay} must stay in test-core")

    def test_a_replay_put_back_in_the_gate_is_caught(self):
        broken = MAKEFILE.replace("\tpython3 -m unittest tests.test_rank_guard.TestSavedValues ",
                                  "\tpython3 -m unittest tests.test_rank_guard ", 1)
        self.assertNotEqual(broken, MAKEFILE)
        self.assertTrue(runs(gate_ids(broken), "tests.test_rank_guard.TestEngineKeepsOrderWhenTheDefaultFallsBack"))

    def test_the_data_gate_is_exactly_the_reviewed_list(self):
        # A deliberate change to the list updates this set and the runbook together.
        self.assertEqual(set(gate_ids()), {f"tests.{m}" for m in (
            "test_site_noindex", "test_static_export",
            "test_rank_guard.TestSavedValues", "test_rank_guard.TestEngineKeepsOrderEverySetting",
            "test_view_invariants.ViewInvariants.test_every_view_holds_its_invariant",
            "test_games_remaining", "test_ppg_tie_parity", "test_kdst_removed",
            "test_comparison_source_integrity", "test_cbsros_bake_identity", "test_suffix_identity",
            "test_player_aliases", "test_razzball_refresh", "test_bake_on_change", "test_razzball_one_save",
            "test_player_scenario_matrix", "test_published_surfaces", "test_verify_live",
            "test_page_load_no_404", "test_lineup_content_week_advance",
            "test_week_history.WeekFileSchemaTest",
            "test_week_history.DeltaRecomputeTest.test_prior_week_is_engine_math_on_saved_inputs")})

    def test_the_export_and_published_number_guards_stay_in_the_data_gate(self):
        gate = gate_ids()
        for test_id in ("tests.test_static_export", "tests.test_rank_guard.TestSavedValues",
                        "tests.test_rank_guard.TestEngineKeepsOrderEverySetting",
                        "tests.test_view_invariants.ViewInvariants.test_every_view_holds_its_invariant",
                        "tests.test_week_history.DeltaRecomputeTest.test_prior_week_is_engine_math_on_saved_inputs",
                        "tests.test_comparison_source_integrity",
                        "tests.test_published_surfaces", "tests.test_lineup_content_week_advance"):
            self.assertTrue(runs(gate, test_id), test_id)
        self.assertIn("value-check-compare", prerequisites("validate-base"))
        self.assertIn("--strict", " ".join(recipe("value-check-compare")))

    def test_page_render_and_perturbation_tests_are_code_tests(self):
        for module in ("tests.test_team_opportunity_render", "tests.test_learn_engine_parity",
                       "tests.test_fractional_seats_stability", "tests.test_value_pipeline_engine",
                       "tests.test_waiver_band_line.BandMathTest"):
            self.assertFalse(runs(gate_ids(), module), module)

    def test_the_runbook_names_every_data_check(self):
        for test_id in gate_ids():
            self.assertIn(test_id.split(".", 1)[1], RUNBOOK, f"{test_id} is not documented")


class PublicationUsesTheDataGate(unittest.TestCase):
    def test_chain_validates_with_validate_data_both_times(self):
        self.assertEqual(CHAIN.count("--kind validation -- make validate-data > output/post-rebuild-validate"), 2)
        self.assertNotRegex(CHAIN, r"-- make validate >")

    def test_pages_build_runs_the_data_gate_and_only_data_commits_skip_test_core(self):
        self.assertIn("      - run: make validate-base\n", PAGES)
        self.assertRegex(PAGES, r"      - run: make data-gate\n(?!        continue-on-error)")
        deploy = PAGES[PAGES.index("\n  deploy:\n"):]
        self.assertIn("    needs: [build, validate-shard]\n", deploy)
        self.assertIn('[ "$BUILD_RESULT" = "success" ]', deploy)
        self.assertIn('"github-actions[bot]|Automated "*)', deploy)
        self.assertIn('*) [ "$SHARD_RESULT" = "success" ] ;;', deploy)

    def test_test_core_still_runs_on_main_and_gates_prs(self):
        self.assertIn("make test-core-shard-${{ matrix.shard }}", PAGES)
        self.assertIn("make test-core-shard-${{ matrix.shard }}", PREVIEW)
        self.assertIn("      - run: make data-gate\n", PREVIEW)

    def test_a_broken_definition_is_caught(self):
        broken = MAKEFILE.replace("validate-data: validate-base data-gate", "validate-data: validate-base", 1)
        self.assertNotEqual(prerequisites("validate-data", broken), ["validate-base", "data-gate"])
        extra = MAKEFILE.replace("\ndata-gate:\n", "\ndata-gate:\n\tpython3 -m unittest tests.test_not_in_core\n", 1)
        self.assertNotIn("python3 -m unittest tests.test_not_in_core", set(recipe("test-core", extra)))
        self.assertIn("python3 -m unittest tests.test_not_in_core", recipe("data-gate", extra))


if __name__ == "__main__":
    unittest.main()
