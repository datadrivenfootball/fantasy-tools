#!/usr/bin/env bash
# Run a Playwright browser install command with retries so a transient apt
# mirror outage (security.ubuntu.com / archive.ubuntu.com unresolvable, exit
# 100) cannot block a deploy.
#
# Usage: retry-browser-install.sh python3 -m playwright install --with-deps chromium
#
# 1. Tells apt to retry each fetch once with a 15s timeout, and caps each attempt at 5 minutes.
# 2. Runs the command up to 4 times, sleeping 20s, 40s, 60s between attempts.
# 3. If every attempt fails and the command used --with-deps, makes one last
#    try without it. With a warm ~/.cache/ms-playwright (actions/cache) that
#    skips apt and the browser download entirely; the OS libraries then have to
#    be on the runner image already. A cold cache still fails loudly.
set -u

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <install command...>" >&2
  exit 2
fi

# Short apt timeouts: with DNS down, apt retries each mirror and one attempt
# otherwise ran ~6 minutes (a 4-attempt run hung a job for 29 minutes).
printf 'Acquire::Retries "1";\nAcquire::http::Timeout "15";\nAcquire::https::Timeout "15";\n' | sudo tee /etc/apt/apt.conf.d/80-retries >/dev/null 2>&1 || true

max_attempts=4
for attempt in $(seq 1 "$max_attempts"); do
  echo "::group::browser install attempt ${attempt}/${max_attempts}"
  timeout 300 "$@"
  rc=$?
  echo "::endgroup::"
  if [ "$rc" -eq 0 ]; then
    exit 0
  fi
  echo "attempt ${attempt} failed with exit code ${rc}"
  if [ "$attempt" -lt "$max_attempts" ]; then
    delay=$((attempt * 20))
    echo "sleeping ${delay}s before retrying"
    sleep "$delay"
  fi
done

fallback=()
for arg in "$@"; do
  [ "$arg" = "--with-deps" ] || fallback+=("$arg")
done
if [ "${#fallback[@]}" -ne "$#" ]; then
  echo "::warning::apt unavailable after ${max_attempts} attempts; trying the install without --with-deps (needs a warm Playwright cache and OS libraries already on the runner)"
  timeout 300 "${fallback[@]}"
  exit $?
fi
exit "$rc"
