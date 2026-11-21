// Name matching for the MCP tools. The rank and typo rules are the site's
// app/v2/namesearch.js (JEG-812), so "Amon Ra St Brown", "Ja'Marr" and
// "Mcafrey" resolve the same way in chat as they do on the page. The chat
// adds an ambiguity stop the page's search box does not need: a query that
// fits more than one player is not silently given to the best-valued one.

export interface Named {
  name: string;
  value?: number;
  player_key?: number;
  pos?: string;
}

export type NameMatchKind = "exact" | "partial" | "fuzzy" | "ambiguous" | "none";

export interface NameMatch<T> {
  player: T | null;
  match: NameMatchKind;
  suggestions: T[];
  /** Short note for the model. Empty on an exact unique match. */
  note: string;
}

// Platform spellings that are not the site's name for the player (JEG-1388): [spelling, player_key].
// Same list as app/v2/roster-paste.js.
// BEGIN GENERATED name aliases: python3 pipelines/build_name_aliases.py (JEG-1388). Do not edit.
const NAME_ALIASES: ReadonlyArray<readonly [string, number]> = [
  ["Cameron Skattebo", 3664],
  ["Cameron Ward", 697],
  ["Chigoziem Okonkwo", 4247],
  ["Christopher Brooks", 2515],
  ["Drew Ogletree", 920],
  ["J. Sturdivant", 2201],
  ["Jalen Cropper", 1268],
  ["Jody Fortson", 437],
  ["Joshua Palmer", 822],
  ["Kenny Gainwell", 785],
  ["Michael Badgley", 235],
  ["Michael Strachan", 657],
  ["Michael Woods", 928],
  ["Mitch Tinsley", 4363],
  ["Mitch Trubisky", 4214],
  ["Nyheim Miller-Hines", 2785],
  ["Scotty Miller", 399],
  ["Tyron Billy-Johnson", 423],
  ["Zonovan Knight", 868]
];
// END GENERATED name aliases

const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);

// Position tags a roster line can carry ("Jason Sanders K", "Sanders (K, MIA)", "Dolphins D/ST", "Kelce TE").
const SKILL_TAGS = new Set(["qb", "rb", "wr", "te"]);
const KICKER_TAGS = new Set(["k", "pk"]);
const DEFENSE_TAGS = new Set(["def", "dst", "defense", "defence"]);
const TEAM_CODES = new Set(["ari", "atl", "bal", "buf", "car", "chi", "cin", "cle", "dal", "den", "det", "gb", "hou", "ind",
  "jac", "jax", "kc", "lac", "lar", "lv", "mia", "min", "ne", "no", "nyg", "nyj", "phi", "pit", "sea", "sf", "tb", "ten", "was", "wsh"]);
// The 32 defenses by team name: the mascot, the city (when only one team has it) and the full name, as roster-paste.js reads them.
const DEFENSES: ReadonlyArray<readonly [string, string, string]> = [
  ["arizona", "cardinals", "ARI"], ["atlanta", "falcons", "ATL"], ["baltimore", "ravens", "BAL"], ["buffalo", "bills", "BUF"],
  ["carolina", "panthers", "CAR"], ["chicago", "bears", "CHI"], ["cincinnati", "bengals", "CIN"], ["cleveland", "browns", "CLE"],
  ["dallas", "cowboys", "DAL"], ["denver", "broncos", "DEN"], ["detroit", "lions", "DET"], ["green bay", "packers", "GB"],
  ["houston", "texans", "HOU"], ["indianapolis", "colts", "IND"], ["jacksonville", "jaguars", "JAC"], ["kansas city", "chiefs", "KC"],
  ["las vegas", "raiders", "LV"], ["los angeles", "chargers", "LAC"], ["los angeles", "rams", "LAR"], ["miami", "dolphins", "MIA"],
  ["minnesota", "vikings", "MIN"], ["new england", "patriots", "NE"], ["new orleans", "saints", "NO"], ["new york", "giants", "NYG"],
  ["new york", "jets", "NYJ"], ["philadelphia", "eagles", "PHI"], ["pittsburgh", "steelers", "PIT"], ["san francisco", "49ers", "SF"],
  ["seattle", "seahawks", "SEA"], ["tampa bay", "buccaneers", "TB"], ["tennessee", "titans", "TEN"], ["washington", "commanders", "WAS"],
];
const DEFENSE_NAMES = new Map<string, string>();
// A city alone ("Miami") names its defense only when no player's name carries that word ("Washington", "Houston").
const DEFENSE_CITIES = new Map<string, string>();
for (const [city, mascot, team] of DEFENSES) {
  DEFENSE_NAMES.set(mascot, team);
  DEFENSE_NAMES.set(`${city} ${mascot}`, team);
  if (DEFENSES.filter(([c]) => c === city).length === 1) DEFENSE_CITIES.set(city, team);
}

/** Some player's name holds these words as whole words ("washington" in Malik Washington). */
function nameHolds<T extends Named>(players: readonly T[], words: string): boolean {
  return players.some((p) => ` ${tokens(p.name).join(" ")} `.includes(` ${words} `));
}

export interface TaggedName {
  /** The name with position and team tags taken off. */
  name: string;
  /** A position the input names (QB, RB, WR, TE, K or DEF), or null. */
  pos: string | null;
  /** The defense's team for a team-only defense name ("Miami", "49ers"), or null. */
  team: string | null;
  /** The name is a city alone ("Miami", "Washington"): a defense only when no player's name holds it. */
  cityOnly?: boolean;
}

/**
 * Position and team tags on a roster line. "Jason Sanders K", "Sanders (K, MIA)" and "Jason Sanders - K - MIA" are a
 * kicker; "Dolphins D/ST", "MIA DEF", "Miami" and "49ers" a defense; "Kelce TE" a tight end. A team code is taken off
 * only next to a position tag, so a name word is never read as a team.
 */
export function positionTag(text: string): TaggedName {
  const words = key(text).split(" ").filter(Boolean);
  let pos: string | null = null;
  const kept: string[] = [];
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (w === "d" && words[i + 1] === "st") { pos = "DEF"; i++; continue; }
    // "k" is a tag only after the name and away from initials: "K. Walker", "J. K. Dobbins" and "K Allen" are names.
    const initialNear = words[i - 1]?.length === 1 || words[i + 1]?.length === 1;
    if (i > 0 && !initialNear && KICKER_TAGS.has(w)) { pos = pos ?? "K"; continue; }
    if (DEFENSE_TAGS.has(w)) { pos = "DEF"; continue; }
    if (words.length > 1 && SKILL_TAGS.has(w)) { pos = pos ?? w.toUpperCase(); continue; }
    kept.push(w);
  }
  const named = pos ? kept.filter((w) => !TEAM_CODES.has(w)) : kept;
  const rest = (named.length ? named : kept).join(" ");
  const city = DEFENSE_CITIES.get(rest) ?? null;
  const team = DEFENSE_NAMES.get(rest) ?? city
    ?? (pos === "DEF" && kept.length === 1 && TEAM_CODES.has(kept[0]) ? kept[0].toUpperCase() : null);
  const cityOnly = !pos && !DEFENSE_NAMES.has(rest) && city !== null;
  if (!pos && team) pos = "DEF";
  return cityOnly ? { name: rest, pos, team, cityOnly } : { name: rest, pos, team: pos === "DEF" ? team : null };
}

/** positionTag, with a city alone left untagged when a player's name holds it (the line stays a name to match). */
function tagFor<T extends Named>(text: string, players: readonly T[]): TaggedName {
  const tag = positionTag(text);
  return tag.cityOnly && nameHolds(players, tag.name) ? { name: tag.name, pos: null, team: null, cityOnly: true } : tag;
}

/** A kicker or defense line: never priced (the values hold neither), so never matched to another player. */
export function notEvaluated<T extends Named>(text: string, players: readonly T[] = []): { pos: "K" | "DEF"; team: string | null } | null {
  const tag = tagFor(text, players);
  return tag.pos === "K" || tag.pos === "DEF" ? { pos: tag.pos, team: tag.team } : null;
}
const SUGGESTIONS = 5;

export function key(text: string): string {
  return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[.'’‘`´]/g, "").replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

/** Words of the key. A trailing Jr/Sr/II/III/IV/V is dropped, except when the text is only that suffix. */
export function tokens(text: string): string[] {
  const words = key(text).split(" ").filter(Boolean);
  const kept = words.filter((word) => !SUFFIXES.has(word));
  return kept.length ? kept : words;
}

function wordsAnyOrder(nameWords: string[], queryWords: string[]): boolean {
  if (queryWords.length > nameWords.length) return false;
  const free = nameWords.slice();
  return queryWords.every((q) => {
    const at = free.findIndex((word) => word.startsWith(q));
    if (at < 0) return false;
    free.splice(at, 1);
    return true;
  });
}

/** 0 whole name, 1 name starts with the query, 2 a word does, 3 every query word starts a different word. */
export function rank(name: string, query: string): number | null {
  const nameWords = tokens(name);
  const queryWords = tokens(query);
  if (!nameWords.length || !queryWords.length) return null;
  const n = nameWords.join(" ");
  const q = queryWords.join(" ");
  if (n === q) return 0;
  if (n.startsWith(q)) return 1;
  const qs = q.replace(/ /g, "");
  for (let i = 0; i < nameWords.length; i++) {
    if (nameWords.slice(i).join("").startsWith(qs)) return i === 0 ? 1 : 2;
  }
  if (wordsAnyOrder(nameWords, queryWords)) return 3;
  return null;
}

function distance(a: string, b: string): number {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const d = Array.from({ length: rows }, (_, i) => [i].concat(Array(cols - 1).fill(0)));
  for (let j = 1; j < cols; j++) d[0][j] = j;
  for (let i = 1; i < rows; i++) {
    for (let j = 1; j < cols; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[rows - 1][cols - 1];
}

const allowedEdits = (length: number) => (length >= 7 ? 2 : length >= 4 ? 1 : 0);

export function fuzzyDistance(name: string, query: string, limit = allowedEdits(tokens(query).join("").length)): number | null {
  const qs = tokens(query).join("");
  if (!limit) return null;
  const words = tokens(name);
  let best: number | null = null;
  for (let i = 0; i < words.length; i++) {
    const run = words.slice(i).join("");
    const candidates = new Set([run, words[i]]);
    for (const cut of [qs.length, qs.length + 1]) {
      if (cut > 0 && cut < run.length) candidates.add(run.slice(0, cut));
    }
    for (const candidate of candidates) {
      if (Math.abs(candidate.length - qs.length) > limit) continue;
      const found = distance(qs, candidate);
      if (found <= limit && (best === null || found < best)) best = found;
    }
  }
  return best;
}

/**
 * A typo of a full name keeps its surname: the last word typed is within an edit or two of one of the name's own words.
 * "Christian Mccafrey" is McCaffrey; "Tyler Bass" (a kicker) is not Tyler Badie, though the run of letters is close.
 */
function surnameFits(name: string, query: string): boolean {
  const q = tokens(query);
  if (q.length < 2) return true;
  const last = q[q.length - 1];
  const limit = Math.max(last.length >= 3 ? 1 : 0, allowedEdits(last.length));
  return tokens(name).some((word) => Math.abs(word.length - last.length) <= limit && distance(last, word) <= limit);
}

function byValue<T extends Named>(rows: T[]): T[] {
  return rows.slice().sort((a, b) => (b.value ?? 0) - (a.value ?? 0) || a.name.localeCompare(b.name));
}

function listNames<T extends Named>(rows: T[]): string {
  return byValue(rows).slice(0, SUGGESTIONS).map((p) => p.name).join(", ");
}

function ambiguous<T extends Named>(query: string, hits: T[]): NameMatch<T> {
  const suggestions = byValue(hits).slice(0, SUGGESTIONS);
  if (!suggestions.length) return { player: null, match: "none", suggestions: [], note: `${query}: NOT FOUND` };
  return {
    player: null,
    match: "ambiguous",
    suggestions,
    note: `${query}: AMBIGUOUS. Could be ${listNames(hits)}. Use a fuller name.`,
  };
}

/** A platform spelling of exactly one player in the pool (NAME_ALIASES), when no player's own name is the query. */
function aliasHit<T extends Named>(players: T[], q: string): NameMatch<T> | null {
  const qk = tokens(q).join(" ");
  const keys = new Set(NAME_ALIASES.filter(([alias]) => tokens(alias).join(" ") === qk).map(([, k]) => k));
  if (!keys.size) return null;
  const hits = players.filter((p) => p.player_key !== undefined && keys.has(p.player_key));
  if (hits.length !== 1) return null;
  return { player: hits[0], match: "exact", suggestions: [], note: `"${q}" is listed as ${hits[0].name}` };
}

/**
 * Resolve one query against the priced players.
 * An exact or unique partial match is returned. A typo with one clear nearest
 * name is returned as fuzzy. Two or more matches, or a suffix-only query
 * ("Jr"), are ambiguous and not guessed.
 */
export function matchName<T extends Named>(players: T[], query: string): NameMatch<T> {
  const raw = String(query ?? "").trim();
  if (!raw) return { player: null, match: "none", suggestions: [], note: "" };
  // A kicker or defense is never given to another player; a skill position tag limits the pool to that position.
  const tag = tagFor(raw, players);
  if (tag.cityOnly && !tag.pos) {
    // "Washington": Malik Washington, Darnell Washington or the Washington defense. Never guessed, so the model asks.
    const hit = ambiguous(raw, players.filter((p) => nameHolds([p], tag.name)));
    const team = DEFENSE_CITIES.get(tag.name);
    return { ...hit, match: "ambiguous", note: `${raw}: AMBIGUOUS. Could be ${listNames(hit.suggestions)}, or the ${team} defense (not valued). Use a fuller name.` };
  }
  if (tag.pos === "K" || tag.pos === "DEF") {
    return { player: null, match: "none", suggestions: [], note: `${raw}: ${tag.pos === "K" ? "kicker" : "defense"}, not valued` };
  }
  if (tag.pos && tag.name && players.some((p) => p.pos)) {
    // An exact full name is kept at its own position (a slot label is not always the player's position); any other
    // form is matched among players at the tagged position only.
    const exact = players.filter((p) => tokens(p.name).join(" ") === tokens(tag.name).join(" "));
    if (exact.length === 1) return { player: exact[0], match: "exact", suggestions: [], note: "" };
    const hit = matchName(players.filter((p) => p.pos === tag.pos), tag.name);
    return { ...hit, note: hit.note.split(tag.name).join(raw) };
  }
  const q = raw;
  const qWords = key(q).split(" ").filter(Boolean);
  if (qWords.length === 1 && SUFFIXES.has(qWords[0])) {
    const hits = players.filter((p) => key(p.name).split(" ").includes(qWords[0]));
    return hits.length ? ambiguous(q, hits) : { player: null, match: "none", suggestions: [], note: `${q}: NOT FOUND` };
  }

  const ranked: Array<{ player: T; rank: number }> = [];
  for (const player of players) {
    const r = rank(player.name, q);
    if (r !== null) ranked.push({ player, rank: r });
  }
  if (ranked.length) {
    const best = Math.min(...ranked.map((row) => row.rank));
    const hits = ranked.filter((row) => row.rank === best).map((row) => row.player);
    if (hits.length > 1) return ambiguous(q, hits);
    const player = hits[0];
    if (best === 0) return { player, match: "exact", suggestions: [], note: "" };
    const alias = aliasHit(players, q);
    if (alias) return alias;
    return { player, match: "partial", suggestions: [], note: `matched "${q}" to ${player.name}` };
  }
  const alias = aliasHit(players, q);
  if (alias) return alias;

  const fuzzy: Array<{ player: T; found: number }> = [];
  for (const player of players) {
    const found = fuzzyDistance(player.name, q);
    if (found !== null && surnameFits(player.name, q)) fuzzy.push({ player, found });
  }
  if (fuzzy.length) {
    const best = Math.min(...fuzzy.map((row) => row.found));
    const hits = fuzzy.filter((row) => row.found === best).map((row) => row.player);
    if (hits.length > 1) return ambiguous(q, hits);
    const player = hits[0];
    return { player, match: "fuzzy", suggestions: [], note: `interpreted "${q}" as ${player.name}` };
  }

  const close: Array<{ player: T; found: number }> = [];
  const qs = tokens(q).join("");
  if (qs.length >= 4) {
    for (const player of players) {
      const found = fuzzyDistance(player.name, q, 3);
      if (found !== null) close.push({ player, found });
    }
    close.sort((a, b) => a.found - b.found || (b.player.value ?? 0) - (a.player.value ?? 0));
  }
  const suggestions = close.slice(0, 3).map((row) => row.player);
  const note = suggestions.length
    ? `${q}: NOT FOUND. Closest: ${suggestions.map((p) => p.name).join(", ")}.`
    : `${q}: NOT FOUND`;
  return { player: null, match: "none", suggestions, note };
}

const SUFFIX_WORD = /^(jr|sr|ii|iii|iv|v)\.?$/i;

/**
 * JEG-1124: the nearest priced names for a query that matched no player, closest first
 * (ties by value). matchName's own "Closest" list when it has one; otherwise the same edit
 * distance with no cap, so a stop that asks "which player?" always has names to offer.
 */
export function closestNames<T extends Named>(players: T[], query: string, hit?: NameMatch<T>, n = 3): T[] {
  if (hit?.suggestions.length) return hit.suggestions.slice(0, n);
  const qs = tokens(query).join("");
  if (!qs) return [];
  const rows: Array<{ player: T; found: number }> = [];
  for (const player of players) {
    const found = fuzzyDistance(player.name, query, Math.max(3, qs.length));
    if (found !== null) rows.push({ player, found });
  }
  rows.sort((a, b) => a.found - b.found || (b.player.value ?? 0) - (a.player.value ?? 0));
  return rows.slice(0, n).map((row) => row.player);
}

/**
 * Split a comma-separated name list. A comma that only introduces a suffix
 * stays with the player: "Brian Thomas, Jr, Ja'Marr Chase" is two names.
 */
export function splitNames(raw: unknown): string[] {
  const parts = String(raw ?? "").split(",");
  const out: string[] = [];
  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    if (out.length && SUFFIX_WORD.test(trimmed)) out[out.length - 1] = `${out[out.length - 1]} ${trimmed.replace(/\.$/, "")}`;
    else out.push(trimmed);
  }
  return out;
}
