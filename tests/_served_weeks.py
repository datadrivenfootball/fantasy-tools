"""Every source on the newest served week, for render tests whose premise is "no week transition".

After a weekly rollover a real source can stay on the older week for a day or more (2026-11-17: USA Today on
Week 10, the other six on Week 11). The engine then leaves it out of the newer week view (no carry-forward) and the
page shows the week selector, so a test that fakes a source a week behind, counts on a chart being shown, or measures
the phone context row turns red on the day's data rather than on the product. Such tests pin the served weeks the
same way they pin holds (tests/_holds.py). The transition itself is tests/test_week_selector_render.py's job.
"""
from __future__ import annotations

import json
from pathlib import Path

INDEX = "assets/history/index.json"
DETAIL = "assets/comparison-sources-data.json"


def newest_served_week(index: dict) -> int | None:
    weeks = [rec.get("week") for rec in (index.get("served") or {}).values() if isinstance(rec, dict)]
    weeks = [w for w in weeks if isinstance(w, int)]
    return max(weeks) if weeks else None


def pinned_documents(dist: Path, detail_transform=None) -> dict[str, str]:
    """{published path: JSON text} for the history index and source detail with every source on the newest week.

    Empty when nothing lags. The source's own label (week_designated) moves with it, as the week-selector harness
    does. Values are not touched: last week's numbers stand in for this week's, which is fine for label, layout and
    parity checks (the engine and the page read the same numbers).

    detail_transform: a function from the source detail to the detail to serve (e.g. a test's own holds, tests/_holds.py),
    applied after the week pin and served whether or not anything lags, so a pinned week never serves the day's holds."""
    index_path, detail_path = dist / INDEX, dist / DETAIL
    if not index_path.exists():
        return {}
    index = json.loads(index_path.read_text(encoding="utf-8"))
    newest = newest_served_week(index)
    moved = [key for key, rec in (index.get("served") or {}).items()
             if isinstance(rec, dict) and isinstance(rec.get("week"), int) and rec["week"] != newest]
    if not moved:
        if detail_transform is None or not detail_path.exists():
            return {}
        return {DETAIL: json.dumps(detail_transform(json.loads(detail_path.read_text(encoding="utf-8"))))}
    for key in moved:
        index["served"][key] = {**index["served"][key], "week": newest, "label_week": newest}
    out = {INDEX: json.dumps(index)}
    if detail_path.exists():
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        for key in moved:
            if isinstance(detail.get("sources", {}).get(key), dict):
                detail["sources"][key]["week_designated"] = f"Week {newest}"
        out[DETAIL] = json.dumps(detail_transform(detail) if detail_transform else detail)
    return out


def pin_served_weeks_in_dist(dist: Path) -> list[str]:
    """Rewrite a copied dist in place; returns the published paths rewritten."""
    docs = pinned_documents(dist)
    for path, text in docs.items():
        (dist / path).write_text(text, encoding="utf-8")
    return sorted(docs)


def route_pinned_weeks(page, dist: Path, detail_transform=None) -> None:
    """Serve the pinned documents to a Playwright page without touching `dist` (for harnesses that serve dist/)."""
    def handler(body: str):
        return lambda route, *_: route.fulfill(status=200, content_type="application/json", body=body)

    for path, text in pinned_documents(dist, detail_transform).items():
        page.route(f"**/{path}*", handler(text))
