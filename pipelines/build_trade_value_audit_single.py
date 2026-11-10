#!/usr/bin/env python3
"""Single-file copy of the trade value audit draft (JEG-1565) for reading away from the repo.

Built from the real page, script and data (app/next/research/), so it never drifts:
the JS and the JSON are inlined, the site-relative links are dropped, and the file
makes no network request. Default output: the ddf-handoff audit folder.

Run: python3 pipelines/build_trade_value_audit_single.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "app" / "next" / "research"
DEFAULT_OUT = Path.home() / "Desktop" / "ddf-handoff 2" / "06-audit" / "trade-value-audit-draft.html"


def build_html(page: str = "trade-value-audit.html", data_file: str = "trade-value-audit-data.json") -> str:
    html = (SRC / page).read_text(encoding="utf-8")
    js = (SRC / "trade-value-audit.js").read_text(encoding="utf-8")
    data = json.loads((SRC / data_file).read_text(encoding="utf-8"))
    # Compact JSON; "</" escaped so the data can never close its <script> early.
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    js = js.replace("</script", "<\\/script")
    replacements = {
        '<a class="brand" href="../index.html">DATA DRIVEN FOOTBALL</a>': '<span class="brand">DATA DRIVEN FOOTBALL</span>',
        ' <a href="trade-value-audit-data.json">The data file</a>.': "",
        '<script src="trade-value-audit.js"></script>':
            f'<script id="tva-data" type="application/json">{blob}</script>\n<script>{js}</script>',
    }
    if page != "trade-value-audit.html":  # the charts-only variant names its own data file
        replacements[' <a href="trade-value-audit-data.json">The data file</a>.'.replace("data.json", "data-chartsonly.json")] = \
            replacements.pop(' <a href="trade-value-audit-data.json">The data file</a>.')
        replacements[' data-src="trade-value-audit-data-chartsonly.json"'] = ""
    for old, new in replacements.items():
        if old not in html:
            raise SystemExit(f"page changed; update the single-file builder: {old[:60]}")
        html = html.replace(old, new)
    return html


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--page", default="trade-value-audit.html")
    ap.add_argument("--data", default="trade-value-audit-data.json")
    args = ap.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_html(args.page, args.data), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
