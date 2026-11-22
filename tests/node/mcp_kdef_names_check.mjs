// The chat connector never reads a kicker or defense as another player (Jeremy, 2026-11-19: "Jason Sanders", the
// kicker, was read as Sanders the TE on the site). names.ts: a K or DEF tag, or a team-only defense name, is not
// valued and never matched; a skill tag limits the pool to that position; a typo keeps its surname, so "Tyler Bass"
// is not Tyler Badie. compare_trade leaves a kicker out with a note instead of stopping or pricing another player.
// Stub get-values, no network. Run by tests/test_mcp_remote.py.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { matchName, notEvaluated, positionTag } from "../../supabase/functions/mcp/names.ts";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";

const players = [
  { player_key: 3925, name: "Ja'Tavion Sanders", pos: "TE", value: 4.1, tier: "bench" },
  { player_key: 2030, name: "Raheim Sanders", pos: "RB", value: 2.0, tier: "waiver" },
  { player_key: 3602, name: "Shedeur Sanders", pos: "QB", value: 6.0, tier: "bench" },
  { player_key: 11, name: "John Bates", pos: "TE", value: 0.5, tier: "waiver" },
  { player_key: 12, name: "Tyler Badie", pos: "RB", value: 1.5, tier: "waiver" },
  { player_key: 13, name: "Christian McCaffrey", pos: "RB", value: 50.0, tier: "starter" },
  { player_key: 14, name: "Jahmyr Gibbs", pos: "RB", value: 62.4, tier: "starter" },
  { player_key: 15, name: "Chuba Hubbard", pos: "RB", value: 27.0, tier: "starter" },
  { player_key: 16, name: "Taysom Hill", pos: "TE", value: 3.0, tier: "bench" },
  { player_key: 17, name: "Kenneth Walker III", pos: "RB", value: 30.0, tier: "starter" },
  { player_key: 18, name: "Khalil Shakir", pos: "WR", value: 12.0, tier: "starter" },
  { player_key: 19, name: "J.K. Dobbins", pos: "RB", value: 10.0, tier: "bench" },
  { player_key: 20, name: "Malik Washington", pos: "WR", value: 5.0, tier: "bench" },
  { player_key: 21, name: "Darnell Washington", pos: "TE", value: 2.0, tier: "waiver" },
  { player_key: 22, name: "Dameon Houston", pos: "RB", value: 1.0, tier: "waiver" },
];
const pick = (q) => { const m = matchName(players, q); return [m.match, m.player?.player_key ?? null]; };

// kickers: tagged forms are not valued; untagged, a kicker name never lands on a skill player
for (const q of ["Jason Sanders K", "Sanders (K, MIA)", "Jason Sanders - K - MIA", "Bates (K)", "Jake Bates K", "Tyler Bass PK"]) {
  assert.deepEqual(pick(q), ["none", null], q);
  assert.equal(notEvaluated(q)?.pos, "K", q);
  assert.match(matchName(players, q).note, /kicker, not valued/, q);
}
for (const q of ["Jason Sanders", "Jake Bates", "Tyler Bass", "Tyler Loop"]) assert.equal(pick(q)[1], null, q);
// defenses: tagged or team-only
for (const [q, team] of [["Dolphins D/ST", "MIA"], ["Miami", "MIA"], ["MIA DEF", "MIA"], ["49ers", "SF"], ["Miami Dolphins", "MIA"], ["NYJ D/ST", "NYJ"]]) {
  assert.deepEqual(pick(q), ["none", null], q);
  assert.deepEqual(notEvaluated(q), { pos: "DEF", team }, q);
}
assert.equal(notEvaluated("New York"), null, "two teams: no defense guessed");
// the TE stays the TE; a skill tag picks among that position only; an exact full name keeps its own position
assert.deepEqual(pick("Ja'Tavion Sanders"), ["exact", 3925]);
assert.deepEqual(pick("Ja'Tavion Sanders TE"), ["exact", 3925]);
assert.deepEqual(pick("Sanders TE"), ["partial", 3925]);
assert.deepEqual(pick("Sanders QB"), ["partial", 3602]);
assert.equal(pick("Sanders")[0], "ambiguous");
assert.deepEqual(pick("Taysom Hill QB"), ["exact", 16]);
assert.match(matchName(players, "Sanders TE").note, /"Sanders TE"/, "the note quotes what was typed");
// a K initial is a name, not a kicker tag
assert.deepEqual(pick("K. Walker"), ["partial", 17]);
assert.deepEqual(pick("K. Shakir"), ["partial", 18]);
assert.deepEqual(pick("J. K. Dobbins"), ["partial", 19]);
for (const q of ["K. Walker", "K. Shakir", "J. K. Dobbins", "K Allen"]) assert.equal(notEvaluated(q, players), null, q);
// a city that is also a surname stays ambiguous (the defense is one of the options); a city no player holds is the defense
for (const q of ["Washington", "Houston"]) {
  const m = matchName(players, q);
  assert.equal(m.match, "ambiguous", q);
  assert.match(m.note, /defense \(not valued\)/, q);
  assert.equal(notEvaluated(q, players), null, q);
}
assert.deepEqual(notEvaluated("Washington Commanders", players), { pos: "DEF", team: "WAS" });
assert.deepEqual(notEvaluated("Washington D/ST", players), { pos: "DEF", team: "WAS" });
assert.deepEqual(notEvaluated("Miami", players), { pos: "DEF", team: "MIA" });

// typos still resolve
assert.deepEqual(pick("Christian Mccafrey"), ["fuzzy", 13]);
assert.deepEqual(positionTag("Kelce TE KC"), { name: "kelce", pos: "TE", team: null });
assert.deepEqual(positionTag("Josh Allen"), { name: "josh allen", pos: null, team: null });

// compare_trade: the kicker is left out with a note, the trade is still priced
const codec = createRequire(import.meta.url)("../../app/v2/ddf-state.js");
const stub = async (scoring, teams, superflex) => ({
  attribution: "Data Driven Football", as_of: "2026-11-19", setting: { scoring, teams, superflex }, players,
  sources_included: ["espn"], sources_excluded: [],
});
const r = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "compare_trade",
  arguments: { scoring: "ppr", superflex: false, side_a: "Jahmyr Gibbs, Jason Sanders K", side_b: "Chuba Hubbard, Dolphins D/ST" } } },
  stub, { codec, siteOrigin: "https://site.test" });
const text = r.result.content[0].text;
assert.notEqual(r.result.isError, true, text);
// Connector walkthrough 2026-11-21: folded into one line after the answer; a few are named.
assert.match(text, /^Left out: 1 kicker and 1 defense \(not valued\): Jason Sanders K, Dolphins D\/ST\.$/m, text);
assert.doesNotMatch(text, /Ja'Tavion|Tyler Badie/, text);
// a K initial in a trade is priced, never left out as a kicker; a bare "Washington" stops and asks
const call = (a, b2) => handleRpc({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "compare_trade",
  arguments: { scoring: "ppr", superflex: false, side_a: a, side_b: b2 } } }, stub, { codec, siteOrigin: "https://site.test" });
const walker = (await call("K. Walker, K. Shakir", "Jahmyr Gibbs")).result;
assert.notEqual(walker.isError, true, walker.content[0].text);
assert.doesNotMatch(walker.content[0].text, /kicker/, walker.content[0].text);
const wash = (await call("Washington", "Jahmyr Gibbs")).result;
assert.equal(wash.isError, true, wash.content[0].text);
assert.match(wash.content[0].text, /Malik Washington/, wash.content[0].text);
console.log("ok");
