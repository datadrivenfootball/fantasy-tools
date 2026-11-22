// Injury flags in the connector's trade answers (Jeremy, 2026-11-22: "It is a flag, not a stopper"). get-values sends
// `injury` on a flagged player (get-values/injury.ts: the site's daily Sleeper copy under the site's rules). Text only:
// nothing here filters, sorts, labels or prices; a healthy player (no `injury`) prints as before.

export interface InjuryFlag { status: string; label: string; level: string; body?: string }
type Flagged = { name: string; injury?: InjuryFlag | null };

/** " [Out, hamstring]" after a name, or "". */
export function injuryTag(p: { injury?: InjuryFlag | null } | null | undefined): string {
  const f = p?.injury;
  return f ? ` [${f.label}${f.body ? `, ${f.body}` : ""}]` : "";
}

/** "Out (hamstring)", "on IR (knee)", "Questionable". */
function phrase(f: InjuryFlag): string {
  const head = f.status === "IR" || f.status === "PUP" ? `on ${f.label}` : f.label;
  return head + (f.body ? ` (${f.body})` : "");
}

/** One line for the flagged players among `players`, or null when none is flagged (the site's Why line, joined). */
export function injuryLine(players: Flagged[]): string | null {
  const seen = new Set<string>();
  const flagged = players.filter((p) => p.injury && !seen.has(p.name) && seen.add(p.name));
  if (!flagged.length) return null;
  return `Injury flag: ${flagged.map((p) => `${p.name} is ${phrase(p.injury!)}`).join("; ")}. A flag, not a stopper: the trade may not work as planned.`;
}

/** player_key -> flag, from get-values' players. */
export function injuryMap(players: Array<{ player_key: number; injury?: InjuryFlag | null }>): Map<number, InjuryFlag> {
  const out = new Map<number, InjuryFlag>();
  for (const p of players ?? []) if (p.injury) out.set(p.player_key, p.injury);
  return out;
}

/** The text with the injury tags and "Injury flag:" lines taken out (what a reply measured without flags reads). */
export function withoutInjury(text: string): string {
  return text.split("\n").filter((l) => !/^\s*Injury flag: /.test(l)).join("\n")
    .replace(/ \[(Out|IR|PUP|Suspended|Doubtful|Questionable)(, [^\]]+)?\]/g, "");
}
