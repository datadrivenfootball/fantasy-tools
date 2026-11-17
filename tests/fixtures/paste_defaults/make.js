// JEG-1689: builds the whole-league paste fixtures in this folder from the page shapes of tests/fixtures/league_paste
// (ESPN League Rosters, Yahoo league rosters, Sleeper league page), with real league sizes and lineups.
// Run: node tests/fixtures/paste_defaults/make.js   (deterministic; players.json is the player list the tests match on)
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..", "..");
const OUT = __dirname;
const table = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const NFL = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "TB", "TEN", "WAS"];
const MASCOT = {ARI: "Cardinals", ATL: "Falcons", BAL: "Ravens", BUF: "Bills", CAR: "Panthers", CHI: "Bears", CIN: "Bengals",
  CLE: "Browns", DAL: "Cowboys", DEN: "Broncos", DET: "Lions", GB: "Packers", HOU: "Texans", IND: "Colts", JAX: "Jaguars",
  KC: "Chiefs", LAC: "Chargers", LAR: "Rams", LV: "Raiders", MIA: "Dolphins", MIN: "Vikings", NE: "Patriots", NO: "Saints",
  NYG: "Giants", NYJ: "Jets", PHI: "Eagles", PIT: "Steelers", SEA: "Seahawks", TB: "Buccaneers", TEN: "Titans", WAS: "Commanders"};
const KICKERS = ["Jason Myers", "Chad Ryland", "Matt Gay", "Chris Boswell", "Dominic Zvada", "Cameron Dicker", "Jake Elliott",
  "Wil Lutz", "Brandon Aubrey", "Tyler Bass", "Ka'imi Fairbairn", "Harrison Butker", "Jake Bates", "Evan McPherson"];
const TEAM_NAMES = ["Gridiron Gurus", "Taco Tuesday", "Mahomes Alone", "The Big Lebowski", "Waiver Wire Warriors",
  "Fourth Down Club", "Hail Marys", "Kingdom of Caleb", "Ricky and the Bobbys", "Bench Mob", "Sunday Scaries",
  "Air Raid", "Run It Back", "Bye Week Blues"];

// distinct, plain-named players with an NFL team, in table order; each league starts from the top of the list
const PLAYERS = [], seen = new Set();
table.forEach(r => {
  const [name, pos, team] = r.split("|");
  const k = name.toLowerCase();
  if (!team || seen.has(k) || !/^[A-Za-z][A-Za-z .'-]+$/.test(name) || ["QB", "RB", "WR", "TE"].indexOf(pos) < 0) return;
  seen.add(k);
  PLAYERS.push({name, pos, team});
});
let pool = null;
const used = new Set();
function take(pos) { const i = pool.findIndex(p => p.pos === pos); if (i < 0) throw new Error("out of " + pos); used.add(pool[i]); return pool.splice(i, 1)[0]; }
const BENCH_CYCLE = ["RB", "WR", "WR", "RB", "QB", "TE", "WR"];

// rows: [{slot, pos}] per team; slot labels as each site prints them
function league(n, lineup, bench, ir) {
  pool = PLAYERS.slice();
  return TEAM_NAMES.slice(0, n).map((name, t) => {
    const rows = lineup.map(([slot, pos]) => ({slot, pos}));
    for (let b = 0; b < bench; b++) rows.push({slot: "BN", pos: BENCH_CYCLE[(b + t) % BENCH_CYCLE.length]});
    for (let i = 0; i < ir; i++) rows.push({slot: "IR", pos: "WR"});
    return {name, rows: rows.map(r => Object.assign(r, r.pos === "K" ? {k: KICKERS[t % KICKERS.length], nfl: NFL[t]} : r.pos === "DEF" ? {nfl: NFL[(t + 7) % NFL.length]} : take(r.pos)))};
  });
}
function cap(code) { return code.charAt(0) + code.slice(1).toLowerCase(); }

function espn(teams, opts) {
  const SLOT = {BN: "Bench", IR: "IR", DEF: "D/ST"};
  const out = ["ESPN", "Fantasy", "League Rosters", "Sample League", ""];
  teams.forEach((tm, t) => {
    out.push(`${tm.name} (${t % 6}-${6 - (t % 6)}-0)`, "SLOT\tPLAYER\tACQ");
    tm.rows.forEach((r, i) => {
      if (opts && opts.cutTeam === t && i >= opts.cutAt) return;
      out.push(SLOT[r.slot] || r.slot);
      if (r.empty) { out.push("Empty"); return; }
      if (r.pos === "K") out.push(r.k + r.k, `${r.nfl} K`);
      else if (r.pos === "DEF") out.push(`${MASCOT[r.nfl]} D/ST${MASCOT[r.nfl]} D/ST`, `${r.nfl} D/ST`);
      else out.push(r.name + r.name, `${r.team} ${r.pos}`);
      out.push(i % 2 ? "Free Agency" : "Draft");
    });
    if (opts && opts.cutTeam === t) return;
    out.push("View Team", "Propose Trade", "");
  });
  return out.join("\n") + "\n";
}
function yahoo(teams) {
  const out = ["Yahoo Sports", "Fantasy", "Football", "Rosters", "Sample League", ""];
  teams.forEach(tm => {
    out.push(tm.name, "Pos\tOffense\tAction\tForecast");
    const off = tm.rows.filter(r => r.pos !== "K" && r.pos !== "DEF");
    off.forEach(r => out.push(r.slot, r.name + "No new player Notes", `${cap(r.team)} - ${r.pos}`, "Sun 12:00 pm vs Opp"));
    tm.rows.filter(r => r.pos === "K").forEach(r => out.push("Pos\tKickers\tAction", "K", r.k + "No new player Notes", `${cap(r.nfl)} - K`));
    tm.rows.filter(r => r.pos === "DEF").forEach(r => out.push("Pos\tDefense/Special Teams\tAction", "DEF", MASCOT[r.nfl] + "No new player Notes", `${cap(r.nfl)} - DEF`));
  });
  out.push("Yahoo Sports LLC", "Terms", "Privacy");
  return out.join("\n") + "\n";
}
function sleeper(teams) {
  const out = ["Sleeper", "LEAGUE", "TEAM", "PLAYERS", ""];
  teams.forEach((tm, t) => {
    out.push(tm.name, `@manager${t}`, `${t % 7}-${7 - (t % 7)}`);
    tm.rows.forEach(r => {
      out.push(r.slot);
      if (r.pos === "K") out.push(r.k, `K - ${r.nfl}`);
      else if (r.pos === "DEF") out.push(r.nfl, MASCOT[r.nfl]);
      else out.push(r.name, `${r.pos} - ${r.team}`);
    });
  });
  return out.join("\n") + "\n";
}

const ESPN_LINEUP = [["QB", "QB"], ["RB", "RB"], ["RB", "RB"], ["WR", "WR"], ["WR", "WR"], ["TE", "TE"], ["FLEX", "WR"], ["DEF", "DEF"], ["K", "K"]];
const espnTeams = league(10, ESPN_LINEUP, 6, 1);
espnTeams[9].rows[14].empty = true;   // an empty bench slot (ESPN prints "Empty" under its label)
fs.writeFileSync(path.join(OUT, "espn-10team.txt"), espn(espnTeams));
fs.writeFileSync(path.join(OUT, "espn-10team-partial.txt"), espn(espnTeams, {cutTeam: 9, cutAt: 4}));   // copy stopped early

const YAHOO_LINEUP = [["QB", "QB"], ["WR", "WR"], ["WR", "WR"], ["WR", "WR"], ["RB", "RB"], ["RB", "RB"], ["TE", "TE"],
  ["W/R/T", "RB"], ["Q/W/R/T", "QB"], ["K", "K"], ["DEF", "DEF"]];
fs.writeFileSync(path.join(OUT, "yahoo-12team-superflex.txt"), yahoo(league(12, YAHOO_LINEUP, 6, 1)));

const SLEEPER_LINEUP = [["QB", "QB"], ["RB", "RB"], ["RB", "RB"], ["WR", "WR"], ["WR", "WR"], ["WR", "WR"], ["TE", "TE"],
  ["FLEX", "RB"], ["FLEX", "WR"], ["K", "K"], ["DEF", "DEF"]];
fs.writeFileSync(path.join(OUT, "sleeper-14team.txt"), sleeper(league(14, SLEEPER_LINEUP, 5, 0)));

fs.writeFileSync(path.join(OUT, "players.json"), JSON.stringify(PLAYERS.filter(p => used.has(p)).map(p => [p.name, p.pos, p.team])) + "\n");
console.log("wrote fixtures, players:", used.size);
