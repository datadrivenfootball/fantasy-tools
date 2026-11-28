// DDF draft tool page, Phase 1 (JEG-1667): the DOM, keyboard and link save
// over draft-core.js. No value math here: every number on the page comes
// from DraftCore.board / buildModel (the Phase 0 engine).
//
// Screens: Board (home), Values, My roster, Setup. State lives in the URL
// fragment (#s=<token>+<check>), rewritten after every change; nothing the
// user enters is sent to a server.
//
// DraftApp.init(opts) -> Promise (also DraftApp.ready). opts (all optional):
//   bundle, lineup   preloaded data (review preview, tests); else Supabase
//   model            a fixed price model (tests: the worked example)
//   state            a starting state; else the link, else the last one in
//                    this tab, else a default league (Setup opens first)
//   now              clock for the stale warning (tests)
(function (root) {
  "use strict";

  var C = root.DraftCore, D = root.DraftData;
  var doc = root.document;
  var ROW_LIMIT = 150;
  var POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "K", "DST"];
  var SCORING_FIELDS = [["rec", "Reception"], ["pass_yds", "Pass yard"], ["pass_tds", "Pass TD"], ["ints", "Interception"],
    ["rush_yds", "Rush yard"], ["rush_tds", "Rush TD"], ["rec_yds", "Rec yard"], ["rec_tds", "Rec TD"], ["fum_lost", "Fumble lost"]];
  var STORE_KEY = "ddf:draft";

  var app = { bundle: null, lineup: null, model: null, fixedModel: false, state: null, calc: null, sel: null, bid: "",
    view: "board", pos: "ALL", q: "", showAll: false, buyerMode: false, toast: null, lastMs: null, maxMs: 0,
    vpos: "ALL", vq: "", vAll: false, setup: { ref: "", msg: null, url: null, paste: "", read: null, link: "" },
    token: null, now: null, bound: false, linkError: null };

  // ---------------------------------------------------------------- helpers
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function money(v) { return v == null || !isFinite(v) ? "–" : "$" + Math.round(v); }
  function money1(v) { return v == null || !isFinite(v) ? "–" : "$" + (Math.round(v * 10) / 10).toFixed(1); }
  function bidCell(v) { return v == null || v <= 0 ? '<span class="zero">–</span>' : "$" + v; }
  function pct(factor) {
    if (factor == null || !isFinite(factor)) return "–";
    var p = (factor - 1) * 100;
    return (p >= 0 ? "+" : "−") + Math.abs(p).toFixed(1) + "%";
  }
  function $(id) { return doc.getElementById(id); }
  function player(key) { return app.model.players[key] || { name: key, pos: app.model.pos[key], team: "" }; }
  function minBid() { return app.state.league.minBid; }
  // The last link, kept on this device only, so a reload mid-draft loses nothing.
  function store(fn) { try { return fn(root.localStorage); } catch (e) { return null; } }
  // Two-step confirm inside the page (some hosts never show confirm()): the
  // first call shows the warning, a second call within 8 seconds goes ahead.
  var pending = { key: null, at: 0 };
  function confirmed(key, message) {
    var now = Date.now();
    if (pending.key === key && now - pending.at < 8000) { pending.key = null; return true; }
    pending.key = key; pending.at = now;
    app.setup.msg = message + " Press the button again to confirm."; app.setup.ok = false;
    app.toast = app.setup.msg;
    render();
    return false;
  }
  function nowMs() { return root.performance && root.performance.now ? root.performance.now() : Date.now(); }
  function teamLetter(i) { return String.fromCharCode(65 + i); }

  // ------------------------------------------------------------------- data
  function loadData(opts) {
    if (opts.model) { app.model = opts.model; app.fixedModel = true; app.bundle = opts.bundle || { players: [], credits: [], asOf: {} }; return Promise.resolve(); }
    if (opts.bundle) { app.bundle = opts.bundle; app.lineup = opts.lineup; return Promise.resolve(); }
    return Promise.all([
      D.loadSupabase(),
      root.fetch("../trade-value-chart/assets/lineup-parameters.json").then(function (r) {
        if (!r.ok) throw new Error("lineup parameters: HTTP " + r.status);
        return r.json();
      })
    ]).then(function (got) { app.bundle = got[0]; app.lineup = got[1]; });
  }

  function loadState(opts) {
    if (opts.state) { app.state = C.normalizeState(opts.state); return Promise.resolve(); }
    var stored = store(function (s) { return s.getItem(STORE_KEY); });
    return C.decodeLink(root.location.hash).then(function (fromLink) {
      if (fromLink && !fromLink.error) { app.state = fromLink; return null; }
      if (fromLink && fromLink.error) app.linkError = fromLink.error;
      return stored ? C.decodeLink(stored) : null;
    }).then(function (fromStore) {
      if (app.state) return;
      if (fromStore && !fromStore.error) { app.state = fromStore; return; }
      app.state = C.newState(C.defaultLeague());
      app.view = "setup";
    });
  }

  function rebuild() {
    if (!app.fixedModel) app.model = C.buildModel(app.bundle, app.state.league, app.state.overrides, app.lineup);
    recompute();
  }

  function recompute() {
    app.calc = C.board(app.state, app.model);
    var avail = app.calc.derived.available;
    if (!app.sel || app.calc.derived.sold[app.sel] || app.model.pos[app.sel] == null) app.sel = visibleKeys()[0] || avail[0] || null;
  }

  // After any change to the draft state: recompute, redraw, time it, save.
  function commit(message) {
    var t0 = nowMs();
    recompute();
    if (message !== undefined) app.toast = message;
    render();
    app.lastMs = nowMs() - t0;
    app.maxMs = Math.max(app.maxMs, app.lastMs);
    var tag = $("recompute-ms");
    if (tag) { tag.hidden = false; tag.textContent = "Recomputed in " + app.lastMs.toFixed(0) + " ms"; }
    return saveLink();
  }

  function saveLink() {
    return C.encodeState(app.state).then(function (token) {
      app.token = token;
      try { root.history.replaceState(null, "", "#s=" + token); } catch (e) { /* sandboxed frame */ }
      store(function (s) { s.setItem(STORE_KEY, token); });
      return token;
    }).catch(function () { app.token = null; return null; });
  }

  // In the review preview the page has no address of its own to share, so
  // the link is the "#s=" part alone (paste it under Setup to reopen).
  function linkUrl() { return (app.preview ? "" : String(root.location.href).split("#")[0]) + "#s=" + app.token; }

  // ---------------------------------------------------------------- actions
  function visibleKeys() {
    if (!app.calc) return [];
    var q = app.q.trim().toLowerCase();
    var keys = app.calc.derived.available.filter(function (k) {
      if (app.pos !== "ALL" && app.model.pos[k] !== app.pos) return false;
      return !q || player(k).name.toLowerCase().indexOf(q) !== -1;
    });
    return q || app.showAll ? keys : keys.slice(0, ROW_LIMIT);
  }

  function select(key, scroll) {
    if (!key || key === app.sel) return;
    app.sel = key; app.bid = ""; app.buyerMode = false; app.toast = null;
    var rows = doc.querySelectorAll("#rows tr[aria-selected=true]");
    for (var i = 0; i < rows.length; i += 1) rows[i].setAttribute("aria-selected", "false");
    var row = rowEl(key);
    if (row) { row.setAttribute("aria-selected", "true"); if (scroll && row.scrollIntoView) row.scrollIntoView({ block: "nearest" }); }
    drawBlock();
  }
  function rowEl(key) {
    var rows = doc.querySelectorAll("#rows tr");
    for (var i = 0; i < rows.length; i += 1) if (rows[i].getAttribute("data-key") === key) return rows[i];
    return null;
  }
  function move(delta) {
    var keys = visibleKeys();
    if (!keys.length) return;
    var i = keys.indexOf(app.sel);
    var next = i === -1 ? 0 : Math.max(0, Math.min(keys.length - 1, i + delta));
    select(keys[next], true);
  }

  function setBid(text) {
    app.bid = String(text).replace(/\D/g, "").replace(/^0+(?=\d)/, "").slice(0, 5);
    app.toast = null;
    drawBlock();
  }
  function stepBid(delta) {
    var cur = app.bid === "" ? minBid() - (delta > 0 ? 1 : 0) : Number(app.bid);
    setBid(String(Math.max(minBid(), cur + delta)));
  }
  function bidTo(field, label) {
    var row = app.sel && app.calc.rows[app.sel];
    var v = row ? row[field] : null;
    if (!(v >= minBid())) { app.toast = "No " + label + " for this player (no slot, no money, or no rival to push)."; app.bid = ""; drawBlock(); return; }
    setBid(String(v));
  }

  function bidPrice() {
    var price = Number(app.bid);
    if (app.bid === "" || !(price >= minBid())) { app.toast = "Type the price first (or press W or P)."; drawBlock(); return null; }
    return price;
  }

  // Record a sale of the selected player to a team at the current bid.
  function sell(teamIndex) {
    if (!app.sel) return;
    var price = bidPrice();
    if (price === null) return;
    var team = app.calc.derived.teams[teamIndex];
    if (!team) return;
    var open = C.SLOT_KEYS.reduce(function (t, k) { return t + team.open[k]; }, 0);
    if (open <= 0) { app.toast = team.name + " has no roster spot left."; app.buyerMode = false; drawBlock(); return; }
    if (price > team.budgetLeft) { app.toast = team.name + " has only $" + team.budgetLeft + " left."; app.buyerMode = false; drawBlock(); return; }
    var name = player(app.sel).name;
    app.state.picks.push([app.sel, teamIndex, price]);
    var next = nextAfter(app.sel);
    app.bid = ""; app.buyerMode = false; app.q = ""; app.sel = next;
    return commit((teamIndex === app.state.me ? "Bought " : "Sold ") + name + " for $" + price +
      (teamIndex === app.state.me ? "." : " to " + team.name + "."));
  }
  function nextAfter(key) {
    var keys = visibleKeys(), i = keys.indexOf(key);
    return i === -1 ? null : (keys[i + 1] || keys[i - 1] || null);
  }
  function myBuy() { return sell(app.state.me); }
  function startSold() {
    if (!app.sel || bidPrice() === null) return;
    app.buyerMode = true; app.toast = null;
    drawBlock();
  }
  function undo() {
    var last = app.state.picks.pop();
    if (!last) { app.toast = "Nothing to undo."; drawBlock(); return; }
    app.sel = last[0]; app.bid = String(last[2]); app.buyerMode = false; app.q = "";
    return commit("Undid " + player(last[0]).name + " for $" + last[2] + ".");
  }

  function setView(view) {
    app.view = view; app.buyerMode = false;
    render();
  }

  function setOverride(key, value) {
    if (value === null) delete app.state.overrides[key];
    else app.state.overrides[key] = Math.max(0, Math.min(200, Math.round(value * 10) / 10));
    rebuild();
    return commit();
  }

  function applyLeague(league, message) {
    if (app.state.picks.length && !confirmed("league", "Loading a league clears the " + app.state.picks.length + " sales recorded so far.")) return;
    var overrides = app.state.overrides;
    app.state = C.newState(league);
    app.state.overrides = overrides;
    app.sel = null;
    rebuild();
    return commit(message);
  }
  function editLeague(change) {
    change(app.state.league);
    app.state = C.normalizeState(app.state);
    rebuild();
    return commit();
  }

  // ------------------------------------------------------------------ board
  function statusHtml() {
    var st = D.staleness(app.bundle, app.now);
    var total = app.model.league.teams * C.SLOT_KEYS.reduce(function (t, k) { return t + app.state.league.slots[k]; }, 0);
    var last = app.state.picks[app.state.picks.length - 1];
    var h = '<div class="status">';
    h += '<span class="tag" id="pick-count">Pick ' + (app.state.picks.length + 1) + " of " + total + "</span>";
    if (last) h += '<span class="tag" id="last-sale">Last sale: ' + esc(player(last[0]).name) + " $" + last[2] + " · " + esc(app.state.league.teams[last[1]].name) + "</span>";
    if (app.bundle.season) h += '<span class="tag">' + esc(app.bundle.season) + " data</span>";
    if (app.bundle.asOf && app.bundle.asOf.pullDate) h += '<span class="tag" id="updated">Updated ' + esc(app.bundle.asOf.pullDate) + "</span>";
    if (st.stale && !app.fixedModel) {
      h += '<span class="tag warn" id="stale" role="status">' + (st.pullDate
        ? "Stale: last pull " + esc(st.pullDate) + ", " + Math.floor(st.hours / 24) + " day" + (Math.floor(st.hours / 24) === 1 ? "" : "s") + " old"
        : "Stale: no pull found") + "</span>";
    }
    h += '<span class="tag" id="recompute-ms"' + (app.lastMs == null ? " hidden" : "") + ">" + (app.lastMs == null ? "" : "Recomputed in " + app.lastMs.toFixed(0) + " ms") + "</span>";
    h += "</div>";
    return h;
  }

  function blockHtml() {
    if (!app.sel) return '<p class="muted">No players left on the board.</p>';
    var r = app.calc.rows[app.sel], p = player(app.sel), s = app.state;
    var tier = app.model.tiers[app.sel];
    var h = '<div class="row between"><div><div class="name" id="block-name">' + esc(p.name) + '</div><div class="small muted"><span class="pos">' + esc(r.pos) + "</span> " +
      esc(p.team || "") + (p.bye ? " · bye " + p.bye : "") + ' · <span id="block-source">' + esc(r.source) + "</span></div></div>" +
      (tier ? '<span class="tier">T' + tier + "</span>" : "") + "</div>";
    h += '<div class="lead"><div class="walk"><span>Walk-away</span><b id="block-walk">' + bidCell(r.walkAway) + "</b></div>" +
      '<div><span>Push floor</span><b id="block-push">' + bidCell(r.pushFloor) + "</b></div>" +
      '<div><span>Buy limit</span><b id="block-buy">' + bidCell(r.buyLimit) + "</b></div></div>";
    var why = [];
    if (r.walkAway === 0) why.push(r.myMaxBid < minBid() ? "No money left for another player." : "No open slot for a " + esc(r.pos) + ".");
    else if (r.buyLimit < r.walkAway) why.push("Only the bench fits him: buy limit is half his price.");
    if (r.pushFloor != null && r.pushFloor < r.buyLimit) why.push("Above $" + r.pushFloor + " no rival can top us: a higher bid is a purchase.");
    if (r.buyLimit >= minBid() && r.pushFloor == null) why.push("No rival can bid against us here.");
    if (why.length) h += '<p class="small muted" id="block-why">' + why.join(" ") + "</p>";
    h += '<div class="three" style="margin-top:8px">' +
      "<div><span>Ours " + (r.ourFactor === "personal" ? "(personal)" : "(room)") + '</span><b id="block-ours">' + money1(r.oursInflated) + "</b></div>" +
      '<div><span>Market now</span><b id="block-market">' + money1(r.marketInflated) + "</b></div>" +
      '<div><span>Platform now</span><b id="block-platform">' + money1(r.platformInflated) + "</b></div></div>";
    h += '<p class="small muted" style="margin-top:6px">Pre-draft: ours ' + money1(r.ours) + ", market " + money1(r.market) + ", platform " + money1(r.platform) +
      ". Ours at the room rate " + money1(r.oursInflatedRoom) + ". My max bid $" + r.myMaxBid + ", best rival max $" + r.rivalCeiling + ".</p>";
    h += '<div class="bidrow"><button type="button" class="step" data-act="bid-down" aria-label="Bid down">−</button>' +
      '<input id="bid" inputmode="numeric" aria-label="Current bid" placeholder="$" value="' + esc(app.bid) + '">' +
      '<button type="button" class="step" data-act="bid-up" aria-label="Bid up">+</button>' +
      '<span class="small muted">Current bid</span></div>';
    h += '<div class="actions">' +
      '<button type="button" data-act="walk">Bid walk-away<kbd>W</kbd></button>' +
      '<button type="button" data-act="push">Bid push floor<kbd>P</kbd></button>' +
      '<button type="button" class="primary" data-act="mine">My buy<kbd>M</kbd></button>' +
      '<button type="button" data-act="sold"' + (app.buyerMode ? ' aria-pressed="true"' : "") + ">Sold<kbd>S</kbd></button>" +
      '<button type="button" data-act="undo">Undo<kbd>U</kbd></button></div>';
    if (app.buyerMode) {
      h += '<p class="small" style="margin-top:8px"><b>Who bought him for $' + esc(app.bid) + "?</b> Tap a team or press its letter. <kbd>Esc</kbd> cancels.</p><div class=\"buyers\" id=\"buyers\">";
      app.calc.derived.teams.forEach(function (t, i) {
        h += '<button type="button" data-buyer="' + i + '"><kbd>' + teamLetter(i) + "</kbd> " + esc(t.name) + (i === s.me ? " (me)" : "") +
          '<br><span class="small muted num">max $' + Math.max(0, app.calc.board.maxBids[i]) + "</span></button>";
      });
      h += "</div>";
    }
    if (app.toast) h += '<p class="note toast" id="toast" role="status">' + esc(app.toast) + "</p>";
    return h;
  }
  function drawBlock() {
    var el = $("block");
    if (!el) return;
    var hadFocus = doc.activeElement && doc.activeElement.id === "bid";
    el.innerHTML = blockHtml();
    if (hadFocus && $("bid")) { $("bid").focus(); $("bid").setSelectionRange(app.bid.length, app.bid.length); }
  }

  function rowsHtml() {
    var keys = visibleKeys(), h = "";
    keys.forEach(function (k) {
      var r = app.calc.rows[k], p = player(k), tier = app.model.tiers[k];
      h += '<tr data-key="' + esc(k) + '" aria-selected="' + (k === app.sel) + '">' +
        '<td class="nm"><b>' + esc(p.name) + '</b> <span class="pos">' + esc(r.pos) + '</span> <span class="src">' + esc(p.team || "") + "</span></td>" +
        '<td class="r walk" data-f="walk">' + bidCell(r.walkAway) + "</td>" +
        '<td class="r num" data-f="push">' + bidCell(r.pushFloor) + "</td>" +
        '<td class="r num" data-f="buy">' + bidCell(r.buyLimit) + "</td>" +
        '<td class="r num wide" data-f="ours">' + money(r.oursInflated) + "</td>" +
        '<td class="r num wide" data-f="market">' + money(r.marketInflated) + "</td>" +
        '<td class="r num wide" data-f="platform">' + money(r.platformInflated) + "</td>" +
        '<td class="wide">' + (tier ? '<span class="tier">T' + tier + "</span>" : "") + "</td>" +
        '<td class="wide src" data-f="source">' + esc(r.source) + "</td></tr>";
    });
    return h || '<tr><td colspan="9" class="muted">No players match.</td></tr>';
  }

  function sideHtml() {
    var inf = app.calc.inflation, s = app.state, teams = app.calc.derived.teams, maxBids = app.calc.board.maxBids;
    var usingPersonal = s.ourFactor !== "room" && inf.personal != null;
    var h = '<div class="card"><h3>Inflation</h3><div class="row between"><div><div class="big ' + ((usingPersonal ? inf.personal : inf.room) >= 1 ? "up" : "dn") + '" id="infl-main">' +
      pct(usingPersonal ? inf.personal : inf.room) + '</div><div class="small muted">' + (usingPersonal ? "Personal (ours): my money against my share of the value left" : "Room rate (ours)") + "</div></div>" +
      '<div class="row" role="group" aria-label="Which rate prices our bids"><button type="button" data-factor="personal" aria-pressed="' + (s.ourFactor !== "room") + '">Personal</button>' +
      '<button type="button" data-factor="room" aria-pressed="' + (s.ourFactor === "room") + '">Room</button></div></div>' +
      '<p class="small muted num" style="margin-top:8px">Room rate, for reference: ours <span id="infl-room">' + pct(inf.room) + '</span> · market <span id="infl-market">' + pct(inf.market) +
      "</span> · platform " + pct(inf.platform) + "</p>" +
      '<p class="small muted num">$' + Math.round(inf.moneyLeft) + " left in the room · $" + Math.round(inf.valueLeft) + " of our value left above $" + minBid() + " · " + inf.openSlots + " open slots</p></div>";

    var top = Math.max.apply(null, teams.map(function (t) { return maxBids[t.id]; }).concat([1]));
    var selRow = app.sel ? app.calc.rows[app.sel] : null;
    var reach = selRow && selRow.marketInflated != null ? selRow.marketInflated : null;
    h += '<div class="card"><h3>Max bid by team</h3><div id="maxbids">';
    teams.slice().sort(function (a, b) { return maxBids[b.id] - maxBids[a.id] || a.id - b.id; }).forEach(function (t) {
      var mb = Math.max(0, maxBids[t.id]);
      var low = reach != null && mb < reach;
      h += '<div class="mb' + (t.id === s.me ? " me" : "") + '" data-team="' + t.id + '"><span class="who">' + esc(t.name) + (t.id === s.me ? " (me)" : "") +
        '</span><div class="bar"><i' + (low ? ' class="low"' : "") + ' style="width:' + Math.round(mb / top * 100) + '%"></i></div><span class="num" data-f="maxbid">$' + mb + "</span></div>";
    });
    h += '</div><p class="small muted" style="margin-top:8px">Max bid = money left minus $' + minBid() + " for each other open slot. Orange cannot reach the selected player's market price now.</p></div>";

    h += '<div class="card"><h3>Tier cliffs</h3><div id="cliffs">';
    C.tierCliffs(app.model, app.calc.derived.available).forEach(function (c) {
      h += '<div class="cliff" data-pos="' + c.pos + '"><span class="pos">' + c.pos + "</span>";
      if (c.tier == null) h += '<span class="muted">None left</span><span></span>';
      else {
        h += "<span><b>" + c.left + "</b> left in T" + c.tier + ' <span class="muted small">' + esc(c.keys.slice(0, 3).map(function (k) { return player(k).name; }).join(", ")) +
          (c.left > 3 ? ", …" : "") + "</span></span>" +
          '<span class="num ' + (c.left <= 2 && c.drop != null ? "dn" : "muted") + '">' + (c.drop == null ? "last tier" : "then −$" + Math.round(c.drop)) + "</span>";
      }
      h += "</div>";
    });
    h += '</div><p class="small muted" style="margin-top:8px">Tiers are bands of our pre-draft prices: a tier holds everyone within $' + C.TIER_GAP_DOLLARS + " or " +
      Math.round(C.TIER_GAP_SHARE * 100) + "% of its best player, whichever is larger.</p></div>";

    h += '<div class="card"><h3>Sales</h3>';
    if (!s.picks.length) h += '<p class="small muted">No sales yet.</p>';
    else {
      h += '<div id="sales">';
      s.picks.slice(-8).reverse().forEach(function (p) {
        h += '<div class="row between small"><span>' + esc(player(p[0]).name) + ' <span class="muted">' + esc(s.league.teams[p[1]].name) + '</span></span><span class="num">$' + p[2] + "</span></div>";
      });
      h += "</div>";
    }
    h += "</div>";
    return h;
  }

  function boardHtml() {
    var h = statusHtml() + '<div class="board"><div class="stack"><div class="card block" id="block">' + blockHtml() + "</div><div>" +
      '<div class="filters"><input type="search" id="q" placeholder="Search player ( / )" aria-label="Search player" value="' + esc(app.q) + '">';
    POSITIONS.forEach(function (ps) {
      h += '<button type="button" class="chip' + (app.pos === ps ? " on" : "") + '" data-pos="' + ps + '">' + (ps === "ALL" ? "All" : ps) + "</button>";
    });
    h += '</div><div class="tw"><table><thead><tr><th>Player</th><th class="r">Walk-away</th><th class="r">Push floor</th><th class="r">Buy limit</th>' +
      '<th class="r wide">Ours now</th><th class="r wide">Market now</th><th class="r wide">Platform now</th><th class="wide">Tier</th><th class="wide">Source</th></tr></thead>' +
      '<tbody id="rows">' + rowsHtml() + "</tbody></table></div>";
    var shown = visibleKeys().length, all = app.calc.derived.available.length;
    if (!app.showAll && !app.q && app.pos === "ALL" && shown < all) h += '<p class="small muted" style="margin-top:8px">Showing the top ' + shown + " of " + all + ' players. <button type="button" data-act="show-all">Show all</button></p>';
    h += '</div></div><div class="stack side">' + sideHtml() + "</div></div>";
    return h;
  }

  // ----------------------------------------------------------------- values
  function valuesHtml() {
    var m = app.model, s = app.state, st = D.staleness(app.bundle, app.now), asOf = app.bundle.asOf || {};
    var nOver = Object.keys(s.overrides).length;
    var h = '<div class="status"><span class="tag" id="v-updated">Updated ' + esc(asOf.pullDate || "unknown") + "</span>";
    if (st.stale) h += '<span class="tag warn" id="v-stale" role="status">Stale: the daily pull is more than a day old</span>';
    if (asOf.projections) h += '<span class="tag">Projections ' + esc(asOf.projections) + "</span>";
    if (asOf.vegas) h += '<span class="tag">Vegas lines ' + esc(asOf.vegas) + "</span>";
    var counts = m.counts || {};
    h += '<span class="tag" id="v-counts">vegas ' + (counts.vegas || 0) + " · vegas+proj " + (counts["vegas+proj"] || 0) + " · proj " + (counts.proj || 0) + " · market " + (counts.market || 0) + "</span>";
    h += "</div>";
    h += '<div class="card stack"><div class="filters"><input type="search" id="vq" placeholder="Search player" aria-label="Search player" value="' + esc(app.vq) + '">';
    POSITIONS.slice(0, 5).forEach(function (ps) {
      h += '<button type="button" class="chip' + (app.vpos === ps ? " on" : "") + '" data-vpos="' + ps + '">' + (ps === "ALL" ? "All" : ps) + "</button>";
    });
    h += '<span class="small muted" id="v-overrides">' + nOver + " override" + (nOver === 1 ? "" : "s") + "</span>" +
      (nOver ? '<button type="button" data-act="reset-overrides">Reset all</button>' : "") + "</div>";
    var q = app.vq.trim().toLowerCase();
    var keys = m.order.filter(function (k) {
      if (["QB", "RB", "WR", "TE"].indexOf(m.pos[k]) === -1) return false;
      if (app.vpos !== "ALL" && m.pos[k] !== app.vpos) return false;
      if (q && player(k).name.toLowerCase().indexOf(q) === -1) return false;
      return m.values[k] != null || m.prices.market[k] != null || m.prices.platform[k] != null;
    });
    var total = keys.length;
    if (!app.vAll && !q) keys = keys.slice(0, 200);
    h += '<div class="tw"><table><thead><tr><th>#</th><th>Player</th><th class="r">Ours</th><th class="r">Market</th><th class="r">Platform</th><th class="r">Spread</th>' +
      '<th>Tier</th><th>Source</th><th>DDF Value (override)</th><th class="wide">Bye</th></tr></thead><tbody id="vrows">';
    keys.forEach(function (k, i) {
      var p = player(k), ours = m.prices.ours[k], mkt = m.prices.market[k], plat = m.prices.platform[k];
      var spread = ours != null && mkt != null ? ours - mkt : null;
      var ovr = s.overrides[k] != null, sold = app.calc.derived.sold[k];
      var val = m.values[k];
      h += '<tr data-key="' + esc(k) + '"><td class="num muted">' + (i + 1) + '</td><td class="nm"><b>' + esc(p.name) + '</b> <span class="pos">' + esc(m.pos[k]) + '</span> <span class="src">' + esc(p.team || "") +
        (sold ? " · sold $" + sold[1] : "") + "</span></td>" +
        '<td class="r num" data-f="ours"><b>' + money1(ours) + '</b></td><td class="r num" data-f="market">' + money1(mkt) + '</td><td class="r num" data-f="platform">' + money1(plat) + "</td>" +
        '<td class="r num ' + (spread == null ? "" : spread >= 0.5 ? "up" : spread <= -0.5 ? "dn" : "") + '" data-f="spread">' + (spread == null ? "–" : (spread >= 0 ? "+" : "−") + Math.abs(spread).toFixed(1)) + "</td>" +
        "<td>" + (m.tiers[k] ? '<span class="tier">T' + m.tiers[k] + "</span>" : "") + '</td><td class="src" data-f="source">' + esc(m.prices.source[k] || "unpriced") + "</td>" +
        '<td><span class="stepper' + (ovr ? " ovr" : "") + '"><button type="button" data-ovr="-1" aria-label="Lower DDF Value">−</button>' +
        '<input data-ovr-input inputmode="decimal" aria-label="DDF Value for ' + esc(p.name) + '" value="' + (val == null ? "" : (Math.round(val * 10) / 10).toFixed(1)) + '">' +
        '<button type="button" data-ovr="1" aria-label="Raise DDF Value">+</button></span>' +
        (ovr ? ' <button type="button" data-ovr-reset aria-label="Reset override">Reset</button>' : "") + "</td>" +
        '<td class="wide num muted">' + (p.bye || "") + "</td></tr>";
    });
    h += "</tbody></table></div>";
    if (keys.length < total) h += '<p class="small muted">Showing the top ' + keys.length + " of " + total + '. <button type="button" data-act="v-all">Show all</button></p>';
    h += '<div class="grid2"><p class="note"><b>How to read it.</b> Spread is ours minus market, in this league\'s dollars before any sale. Source says where our price came from: Vegas season props, props with the projection filling the gaps, the projection alone, or the market. An override replaces the player\'s DDF Value, as on the trade tools; a green border marks it and every other price re-splits the same money.</p>' +
      '<p class="note">Market is the FantasyPros consensus rank (' + esc(m.formats ? m.formats.ecr : "") + ") on ESPN's dollar curve. Platform is ESPN's published auction value (" + esc(m.formats ? m.formats.espn : "") +
      "), rescaled to this league. " + (s.league.platform === "espn" || s.league.platform === "manual" ? "" : "This league is on " + esc(s.league.platform) + ": its own draft-room values are not loaded yet, so ESPN's stand in.") + "</p></div></div>";
    return h;
  }

  // ----------------------------------------------------------------- roster
  function rosterHtml() {
    var s = app.state, me = app.calc.derived.teams[s.me], sum = C.rosterSummary(s, app.model, app.calc.derived);
    var h = '<div class="status"><span class="tag">' + esc(me.name) + '</span><span class="tag" id="r-money">$' + sum.spent + " spent · $" + sum.budgetLeft + ' left</span><span class="tag" id="r-max">My max bid $' +
      Math.max(0, app.calc.board.maxBids[s.me]) + "</span></div>";
    h += '<div class="grid2"><div class="card"><h3>Starters and bench</h3><div id="r-slots">';
    sum.slots.forEach(function (x) {
      if (!x.key) h += '<div class="slot open" data-slot="' + x.slot + '"><span class="pos">' + x.slot + "</span><span>Open</span><span></span><span></span></div>";
      else {
        h += '<div class="slot" data-slot="' + x.slot + '" data-key="' + esc(x.key) + '"><span class="pos">' + (x.slot === "OVER" ? "NO SLOT" : x.slot) + "</span><span>" + esc(x.name) +
          ' <span class="muted small">' + esc(x.pos) + (x.bye ? " · bye " + x.bye : "") + '</span></span><span class="num muted small">' + (x.value == null ? "" : "DDF " + x.value.toFixed(1)) +
          '</span><span class="num">$' + x.price + "</span></div>";
      }
    });
    h += "</div></div><div class=\"stack\">";
    h += '<div class="card"><h3>Open starters</h3><div id="r-open">';
    if (!sum.openStarters.length) h += '<p class="small">Every starting slot is filled.</p>';
    else h += '<div class="row">' + sum.openStarters.map(function (o) { return '<span class="chip">' + o.count + " " + o.slot + "</span>"; }).join("") + "</div>";
    h += "</div></div>";
    h += '<div class="card"><h3>Bye collisions</h3><div id="r-byes">';
    if (!sum.byeCollisions.length) h += '<p class="small">No week has two of my starters on bye.</p>';
    else sum.byeCollisions.forEach(function (c) {
      h += '<p class="warn" style="margin-bottom:6px" data-week="' + c.week + '">Week ' + c.week + ": " + c.players.length + " starters out (" + esc(c.players.join(", ")) + ").</p>";
    });
    h += "</div></div>";
    var share = sum.starterShare;
    h += '<div class="card"><h3>Starter value vs roster value</h3><div class="kpis">' +
      '<div class="kpi"><span>DDF Value, starters</span><b class="big" id="r-starter-value">' + sum.starterValue.toFixed(1) + "</b></div>" +
      '<div class="kpi"><span>DDF Value, roster</span><b class="big" id="r-roster-value">' + sum.rosterValue.toFixed(1) + "</b></div>" +
      '<div class="kpi"><span>Share that starts</span><b class="big" id="r-share">' + (share == null ? "–" : Math.round(share * 100) + "%") + "</b></div></div>" +
      '<p class="small muted" style="margin-top:8px">Dollars: $' + sum.starterDollars + " of $" + sum.rosterDollars + " spent sit in starters. Value on the bench cannot be started every week.</p></div>";
    h += "</div></div>";
    return h;
  }

  // ------------------------------------------------------------------ setup
  function setupHtml() {
    var s = app.state, lg = s.league, su = app.setup, teams = app.calc.derived.teams;
    var h = '<div class="grid2 g-wide"><div class="stack">';
    h += '<div class="card stack"><h2>1. Your league</h2><p class="small muted">Paste a league link or ID from Sleeper or ESPN and the tool reads teams, budgets, roster slots and scoring. Nothing is sent anywhere but the platform\'s own public address. It never asks for a password, cookie or token.</p>' +
      '<div class="row"><input type="text" id="league-ref" placeholder="League link or ID" aria-label="League link or ID" style="flex:1 1 220px" value="' + esc(su.ref) + '">' +
      '<button type="button" class="primary" data-act="fetch-league">Get league</button></div>';
    if (su.msg) h += '<p class="' + (su.ok ? "note" : "warn") + '" id="league-msg" role="status">' + esc(su.msg) + "</p>";
    if (su.url) {
      h += '<p class="small" id="paste-steps">Open <a href="' + esc(su.url) + '" target="_blank" rel="noopener" id="settings-link">your league\'s settings page</a>, select all, copy, and paste it here.</p>';
    } else h += '<p class="small muted">Yahoo, or a private league: open the league\'s settings page, select all, copy, and paste it here.</p>';
    h += '<textarea id="league-paste" aria-label="League settings page text" placeholder="Paste the league settings page here">' + esc(su.paste) + "</textarea>" +
      '<div class="row"><button type="button" data-act="read-paste">Read settings</button></div>';
    if (su.read) {
      h += '<div id="paste-read"><p class="small"><b>What we read</b> (' + esc(su.read.platform || "unknown site") + ")</p><div class=\"row\">" +
        su.read.found.map(function (f) { return '<span class="chip on">' + esc(f) + "</span>"; }).join("") + "</div>" +
        (su.read.missing.length ? '<p class="warn" style="margin-top:8px">Not found, left at the default: ' + esc(su.read.missing.join(", ")) + ". Check them below.</p>" : "") +
        (su.read.unread && su.read.unread.length ? '<p class="warn" style="margin-top:8px">Read but not applied: ' + esc(su.read.unread.slice(0, 6).join("; ")) + ".</p>" : "") + "</div>";
    }
    h += "</div>";

    h += '<div class="card stack"><h2>2. Settings</h2><div class="form">' +
      '<label>League name<input type="text" data-lg="name" value="' + esc(lg.name) + '"></label>' +
      '<label>Teams<input type="number" min="2" max="32" data-lg="teamCount" value="' + lg.teams.length + '"></label>' +
      '<label>Budget per team<input type="number" min="1" data-lg="budget" value="' + lg.budget + '"></label>' +
      '<label>Minimum bid<input type="number" min="1" data-lg="minBid" value="' + lg.minBid + '"></label>' +
      '<label>My team<select data-lg="me">' + lg.teams.map(function (t, i) { return '<option value="' + i + '"' + (i === s.me ? " selected" : "") + ">" + esc(t.name) + "</option>"; }).join("") + "</select></label></div>" +
      '<h3 style="margin-top:6px">Roster slots per team</h3><div class="form">' +
      C.SLOT_KEYS.map(function (k) { return "<label>" + k + '<input type="number" min="0" max="30" data-slot="' + k + '" value="' + lg.slots[k] + '"></label>'; }).join("") + "</div>" +
      '<h3 style="margin-top:6px">Scoring (points) · ' + esc(C.scoringLabel(lg.scoring)) + '</h3><div class="form">' +
      SCORING_FIELDS.map(function (f) { return "<label>" + f[1] + '<input type="number" step="any" data-score="' + f[0] + '" value="' + lg.scoring[f[0]] + '"></label>'; }).join("") + "</div>" +
      (lg.notes.length ? '<p class="warn" id="league-notes">Not applied to values: ' + esc(lg.notes.join("; ")) + ".</p>" : "") + "</div>";
    h += "</div><div class=\"stack\">";

    var room = lg.teams.reduce(function (t, x) { return t + x.budget; }, 0);
    h += '<div class="card stack"><h2>3. Draft capital by team</h2><div class="tw"><table><thead><tr><th>Team</th><th class="r">Budget</th><th class="r">Spent</th><th class="r">Open</th><th class="r">Max bid</th></tr></thead><tbody id="team-rows">';
    teams.forEach(function (t, i) {
      var open = C.SLOT_KEYS.reduce(function (n, k) { return n + t.open[k]; }, 0);
      h += '<tr data-team="' + i + '"><td><input type="text" data-team-name aria-label="Team ' + (i + 1) + ' name" value="' + esc(t.name) + '" style="width:100%;min-width:110px"></td>' +
        '<td class="r"><span class="stepper' + (t.budget !== lg.budget ? " ovr" : "") + '"><button type="button" data-budget="-1" aria-label="Budget down">−</button>' +
        '<input data-budget-input inputmode="numeric" aria-label="Budget for ' + esc(t.name) + '" value="' + t.budget + '"><button type="button" data-budget="1" aria-label="Budget up">+</button></span></td>' +
        '<td class="r num">$' + t.spent + '</td><td class="r num">' + open + '</td><td class="r num">$' + Math.max(0, app.calc.board.maxBids[i]) + "</td></tr>";
    });
    h += '</tbody></table></div><p class="small muted">A green border marks a budget changed from the league default (traded draft dollars, for example).</p>' +
      '<div class="kpis"><div class="kpi"><span>Room total</span><b class="big" id="room-total">$' + room + '</b></div><div class="kpi"><span>Roster spots</span><b class="big">' +
      lg.teams.length * C.SLOT_KEYS.reduce(function (t, k) { return t + lg.slots[k]; }, 0) + "</b></div></div></div>";

    h += '<div class="card stack"><h2>4. Save and reopen</h2><p class="small muted">The whole draft is in the link: league, budgets, every sale and every override. Copy it any time; opening it restores this exact state. Nothing is stored on a server.</p>' +
      '<div class="row"><button type="button" class="primary" data-act="copy-link">Copy link</button><button type="button" data-act="reset-draft">Clear all sales</button></div>' +
      '<div class="row"><input type="text" id="open-link" placeholder="Paste a saved link" aria-label="Paste a saved link" style="flex:1 1 220px" value="' + esc(su.link) + '"><button type="button" data-act="open-link">Open</button></div>' +
      (su.linkMsg ? '<p class="' + (su.linkOk ? "note" : "warn") + '" id="link-msg" role="status">' + esc(su.linkMsg) + "</p>" : "") +
      (su.linkShown ? '<input type="text" readonly id="link-shown" aria-label="Saved link" value="' + esc(su.linkShown) + '">' : "") + "</div>";
    h += "</div></div>";
    return h;
  }

  // ----------------------------------------------------------------- render
  function render() {
    var main = $("app");
    if (!main) return;
    var focusId = doc.activeElement && doc.activeElement.id;
    var tabs = doc.querySelectorAll("nav.tabs button");
    for (var i = 0; i < tabs.length; i += 1) tabs[i].setAttribute("aria-pressed", String(tabs[i].getAttribute("data-view") === app.view));
    main.setAttribute("data-view", app.view);
    var linkError = app.linkError ? '<p class="warn" id="link-error" style="margin-bottom:12px">That link could not be read (' +
      (app.linkError === "checksum" ? "it is cut off or mistyped" : esc(app.linkError)) + "). Showing " +
      (app.state.picks.length ? "the last draft in this tab" : "a new draft") + " instead.</p>" : "";
    main.innerHTML = linkError + (app.view === "values" ? valuesHtml() : app.view === "roster" ? rosterHtml() : app.view === "setup" ? setupHtml() : boardHtml());
    if (focusId && (focusId === "q" || focusId === "vq") && $(focusId)) {
      var el = $(focusId); el.focus(); el.setSelectionRange(el.value.length, el.value.length);
    }
    var credits = $("credits");
    if (credits) {
      credits.textContent = [(app.bundle.season ? app.bundle.season + " data." : "")].concat(app.bundle.credits || [])
        .concat(app.fixedModel ? [] : ["Projections: FantasyPros (fantasypros.com)", "Season props: DraftKings and FanDuel lines"]).filter(Boolean).join(" · ");
    }
  }

  function fatal(err) {
    var main = $("app");
    if (main) main.innerHTML = '<p class="warn" id="fatal">The draft data could not be loaded (' + esc(err && err.message ? err.message : err) + "). Check your connection and reload.</p>";
    throw err;
  }

  // ----------------------------------------------------------------- events
  function copyLink() {
    return (app.token ? Promise.resolve(app.token) : saveLink()).then(function (token) {
      if (!token) { app.setup.linkMsg = "This browser cannot make links (it lacks CompressionStream)."; app.setup.linkOk = false; setView("setup"); return; }
      var url = linkUrl();
      app.setup.linkShown = url;
      var done = function (ok) {
        app.setup.linkMsg = ok ? "Link copied. Bookmark it or send it to yourself." : "Copy the link below."; app.setup.linkOk = ok;
        if (app.view === "setup") render(); else { app.toast = app.setup.linkMsg; drawBlock(); }
        var btn = $("save-link");
        if (btn && ok) { btn.textContent = "Copied"; root.setTimeout(function () { btn.textContent = "Copy link"; }, 1500); }
        if (!ok && app.view !== "setup") setView("setup");
      };
      if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
        return root.navigator.clipboard.writeText(url).then(function () { done(true); }, function () { done(false); });
      }
      done(false);
    });
  }

  function openLink(text) {
    return C.decodeLink(text).then(function (st) {
      if (!st || st.error) {
        app.setup.linkMsg = !st ? "No saved draft found in that text." : st.error === "checksum" ? "That link is cut off or mistyped (its check does not match). Copy it again." : "That link could not be read.";
        app.setup.linkOk = false; render(); return null;
      }
      app.state = st; app.sel = null; app.bid = ""; app.linkError = null;
      app.setup.linkMsg = "Draft restored: " + st.picks.length + " sale" + (st.picks.length === 1 ? "" : "s") + "."; app.setup.linkOk = true; app.setup.link = "";
      rebuild();
      return commit();
    });
  }

  function fetchLeague() {
    var L = root.DraftLeague, su = app.setup;
    su.ref = $("league-ref") ? $("league-ref").value : su.ref;
    su.read = null;
    var ref = L && L.parseRef(su.ref);
    if (!ref) { su.ok = false; su.url = null; su.msg = "That does not look like a Sleeper, ESPN or Yahoo league link or ID."; render(); return Promise.resolve(); }
    su.ok = true; su.msg = "Reading the league from " + ref.platform + "…"; su.url = null; render();
    return L.load(ref).then(function (res) {
      if (res.ok) {
        su.ok = true; su.msg = "Read " + res.league.name + ": " + res.league.teams.length + " teams, $" + res.league.budget + " budget, " + (res.league.scoringLabel || "") + ". Check the settings below.";
        su.url = null;
        return applyLeague(res.league);
      }
      su.ok = false; su.url = res.settingsUrl || L.settingsUrl(ref);
      su.msg = res.message || (res.code === "paste" ? "Yahoo leagues are read from a paste for now."
        : res.code === "private" ? "That league is private, so its settings cannot be read from a link."
        : res.code === "notfound" ? "No league was found with that ID."
        : "The league could not be reached just now.");
      render();
    });
  }

  function readPaste() {
    var L = root.DraftLeague, su = app.setup;
    su.paste = $("league-paste") ? $("league-paste").value : su.paste;
    var rows = app.bundle.players.map(function (p) { return { player_key: p.key, name: p.name, pos: p.pos === "DST" ? "DEF" : p.pos, team: p.team }; });
    var res = L ? L.parsePaste(su.paste, { rows: rows }) : { ok: false };
    if (!res.ok) { su.read = null; su.ok = false; su.msg = "No league settings were found in that text. Copy the whole settings page (select all, then copy) and paste it again."; render(); return; }
    su.read = { platform: res.platform, found: res.found || [], missing: res.missing || [], unread: res.unread || [] };
    su.ok = true;
    su.msg = res.source === "rosters" ? "That is a rosters page: team names and roster slots were read. Scoring and budget are not on it, so check them below."
      : "Settings read from the paste. Check them below.";
    return applyLeague(res.league);
  }

  function onClick(e) {
    var t = e.target.closest ? e.target.closest("button, tr[data-key], [data-buyer]") : null;
    if (!t) return;
    if (t.getAttribute("data-view")) return setView(t.getAttribute("data-view"));
    if (t.id === "save-link") return copyLink();
    if (t.id === "help-open") return $("help").showModal();
    if (t.id === "help-close") return $("help").close();
    if (t.hasAttribute("data-buyer")) return sell(Number(t.getAttribute("data-buyer")));
    if (t.hasAttribute("data-pos")) { app.pos = t.getAttribute("data-pos"); recompute(); return render(); }
    if (t.hasAttribute("data-vpos")) { app.vpos = t.getAttribute("data-vpos"); return render(); }
    if (t.hasAttribute("data-factor")) { app.state.ourFactor = t.getAttribute("data-factor"); return commit(); }
    if (t.hasAttribute("data-ovr") || t.hasAttribute("data-ovr-reset")) {
      var key = t.closest("tr").getAttribute("data-key");
      if (t.hasAttribute("data-ovr-reset")) return setOverride(key, null);
      return setOverride(key, (app.model.values[key] || 0) + Number(t.getAttribute("data-ovr")));
    }
    if (t.hasAttribute("data-budget")) {
      var ti = Number(t.closest("tr").getAttribute("data-team"));
      return editLeague(function (lg) { lg.teams[ti].budget = Math.max(0, lg.teams[ti].budget + Number(t.getAttribute("data-budget"))); });
    }
    var act = t.getAttribute("data-act");
    if (act === "walk") return bidTo("walkAway", "walk-away");
    if (act === "push") return bidTo("pushFloor", "push floor");
    if (act === "mine") return myBuy();
    if (act === "sold") return app.buyerMode ? (app.buyerMode = false, drawBlock()) : startSold();
    if (act === "undo") return undo();
    if (act === "bid-up") return stepBid(1);
    if (act === "bid-down") return stepBid(-1);
    if (act === "show-all") { app.showAll = true; return render(); }
    if (act === "v-all") { app.vAll = true; return render(); }
    if (act === "reset-overrides") { app.state.overrides = {}; rebuild(); return commit(); }
    if (act === "fetch-league") return fetchLeague();
    if (act === "read-paste") return readPaste();
    if (act === "copy-link") return copyLink();
    if (act === "open-link") return openLink($("open-link").value);
    if (act === "reset-draft") {
      if (!app.state.picks.length || confirmed("reset", "This clears all " + app.state.picks.length + " sales.")) { app.state.picks = []; app.sel = null; app.setup.msg = null; return commit("Sales cleared."); }
      return;
    }
    if (t.tagName === "TR" && t.getAttribute("data-key") && app.view === "board") return select(t.getAttribute("data-key"), false);
  }

  function onInput(e) {
    var t = e.target;
    if (t.id === "q") { app.q = t.value; recompute(); var keys = visibleKeys(); if (keys.indexOf(app.sel) === -1) app.sel = keys[0] || app.sel; $("rows").innerHTML = rowsHtml(); drawBlock(); }
    else if (t.id === "vq") { app.vq = t.value; render(); }
    else if (t.id === "bid") { app.bid = t.value.replace(/\D/g, "").slice(0, 5); if (t.value !== app.bid) t.value = app.bid; }
    else if (t.id === "league-ref") app.setup.ref = t.value;
    else if (t.id === "league-paste") app.setup.paste = t.value;
    else if (t.id === "open-link") app.setup.link = t.value;
  }

  function onChange(e) {
    var t = e.target, v = t.value;
    if (t.hasAttribute("data-ovr-input")) {
      var key = t.closest("tr").getAttribute("data-key");
      return v.trim() === "" || !isFinite(Number(v)) ? setOverride(key, null) : setOverride(key, Number(v));
    }
    if (t.hasAttribute("data-budget-input")) {
      var ti = Number(t.closest("tr").getAttribute("data-team"));
      return editLeague(function (lg) { var n = Math.floor(Number(v)); if (isFinite(n) && n >= 0) lg.teams[ti].budget = n; });
    }
    if (t.hasAttribute("data-team-name")) {
      var tn = Number(t.closest("tr").getAttribute("data-team"));
      return editLeague(function (lg) { if (v.trim()) lg.teams[tn].name = v.trim(); });
    }
    if (t.hasAttribute("data-slot")) return editLeague(function (lg) { lg.slots[t.getAttribute("data-slot")] = Number(v); });
    if (t.hasAttribute("data-score")) return editLeague(function (lg) { if (isFinite(Number(v)) && v !== "") { lg.scoring[t.getAttribute("data-score")] = Number(v); lg.scoringLabel = C.scoringLabel(lg.scoring); } });
    var f = t.getAttribute("data-lg");
    if (f === "name") return editLeague(function (lg) { lg.name = v; });
    if (f === "minBid") return editLeague(function (lg) { lg.minBid = Number(v); });
    if (f === "me") { app.state.me = Number(v); return commit(); }
    if (f === "budget") {
      return editLeague(function (lg) {
        var n = Math.floor(Number(v));
        if (!(n >= 1)) return;
        // Teams still on the old default follow it; a changed budget stays.
        lg.teams.forEach(function (tm) { if (tm.budget === lg.budget) tm.budget = n; });
        lg.budget = n;
      });
    }
    if (f === "teamCount") {
      var n = Math.floor(Number(v));
      if (!(n >= 2 && n <= 32) || n === app.state.league.teams.length) return render();
      var lost = app.state.picks.filter(function (p) { return p[1] >= n; }).length;
      if (lost && !confirmed("teams" + n, "Removing teams drops their " + lost + " recorded sales. Enter the number again to confirm.")) return;
      app.state.picks = app.state.picks.filter(function (p) { return p[1] < n; });
      if (app.state.me >= n) app.state.me = 0;
      return editLeague(function (lg) {
        while (lg.teams.length < n) lg.teams.push({ name: "Team " + (lg.teams.length + 1), budget: lg.budget });
        lg.teams.length = n;
      });
    }
  }

  function onKey(e) {
    var t = e.target, tag = t && t.tagName;
    var help = $("help");
    if (help && help.open) return;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      if (t.id === "q") {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); move(e.key === "ArrowDown" ? 1 : -1); }
        else if (e.key === "Enter") { e.preventDefault(); var first = visibleKeys()[0]; if (first) { app.sel = null; select(first, true); } t.blur(); }
        else if (e.key === "Escape") { e.preventDefault(); app.q = ""; t.blur(); recompute(); render(); }
      } else if (t.id === "bid" && (e.key === "Enter" || e.key === "Escape")) { e.preventDefault(); t.blur(); drawBlock(); }
      else if (t.id === "league-ref" && e.key === "Enter") { e.preventDefault(); fetchLeague(); }
      else if (t.id === "open-link" && e.key === "Enter") { e.preventDefault(); openLink(t.value); }
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var k = e.key, lower = k.length === 1 ? k.toLowerCase() : k;
    if (k === "?") { e.preventDefault(); return help.showModal(); }
    if (app.view === "board" && app.buyerMode) {
      if (k === "Escape") { app.buyerMode = false; return drawBlock(); }
      if (/^[a-z]$/.test(lower)) {
        var idx = lower.charCodeAt(0) - 97;
        if (idx < app.state.league.teams.length) { e.preventDefault(); return sell(idx); }
      }
      return;
    }
    if (lower === "b") return setView("board");
    if (lower === "v") return setView("values");
    if (lower === "r") return setView("roster");
    if (lower === "l") return setView("setup");
    if (app.view !== "board") return;
    if (k === "ArrowDown") { e.preventDefault(); return move(1); }
    if (k === "ArrowUp") { e.preventDefault(); return move(-1); }
    if (k === "PageDown") { e.preventDefault(); return move(10); }
    if (k === "PageUp") { e.preventDefault(); return move(-10); }
    if (k === "Home") { e.preventDefault(); return move(-100000); }
    if (k === "End") { e.preventDefault(); return move(100000); }
    if (k === "/") { e.preventDefault(); var q = $("q"); if (q) { q.focus(); q.select(); } return; }
    if (/^\d$/.test(k)) { e.preventDefault(); return setBid(app.bid + k); }
    if (k === "Backspace") { e.preventDefault(); return setBid(app.bid.slice(0, -1)); }
    if (k === "+" || k === "=") { e.preventDefault(); return stepBid(1); }
    if (k === "-" || k === "_") { e.preventDefault(); return stepBid(-1); }
    if (lower === "w") return bidTo("walkAway", "walk-away");
    if (lower === "p") return bidTo("pushFloor", "push floor");
    if (lower === "m") return myBuy();
    if (lower === "s") return startSold();
    if (lower === "u") return undo();
  }

  function bind() {
    if (app.bound) return;
    app.bound = true;
    doc.addEventListener("click", onClick);
    doc.addEventListener("input", onInput);
    doc.addEventListener("change", onChange);
    doc.addEventListener("keydown", onKey);
    root.addEventListener("hashchange", function () {
      var token = /(?:^#|&)s=([^&]*)/.exec(root.location.hash);
      if (token && token[1] !== app.token) openLink(root.location.hash);
    });
  }

  function init(opts) {
    var o = opts || root.DRAFT_PREVIEW || {};
    app.now = o.now == null ? null : o.now;
    app.preview = !!o.preview;
    bind();
    app.ready = loadData(o).then(function () { return loadState(o); }).then(function () {
      rebuild();
      render();
      return saveLink();
    }).then(function () { return app; }, fatal);
    DraftApp.ready = app.ready;
    return app.ready;
  }

  var DraftApp = { init: init, app: app, ready: null, select: function (key) { app.sel = null; select(key, true); },
    openLink: openLink, linkUrl: linkUrl };
  root.DraftApp = DraftApp;
})(typeof globalThis !== "undefined" ? globalThis : this);
