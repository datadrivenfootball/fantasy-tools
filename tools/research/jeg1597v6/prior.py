"""Read-only access to the prior research code (v1-v5.1) that v6 builds on.

The v4/v5/v5.1 lane code lives on stacked draft PR branches, not on main. v6 never copies or
edits it: it imports it from a detached git worktree pinned at PRIOR_COMMIT (the head of
claude/JEG-1691-v51-prereg, which holds the locked v5 and v5.1 outputs). Set V6_PRIOR_TREE to
use another checkout of that same commit; `ensure()` creates the worktree when it is missing.
Nothing here writes into the prior tree.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PRIOR_COMMIT = "8105a5f787879b969fd5fbef47340a3ef30f635f"
DEFAULT_TREE = Path(os.environ.get("V6_PRIOR_TREE", str(REPO.parent / "ft-wt-jeg1597-v6-prior")))
LANES = ("jeg1597", "jeg1605", "jeg1610", "jeg1611", "jeg1611/shrink", "jeg1691", "jeg1691/v51")


def _git(*a, cwd=REPO):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()


def ensure(tree: Path = DEFAULT_TREE) -> Path:
    if not (tree / ".git").exists():
        _git("worktree", "add", "--detach", str(tree), PRIOR_COMMIT)
    head = _git("rev-parse", "HEAD", cwd=tree)
    if head != PRIOR_COMMIT:
        raise SystemExit(f"prior tree {tree} is at {head}, expected {PRIOR_COMMIT}")
    return tree


def activate(tree: Path = DEFAULT_TREE) -> Path:
    """Put the prior lanes and the prior tree's pipelines on sys.path (idempotent)."""
    tree = ensure(tree)
    paths = [tree / "pipelines"] + [tree / "tools" / "research" / lane for lane in LANES]
    for p in reversed(paths):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    return tree


def dirty(tree: Path = DEFAULT_TREE) -> list:
    """Tracked files changed in the prior tree (must stay empty: v6 never writes there)."""
    out = _git("status", "--porcelain", "--untracked-files=no", cwd=tree)
    return [ln for ln in out.splitlines() if ln.strip()]
