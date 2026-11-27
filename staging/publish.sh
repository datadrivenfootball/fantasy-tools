#!/usr/bin/env bash
# Publish staging/account/ to datadrivenfootball/ddf-staging (GitHub Pages, main branch root).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
gh repo clone datadrivenfootball/ddf-staging "$work" -- -q
rsync -a --delete --exclude .git "$here/account/" "$work/"
touch "$work/.nojekyll"
# Version-stamp the page's own files so phones never pair a new page with a cached old script.
ver="$(git -C "$here" rev-parse --short HEAD)-$(date +%s)"
sed -i.bak -e "s|src=\"app.js\"|src=\"app.js?v=$ver\"|" -e "s|href=\"connect-page.css\"|href=\"connect-page.css?v=$ver\"|" "$work/index.html" && rm "$work/index.html.bak"
cd "$work"
git add -A
if git diff --cached --quiet; then echo "staging already up to date"; exit 0; fi
git commit -q -m "Publish staging page from fantasy-tools $(git -C "$here" rev-parse --short HEAD) (JEG-1732)"
git push -q origin HEAD:main
echo "published: https://datadrivenfootball.github.io/ddf-staging/"
