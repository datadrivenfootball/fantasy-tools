// Draft tool review preview (JEG-1667, Phase 1): one self-contained HTML
// page for Jeremy to review on his phone (a private page, never the live
// site). Inlines the page's CSS and scripts and a data bundle written by
// tools/draft_bundle.mjs, so it needs no network. The output holds
// third-party numbers: keep it out of the repo.
//
// Usage: node tools/draft_preview_build.mjs --bundle <bundle.json> --out <file.html>
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const arg = (name) => { const i = process.argv.indexOf(`--${name}`); return i === -1 ? null : process.argv[i + 1]; };
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
if (!arg("bundle") || !arg("out")) throw new Error("--bundle <bundle.json> --out <file.html> are required");

const page = read("app/draft/index.html");
const body = page.slice(page.indexOf("<body>") + 6, page.indexOf('<script src='));
const scripts = [...page.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => path.join("app/draft", m[1]));
const inline = (js) => js.replace(/<\/script/gi, "<\\/script");
const data = { bundle: JSON.parse(fs.readFileSync(arg("bundle"), "utf8")), lineup: JSON.parse(read("config/lineup_parameters.json")), preview: true };

const html = [
  "<title>DDF Auction Draft</title>",
  '<meta name="claude:viewport-fit-sides" content="cover">',
  '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap">',
  `<style>${read("app/draft/draft.css")}</style>`,
  body,
  `<script>window.DRAFT_PREVIEW = ${inline(JSON.stringify(data))};</script>`,
  ...scripts.map((s) => `<script>${inline(read(s))}</script>`),
  "<script>DraftApp.init();</script>",
].join("\n");
fs.writeFileSync(arg("out"), html);
process.stdout.write(JSON.stringify({ out: arg("out"), bytes: html.length, scripts }) + "\n");
