// The daily Sleeper status rule (moved out of waivers.js, 2026-11-22, so Build a Trade's injury flags need only this file).
// Used by the Waivers tab (waivers.js re-exports both functions), the trade pages' injury flag (app/next/injury-flag.js)
// and mirrored for the connector in supabase/functions/get-values/injury.ts (tests/node/injury_flag_connector_check.mjs).
//   statusFreshness(status, nowMs) -> {shown, asOf, ageDays, bySleeperId, label, text}
//   statusOf(row, freshness)       -> "Questionable" | "Doubtful" | "Out" | "IR" | "PUP" | "Sus" | null
(function (root) {
  "use strict";
  const finite = value => typeof value === "number" && Number.isFinite(value);
  // JEG-1363: daily display status is separate from the identity/value bake (window.TradeValueStatus).
  // Both dated rows and the daily id map use the Waivers six-day rule
  // (JEG-892 / JEG-1401), checked again on every render.
  const STATUS_MAX_AGE_DAYS = 6;
  const DAY_MS = 24 * 60 * 60 * 1000;
  const statusDay = ms => new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", timeZone: "UTC"}).format(new Date(ms));
  // status: {as_of: ISO time} or null. nowMs: the reader's clock. -> {shown, asOf, ageDays, label, text}.
  function statusFreshness(status, nowMs) {
    const at = status && typeof status.as_of === "string" ? Date.parse(status.as_of) : NaN;
    if (!Number.isFinite(at) || !finite(nowMs)) {
      return {shown: false, asOf: null, ageDays: null, label: null, text: "Injury status is not shown: the Sleeper status copy has no date."};
    }
    const ageDays = Math.max(0, (nowMs - at) / DAY_MS);
    const day = statusDay(at);
    const daily = status.by_sleeper_id;
    // Future-dated and undated observations are never shown.
    if (at > nowMs || ageDays > STATUS_MAX_AGE_DAYS) {
      const old = Math.floor(ageDays);
      return {shown: false, asOf: status.as_of, ageDays, label: null,
        text: `Injury status is not shown: the latest Sleeper status is from ${day}, ${old} day${old === 1 ? "" : "s"} old.`};
    }
    const dated = daily ? `${day}, ${new Date(at).toISOString().slice(11, 16)} UTC` : day;
    return {shown: true, asOf: status.as_of, ageDays, bySleeperId: daily,
      label: `Sleeper status as of ${dated}`, text: `Injury status: Sleeper, as of ${dated}.`};
  }
  // The status a row may show: null when the copy is stale or undated, or the player has no status (never "healthy").
  function statusOf(row, freshness) {
    if (!freshness || !freshness.shown || !row) return null;
    if (freshness.bySleeperId) {
      const p = freshness.bySleeperId[String(row.sleeper_id)];
      const team = t => ({JAC: "JAX", LAR: "LA", WSH: "WAS", LVR: "LV"}[t] || t);
      if (!p || !row.team || team(p.team) !== team(row.team) || p.pos !== row.pos) return null;
      return ["Questionable", "Doubtful", "Out", "IR", "PUP", "Sus"].includes(p.injury_status) ? p.injury_status : null;
    }
    // Compatibility for older dated callers; the built page always has the
    // daily id map, even when it is missing/empty. Never mix the two vintages.
    return row.injury_status && !["Active", "Inactive"].includes(row.injury_status) ? row.injury_status : null;
  }
  const api = {STATUS_MAX_AGE_DAYS, statusFreshness, statusOf};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.DDFStatusRule = api;
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
