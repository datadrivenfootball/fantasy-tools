"""Run every recipe line of a Makefile target, continuing past failures.

`make test-unit` used to stop at the first failing module: on 2026-10-08 one
playwright timeout in tests.test_espn_zero_badge_render meant the ~90 modules
after it (test_rebuild_chain_workflow, test_rebuild_chain_conflict_handoff ...)
never ran in preview CI. This runner reads the target's recipe lines from the
Makefile, runs each one, and exits 1 at the end listing every failed line.

Usage: python3 tests/run_suite.py [--makefile PATH] [--shard-index I --shard-count N] TARGET

Shards are one-based, round-robin partitions of the full command list, including
suite guards. Defaults preserve the unsharded run. CI may set
RUN_SUITE_SHARD_INDEX/COUNT instead; these are consumed before children run.
Every command logs its start, exit status and elapsed seconds.

Recipe lines may use make variables ($(NODE_CHROMIUM) in the node harness
lines): when any line contains "$", the runner asks `make -n` for the expanded
recipe instead of running it. Comment lines are skipped. A leading "python3 " runs with this interpreter, so the runner
also works where python3 is not on PATH (Windows).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def clean_command(line: str) -> str:
    return line.strip().lstrip("@-").strip()


def expanded_recipe_lines(makefile: Path, target: str) -> list[str]:
    """The recipe as make expands it (`make -n` prints, never runs, the commands)."""
    try:
        proc = subprocess.run(["make", "-n", "-s", "-f", str(makefile), target],
                              cwd=str(makefile.resolve().parent), capture_output=True,
                              text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"run_suite: {target} needs make to expand variables but make failed: {exc}")
    if proc.returncode != 0:
        raise SystemExit(f"run_suite: make -n {target} failed (rc={proc.returncode}): {proc.stderr.strip()}")
    commands = [clean_command(line) for line in proc.stdout.splitlines()]
    return [c for c in commands if c and not c.startswith("#")]


def recipe_lines(makefile: Path, target: str) -> list[str]:
    """The target's recipe commands, in order, without comments or @/- prefixes."""
    lines = makefile.read_text(encoding="utf-8").splitlines()
    header = re.compile(rf"^{re.escape(target)}\s*:(?!=)")
    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        raise SystemExit(f"run_suite: no target {target!r} in {makefile}")
    commands = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        command = clean_command(line)
        if not command or command.startswith("#"):
            continue
        if command.endswith("\\"):
            raise SystemExit(f"run_suite: {target} has a continued line the runner cannot split: {command}")
        commands.append(command)
    if any("$" in command for command in commands):
        commands = expanded_recipe_lines(makefile, target)
    if not commands:
        raise SystemExit(f"run_suite: target {target!r} has no commands")
    return commands


def run(commands: list[str], cwd: Path) -> list[str]:
    failed = []
    for command in commands:
        argv_command = command
        if command.startswith("python3 "):
            argv_command = f'"{sys.executable}" {command[len("python3 "):]}'
        print(command, flush=True)
        print(f"run_suite: START: {command}", flush=True)
        started = time.monotonic()
        rc = subprocess.run(argv_command, shell=True, cwd=str(cwd)).returncode
        elapsed = time.monotonic() - started
        print(f"run_suite: END (rc={rc}, {elapsed:.3f}s): {command}", flush=True)
        if rc != 0:
            failed.append(command)
            print(f"run_suite: FAILED (rc={rc}, {time.monotonic() - started:.0f}s): {command}", flush=True)
    return failed


def suite_guards(target: str) -> list[str]:
    """Cheap CI guards registered here without changing the Makefile recipes."""
    return (["python3 -m unittest tests.test_no_real_clock"]
            if target == "test-unit-modules" else [])


def shard_commands(commands: list[str], shard_index: int, shard_count: int) -> list[str]:
    """One-based round-robin partition; preserve order within each shard."""
    if shard_count < 1 or not 1 <= shard_index <= shard_count:
        raise ValueError("require 1 <= shard-index <= shard-count")
    return commands[shard_index - 1::shard_count]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target")
    parser.add_argument("--makefile", type=Path, default=ROOT / "Makefile")
    parser.add_argument("--shard-index", type=int, default=os.environ.get("RUN_SUITE_SHARD_INDEX", "1"))
    parser.add_argument("--shard-count", type=int, default=os.environ.get("RUN_SUITE_SHARD_COUNT", "1"))
    args = parser.parse_args(argv)
    if args.shard_count < 1 or not 1 <= args.shard_index <= args.shard_count:
        parser.error("require 1 <= shard-index <= shard-count")
    # Consume once: child tests may invoke this runner and must not inherit a shard.
    os.environ.pop("RUN_SUITE_SHARD_INDEX", None)
    os.environ.pop("RUN_SUITE_SHARD_COUNT", None)
    commands = suite_guards(args.target) + recipe_lines(args.makefile, args.target)
    commands = shard_commands(commands, args.shard_index, args.shard_count)
    failed = run(commands, args.makefile.resolve().parent)
    print(f"\nrun_suite: {args.target}: {len(commands) - len(failed)}/{len(commands)} passed", flush=True)
    for command in failed:
        print(f"run_suite: failed: {command}", flush=True)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::{args.target}: {command}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
