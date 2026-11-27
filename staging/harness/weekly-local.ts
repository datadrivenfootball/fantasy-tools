// Build the real weekly read for a league snapshot on this Mac (JEG-1736): the same buildWeekly the function runs,
// with warehouse and schedule rows read through `supabase db query --linked` (read only, Management API login) and
// live Sleeper / Dynasty Daddy ids and ESPN K/DEF projections.
//   deno run -A staging/harness/weekly-local.ts <snapshot.json> <out-dir>
// Writes <out-dir>/weekly.json (ddf-league-weekly/0) and <out-dir>/warehouse.json ({rows, schedule}, for serve.ts).
const [snapPath, outDir] = Deno.args;
const REPO = new URL("../../", import.meta.url);
const { buildWeekly, fetchXwalk, fetchEspnKdef } = await import(new URL("supabase/functions/ddf-account/weekly.ts", REPO).href);
const REF = "iskiybsimubiujwuchsl";
const lit = (xs: string[]) => "array[" + (xs.length ? xs.map((x) => "'" + x.replace(/'/g, "''") + "'").join(",") : "") + "]::text[]";
async function q(sql: string) {
  const out = await new Deno.Command("supabase", { args: ["db", "query", "--linked", "--project-ref", REF, "--output-format", "json", sql], cwd: new URL(".", REPO).pathname, stdout: "piped", stderr: "piped" }).output();
  const text = new TextDecoder().decode(out.stdout);
  const body = JSON.parse(text.slice(text.indexOf("{")));
  if (!body.rows) throw new Error("query failed: " + text.slice(0, 300));
  return body.rows;
}
const snap = JSON.parse(await Deno.readTextFile(snapPath));
const f = (u: string | URL, i?: RequestInit) => fetch(u, i);
let rows: unknown[] = [], schedule: unknown[] = [];
const weekly = await buildWeekly(snap, {
  rows: async (season: number, from: number, e: string[], s: string[]) => {
    rows = (await q(`with latest as (select distinct on (source) run_id, source, as_of from public.source_projection_runs
        where source in ('espn','sleeper') and season = ${season} order by source, as_of desc)
      select w.source, l.as_of, w.target_week, w.source_player_id, w.sleeper_id, w.team, w.position,
        w.points_std::float8 as points_std, w.points_half_ppr::float8 as points_half_ppr, w.points_ppr::float8 as points_ppr
      from public.source_weekly_projections w join latest l on l.run_id = w.run_id and l.source = w.source
      where w.target_week >= ${from} and ((w.source = 'espn' and w.source_player_id = any(${lit(e)})) or (w.source = 'sleeper' and w.sleeper_id = any(${lit(s)})))`))
      .map((r: Record<string, unknown>) => ({ ...r, as_of: new Date(String(r.as_of).replace(" ", "T").replace(/\+00$/, "Z")).toISOString() }));
    return rows;
  },
  schedule: async (season: number) => {
    schedule = (await q(`with latest as (select run_id, as_of from public.source_projection_runs where source = 'nflverse_schedule' order by as_of desc limit 1)
      select s.week::int as week, s.home_team, s.away_team, l.as_of from public.nflverse_schedule_snapshots s join latest l using (run_id)
      where s.season = ${season} and s.game_type = 'REG'`))
      .map((r: Record<string, unknown>) => ({ ...r, as_of: new Date(String(r.as_of).replace(" ", "T").replace(/\+00$/, "Z")).toISOString() }));
    return schedule;
  },
  xwalk: () => fetchXwalk(f),
  kdef: (season: number) => fetchEspnKdef(f, season, new Date()),
});
await Deno.mkdir(outDir, { recursive: true });
await Deno.writeTextFile(`${outDir}/weekly.json`, JSON.stringify(weekly));
await Deno.writeTextFile(`${outDir}/warehouse.json`, JSON.stringify({ rows, schedule }));
const cells = Object.values(weekly.players as Record<string, { weeks: Record<string, { points: number | null }> }>).flatMap((p) => Object.values(p.weeks));
console.log(JSON.stringify({ players: Object.keys(weekly.players).length, weeks: weekly.weeks, cells: cells.length, null_cells: cells.filter((c) => c.points === null).length, unmatched: weekly.unmatched.length, as_of: weekly.as_of }));
