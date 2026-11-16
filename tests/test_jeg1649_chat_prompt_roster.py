"""JEG-1649: the connect.html chat prompts take their default roster from the engine, not typed text.

Pinned here: the copied prompt (desktop and phone versions) names the engine's standard roster (the same text the
settings page shows), never the old hard-coded "WR 3, bench 6", and the page source holds no typed roster default.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_jeg1632_kdef_slots import SettingsPage as _Base  # noqa: E402

STANDARD_TEXT = "1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 DEF, 7 bench"


class ChatPromptRoster(unittest.TestCase):
    # Reuse the settings-page harness (server and browser) without inheriting its tests.
    setUpClass = classmethod(lambda cls: _Base.setUpClass.__func__(cls))
    tearDownClass = classmethod(lambda cls: _Base.tearDownClass.__func__(cls))

    def copied(self, width):
        context = self.browser.new_context(viewport={"width": width, "height": 900 if width > 760 else 812})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.defaultRoster && DDF.engine.defaultRoster()", timeout=60000)
        page.evaluate("() => { window.__copied = null; DDF.copyText = (t) => { window.__copied = t; }; }")
        page.click("#copy-prompt")
        text = page.evaluate("() => window.__copied")
        self.assertTrue(text, "prompt was copied")
        return page, text

    def test_copied_prompt_uses_engine_default_roster(self):
        for width in (1440, 375):
            with self.subTest(width=width):
                page, text = self.copied(width)
                engine_text = page.evaluate("() => DDF.engine.rosterText(DDF.engine.defaultRoster())")
                self.assertEqual(engine_text, STANDARD_TEXT)
                self.assertIn(f"default {engine_text}", text)
                self.assertNotIn("{{DEFAULT_ROSTER}}", text)
                self.assertNotIn("WR 3", text)
                self.assertNotIn("bench 6", text)

    def test_page_source_has_no_typed_roster_default(self):
        src = (ROOT / "app" / "next" / "connect.html").read_text()
        self.assertEqual(len(re.findall(r"\(default \{\{DEFAULT_ROSTER\}\}\)", src)), 2)
        self.assertIsNone(re.search(r"default QB ?1", src))


if __name__ == "__main__":
    unittest.main()
