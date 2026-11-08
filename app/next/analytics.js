/* Privacy-first visit counter (JEG-1548). OFF until GOATCOUNTER_CODE below is set.

   Jeremy's decisions (2026-11-08): a cookie-less hosted counter (GoatCounter), no consent banner, the journey funnel
   plus a few key actions, and chat link-backs tagged with a source.

   What leaves the browser, and only when the code is set, the host is the live site, and the reader has neither Do
   Not Track nor Global Privacy Control on: one request per count to https://<code>.goatcounter.com/count with
   exactly three parameters (sent with fetch: no cookies, no referrer, keepalive): p (a fixed label from PAGES or EVENTS below, never the address), e (true for an event)
   and rnd (a random cache buster, new on every request). No title, no referrer (the request is sent with
   no-referrer), no screen size, no query, no hash. Nothing is read from the league, the teams, the players or the link
   state. No cookies and no storage of any kind: this file never touches document.cookie, localStorage,
   sessionStorage or IndexedDB. Any failure is swallowed; the request is never added to the page.

   The vendor's count.js is NOT loaded: by default it sends document.title (which carries the league name, JEG-1564)
   and the query string. The documented /count endpoint takes the same fields with nothing else.

   Source tags: a link from the DDF connector ends ?src=<client>[-<tool>] (for example ?src=claude-find_trades). The
   tag is read against the allow-list below, counted as an event, and removed from the address bar (the #s= hash is
   left exactly as it was). The tag is removed even when counting is off. */
(function(){
  'use strict';
  window.DDF = window.DDF || {};
  if (window.DDF._analytics) return;

  /* ---- The one switch. The GoatCounter site code: the "abc" in https://abc.goatcounter.com. Empty = off. ---- */
  var GOATCOUNTER_CODE = '';
  /* Counting happens only on the live site (not local copies, previews on other hosts, or tests). */
  var HOSTS = ['datadrivenfootball.github.io'];

  /* Page file -> the fixed label sent as the page view. A page not listed sends no page view. */
  var PAGES = {
    'index.html': '/',                       // Get started
    'connect.html': '/entry/connect',        // Add your league
    'setup.html': '/entry/setup',            // Which team is yours?
    'settings.html': '/entry/settings',      // Settings
    'team.html': '/workspace/team',          // Team assessment
    'explore.html': '/workspace/explore',    // Pick players
    'partners.html': '/workspace/partners',  // Pick trading partners
    'find.html': '/workspace/find',          // Trade & Waiver Recommendations
    'waivers.html': '/workspace/waivers',
    'build.html': '/build',                  // Build a Trade
    'values.html': '/values',
    'learn.html': '/learn',
    'ai.html': '/ai'
  };
  var CLIENTS = ['claude', 'chatgpt', 'ai'];
  /* The DDF connector's tool names (09-mcp-server tools.ts). */
  var TOOLS = ['get_values', 'get_player_value', 'trade_targets', 'compare_trade', 'read_state', 'make_state',
    'site_next_steps', 'find_trades', 'find_trades_league', 'risers_fallers', 'audit_values', 'explain'];
  var EVENTS = ['league-added/paste', 'league-added/link', 'league-added/sleeper', 'league-added/manual',
    'settings-confirmed', 'bookmark-clicked', 'bookmark-again', 'trade-message-copied', 'value-override-set',
    'start-fresh', 'visit/direct', 'visit/saved-link', 'visit/other-tag', 'device/phone', 'device/desktop'];
  CLIENTS.forEach(function(c){
    EVENTS.push('visit/' + c);
    TOOLS.forEach(function(t){ EVENTS.push('visit/' + c + '/' + t); });
  });
  var SRC_RE = new RegExp('^(' + CLIENTS.join('|') + ')(?:-(' + TOOLS.join('|') + '))?$');

  function codeOk(){ return /^[a-z0-9][a-z0-9-]{0,49}$/.test(GOATCOUNTER_CODE); }
  function optedOut(){
    try{
      var n = navigator, dnt = n.doNotTrack || window.doNotTrack || n.msDoNotTrack;
      return dnt === '1' || dnt === 'yes' || n.globalPrivacyControl === true;
    }catch(e){ return true; }
  }
  function on(){
    try{ return codeOk() && HOSTS.indexOf(location.hostname) >= 0 && !optedOut(); }catch(e){ return false; }
  }
  function pageLabel(){
    try{
      var f = location.pathname.split('/').pop() || 'index.html';
      return Object.prototype.hasOwnProperty.call(PAGES, f) ? PAGES[f] : null;
    }catch(e){ return null; }
  }

  var sent = {};
  /* label must be a PAGES value (page view) or an EVENTS entry (event); anything else is dropped. */
  function send(label, isEvent){
    try{
      if(!on()) return false;
      var known = isEvent ? EVENTS.indexOf(label) >= 0 : Object.keys(PAGES).some(function(k){ return PAGES[k] === label; });
      if(!known) return false;
      var key = (isEvent ? 'e:' : 'p:') + label;
      if(sent[key]) return false;      // once per page load
      sent[key] = true;
      var url = 'https://' + GOATCOUNTER_CODE + '.goatcounter.com/count?p=' + encodeURIComponent(label)
        + '&e=' + (isEvent ? 'true' : 'false') + '&rnd=' + Math.random().toString(36).slice(2, 8);
      if(typeof fetch === 'function'){
        /* keepalive: a count made just before the page navigates away (Start fresh) still goes */
        fetch(url, {method: 'GET', mode: 'no-cors', credentials: 'omit', referrerPolicy: 'no-referrer',
          cache: 'no-store', keepalive: true}).catch(function(){});
      }else{
        var img = new Image();
        img.referrerPolicy = 'no-referrer';
        img.onload = img.onerror = function(){ img.onload = img.onerror = null; };
        img.src = url;
      }
      return true;
    }catch(e){ return false; }
  }

  /* The ?src= tag. site.js takes it off the address bar as soon as it runs (DDF._srcTag); a page without site.js has it
     removed here. Only the src pair goes; the rest of the query and the hash stay exactly as they were. */
  function takeSource(){
    var raw = null;
    try{
      if(typeof window.DDF._srcTag === 'string') raw = window.DDF._srcTag;
      else{
        var parts = location.search.replace(/^\?/, '').split('&').filter(Boolean), kept = [];
        parts.forEach(function(x){ if(/^src=/.test(x)){ if(raw === null) raw = x.slice(4); } else kept.push(x); });
        if(raw !== null){
          try{ raw = decodeURIComponent(raw); }catch(e){ raw = ''; }
          history.replaceState(history.state, '', location.pathname + (kept.length ? '?' + kept.join('&') : '') + location.hash);
        }
      }
    }catch(e){}
    if(raw === null) return null;
    var m = SRC_RE.exec(String(raw).slice(0, 80));
    return m ? 'visit/' + m[1] + (m[2] ? '/' + m[2] : '') : 'visit/other-tag';
  }
  /* The first page of a visit: no same-origin referrer. Read here only; the referrer is never sent. */
  function entryPage(){
    try{ return !document.referrer || new URL(document.referrer).origin !== location.origin; }catch(e){ return true; }
  }
  function footerNote(){
    try{
      if(!codeOk() || HOSTS.indexOf(location.hostname) < 0) return;
      var feet = document.querySelectorAll('footer');
      for(var i = 0; i < feet.length; i++){
        if(feet[i].querySelector('.ddf-count-note')) continue;
        var p = document.createElement('p');
        p.className = 'ddf-count-note';
        p.style.cssText = 'margin:8px auto 0;max-width:720px;padding:0 16px;font-size:12px;line-height:1.5;opacity:.75;text-align:center;';
        p.textContent = 'What we count: which pages are opened and a few clicks (like Bookmark or Copy message), with no '
          + 'cookies and nothing about your league, teams or players. Turn on Do Not Track or Global Privacy Control in '
          + 'your browser and we count nothing.';
        (feet[i].querySelector('.footer') || feet[i]).appendChild(p);
      }
    }catch(e){}
  }

  /* Pages report actions only; the visit source and device class are counted here, once, never by page code. */
  function track(name){
    try{ return typeof name === 'string' && !/^(visit|device)\//.test(name) ? send(name, true) : false; }catch(e){ return false; }
  }

  var source = takeSource();
  /* An old-style link (legacy-routes.js) is on its way to the page that does the job now: that page counts the visit
     (the tag rides along). Untagged, this stop still counts where the visit came from, but not a page view. */
  var passing = false;
  try{ passing = !!(window.DDFLegacyRoutes && window.DDFLegacyRoutes.redirecting); }catch(e){}
  var label = pageLabel();
  if(label && !passing) send(label, false);
  /* A tagged link counts its source even after connect.html or an old route forwarded it (same-origin referrer). */
  if(passing && source){ /* counted on the next page */ }
  else if(source || entryPage()){
    var saved = false;
    try{ saved = /(^|[#&])s=/.test(location.hash); }catch(e){}
    send(source || (saved ? 'visit/saved-link' : 'visit/direct'), true);
    var phone = false;
    try{ phone = window.innerWidth < 768; }catch(e){}
    send(phone ? 'device/phone' : 'device/desktop', true);
  }

  var queued = window.DDF._trackQueue || [];
  window.DDF.track = track;
  window.DDF._analytics = {on: on, PAGES: PAGES, EVENTS: EVENTS.slice(), SRC_RE: SRC_RE};
  queued.splice(0).forEach(track);
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', footerNote); else footerNote();
})();
