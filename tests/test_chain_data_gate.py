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


def gate_modules(text: str = MAKEFILE) -> list[str]:
    return [ln.split()[-1] for ln in recipe("data-gate", text)]


class DataGateDefinition(unittest.TestCase):
    def test_validate_data_is_validate_base_plus_data_gate(self):
        self.assertEqual(prerequisites("validate-data"), ["validate-base", "data-gate"])
        self.assertEqual(recipe("validate-data"), [])

    def test_every_data_check_is_also_a_code_gate_test(self):
        core = set(recipe("test-core"))
        lines = recipe("data-gate")
        self.assertGreaterEqual(len(lines), 15)
        for line in lines:
            self.assertTrue(line.startswith("python3 -m unittest tests."), line)
            self.assertIn(line, core, f"{line} is in data-gate but not test-core")
        self.assertEqual(len(lines), len(set(lines)), "data-gate runs a line twice")

    def test_the_data_gate_is_exactly_the_reviewed_list(self):
        # A deliberate change to the list updates this set and the runbook together.
        self.assertEqual(set(gate_modules()), {f"tests.{m}" for m in (
            "test_site_noindex", "test_static_export", "test_seeded_hold_build", "test_rank_guard",
            "test_view_invariants", "test_games_remaining", "test_ppg_tie_parity", "test_kdst_removed",
            "test_comparison_source_integrity", "test_cbsros_bake_identity", "test_suffix_identity",
            "test_player_aliases", "test_razzball_refresh", "test_bake_on_change", "test_razzball_one_save",
            "test_player_scenario_matrix", "test_published_surfaces", "test_verify_live",
            "test_page_load_no_404", "test_lineup_content_week_advance", "test_week_history")})

    def test_the_export_and_published_number_guards_stay_in_the_data_gate(self):
        for module in ("tests.test_static_export", "tests.test_seeded_hold_build", "tests.test_rank_guard",
                       "tests.test_view_invariants", "tests.test_comparison_source_integrity",
                       "tests.test_published_surfaces", "tests.test_lineup_content_week_advance"):
            self.assertIn(module, gate_modules())
        self.assertIn("value-check-compare", prerequisites("validate-base"))
        self.assertIn("--strict", " ".join(recipe("value-check-compare")))

    def test_page_render_and_perturbation_tests_are_code_tests(self):
        for module in ("tests.test_team_opportunity_render", "tests.test_learn_engine_parity",
                       "tests.test_fractional_seats_stability", "tests.test_value_pipeline_engine",
                       "tests.test_waiver_band_line.BandMathTest"):
            self.assertNotIn(module, gate_modules())

    def test_the_runbook_names_every_data_check(self):
        for module in gate_modules():
            self.assertIn(module.split(".", 1)[1], RUNBOOK, f"{module} is not documented")


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
        self.assertIn('"Automated "*)', deploy)
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
