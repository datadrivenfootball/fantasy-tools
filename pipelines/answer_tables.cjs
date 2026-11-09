#!/usr/bin/env node
// JEG-1543: the answers version's pre-built DDF Value tables (decisions D1/D2, Jeremy 2026-11-08).
//
// For every setting in the grid it runs get-values' own pipeline (supabase/functions/get-values/league.ts and
// pipeline.ts over dist/assets/value-model.js, the modules tests/_edge_pipeline_runner.cjs uses), loaded once, and
// writes only DDF outputs: per player the DDF Value, its noise (sd = |charts version - projections version| / 2, the
// finder's DDF-side noise) and the low-confidence flag (one source counted). No source name, per-source value, fit factor or
// anchor reaches the output: every record is built from an allowlist (TABLE_KEYS / PLAYER_KEYS) and checked again
// before it is written (pipelines/build_answers_pages.py checks the files once more).
//
// Usage: node --experimental-strip-types --no-warnings pipelines/answer_tables.cjs --dist dist --out dist/answers/data
//        [--cells ppr-12-sf0-q1w2f1-b7,...]   (only those cells; tests)
//        [--print-cell ppr-12-sf0-q1w2f1-b7]  (print one cell's table to stdout, write nothing)
"use strict";

const { readFileSync, writeFileSync, mkdirSync } = require("fs");
const { resolve, join } = require("path");
const os = require("os");
const { Worker, isMainThread, parentPort, workerData } = require("worker_threads");

const ROOT = resolve(__dirname, "..");
const { mapLeague } = require(join(ROOT, "supabase/functions/get-values/league.ts"));
const { buildPipelineInput, planWeek, todayIso } = require(join(ROOT, "supabase/functions/get-values/pipeline.ts"));

// The grid (design section 2): RB 2 and TE 1 fixed; everything else is computed by the server (phase 2).
const GRID = {
  scoring: ["standard", "half_ppr", "ppr"],
  teams: [8, 10, 12, 14],
  sf: [0, 1, 2],
  qb: [1, 2],
  wr: [2, 3],
  flex: [1, 2],
  bench: [5, 6, 7, 8, 9, 10],
};
const SCHEMA = 1;
// Allowlists: the only keys an answers table or the players file may carry.
const TABLE_KEYS = ["v", "cell", "build", "as_of", "week", "fields", "rows"];
const ROW_FIELDS = ["key", "ddf", "sd", "low"];
const PLAYER_KEYS = ["v", "build", "fields", "rows"];
const PLAYER_FIELDS = ["key", "name", "pos", "team"];
const POSITIONS = new Set(["QB", "RB", "WR", "TE"]);

function cellId(c) {
  return `${c.scoring}-${c.teams}-sf${c.sf}-q${c.qb}w${c.wr}f${c.flex}-b${c.bench}`;
}
function parseCell(id) {
  const m = /^(standard|half_ppr|ppr)-(\d+)-sf(\d)-q(\d)w(\d)f(\d)-b(\d+)$/.exec(id);
  if (!m) throw new Error(`bad cell id ${id}`);
  return { scoring: m[1], teams: +m[2], sf: +m[3], qb: +m[4], wr: +m[5], flex: +m[6], bench: +m[7] };
}
function allCells() {
  const out = [];
  for (const scoring of GRID.scoring) for (const teams of GRID.teams) for (const sf of GRID.sf)
    for (const qb of GRID.qb) for (const wr of GRID.wr) for (const flex of GRID.flex) for (const bench of GRID.bench)
      out.push({ scoring, teams, sf, qb, wr, flex, bench });
  return out;
}

const round1 = (v) => (typeof v === "number" && Number.isFinite(v) ? Math.round(v * 10) / 10 : null);

function loadBundle(distDir) {
  const ValueModel = require(join(distDir, "assets/value-model.js"));
  const detail = JSON.parse(readFileSync(join(distDir, "assets/comparison-sources-data.json"), "utf8"));
  const html = readFileSync(join(distDir, "index.html"), "utf8");
  const match = html.match(/id="players-data"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) throw new Error("players-data island not found in dist/index.html");
  const players = JSON.parse(match[1]).players;
  let history = null;
  try {
    const index = JSON.parse(readFileSync(join(distDir, "assets/history/index.json"), "utf8"));
    const docs = {};
    for (const [week, meta] of Object.entries(index.weeks || {})) {
      try {
        const doc = JSON.parse(readFileSync(join(distDir, meta.file), "utf8"));
        if (doc.week === Number(week)) docs[week] = doc;
      } catch (e) { /* an unpublished week stays unloaded, as in the function */ }
    }
    history = { index, docs };
  } catch (e) { /* no week history: the calendar rule applies */ }
  let lineupConfig = null;
  try { lineupConfig = JSON.parse(readFileSync(join(distDir, "assets/lineup-parameters.json"), "utf8")); } catch (e) { /* slices mode */ }
  const tagMatch = html.match(/<meta name="trade-chart-build" content="([^"]*)">/);
  return { bundle: { detail, players, ValueModel, lineupConfig, history }, build: tagMatch ? tagMatch[1] : null,
    asOf: typeof detail.built_at === "string" ? detail.built_at.replace(/\.\d+/, "") : null };
}

function league(c) {
  return { scoring: c.scoring, teams: c.teams,
    roster: { QB: c.qb, RB: 2, WR: c.wr, TE: 1, FLEX: c.flex, SUPERFLEX: c.sf, BENCH: c.bench } };
}

function table(loaded, c, today) {
  const { bundle } = loaded;
  const mapped = mapLeague(league(c), bundle.lineupConfig);
  const plan = planWeek(bundle, mapped, null, today);
  if (!plan.ok) throw new Error(`${cellId(c)}: ${plan.error}`);
  const input = buildPipelineInput(bundle, mapped, plan);
  const pipeline = bundle.ValueModel.runValuePipeline({ ...input, basisConfig: null });
  const rows = [];
  for (const [pk, r] of Object.entries(pipeline.rows || {})) {
    const v = r.ddfByVersion || {};
    const ddf = round1(v.blended && v.blended.value);
    // Only priced players above 0 are listed: a player in players.json who is not in a table is priced at 0 there
    // (below the waiver line; "no price is an implied 0"), which keeps a table near 1-2 KB gzipped.
    if (ddf === null || ddf <= 0) continue;
    const charts = round1(v.charts && v.charts.value), projs = round1(v.projections && v.projections.value);
    const sd = charts !== null && projs !== null ? round1(Math.abs(charts - projs) / 2) : null;
    rows.push([Number(pk), ddf, sd, v.blended.count === 1 ? 1 : 0]);
  }
  rows.sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  return { v: SCHEMA, cell: cellId(c), build: loaded.build, as_of: loaded.asOf, week: weekOf(plan), fields: ROW_FIELDS, rows };
}
const weekOf = (plan) => (Number.isInteger(plan.week) ? plan.week : null);

function playersFile(loaded, keys) {
  const rows = [];
  for (const p of loaded.bundle.players) {
    const key = Number(p.player_key);
    if (!keys.has(key) || !POSITIONS.has(p.pos)) continue;
    rows.push([key, String(p.name || ""), p.pos, String(p.team || "")]);
  }
  rows.sort((a, b) => a[0] - b[0]);
  return { v: SCHEMA, build: loaded.build, fields: PLAYER_FIELDS, rows };
}

// The write-time schema check: exact keys, exact row shapes, numbers only where numbers belong.
function checkTable(t) {
  const keys = Object.keys(t);
  if (keys.join() !== TABLE_KEYS.join()) throw new Error(`table keys ${keys} != ${TABLE_KEYS}`);
  if (t.fields.join() !== ROW_FIELDS.join()) throw new Error("table fields changed");
  for (const r of t.rows) {
    if (r.length !== ROW_FIELDS.length || !Number.isInteger(r[0]) || typeof r[1] !== "number"
        || !(r[2] === null || typeof r[2] === "number") || !(r[3] === 0 || r[3] === 1)) {
      throw new Error(`${t.cell}: bad row ${JSON.stringify(r)}`);
    }
  }
}
function checkPlayers(p) {
  if (Object.keys(p).join() !== PLAYER_KEYS.join()) throw new Error("players keys changed");
  for (const r of p.rows) {
    if (r.length !== PLAYER_FIELDS.length || !Number.isInteger(r[0]) || !POSITIONS.has(r[2])
        || typeof r[1] !== "string" || typeof r[3] !== "string") throw new Error(`bad player row ${JSON.stringify(r)}`);
  }
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 2) args[argv[i].replace(/^--/, "")] = argv[i + 1];
  return args;
}

// One worker's share: load the bundle once, write its tables, return the player keys they list.
function runCells(distDir, outDir, cellIds, today) {
  const loaded = loadBundle(distDir);
  const keys = [];
  for (const id of cellIds) {
    const t = table(loaded, parseCell(id), today);
    checkTable(t);
    t.rows.forEach((r) => keys.push(r[0]));
    writeFileSync(join(outDir, `${t.cell}.json`), JSON.stringify(t));
  }
  return keys;
}

async function main() {
  const args = parseArgs(process.argv);
  const distDir = resolve(args.dist || join(ROOT, "dist"));
  const today = process.env.TRADE_VALUE_TODAY || todayIso();
  if (args["print-cell"]) {
    const t = table(loadBundle(distDir), parseCell(args["print-cell"]), today);
    checkTable(t);
    process.stdout.write(JSON.stringify(t));
    return;
  }
  const outDir = resolve(args.out || join(distDir, "answers/data"));
  mkdirSync(outDir, { recursive: true });
  const cells = (args.cells ? args.cells.split(",").map(parseCell) : allCells()).map(cellId);
  const started = Date.now();
  // Cells are independent; workers each load the bundle once (about 0.1 s of pipeline per cell).
  const n = Math.max(1, Math.min(Number(args.workers) || os.cpus().length, 8, cells.length));
  const chunks = Array.from({ length: n }, (_, i) => cells.filter((_, j) => j % n === i));
  const parts = await Promise.all(chunks.map((chunk) => new Promise((ok, fail) => {
    const w = new Worker(__filename, { workerData: { distDir, outDir, cells: chunk, today }, execArgv: process.execArgv });
    w.once("message", ok);
    w.once("error", fail);
    w.once("exit", (code) => { if (code !== 0) fail(new Error(`answer_tables worker exited ${code}`)); });
  })));
  const keys = new Set(parts.flat());
  const loaded = loadBundle(distDir);
  const p = playersFile(loaded, keys);
  checkPlayers(p);
  writeFileSync(join(outDir, "players.json"), JSON.stringify(p));
  writeFileSync(join(outDir, "grid.json"), JSON.stringify({ v: SCHEMA, build: loaded.build, grid: GRID, cells: cells.length }));
  process.stderr.write(`answer_tables: ${cells.length} tables, ${p.rows.length} players, ${n} workers, ` +
    `${((Date.now() - started) / 1000).toFixed(1)} s\n`);
}

module.exports = { GRID, ROW_FIELDS, TABLE_KEYS, PLAYER_FIELDS, cellId, parseCell, allCells };
if (!isMainThread) {
  parentPort.postMessage(runCells(workerData.distDir, workerData.outDir, workerData.cells, workerData.today));
} else if (require.main === module) {
  main().catch((e) => { process.stderr.write(`answer_tables: ${e.stack || e}\n`); process.exit(1); });
}
