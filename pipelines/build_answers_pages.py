"""JEG-1543: build the answers version of the site at dist/answers/ (no source names, no source data).

Jeremy, 2026-11-08 (decisions D1-D6 on 06-audit/jeg1543-answers-site-design-2026-11-08.md): same repo at a separate
path, the same engine, a pre-built grid of DDF Value tables for common settings and a server for the rest.

The build:
- copies the answers pages and scripts from app/answers/ (PAGE_FILES), stamped with the build tag like the root
  pages; the pages never carry the value engine, the players-data island or any source file;
- writes the answer tables with pipelines/answer_tables.cjs (get-values' own pipeline over this build's dist/),
  DDF outputs only;
- runs the privacy check (answers_privacy.check_tree) on the whole tree; a finding raises AnswersBuildError, and the
  sync then removes dist/answers (nothing unchecked is published) without stopping the full site.

noindex comes from sync's last step (site_noindex), like every other page. The pages are linked from no public page.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "answers"
DIST = ROOT / "dist"
TABLES = ROOT / "pipelines" / "answer_tables.cjs"
sys.path.insert(0, str(ROOT / "pipelines"))
from answers_privacy import PAGE_FILES, check_tree  # noqa: E402
from build_next_preview import LOCAL_ASSET, data_version_script  # noqa: E402

NODE = ["node", "--experimental-strip-types", "--no-warnings"]
BUILD_META = '<meta name="trade-chart-build" content="{tag}">'
# Tables are reused within a checkout when every input is unchanged (key = hash of the build tag and the files the
# tables are made from, plus this builder, the table script and the checker). CI's test shards run the sync once per
# test module; without the cache each run rebuilt the grid (about 3.5 min on a 4-core runner) and the shards passed
# their 30-minute limit. A cached grid already passed the full check, fingerprints included.
CACHE = ROOT / "build" / "answers-cache"
TABLE_INPUTS = ("assets/value-model.js", "assets/comparison-sources-data.json", "assets/lineup-parameters.json",
                "index.html")
CODE_INPUTS = ("pipelines/answer_tables.cjs", "pipelines/answers_privacy.py", "pipelines/build_answers_pages.py",
               "supabase/functions/get-values/league.ts", "supabase/functions/get-values/pipeline.ts")

# The build checks every table's columns against the sources (a stride over the sorted files would always land on the
# same bench size; review of #1396).
FINGERPRINT_EVERY = 1


class AnswersBuildError(RuntimeError):
    pass


def page_html(html: str, tag: str | None, name: str) -> str:
    if not tag:
        return html
    html = LOCAL_ASSET.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={tag}{m.group(3)}", html)
    head = re.search(r'<meta charset="[^"]*">', html, re.I)
    if not head:
        raise AnswersBuildError(f"{name}: no <meta charset> to carry the build tag")
    return html[:head.end()] + BUILD_META.format(tag=html_lib.escape(tag)) + data_version_script(tag) + html[head.end():]


def build_tag(dist: Path) -> str | None:
    index = dist / "index.html"
    if not index.exists():
        return None
    m = re.search(r'<meta name="trade-chart-build" content="([^"]*)">', index.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def write_tables(dist: Path, out: Path, cells: list[str] | None = None) -> None:
    cmd = [*NODE, str(TABLES), "--dist", str(dist), "--out", str(out)]
    if cells:
        cmd += ["--cells", ",".join(cells)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        raise AnswersBuildError(f"answer_tables failed (rc={proc.returncode}): {proc.stderr[-1500:]}")
    print(proc.stderr.strip())


def cache_key(dist: Path, tag: str | None, cells: list[str] | None) -> str:
    # The day (the week choice falls back to the calendar when history does not match the build) and node's version
    # are inputs too.
    import datetime
    day = os.environ.get("TRADE_VALUE_TODAY") or datetime.date.today().isoformat()
    node = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip() if shutil.which("node") else "-"
    h = hashlib.sha256(f"{tag}|{','.join(cells or [])}|{day}|{node}".encode())
    files = [dist / f for f in TABLE_INPUTS] + sorted((dist / "assets" / "history").glob("*.json")) + [ROOT / f for f in CODE_INPUTS]
    for path in files:
        h.update(path.name.encode())
        h.update(path.read_bytes() if path.exists() else b"-")
    return h.hexdigest()[:24]


def complete(data: Path) -> bool:
    """Every cell grid.json counts has its table, plus players.json."""
    try:
        cells = json.loads((data / "grid.json").read_text(encoding="utf-8"))["cells"]
    except (OSError, ValueError, KeyError):
        return False
    return (data / "players.json").exists() and len(list(data.glob("*-sf*-q*.json"))) == cells


def build(dist: Path = DIST, tag: str | None = None, source: Path = SOURCE, cells: list[str] | None = None,
          cache: Path | None = CACHE) -> Path:
    out = dist / "answers"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    tag = tag or build_tag(dist)
    for name in sorted(PAGE_FILES):
        src = source / name
        if not src.exists():
            raise AnswersBuildError(f"{name} is missing from {source}")
        text = src.read_text(encoding="utf-8")
        (out / name).write_text(page_html(text, tag, name) if name.endswith(".html") else text, encoding="utf-8")
    key = cache_key(dist, tag, cells) if cache else None
    hit = cache / key if key else None
    if hit and (hit / "checked").exists() and not complete(hit / "data"):
        shutil.rmtree(hit, ignore_errors=True)   # a partial cache is rebuilt, never published (review of #1396)
    if hit and (hit / "checked").exists():
        shutil.copytree(hit / "data", out / "data")
        print(f"answer_tables: reused the checked tables ({key})")
    else:
        write_tables(dist, out / "data", cells)
    bundle = json.loads((dist / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
    reused = bool(hit and (hit / "checked").exists())
    findings = check_tree(out, bundle, fingerprint_every=0 if reused else FINGERPRINT_EVERY)
    if findings:
        raise AnswersBuildError("answers privacy check failed:\n  " + "\n  ".join(findings[:40]))
    if hit and not reused:
        shutil.rmtree(cache, ignore_errors=True)   # keep only the current grid
        shutil.copytree(out / "data", hit / "data")
        (hit / "checked").write_text("ok\n", encoding="utf-8")
    return out


def node_ready() -> str | None:
    """None when node can run the edge function's .ts modules, else why not."""
    if shutil.which("node") is None:
        return "node is not installed"
    probe = f"require({json.dumps(str(ROOT / 'supabase/functions/get-values/league.ts'))})"
    proc = subprocess.run([*NODE, "-e", probe], capture_output=True, text=True)
    return None if proc.returncode == 0 else f"node cannot load the edge function's .ts modules: {proc.stderr.strip()[:200]}"


if __name__ == "__main__":
    reason = node_ready()
    if reason:
        raise SystemExit(f"build_answers_pages: {reason}")
    print(f"Wrote {build(cells=os.environ.get('ANSWERS_CELLS', '').split(',') if os.environ.get('ANSWERS_CELLS') else None)}")
