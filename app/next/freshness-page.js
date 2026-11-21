/* Source freshness page: renders DDF.freshness.summarize() (site.js) from modules/comparison-chain-status.json. */
(function(){
  function el(tag, cls, text){ var e = document.createElement(tag); if(cls) e.className = cls; if(text !== undefined) e.textContent = text; return e; }
  function fmt(iso, withTime){
    if(!iso) return 'Not reported';
    var dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso);
    var d = new Date(dateOnly ? iso + 'T12:00:00Z' : iso);
    if(isNaN(d.getTime())) return 'Not reported';
    var opt = dateOnly ? {timeZone:'UTC', month:'short', day:'numeric'}
      : {timeZone:'America/Chicago', month:'short', day:'numeric', hour:'numeric', minute:'2-digit'};
    var s = d.toLocaleString('en-US', opt);
    return dateOnly || !withTime ? s : s + ' CT';
  }
  function render(sum){
    var dot = document.getElementById('fresh-sum-dot'), t = document.getElementById('fresh-sum-t'), s = document.getElementById('fresh-sum-s');
    var list = document.getElementById('fresh-list'), checked = document.getElementById('fresh-checked');
    list.textContent = '';
    if(!sum){
      dot.removeAttribute('data-state'); dot.setAttribute('aria-hidden', 'true');
      t.textContent = 'Freshness status is not available right now';
      s.textContent = ' Try again in a few minutes.';
      checked.textContent = '';
      return;
    }
    var label = DDF.freshness.dotLabel(sum);
    dot.setAttribute('data-state', sum.state); dot.setAttribute('role', 'img'); dot.setAttribute('aria-label', label); dot.removeAttribute('aria-hidden');
    t.textContent = label;
    s.textContent = ' ' + sum.fresh + ' of ' + sum.total + ' are on ' + (sum.expected ? 'Week ' + sum.expected : 'the newest week') + '.';
    sum.rows.forEach(function(r){
      var li = el('li', 'fresh-item'); li.setAttribute('data-source', r.key);
      var head = el('div', 'fresh-head'); head.appendChild(el('h2', '', r.label));
      var chip = el('span', 'fresh-chip'); chip.setAttribute('data-fresh', r.fresh ? 'yes' : (r.stale ? 'stale' : 'no'));
      chip.textContent = r.fresh ? 'Fresh' : (r.stale ? 'Stale' : 'Behind');
      head.appendChild(chip); li.appendChild(head);
      var dl = el('dl', 'fresh-facts');
      [['Data is on', r.served === null ? 'Not reported' : 'Week ' + r.served],
       ['Newest expected', r.expected === null ? 'Not reported' : 'Week ' + r.expected],
       ['Last updated', fmt(r.updated, true)]].forEach(function(f){
        var d = el('div'); d.appendChild(el('dt', '', f[0])); d.appendChild(el('dd', '', f[1])); dl.appendChild(d);
      });
      li.appendChild(dl);
      if(r.reason){ var p = el('p', 'fresh-reason', r.reason); p.setAttribute('data-stale', r.stale ? 'yes' : 'no'); li.appendChild(p); }
      list.appendChild(li);
    });
    checked.textContent = sum.runAt ? 'Status checked ' + fmt(sum.runAt, true) + '. It refreshes whenever the site data updates.' : '';
  }
  function go(){ DDF.freshness.load().then(render); }
  if(window.DDF && DDF.freshness) go(); else window.addEventListener('load', go);
})();
