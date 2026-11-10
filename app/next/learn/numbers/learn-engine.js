/* Learn > How we get our numbers: read-only view of the live engine (JEG-1536).
   No value math here. Every number is read from the engine that runs hidden on this page
   (window.DDF.engine, ddf-engine.js, over TradeValueCurveControls): getInspection() for each
   source's published / indexed / adjusted values, getAllRows() for DDF Value, getPublishedMath()
   for each chart's index factor. The Health check and Source build-up models come from the same
   modules the old #values-auditing tabs used (AuditPie in v2/audit-pie.js, DDFAuditSource in
   v2/audit-source.js), so their checks and rows are computed in one place only.
   A value the engine does not have stays null and is shown as a dash: missing is never zero. */
(function () {
  'use strict';

  var CHARTS = ['cbs', 'usatoday', 'fantasypros', 'fantasycalc'];
  var LABELS = {
    cbs: 'CBS Sports', usatoday: 'USA Today', fantasypros: 'FantasyPros', fantasycalc: 'FantasyCalc',
    espn: 'ESPN', cbsros: 'CBS rest of season', razzball: 'Razzball'
  };
  var SCORING_LABEL = { standard: 'Standard', half_ppr: 'Half PPR', ppr: 'Full PPR' };
  var SLOT_KEYS = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX', 'BENCH'];
  var finite = function (v) { return typeof v === 'number' && isFinite(v) ? v : null; };

  function engine() { return window.DDF && window.DDF.engine ? window.DDF.engine : null; }

  /* ---- settings ---- */
  function rosterLabel(r) {
    return ['QB', 'RB', 'WR', 'TE', 'FLEX'].map(function (k) { return k + (r[k] || 0); }).join(' ') +
      (r.SUPERFLEX ? ' SUPERFLEX' + r.SUPERFLEX : '') + ' BENCH' + (r.BENCH || 0);
  }
  function currentSettings(C) {
    var st = C.getState();
    var roster = C.getRosterShape();
    var r = {};
    SLOT_KEYS.forEach(function (k) { r[k] = Number(roster[k] || 0); });
    return {
      scoring: st.scoring, scoringLabel: SCORING_LABEL[st.scoring] || st.scoring, teams: Number(st.teams),
      superflex: r.SUPERFLEX > 0, roster: r, rosterLabel: rosterLabel(r)
    };
  }

  function fillPathOf(vp, source, pos, pk) {
    var o = vp.sources && vp.sources[source], e = o && o.positions && o.positions[pos] && o.positions[pos].estimates;
    return e && e[pk] ? e[pk].path || null : null;
  }

  /* ---- snapshot of the engine's current build ---- */
  function snapshot() {
    var E = engine();
    var C = E.controls();
    var ins = C.getInspection();
    var vp = ins.valuePipeline || {};
    var settings = currentSettings(C);
    var meta = (E.meta && E.meta()) || {};
    var basis = C.getBasis ? C.getBasis() : null;
    var comp = C.getCompositeInputs ? C.getCompositeInputs() : null;
    var rows = C.getAllRows();

    /* Charts in the DDF Value this week (a held chart is left out, never counted as zero). */
    var inputs = (comp && comp.inputs) || CHARTS;
    var charts = CHARTS.filter(function (k) { return inputs.indexOf(k) >= 0; });

    var factor = {}, factorTotals = {};
    var players = [];
    rows.forEach(function (row) {
      var pk = String(row.player_key);
      var blended = row.ddfByVersion && row.ddfByVersion.blended;
      /* The model's own DDF Value: with a reader override, applyDdfOverride keeps it in pipelineValue. */
      var overridden = row.valueOverride !== undefined && row.valueOverride !== null;
      if (overridden && !(blended && finite(blended.pipelineValue) !== null)) return;   // no model value to explain
      var ddf = finite(blended && (overridden ? blended.pipelineValue : blended.value));
      if (ddf === null) return;
      var irow = (ins.rows && ins.rows[pk]) || {};
      var sources = {};
      CHARTS.forEach(function (s) {
        var p = ins.players && ins.players[s] && ins.players[s][pk];
        /* Indexed and adjusted come from the engine's row: a chart that does not list a player can still carry a
           real 0 there, and DDF Value averages it. Only the published value is missing (null) then. */
        var idx = finite(irow.indexed && irow.indexed[s]), adj = finite(irow.adjusted && irow.adjusted[s]);
        if (!p && idx === null && adj === null) { sources[s] = null; return; }
        if (factor[s] === undefined) {
          var pm = C.getPublishedMath(row.player_key, s);
          factor[s] = pm ? finite(pm.factor) : null;
          /* The factor's own two totals, over the same players (the ones the chart lists; estimates excluded). */
          factorTotals[s] = pm ? { ddf: finite(pm.anchorTotal), published: finite(pm.chartTotal), players: finite(pm.sharedPlayers) } : null;
        }
        sources[s] = {
          published: p ? finite(p.native) : null, indexed: idx, adjusted: adj, role: p ? p.role || null : null,
          estimated: p ? Boolean(p.estimated) : false, listed: Boolean(p), rank: p ? finite(p.rank) : null,
          fillPath: p && p.estimated ? fillPathOf(vp, s, p.pos, pk) : null
        };
      });
      players.push({
        player_key: row.player_key, name: row.name, pos: row.pos, team: row.team || '',
        ddf: ddf, tier: row.ddfTier || null,
        ddfSources: (blended.sources || []).slice(),
        override: overridden ? finite(row.values && row.values.ddf_value) : null,
        overrideSet: overridden,
        sources: sources
      });
    });
    players.sort(function (a, b) { return b.ddf - a.ddf || a.player_key - b.player_key; });
    players.forEach(function (p, i) { p.rank = i + 1; });

    var startSlots = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX'].reduce(function (t, k) { return t + (settings.roster[k] || 0); }, 0);
    var pie = finite(vp.pie);
    var perSlot = pie !== null && settings.teams && startSlots ? pie / (settings.teams * startSlots) : null;

    var srcMeta = {};
    CHARTS.forEach(function (s) {
      var ps = (ins.players && ins.players[s]) || {};
      var keys = Object.keys(ps);
      var totals = { published: 0, indexed: 0, adjusted: 0 };
      var filled = 0;
      keys.forEach(function (k) {
        var p = ps[k], r = (ins.rows && ins.rows[k]) || {};
        if (p.estimated) filled += 1; else totals.published += finite(p.native) || 0;
        totals.indexed += finite(r.indexed && r.indexed[s]) || 0;
        totals.adjusted += finite(r.adjusted && r.adjusted[s]) || 0;
      });
      var excluded = (ins.excluded || []).filter(function (e) { return e.key === s; })[0] || null;
      srcMeta[s] = {
        key: s, label: LABELS[s], players: keys.length, listed: keys.length - filled, filledIn: filled,
        totals: totals, factor: factor[s] === undefined ? null : factor[s], factorTotals: factorTotals[s] || null,
        inDdf: charts.indexOf(s) >= 0, excludedReason: excluded ? excluded.reason : null
      };
    });

    return {
      settings: settings,
      meta: { week: meta.week === undefined ? null : meta.week, asOf: meta.asOf || null, build: meta.buildTag || null },
      pie: pie, perSlot: perSlot !== null && Math.abs(perSlot - Math.round(perSlot)) < 1e-6 ? Math.round(perSlot) : perSlot,
      startSlots: startSlots,
      charts: charts,
      basis: basis ? { isDefault: basis.isDefault !== false, label: basis.label || '', percents: basis.percents || {} } : { isDefault: true, label: '', percents: {} },
      sources: srcMeta,
      players: players,
      overrides: players.filter(function (p) { return p.overrideSet; }).length,
      inspection: ins
    };
  }

  /* Health check (the old #values-auditing/health-check): AuditPie's own extract + checks. */
  function health(snap) {
    var A = window.AuditPie;
    if (!A) return null;
    var data = A.extract(snap.inspection);
    if (!data) return null;
    A.computeFlags(data);
    data.checks = A.computeChecks(data);
    return data;
  }

  /* Source build-up (the old #values-auditing/single-source): DDFAuditSource's own model. */
  function buildUp(snap, source, position) {
    var S = window.DDFAuditSource;
    return S ? S.build(snap.inspection, source, position) : null;
  }
  /* One player's path from a source's own number to its Adjusted value (JEG-1393, R1-CX-07 / R1-OP-07): the engine's
     own intermediates (getInspection players[source][key] and valuePipeline.sources[source]), for a trade chart as well
     as a projection. A readout the engine does not expose stays null. R2-OP-03 / R2-OP-05 / R2-CX-02 add the inputs the
     formulas need, read from the same records: the pie-scaled value above waivers (vorpDisplay, vorpFactor), each
     group's budget (value pie × DDF weight) and this source's group total, and the chance he fills in from the bench,
     the one derived readout (lineup share ÷ availability − chance above the starter line, the engine's own identity). */
  function worked(snap, source, key) {
    var ins = snap && snap.inspection;
    var p = ins && ins.players && ins.players[source] && ins.players[source][String(key)];
    if (!p) return null;
    var vsrc = (ins.valuePipeline && ins.valuePipeline.sources && ins.valuePipeline.sources[source]) || {};
    var posInfo = (vsrc.positions && vsrc.positions[p.pos]) || {};
    var rates = vsrc.rates || {};
    var vp = ins.valuePipeline || {}, W = vp.ddfWeights || {}, groups = vsrc.groups || {};
    var budget = function (g) { return finite(vp.pie) !== null && finite(W[g]) !== null ? vp.pie * W[g] : null; };
    var movedGroups = (vsrc.unfundedMoved || []).concat(vsrc.unfundedGroups || []).reduce(function (acc, m) {
      [m.from, m.to, m.group].forEach(function (g) { if (g) acc[g] = true; }); return acc;
    }, {});
    var avail = finite(posInfo.avail), share = finite(p.lineupShare), pStart = finite(p.startWorthy);
    var fill = avail && share !== null && pStart !== null ? Math.max(0, share / avail - pStart) : null;
    var sg = p.pos + '|starter', bg = p.pos + '|bench';
    /* R4-OP-04: the spread the chance above the starter line uses (esPositionParts: σ = max(rate × native, floor)). */
    var lineup = posInfo.lineup || {};
    var sigmaRel = finite(lineup.sigmaRel), sigmaFloor = finite(lineup.sigmaFloor) || 0, native = finite(p.native);
    var sigma = sigmaRel === null || native === null ? null : native > 0 ? Math.max(sigmaRel * native, sigmaFloor) : sigmaFloor;
    var lp = vp.lineup || {}, cs = (vp.chartSigma || {})[p.pos] || null;
    var est = p.estimated && posInfo.estimates ? posInfo.estimates[String(key)] : null;
    return {
      /* JEG-1393 R5-OP-02: the inputs behind availability, the starter line, the spread rate and the DDF weights, at
         the reader's setting, so the worked rows can print their derivation. */
      family: vsrc.family || null, byeShare: finite(lp.bye), missRate: finite(lineup.m), confidence: finite(lp.projection_confidence),
      chartSpread: vsrc.family === 'chart' && cs ? { rate: finite(cs.sigma_rel), band: finite(cs.band), starters: finite(cs.starters),
        rostered: finite(cs.rostered), players: finite(cs.players) } : null,
      starterLineParts: starterLineParts(ins, source, p.pos, posInfo),
      waiverLineParts: waiverLineParts(snap, source, p.pos, posInfo), leagueRostered: finite(posInfo.rostered),
      starterWeightInputs: weightInputs(vp, sg, p.pos), fillInWeightInputs: weightInputs(vp, bg, p.pos),
      allocationParts: allocationParts(vp, p.pos),
      fillPath: est ? est.path || null : null,
      sigmaRel: sigmaRel, sigmaFloor: sigmaFloor, sigma: sigma,
      /* R4-OP-03 / R4-OP-09: how many league allocations the engine averages, and the averaged total value above
         waivers the value-pie factor divides (vorpFactor = pie ÷ surplusTotal in each allocation). */
      allocations: Array.isArray(vp.allocationMix) && vp.allocationMix.length ? vp.allocationMix.length : 1,
      surplusTotal: finite(vsrc.surplusTotal),
      source: source, key: String(key), pos: p.pos, estimated: Boolean(p.estimated), role: p.role || null,
      published: finite(p.native), waiver: finite(posInfo.waiver), starterLine: finite(posInfo.starterLine),
      availability: finite(posInfo.avail), aboveWaivers: finite(p.vorp), startWorthy: finite(p.startWorthy),
      lineupShare: finite(p.lineupShare), starterPart: finite(p.starterSlice), fillInPart: finite(p.benchSlice),
      starterRate: finite(rates[p.pos + '|starter']), fillInRate: finite(rates[p.pos + '|bench']),
      adjusted: finite(p.adjusted),
      aboveWaiversPie: finite(p.vorpDisplay), vorpFactor: finite(vsrc.vorpFactor), fillInChance: fill,
      starterBudget: budget(sg), fillInBudget: budget(bg), starterWeight: finite(W[sg]), fillInWeight: finite(W[bg]),
      starterGroupTotal: finite(groups[sg]), fillInGroupTotal: finite(groups[bg]),
      starterMoved: Boolean(movedGroups[sg]), fillInMoved: Boolean(movedGroups[bg]), pie: finite(vp.pie)
    };
  }
  /* The starter line's two players (value-model.js VP-2.5: the midpoint of the last starter and the first non-starter on
     the source's filled-in list, never below the waiver line), for each starter count the league allocations give the
     position, with the share of the allocations that have it. The list is the engine's own order (rank). */
  function starterLineParts(ins, source, pos, posInfo) {
    var vp = ins.valuePipeline || {};
    var ps = (ins.players && ins.players[source]) || {};
    var work = Object.keys(ps).filter(function (k) { return ps[k].pos === pos && finite(ps[k].rank) !== null && finite(ps[k].native) !== null; })
      .sort(function (a, b) { return ps[a].rank - ps[b].rank; }).map(function (k) { return { key: k, value: ps[k].native }; });
    var mix = Array.isArray(vp.allocationMix) && vp.allocationMix.length ? vp.allocationMix : [{ weight: 1, allocation: vp.allocation }];
    var byS = {}, total = 0;
    mix.forEach(function (m) {
      var a = m.allocation && m.allocation[pos], S = a ? finite(a.starters) : null, wt = finite(m.weight);
      if (S === null || wt === null) return;
      byS[S] = (byS[S] || 0) + wt; total += wt;
    });
    var waiver = finite(posInfo.waiver);
    if (!total || waiver === null) return null;
    var groups = Object.keys(byS).map(Number).sort(function (a, b) { return b - a; }).map(function (S) {
      if (S <= 0 || work.length < S) return { starters: S, share: byS[S] / total, last: null, next: null, line: waiver, floored: true };
      var last = work[S - 1], next = work.length > S ? work[S] : null;
      var mid = next ? (last.value + next.value) / 2 : last.value;
      return { starters: S, share: byS[S] / total, last: last, next: next, mid: mid, line: Math.max(mid, waiver), floored: mid < waiver };
    });
    var line = groups.reduce(function (t, g) { return t + g.share * g.line; }, 0);
    return { groups: groups, line: line, waiver: waiver };
  }
  /* JEG-1393 R6-OP-01: where the waiver line comes from (value-model.js VP-2.3: a chart reads the one player at the
     first seat past the rostered count, work[W]; a projection the mean of the 7 players around it). Each league
     allocation lists its own players, so the line is read from each allocation's own run (TradeValueCurveHarness
     .runPipelineWith, read-only, the same call Full value logic's builder makes), once per snapshot. A league whose
     waiver line follows a replacement player's own row is left without a derivation. */
  function allocationRuns(snap) {
    if (snap._allocRuns !== undefined) return snap._allocRuns;
    var H = window.TradeValueCurveHarness, vp = (snap.inspection && snap.inspection.valuePipeline) || {};
    var mix = Array.isArray(vp.allocationMix) && vp.allocationMix.length ? vp.allocationMix : null;
    var runs = null;
    try {
      if (!mix || mix.length === 1) runs = [{ weight: 1, res: null, allocation: mix ? mix[0].allocation : vp.allocation }];
      else if (H && H.runPipelineWith) runs = mix.map(function (m) { return { weight: m.weight, res: H.runPipelineWith({ seatAllocation: m.allocation }), allocation: m.allocation }; });
    } catch (e) { runs = null; }
    snap._allocRuns = runs;
    return runs;
  }
  function waiverLineParts(snap, source, pos, posInfo) {
    var ins = snap && snap.inspection, waiver = finite(posInfo.waiver);
    if (!ins || waiver === null) return null;
    var vsrc = (ins.valuePipeline && ins.valuePipeline.sources && ins.valuePipeline.sources[source]) || {};
    var family = vsrc.family || null;
    var runs = allocationRuns(snap);
    if (!runs) return null;
    var reads = [];
    for (var j = 0; j < runs.length; j++) {
      var r = runs[j];
      /* One allocation and no rerun: the inspection itself is that allocation's run. */
      var src = r.res ? (r.res.sources || {})[source] : { players: ins.players[source], positions: vsrc.positions };
      var P = src && src.positions && src.positions[pos];
      if (!P || P.bench_basis === 'above_replacement' || finite(P.waiver) === null) return null;
      var ps = src.players || {};
      var work = Object.keys(ps).filter(function (k) { return ps[k].pos === pos && finite(ps[k].rank) !== null && finite(ps[k].native) !== null; })
        .sort(function (a, b) { return ps[a].rank - ps[b].rank; });
      var a = r.allocation && r.allocation[pos];
      var W = finite(P.replacement) !== null ? P.replacement : a ? finite(a.rostered) : finite(P.rostered);
      if (W === null) return null;
      var read = { weight: finite(r.weight) || 0, rostered: W, listed: work.length, waiver: P.waiver };
      if (work.length > W) {
        if (family === 'projection') {
          read.lo = Math.max(0, W - 3) + 1; read.hi = Math.min(work.length, W + 4);
        } else {
          read.key = work[W]; read.value = ps[work[W]].native; read.estimated = Boolean(ps[work[W]].estimated);
        }
      } else if (work.length) {
        read.short = true; read.key = work[work.length - 1]; read.value = ps[read.key].native;
      } else return null;
      reads.push(read);
    }
    var tot = reads.reduce(function (t, x) { return t + x.weight; }, 0);
    if (!tot) return null;
    var heavy = reads.reduce(function (h, x) { return x.weight > h.weight ? x : h; }, reads[0]);
    var line = reads.reduce(function (t, x) { return t + x.weight * x.waiver; }, 0) / tot;
    return { family: family, reads: reads, heavy: heavy, line: line, waiver: waiver, allocations: reads.length };
  }
  /* One group's DDF weight and the included sources' own shares it averages (value-model.js VP-4, ES-15.1: each source
     counts where it has weights and players at the position; held sources are in the included set). */
  /* R7-OP-03: the league allocations at the reader's setting for one position (value-model.js vpAllocate with fractional
     flex and bench seats: allocationMix, each a whole split of the seats with a weight, and allocationExpected, their
     weighted mean). Heaviest first. */
  function allocationParts(vp, pos) {
    var mix = Array.isArray(vp.allocationMix) && vp.allocationMix.length ? vp.allocationMix : vp.allocation ? [{ weight: 1, allocation: vp.allocation }] : null;
    if (!mix) return null;
    var F = ['dedicated', 'superflex', 'flex', 'bench', 'starters', 'rostered'];
    var list = mix.map(function (m) {
      var a = m.allocation && m.allocation[pos];
      if (!a) return null;
      var o = { weight: finite(m.weight) };
      F.forEach(function (f) { o[f] = finite(a[f]); });
      return o.weight === null || o.starters === null || o.rostered === null ? null : o;
    }).filter(Boolean).sort(function (a, b) { return b.weight - a.weight; });
    if (!list.length) return null;
    var e = vp.allocationExpected && vp.allocationExpected[pos], expected = null;
    if (e) { expected = {}; F.forEach(function (f) { expected[f] = finite(e[f]); }); }
    return { list: list, expected: expected };
  }
  function groupMean(vp, group, pos) {
    var srcs = vp.sources || {};
    var rows = (vp.included || []).filter(function (s) {
      var o = srcs[s];
      return o && o.weights && finite(o.weights[group]) !== null && !(o.positions && o.positions[pos] && o.positions[pos].method === 'no_players');
    }).map(function (s) { return { source: s, label: LABELS[s] || s, share: srcs[s].weights[group] }; });
    return rows.length ? { rows: rows, mean: rows.reduce(function (t, r) { return t + r.share; }, 0) / rows.length } : null;
  }
  var ROLES = ['starter', 'bench'];
  var POS4 = ['QB', 'RB', 'WR', 'TE'];
  /* R7-CX-01: each DDF weight's derivation, read back from the engine's own inputs (value-model.js vpWeightsOver, ES-15.1
     and JEG-1366, then VP-4 saved position shares). Default: each group's weight is the mean of the included sources' own
     shares, renormalized over the 8 groups. In a league with two or more QB slots and no superflex, the QB groups are the
     mean of the included projections' own QB shares (held ones too) and RB, WR and TE keep their relative shares of the
     rest. Saved position shares then scale each position's starter and bench weights to its share, in their own ratio.
     The page prints the derivation only when it reproduces the engine's weight (verified); otherwise it names the gap. */
  function twoQbRule(vp) {
    var st = vp.setting || {}, slots = st.slots || {};
    return Math.floor(Number(slots.QB) || 0) >= 2 && !(Number(st.superflex) > 0) && vp.ddfSplit !== 'charts';
  }
  function weightModel(vp) {
    var srcs = vp.sources || {}, means = {}, total = 0;
    POS4.forEach(function (p) { ROLES.forEach(function (role) { var g = p + '|' + role, m = groupMean(vp, g, p); means[g] = m; total += m ? m.mean : 0; }); });
    var base = {}, two = null;
    POS4.forEach(function (p) { ROLES.forEach(function (role) { var g = p + '|' + role; base[g] = means[g] && total > 0 ? means[g].mean / total : 0; }); });
    if (twoQbRule(vp)) {
      var projs = (vp.included || []).filter(function (s) {
        var o = srcs[s];
        return o && o.family === 'projection' && o.weights && finite(o.weights['QB|starter']) !== null && !(o.positions && o.positions.QB && o.positions.QB.method === 'no_players');
      });
      if (projs.length) {
        var q = {};
        ROLES.forEach(function (role) { q[role] = projs.reduce(function (t, s) { return t + srcs[s].weights['QB|' + role]; }, 0) / projs.length; });
        var restRaw = 0;
        ['RB', 'WR', 'TE'].forEach(function (p) { ROLES.forEach(function (role) { restRaw += means[p + '|' + role] ? means[p + '|' + role].mean : 0; }); });
        var remainder = 1 - q.starter - q.bench;
        two = { projections: projs, qbStarter: q.starter, qbBench: q.bench, remainder: remainder, restRaw: restRaw };
        POS4.forEach(function (p) { ROLES.forEach(function (role) {
          var g = p + '|' + role;
          base[g] = p === 'QB' ? q[role] : means[g] && restRaw > 0 ? means[g].mean * remainder / restRaw : 0;
        }); });
      }
    }
    var shares = vp.setting && vp.setting.position_shares && typeof vp.setting.position_shares === 'object' ? vp.setting.position_shares : null;
    var final = {};
    POS4.forEach(function (p) {
      var sh = shares ? finite(shares[p]) : null, bt = base[p + '|starter'] + base[p + '|bench'];
      ROLES.forEach(function (role) { var g = p + '|' + role; final[g] = sh !== null && bt > 0 ? base[g] * sh / bt : base[g]; });
    });
    return { means: means, total: total, base: base, two: two, shares: shares, final: final };
  }
  function weightInputs(vp, group, pos) {
    var m = groupMean(vp, group, pos);
    var W = vp.ddfWeights ? finite(vp.ddfWeights[group]) : null;
    if (!m || W === null) return null;
    var M = weightModel(vp), srcs = vp.sources || {}, role = group.split('|')[1];
    var sh = M.shares ? finite(M.shares[pos]) : null;
    /* The 2-QB rescale and saved shares are ratios, applied in each league allocation and then averaged, so the
       derivation from the averaged source shares lands close to the engine's weight, not on it (about 1e-5 here). */
    var gap = Math.abs(M.final[group] - W);
    var out = { rows: m.rows, mean: m.mean, weight: W, total: M.total, base: M.base[group], computed: M.final[group],
      verified: gap <= 5e-4, exact: gap <= 5e-6 };
    if (M.two) {
      out.twoQb = { projections: M.two.projections.map(function (s) { return { source: s, label: LABELS[s] || s, share: srcs[s].weights['QB|' + role] }; }),
        qbStarter: M.two.qbStarter, qbBench: M.two.qbBench, remainder: M.two.remainder, restRaw: M.two.restRaw };
    }
    if (sh !== null) out.shares = { share: sh, baseStarter: M.base[pos + '|starter'], baseBench: M.base[pos + '|bench'] };
    return out;
  }
  /* How each filled-in player at a source got his estimate (value-model.js estimateFor: "peers" = scaled from the other
     charts, "curve" = the chart's own values against projected points), counted over the given positions. */
  function fillMethods(snap, source, positions) {
    var vsrc = snap && snap.inspection && snap.inspection.valuePipeline && snap.inspection.valuePipeline.sources && snap.inspection.valuePipeline.sources[source];
    if (!vsrc || !vsrc.positions) return null;
    var out = { peers: 0, curve: 0, other: 0 };
    positions.forEach(function (pos) {
      var e = (vsrc.positions[pos] && vsrc.positions[pos].estimates) || {};
      Object.keys(e).forEach(function (k) { var path = e[k] && e[k].path; out[path === 'peers' || path === 'curve' ? path : 'other'] += 1; });
    });
    return out;
  }
  function buildUpSources() {
    var S = window.DDFAuditSource;
    return S ? S.SOURCES.map(function (s) { return { key: s.key, label: LABELS[s.key] || s.label, family: s.family }; }) : [];
  }

  /* A source's own page, from the bundle (sources.<key>.url, else .source_url); same position swap as audit-source.js. */
  function sourceUrl(key, position) {
    var snap = window.TradeValueProductData && window.TradeValueProductData.getSnapshot ? window.TradeValueProductData.getSnapshot() : null;
    var src = snap && snap.sources && snap.sources[key];
    var url = src && (src.url || src.source_url);
    if (typeof url !== 'string' || !/^https?:\/\//.test(url)) return '';
    var pos = ['QB', 'RB', 'WR', 'TE'].indexOf(position) >= 0 ? position : 'QB';
    if (key === 'cbsros') return url.replace('/QB/', '/' + pos + '/');
    if (key === 'razzball') return url.replace('-qb-', '-' + pos.toLowerCase() + '-');
    return url;
  }

  /* Settings checked on this page apply to this page only: the engine's own setters with publish off, never
     DDF.engine.apply (which saves them as the reader's league). With no settings the engine keeps the reader's
     saved league, which ddf-engine.js applied before `ready` resolved. */
  function applyHere(C, s) {
    if (s.scoring) C.setScoring(s.scoring, false);
    if (s.teams) C.setTeams(Number(s.teams), false);
    if (s.roster) Object.keys(s.roster).forEach(function (k) { C.setRosterSpot(k, s.roster[k], false); });
  }
  /* Learn explains the default DDF Value (the four-chart mean), so a reader's own value basis is set aside on this
     page only (publish off; ddf-engine.js keeps it saved) and named in the page's notes. */
  function readerBasisLabel(E) {
    var rec = E.basis ? E.basis() : null;
    if (!rec || !rec.mode || rec.mode === 'default') return null;
    if (rec.mode === 'single') return (LABELS[rec.source] || rec.source) + ' only';
    return 'a blend of ' + (rec.sources || []).map(function (s) { return LABELS[s] || s; }).join(', ');
  }
  function pinDefaultBasis(C) {
    var b = C.getBasis ? C.getBasis() : null;
    if (b && b.isDefault === false) C.setBasis(null, false);
  }
  function load(settings) {
    var E = engine();
    if (!E) return Promise.reject(new Error('engine missing'));
    return E.ready.then(function (C) {
      C = E.controls() || C;
      pinDefaultBasis(C);
      if (settings) applyHere(C, settings);
      var snap = snapshot();
      snap.readerBasis = readerBasisLabel(E);
      return snap;
    });
  }

  window.DDFLearnEngine = {
    CHARTS: CHARTS, LABELS: LABELS, SCORING_LABEL: SCORING_LABEL,
    load: load, snapshot: snapshot, health: health, buildUp: buildUp, worked: worked, fillMethods: fillMethods, buildUpSources: buildUpSources, sourceUrl: sourceUrl,
    rosterLabel: rosterLabel, onRebuild: function (fn) { var E = engine(); if (E && E.on) E.on(fn); }
  };
})();
