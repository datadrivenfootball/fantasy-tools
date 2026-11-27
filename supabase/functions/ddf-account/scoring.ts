// Rescore projected stat lines with the league's own scoring settings (JEG-1736).
// Jeremy, 2026-11-27: projections from another platform are used only when mapped to the league's scoring
// settings, or labelled as not mapped. The rules are Yahoo statModifiers ([{statId, value, name}]) in
// summary.settings.scoring_raw; each source's projected stat line is mapped onto Yahoo stat ids and summed.
// Missing a stat in a source's line is listed, never guessed.

// deno-lint-ignore no-explicit-any
type J = any;
export type Rules = { mods: Map<string, number>; names: Map<string, string> };
export type Rescore = { points: number; missing: string[] };

export function leagueRules(summary: J): Rules | null {
  const raw = summary?.settings?.scoring_raw;
  const list = Array.isArray(raw) ? raw : Array.isArray(raw?.statModifiers) ? raw.statModifiers : null;
  if (!list || !list.length) return null;
  const mods = new Map<string, number>(), names = new Map<string, string>();
  for (const m of list) {
    const id = String(m?.statId ?? m?.stat_id ?? "");
    const v = Number(m?.value);
    if (!id || !Number.isFinite(v)) continue;
    mods.set(id, v);
    names.set(id, String(m?.displayName || m?.name || id));
  }
  return mods.size ? { mods, names } : null;
}

// Yahoo stat id -> the source's stat key(s), with a weight for split bands
type Map1 = Record<string, [string, number][]>;
const one = (k: string): [string, number][] => [[k, 1]];
const OFFENSE: Record<"espn" | "sleeper", Map1> = {
  espn: { "4": one("passing_yards"), "5": one("passing_tds"), "6": one("interceptions"), "9": one("rushing_yards"), "10": one("rushing_tds"), "11": one("receptions"), "12": one("receiving_yards"), "13": one("receiving_tds") },
  sleeper: {
    "4": one("pass_yd"), "5": one("pass_td"), "6": one("pass_int"), "9": one("rush_yd"), "10": one("rush_td"), "11": one("rec"), "12": one("rec_yd"), "13": one("rec_td"),
    "16": [["pass_2pt", 1], ["rush_2pt", 1], ["rec_2pt", 1]], "18": one("fum_lost"),
  },
};
// ESPN kona stat ids (checked 2026-11-27 against ESPN's own default totals): K 74 FG 50+, 77 FG 40-49, 80 FG under 40,
// missed 76 (50+), 79 (40-49), 82 (under 40), 85 (all), 86 PAT made, 88 PAT missed. D/ST 99 sacks, 95 INT, 96 fumbles recovered, 94 defensive TDs, 93 blocked
// kick TD, 98 safeties, 97 blocked kicks, 101/102 kick/punt return TDs, points-allowed bands 89 (0), 90 (1-6),
// 91 (7-13), 92 (14-17), 121 (18-21), 122 (22-27), 123 (28-34), 124 (35-45), 125 (46+), each the band's probability.
// Yahoo's bands are 14-20 and 21-27, so ESPN's 18-21 band is split by points: three quarters to 14-20, one to 21-27.
const KICKER: Map1 = {
  "19": one("80"), "20": one("80"), "21": one("80"), "22": one("77"), "23": one("74"), "29": one("86"), "30": one("88"),
  "24": one("82"), "25": one("82"), "26": one("82"), "27": one("79"), "28": one("76"),
};
const DEFENSE: Map1 = {
  "32": one("99"), "33": one("95"), "34": one("96"), "35": [["94", 1], ["93", 1]], "36": one("98"), "37": one("97"), "49": [["101", 1], ["102", 1]],
  "50": one("89"), "51": one("90"), "52": one("91"), "53": [["92", 1], ["121", 0.75]], "54": [["121", 0.25], ["122", 1]], "55": one("123"), "56": [["124", 1], ["125", 1]],
};
// stat ids that belong to each group, so a K rule never counts as "missing" from a QB's line
const GROUP: Record<string, Set<string>> = {
  offense: new Set(["4", "5", "6", "9", "10", "11", "12", "13", "15", "16", "18", "57", "58", "78"]),
  K: new Set(["19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30"]),
  DEF: new Set(["31", "32", "33", "34", "35", "36", "37", "48", "49", "82", "50", "51", "52", "53", "54", "55", "56", "67", "68", "69", "70", "71", "72", "73", "74", "75", "76", "77"]),
};
// Field goals: ESPN projects made and missed FGs under 40 as one number each. The league's 0-19, 20-29 and 30-39 values
// must agree for that to be exact; when they don't, the 30-39 value is used and the rule is listed as approximate.
function kickerSplitNote(r: Rules) {
  const v = (id: string) => r.mods.get(id) ?? 0;
  const notes: string[] = [];
  if (!(v("19") === v("20") && v("20") === v("21"))) notes.push("FG under 40 scored at the 30-39 value (ESPN does not split it)");
  const miss = ["24", "25", "26"].map(v);
  if (miss.some((x) => x !== miss[0])) notes.push("missed FGs under 40 scored at the 30-39 value (ESPN does not split them)");
  return notes;
}

export function rescore(kind: "espn" | "sleeper" | "K" | "DEF", stats: Record<string, number> | null | undefined, r: Rules): Rescore | null {
  if (!stats || typeof stats !== "object") return null;
  const map = kind === "K" ? KICKER : kind === "DEF" ? DEFENSE : OFFENSE[kind];
  const group = kind === "K" ? GROUP.K : kind === "DEF" ? GROUP.DEF : GROUP.offense;
  let pts = 0;
  const missing: string[] = [];
  for (const [id, val] of r.mods) {
    if (!group.has(id) || val === 0) continue;
    const keys = map[id];
    if (!keys) { missing.push(r.names.get(id) || id); continue; }
    if (kind === "K" && ["19", "20"].includes(id)) continue; // under-40 FGs counted once, at the 30-39 value (21)
    if (kind === "K" && ["24", "25"].includes(id)) continue; // missed FGs under 40 counted once, at the 30-39 value (26)
    for (const [k, w] of keys) pts += (Number(stats[k]) || 0) * w * val;
  }
  return { points: Math.round(pts * 100) / 100, missing };
}

export function rulesNotes(r: Rules | null) { return r ? kickerSplitNote(r) : []; }
