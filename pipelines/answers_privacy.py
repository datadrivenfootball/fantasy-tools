"""JEG-1543: the privacy check for the answers version (/answers/): no source name or third-party number in it.

Jeremy, 2026-11-08: the answers version shows no source names, per-source values, chart comparisons or methodology
that names sources, and no source data reaches the browser on that path. This module is the check, used twice:

- at build time on every file under dist/answers/ (build_answers_pages.py fails the sync on any finding), and
- by tests/test_answers_site.py on what the browser actually receives (every response body and the rendered DOM).

Checks:
1. Banned text (case-insensitive): source and publisher names, the full site's names for source views, and the
   identifiers of the source files and islands (BANNED).
2. Numbers with 3 or more decimals anywhere (published factors, anchors and rescaled chart values carry them;
   every answers number is at 1 dp).
3. Exact schema for the answer tables and the players file (keys, fields, row shapes).
4. Column fingerprints: no table column (DDF Value, sd) equals one source's own column (published, superflex or
   rescaled values, at 1 dp) for most of its rows, so a table that swapped in a source's values fails even though
   its keys look right.
5. File allowlist: only the answers pages, their scripts and stylesheet, and data/*.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BANNED = [
    r"cbs", r"usa\s*today", r"usatoday", r"fantasy\s*pros", r"fantasy\s*calc", r"razzball", r"mike\s+clay",
    r"espn",  # the answers pages have no league-platform picker yet; when they do, allow it there by selector
    r"analyst\s+charts?", r"live\s+market", r"trade\s+charts?", r"chart_values", r"chart_indexed",
    r"published\s+values?", r"players-data", r"methodology-data", r"comparison-sources", r"reindex",
    r"source_provenance", r"sources_included", r"sources_excluded", r"missing_sources", r"basis_members",
]
BANNED_RE = re.compile("|".join(f"(?:{p})" for p in BANNED), re.I)
LONG_DECIMAL = re.compile(r"(?<![\w.])\d+\.\d{3,}(?![\w.])")

PAGE_FILES = frozenset({"index.html", "values.html", "answers.css", "answers-engine.js", "answers-home.js",
                        "answers-values.js"})
TABLE_KEYS = ["v", "cell", "build", "as_of", "week", "fields", "rows"]
ROW_FIELDS = ["key", "ddf", "sd", "low"]
PLAYER_KEYS = ["v", "build", "fields", "rows"]
PLAYER_FIELDS = ["key", "name", "pos", "team"]
GRID_KEYS = ["v", "build", "grid", "cells"]
CELL_ID = re.compile(r"^(standard|half_ppr|ppr)-\d+-sf\d-q\dw\df\d-b\d+$")
POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


def text_findings(name: str, text: str) -> list[str]:
    out = [f"{name}: banned text {m.group(0)!r} at {m.start()}" for m in BANNED_RE.finditer(text)]
    out += [f"{name}: number with 3+ decimals {m.group(0)!r}" for m in LONG_DECIMAL.finditer(text)]
    return out


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def table_findings(name: str, doc) -> list[str]:
    if not isinstance(doc, dict) or list(doc) != TABLE_KEYS:
        return [f"{name}: table keys {list(doc) if isinstance(doc, dict) else type(doc).__name__} != {TABLE_KEYS}"]
    out = []
    if doc["fields"] != ROW_FIELDS:
        out.append(f"{name}: fields {doc['fields']} != {ROW_FIELDS}")
    if not isinstance(doc["cell"], str) or not CELL_ID.match(doc["cell"]):
        out.append(f"{name}: bad cell id {doc['cell']!r}")
    for r in doc["rows"]:
        ok = (isinstance(r, list) and len(r) == 4 and isinstance(r[0], int) and _num(r[1])
              and (r[2] is None or _num(r[2])) and r[3] in (0, 1))
        if not ok:
            out.append(f"{name}: bad row {r!r}")
            break
    return out


def players_findings(name: str, doc) -> list[str]:
    if not isinstance(doc, dict) or list(doc) != PLAYER_KEYS:
        return [f"{name}: players keys != {PLAYER_KEYS}"]
    if doc["fields"] != PLAYER_FIELDS:
        return [f"{name}: fields {doc['fields']} != {PLAYER_FIELDS}"]
    for r in doc["rows"]:
        if not (isinstance(r, list) and len(r) == 4 and isinstance(r[0], int) and isinstance(r[1], str)
                and r[2] in POSITIONS and isinstance(r[3], str)):
            return [f"{name}: bad player row {r!r}"]
    return []


def source_columns(bundle: dict) -> dict[str, dict[int, float]]:
    """Every per-player numeric column in the source bundle, by player key, at 1 dp: {label: {key: value}}."""
    keys = bundle.get("player_keys") or {}
    cols: dict[str, dict[int, float]] = {}

    def walk(obj, label, depth):
        if depth > 5 or not isinstance(obj, dict):
            return
        named = {k: v for k, v in obj.items() if k in keys and _num(v)}
        if len(named) >= 20:
            cols[label] = {int(keys[k]): round(float(v), 1) for k, v in named.items()}
        for k, v in obj.items():
            if isinstance(v, dict):
                walk(v, f"{label}.{k}", depth + 1)

    for src, doc in (bundle.get("sources") or {}).items():
        walk(doc, src, 0)
    return cols


def fingerprint_findings(name: str, doc, columns: dict[str, dict[int, float]], share: float = 0.4,
                         min_rows: int = 20) -> list[str]:
    out = []
    rows = doc.get("rows") or []
    for field, idx in (("ddf", 1), ("sd", 2)):
        vals = {r[0]: round(float(r[idx]), 1) for r in rows if _num(r[idx])}
        for label, col in columns.items():
            both = [k for k in vals if k in col]
            if len(both) < min_rows:
                continue
            same = sum(1 for k in both if vals[k] == col[k] and col[k] != 0)
            if same / len(both) >= share:
                out.append(f"{name}: column {field} matches source column {label} on {same}/{len(both)} rows")
    return out


def check_tree(root: Path, bundle: dict | None = None, fingerprint_every: int = 1) -> list[str]:
    """All findings for a built answers tree (dist/answers). bundle = the same build's source bundle, for the
    fingerprints; fingerprint_every = N checks every Nth table (the build samples, the test checks all)."""
    findings: list[str] = []
    columns = source_columns(bundle) if bundle else {}
    tables = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        findings += text_findings(rel, text)
        if rel in PAGE_FILES:
            continue
        if not (rel.startswith("data/") and rel.endswith(".json") and rel.count("/") == 1):
            findings.append(f"{rel}: not an answers file (allowlist: the pages, their scripts, data/*.json)")
            continue
        doc = json.loads(text)
        base = rel[len("data/"):-len(".json")]
        if base == "players":
            findings += players_findings(rel, doc)
        elif base == "grid":
            if not isinstance(doc, dict) or list(doc) != GRID_KEYS:
                findings.append(f"{rel}: grid keys != {GRID_KEYS}")
        elif CELL_ID.match(base):
            findings += table_findings(rel, doc)
            if columns and tables % fingerprint_every == 0 and isinstance(doc, dict):
                findings += fingerprint_findings(rel, doc, columns)
            tables += 1
        else:
            findings.append(f"{rel}: unknown data file")
    return findings
