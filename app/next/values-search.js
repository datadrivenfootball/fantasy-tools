(()=>{
/* Find a player (top of Values): type a name, team or position, pick a player, see his value and the players valued about
   the same. Every number is a DDFValues.D row (values-chart.js load(): engine records from ddf-engine.js, so the reader's
   scoring, teams, superflex, basis and overrides all apply); this file only orders rows and takes differences, it never
   computes a value. Kickers and defenses are not in D (the engine prices QB/RB/WR/TE only), and are filtered again here.
   Names go through the site's shared matcher (v2/namesearch.js, TradeValueNameSearch: word starts, reversed names, typos),
   loaded on first focus so the page pays nothing until the box is used; initials ("jsn", "arsb") are matched on top of it.
   Comparably valued = within a band of DDF Value points (default 3, widen to 6 or 10). State lives in the hash token
   player=<key>, next to the tab tokens and any #s= link token. */
const $=id=>document.getElementById(id);
const V=()=>window.DDFValues;
const S=()=>window.TradeValueNameSearch||null;
const num=v=>typeof v==='number'&&isFinite(v);
const POS=['QB','RB','WR','TE'],POS_NAME={QB:'quarterbacks',RB:'running backs',WR:'wide receivers',TE:'tight ends'};
const BANDS=[3,6,10],SHOW=12,MAX_OPTS=8;
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const f1=v=>num(v)?v.toFixed(1):'—';
const sg=v=>{const r=Math.round(v*10)/10;return r===0?'±0.0':(r>0?'+':'−')+Math.abs(r).toFixed(1)};
const q=$('vfind-q'),list=$('vfind-list'),msg=$('vfind-msg'),card=$('vfind-card');
if(!q)return;
let st={key:null,band:BANDS[0],scope:'all',all:false},ready=false,failed=false,opts=[],typeT=null;

/* ---- the shared matcher, on first use ---- */
let loading=null;
function loadMatcher(){
 if(S()||loading)return loading||Promise.resolve();
 const ref=document.querySelector('script[src*="v2/finder.js"]');
 const src=ref?ref.getAttribute('src').replace('finder.js','namesearch.js'):'v2/namesearch.js';
 loading=new Promise(res=>{const s=document.createElement('script');s.src=src;s.async=true;s.onload=s.onerror=()=>res();document.head.appendChild(s)})
  .then(()=>{if(S()&&S().combobox)S().combobox(q,list);if(document.activeElement===q&&q.value.trim())renderOpts()});
 return loading;
}

/* ---- rows, ranks, matching ---- */
const rows=()=>((V()&&V().D)||[]).filter(p=>POS.includes(p.pos)&&num(p.ddf));   // D is sorted by DDF Value, high to low
function ranks(all){const pos={},out=new Map();all.forEach((p,i)=>{pos[p.pos]=(pos[p.pos]||0)+1;out.set(p.key,{rank:i+1,posRank:pos[p.pos]})});return out}
function nameHits(pool,text){
 const M=S();
 if(!M){const k=text.toLowerCase();return pool.filter(p=>p.n.toLowerCase().includes(k))}
 const ranked=[];pool.forEach((p,i)=>{const r=M.rank(p.n,text);if(r!==null)ranked.push([r,i,p])});
 const qs=M.key(text).replace(/ /g,'');
 const initials=qs.length>=2&&qs.length<=5&&/^[a-z]+$/.test(qs)?pool.filter(p=>{const t=M.tokens(p.n);return t.length>=2&&t.map(w=>w[0]).join('')===qs}):[];
 if(!ranked.length&&!initials.length)return M.search(pool,text,p=>p.n);
 const out=ranked.sort((a,b)=>a[0]-b[0]||a[1]-b[1]).map(x=>x[2]),seen=new Set(out);
 initials.forEach(p=>{if(!seen.has(p))out.push(p)});
 return out;
}
/* A whole word that is a position (QB/RB/WR/TE) or a team on the board filters; the other words are the name. */
function find(text){
 const all=rows(),words=String(text||'').trim().split(/\s+/).filter(Boolean);if(!words.length)return{hits:[],pos:null,team:null};
 const teams=new Set(all.map(p=>p.team).filter(Boolean));let pos=null,team=null;const rest=[];
 words.forEach(w=>{const u=w.toUpperCase();if(!pos&&POS.includes(u))pos=u;else if(!team&&teams.has(u))team=u;else rest.push(w)});
 const pool=all.filter(p=>(!pos||p.pos===pos)&&(!team||p.team===team));
 if(!rest.length)return{hits:pool,pos,team};
 let hits=nameHits(pool,rest.join(' '));
 if(!hits.length&&(pos||team)){hits=nameHits(all,words.join(' '));pos=team=null}
 return{hits,pos,team};
}
function comparables(key,band,scope){
 const all=rows(),me=all.find(p=>p.key===key);if(!me)return null;
 const near=all.filter(p=>p.key!==key&&Math.abs(p.ddf-me.ddf)<=band+1e-9);
 const by={all:near,same:near.filter(p=>p.pos===me.pos),other:near.filter(p=>p.pos!==me.pos)};
 return{me,band,lo:me.ddf-band,hi:me.ddf+band,counts:{all:by.all.length,same:by.same.length,other:by.other.length},list:by[scope]||by.all};
}

/* ---- league marks (read only when a player is shown, never while typing) ---- */
function owners(){
 const out=new Map();let lg=null;
 try{const L=window.DDF&&DDF.league,cur=L&&L.current?L.current():null;
  if(cur)lg={teams:cur.teams.map(t=>({id:String(t.index),name:t.name,keys:t.players.filter(x=>!x.unpriced).map(x=>String(x.key))})),mine:cur.me===null?null:String(cur.me)};
  else{const e=DDF.engine.league();if(e)lg={teams:e.teams.map(t=>({id:String(t.id),name:t.name,keys:[...t.keys].map(String)})),mine:e.mine===null?null:String(e.mine)}}}catch(_){lg=null}
 if(!lg)return out;
 lg.teams.forEach(t=>t.keys.forEach(k=>{if(!out.has(k))out.set(k,t.id===lg.mine?{mine:true,name:'Your team'}:{mine:false,name:t.name||'Another team'})}));
 return out;
}
const ownTag=o=>o?`<span class="vfind-own${o.mine?' mine':''}">${esc(o.name)}</span>`:'';

/* ---- type-ahead ---- */
function optHTML(p,i){
 return `<li><button type="button" id="vfind-opt-${i}" data-key="${esc(p.key)}"><span><span class="vfind-pn">${esc(p.n)}</span><span class="pos pos-${esc(p.pos)}">${esc(p.pos)}</span><span class="vfind-meta">${esc(p.team||'Free agent')}</span></span><span class="vfind-num">${f1(p.ddf)}</span></button></li>`;
}
function renderOpts(){
 const text=q.value.trim();
 if(!text){list.hidden=true;list.innerHTML='';return}
 if(!ready){list.innerHTML=`<li class="is-empty">${failed?'The values could not load.':'Loading values…'}</li>`;list.hidden=false;return}
 const r=find(text);opts=r.hits.slice(0,MAX_OPTS);
 const head=(r.pos||r.team)&&opts.length?`<li class="vfind-ohead" role="presentation">${esc([r.team,r.pos?POS_NAME[r.pos]:'players'].filter(Boolean).join(' '))}, by DDF Value</li>`:'';
 list.innerHTML=opts.length?head+opts.map(optHTML).join(''):'<li class="is-empty">No players match. Check the spelling, or try a last name.</li>';
 list.hidden=false;
}
q.addEventListener('focus',()=>{loadMatcher();if(q.value.trim()&&q.value!==q.dataset.picked)renderOpts()});
q.addEventListener('input',()=>{loadMatcher();clearTimeout(typeT);typeT=setTimeout(renderOpts,60)});
q.addEventListener('keydown',e=>{
 if(e.key==='Escape'&&!list.hidden){e.preventDefault();list.hidden=true;return}
 if(e.key==='Enter'){e.preventDefault();clearTimeout(typeT);if(list.hidden||!opts.length)renderOpts();if(opts[0])pick(opts[0].key,{push:true})}
});
list.addEventListener('click',e=>{const b=e.target.closest('button[data-key]');if(b)pick(b.dataset.key,{push:true})});
document.addEventListener('click',e=>{if(!e.target.closest('.vfind-box'))list.hidden=true});

/* ---- hash: player=<key> ---- */
const tokens=()=>location.hash.slice(1).split('&').filter(Boolean);
function hashKey(){for(const t of tokens()){const m=/^player=([^&?]+)$/.exec(t);if(m){try{return decodeURIComponent(m[1])}catch(_){return m[1]}}}return null}
function writeHash(key,push){
 const parts=tokens().filter(t=>!/^player=/.test(t));if(key)parts.push('player='+encodeURIComponent(key));
 const base=location.pathname+location.search,url=base+(parts.length?'#'+parts.join('&'):'');
 if(url===base+location.hash)return;
 if(push)history.pushState(history.state,'',url);else history.replaceState(history.state,'',url);
}

/* ---- the picked player and his comparables ---- */
function pick(key,o){o=o||{};
 st.key=key?String(key):null;st.all=false;if(o.resetScope!==false)st.scope='all';
 list.hidden=true;
 if(o.write!==false)writeHash(st.key,!!o.push);
 render();
 const me=st.key&&rows().find(p=>p.key===st.key);
 if(me){q.value=me.n;q.dataset.picked=me.n}
 if(o.push&&!card.hidden){const h=$('vfind-name');if(h){h.focus({preventScroll:true});card.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'})}}
}
function ctxText(){return ['vchip-week','vchip-scoring','vchip-teams','vchip-sf'].map($).filter(el=>el&&!el.hidden&&el.textContent.trim()).map(el=>el.textContent.trim()).join(' · ')}
function seg(name,label,items,cur){
 return `<div class="vfind-ctrl"><span class="range-title" id="vfind-${name}-l">${label}</span><div class="segmented" role="radiogroup" aria-labelledby="vfind-${name}-l">${items.map(([v,t,aria])=>`<button type="button" role="radio" data-${name}="${v}" aria-checked="${String(v)===String(cur)}" tabindex="${String(v)===String(cur)?0:-1}"${aria?` aria-label="${esc(aria)}"`:''}>${t}</button>`).join('')}</div></div>`;
}
function rowHTML(p,me,rk,own){
 const r=rk.get(p.key)||{},g=p.ddf-me.ddf,meta=[p.team||'Free agent','#'+r.rank,p.pos+r.posRank].join(' · ');
 const rel=Math.round(g*10)===0?'the same as':Math.abs(g).toFixed(1)+(g>0?' above ':' below ');
 return `<li><button type="button" data-key="${esc(p.key)}" aria-label="${esc(`${p.n}, ${p.pos}, ${p.team||'free agent'}, DDF Value ${f1(p.ddf)}, ${rel}${rel==='the same as'?' ':''}${me.n}, rank ${r.rank}, ${p.pos}${r.posRank}${own?', '+own.name:''}. Show his comparables.`)}"><span class="vfind-who"><span class="vfind-pn">${esc(p.n)}</span><span class="pos pos-${esc(p.pos)}">${esc(p.pos)}</span>${ownTag(own)}<span class="vfind-meta">${esc(meta)}</span></span><span class="vfind-num">${f1(p.ddf)}</span><span class="vfind-gap ${g>0.05?'up':g<-0.05?'down':''}">${sg(g)}</span></button></li>`;
}
function selfHTML(me,rk,own){
 const r=rk.get(me.key)||{};
 return `<li class="vfind-self" aria-label="${esc(me.n)}, the player you searched, DDF Value ${f1(me.ddf)}"><span class="vfind-who"><span class="vfind-pn">${esc(me.n)}</span><span class="pos pos-${esc(me.pos)}">${esc(me.pos)}</span>${ownTag(own)}<span class="vfind-meta">${esc([me.team||'Free agent','#'+r.rank,me.pos+r.posRank].join(' · '))} · you searched</span></span><span class="vfind-num">${f1(me.ddf)}</span><span class="vfind-gap">—</span></li>`;
}
function shownList(c){
 if(st.all||c.list.length<=SHOW)return{rows:c.list,cut:false};
 const near=c.list.slice().sort((a,b)=>Math.abs(a.ddf-c.me.ddf)-Math.abs(b.ddf-c.me.ddf)||b.ddf-a.ddf).slice(0,SHOW);
 const keep=new Set(near);return{rows:c.list.filter(p=>keep.has(p)),cut:true};
}
function render(){
 if(!st.key){card.hidden=true;card.innerHTML='';msg.textContent='';return}
 if(!ready){card.hidden=true;msg.textContent=failed?'The values could not load. Reload the page to try again.':'Loading values…';return}
 const c=comparables(st.key,st.band,st.scope);
 if(!c){card.hidden=true;card.innerHTML='';msg.textContent='That player has no DDF Value at your league settings this week, so there is nothing to compare. Search for another player.';return}
 msg.textContent='';
 const all=rows(),rk=ranks(all),own=owners(),me=c.me,r=rk.get(me.key),avg=num(me.avg)?me.avg:null;
 const sh=shownList(c);
 const items=sh.rows.slice();let at=items.findIndex(p=>p.ddf<me.ddf);if(at<0)at=items.length;
 const lis=items.map(p=>rowHTML(p,me,rk,own.get(p.key)));lis.splice(at,0,selfHTML(me,rk,own.get(me.key)));
 const scopeName={all:'all positions',same:me.pos+' only',other:'other positions'}[st.scope];
 const empty=!c.list.length?`<p class="vfind-empty">No ${st.scope==='same'?me.pos+'s':st.scope==='other'?'players at other positions':'other players'} are within ±${st.band} points of his ${f1(me.ddf)}.${st.band<BANDS[BANDS.length-1]?' Widen the band to see more.':''}</p>`:'';
 card.innerHTML=`<div class="vfind-top"><div><h3 class="vfind-name" id="vfind-name" tabindex="-1">${esc(me.n)} <span class="pos pos-${esc(me.pos)}">${esc(me.pos)}</span>${ownTag(own.get(me.key))}</h3><p class="vfind-ctx">${esc(me.team||'Free agent')} · ${esc(ctxText())}</p></div><button type="button" class="link-button vfind-clear" id="vfind-clear">Clear</button></div>
<dl class="vfind-stats"><div><dt><a href="learn.html#numbers/glossary/ddf-value">DDF Value</a></dt><dd>${f1(me.ddf)}</dd>${me.ov?`<small>Your value (DDF ${f1(me.base)})</small>`:''}</div><div><dt>Rank</dt><dd>#${r.rank}</dd><small>of ${all.length} by DDF Value</small></div><div><dt>Position rank</dt><dd>${esc(me.pos)}${r.posRank}</dd></div><div><dt>Trade chart average</dt><dd>${f1(avg)}</dd><small>${avg===null?'No chart lists him':'indexed, '+me.avgN+'/4 charts'}</small></div></dl>
<h3 class="vfind-h3" id="vfind-comp-h">Comparably valued</h3>
<p class="vfind-basis" id="vfind-basis">Players within ±${st.band} DDF Value points of his ${f1(me.ddf)} (${f1(Math.max(0,c.lo))} to ${f1(c.hi)}), at your league settings. DDF Value runs from 0 to 100. Gap is each player’s DDF Value minus his.</p>
<div class="vfind-ctrls">${seg('band','Band',BANDS.map(b=>[b,'±'+b,'Within plus or minus '+b+' points']),st.band)}${seg('scope','Show',[['all','All '+c.counts.all],['same',esc(me.pos)+' '+c.counts.same],['other','Other '+c.counts.other,'Other positions '+c.counts.other]],st.scope)}</div>
${empty}${c.list.length?`<ul class="vfind-rows" aria-labelledby="vfind-comp-h" aria-describedby="vfind-basis">${lis.join('')}</ul>`:''}
${sh.cut?`<p class="vfind-more"><button type="button" class="link-button" id="vfind-all">Show all ${c.list.length} in the band</button> <span class="vfind-meta">Showing the ${SHOW} closest in value, ${scopeName}.</span></p>`:''}`;
 card.hidden=false;
}
card.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.id==='vfind-clear'){q.value='';q.dataset.picked='';pick(null,{push:true});q.focus();return}
 if(b.id==='vfind-all'){st.all=true;render();return}
 if(b.dataset.band){st.band=+b.dataset.band;st.all=false;render();const n=card.querySelector(`[data-band="${st.band}"]`);if(n)n.focus();return}
 if(b.dataset.scope){st.scope=b.dataset.scope;st.all=false;render();const n=card.querySelector(`[data-scope="${st.scope}"]`);if(n)n.focus();return}
 if(b.dataset.key)pick(b.dataset.key,{push:true,resetScope:false});
});
card.addEventListener('keydown',e=>{
 const b=e.target.closest('[role=radio]');if(!b||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
 const g=[...b.parentElement.querySelectorAll('[role=radio]')],i=g.indexOf(b),j=(i+(e.key==='ArrowRight'||e.key==='ArrowDown'?1:-1)+g.length)%g.length;
 e.preventDefault();g[j].click();
});
function fromHash(){const k=hashKey();if(k!==st.key)pick(k,{write:false})}
addEventListener('hashchange',fromHash);
addEventListener('popstate',fromHash);
document.addEventListener('ddf:values-change',()=>{render();if(!list.hidden)renderOpts()});
const boot=V()&&V().ready;
if(boot)boot.then(()=>{ready=true;if(!list.hidden)renderOpts();fromHash();render()},()=>{failed=true;render();if(!list.hidden)renderOpts()});
if(hashKey())loadMatcher();
V().find={find,comparables,pick,state:()=>Object.assign({},st),BANDS,SHOW,loadMatcher};
})();
