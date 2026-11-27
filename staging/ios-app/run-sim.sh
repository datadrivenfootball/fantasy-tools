#!/usr/bin/env bash
# Build the DDF app for the booted iOS Simulator and launch it.
#   ./run-sim.sh            loads the DDF page
#   ./run-sim.sh harness    loads the local test harness (http://localhost:8791/ddf-staging/), signed in to DDF,
#                           with a "Test sign-in" button on the ESPN sheet that stands in for a real ESPN sign-in
#   ./run-sim.sh planted    as harness, but already signed in to ESPN (test session planted at launch)
set -euo pipefail
cd "$(dirname "$0")"
xcodebuild -project DDF.xcodeproj -scheme DDF -configuration Debug -destination 'generic/platform=iOS Simulator' -derivedDataPath build build | grep -E "error|BUILD" || true
app=build/Build/Products/Debug-iphonesimulator/DDF.app
id=com.datadrivenfootball.ddf
xcrun simctl terminate booted "$id" 2>/dev/null || true
xcrun simctl uninstall booted "$id" 2>/dev/null || true   # a clean start: no leftover sign-ins
xcrun simctl install booted "$app"
args=()
case "${1:-}" in
  harness) args=(-ddfBaseURL http://localhost:8791/ddf-staging/ -ddfHarnessSignedIn YES -ddfTestSignInButton YES) ;;
  planted) args=(-ddfBaseURL http://localhost:8791/ddf-staging/ -ddfHarnessSignedIn YES -ddfPlantTestESPN YES) ;;
esac
xcrun simctl launch booted "$id" "${args[@]}"
