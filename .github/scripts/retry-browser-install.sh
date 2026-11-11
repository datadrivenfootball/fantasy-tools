#!/usr/bin/env bash
# Run a Playwright browser install command so an apt mirror outage
# (security.ubuntu.com / archive.ubuntu.com unresolvable, exit 100) cannot
# block a deploy.
#
# Usage: retry-browser-install.sh python3 -m playwright install --with-deps chromium
#
# JEG-1623: the GitHub runner image already carries the OS libraries Chromium
# needs (probed 2026-11-11 on ubuntu-26.04: `playwright install chromium`
# without --with-deps launches headless fine), and the browser download comes
# from the Playwright CDN, not apt. So:
#   1. Probe DNS for archive.ubuntu.com (5s cap). If it fails, skip apt and run
#      the command without --with-deps right away.
#   2. Otherwise run the full command (cap 180s per attempt, 3 attempts, 10s and
#      20s sleeps, apt fetch timeouts 15s, one retry).
#   3. If all attempts fail, fall back to the command without --with-deps.
set -u

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <install command...>" >&2
  exit 2
fi

without_deps=()
for arg in "$@"; do
  [ "$arg" = "--with-deps" ] || without_deps+=("$arg")
done

run_without_deps() {
  echo "::warning::$1; installing the browser without --with-deps (OS libraries come from the runner image)"
  timeout 120 "${without_deps[@]}"
  return $?
}

if [ "${#without_deps[@]}" -eq "$#" ]; then
  # Command has no --with-deps: nothing apt-related to skip.
  exec "$@"
fi

if ! timeout 5 getent hosts archive.ubuntu.com >/dev/null 2>&1; then
  run_without_deps "apt mirror DNS probe failed"
  exit $?
fi

printf 'Acquire::Retries "1";\nAcquire::http::Timeout "15";\nAcquire::https::Timeout "15";\n' | sudo tee /etc/apt/apt.conf.d/80-retries >/dev/null 2>&1 || true

max_attempts=3
rc=1
for attempt in $(seq 1 "$max_attempts"); do
  echo "::group::browser install attempt ${attempt}/${max_attempts}"
  timeout 180 "$@"
  rc=$?
  echo "::endgroup::"
  [ "$rc" -eq 0 ] && exit 0
  echo "attempt ${attempt} failed with exit code ${rc}"
  [ "$attempt" -lt "$max_attempts" ] && sleep $((attempt * 10))
done

run_without_deps "apt install failed after ${max_attempts} attempts"
exit $?
