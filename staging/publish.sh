#!/usr/bin/env bash
# Publish staging/account/ to datadrivenfootball/ddf-staging (GitHub Pages, main branch root).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
gh repo clone datadrivenfootball/ddf-staging "$work" -- -q
rsync -a --delete --exclude .git "$here/account/" "$work/"
touch "$work/.nojekyll"
# The unpublished DDF ESPN extension, as a zip the staging page links to (load unpacked).
( cd "$here" && rm -rf "$work/.ext" && mkdir -p "$work/.ext/ddf-espn-extension" && cp extension/manifest.json extension/background.js extension/popup.html "$work/.ext/ddf-espn-extension/" \
  && cd "$work/.ext" && zip -qr -X "$work/ddf-espn-extension.zip" ddf-espn-extension ) && rm -rf "$work/.ext"
# Version-stamp the page's own files so phones never pair a new page with a cached old script.
ver="$(git -C "$here" rev-parse --short HEAD)-$(date +%s)"
for page in "$work"/*.html; do
  sed -i.bak -E -e "s#(src|href)=\"([a-z0-9-]+\.(js|css))\"#\1=\"\2?v=$ver\"#g" "$page" && rm "$page.bak"
done
cd "$work"
git add -A
if git diff --cached --quiet; then echo "staging already up to date"; exit 0; fi
git commit -q -m "Publish staging page from fantasy-tools $(git -C "$here" rev-parse --short HEAD) (JEG-1732)"
git push -q origin HEAD:main
echo "published: https://datadrivenfootball.github.io/ddf-staging/"
