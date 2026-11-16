"""JEG-1629: the Pages retry-infra job stays bounded and cannot mask a data failure."""
import re
import unittest
from pathlib import Path

from tests.test_preview_workflow_matches_pages import job

ROOT = Path(__file__).resolve().parent.parent
PAGES = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")


class PagesRetryInfraTest(unittest.TestCase):
    def setUp(self):
        self.retry = job(PAGES, "retry-infra")
        self.assertIsNotNone(self.retry, "retry-infra job missing")

    def test_runs_only_on_build_failure_on_main_without_prior_retry(self):
        self.assertIn("needs: [build]", self.retry)
        self.assertIn("if: always() && github.ref == 'refs/heads/main'", self.retry)
        self.assertIn("BUILD_RESULT: ${{ needs.build.result }}", self.retry)
        self.assertIn('[ "$BUILD_RESULT" != "failure" ]', self.retry)
        self.assertIn("github.ref == 'refs/heads/main'", self.retry)
        self.assertIn("inputs.retry_of == ''", self.retry)

    def test_dispatch_carries_retry_of_and_input_is_declared(self):
        self.assertRegex(self.retry, r'-f retry_of="\$RUN_ID"')
        self.assertRegex(PAGES, r"workflow_dispatch:\n    inputs:\n      retry_of:")

    def test_allowlist_has_only_infra_steps(self):
        m = re.search(r"allowed='(\[.*?\])'", self.retry)
        self.assertIsNotNone(m)
        self.assertEqual(
            sorted(re.findall(r'"([^"]+)"', m.group(1))),
            sorted(["Run actions/checkout@v4", "Browser for the render tests",
                    "Run actions/upload-pages-artifact@v3"]))
        self.assertNotRegex(m.group(1), r"make|gate|validate")

    def test_job_scoped_permission_and_no_widening(self):
        self.assertRegex(self.retry, r"    permissions:\n      actions: write")
        top = PAGES.split("\nconcurrency:")[0]
        self.assertNotIn("actions: write", top)

    def test_deploy_still_requires_successful_build_and_concurrency_intact(self):
        deploy = job(PAGES, "deploy")
        self.assertIn('[ "$BUILD_RESULT" = "success" ]', deploy)
        self.assertNotIn("retry-infra", deploy)
        self.assertRegex(PAGES, r"concurrency:\n  group: pages\n  cancel-in-progress: false")


if __name__ == "__main__":
    unittest.main()
