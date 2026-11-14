(()=>{
const $=id=>document.getElementById(id);
/* Every number here is an engine row (DDF.engine, ddf-engine.js): the same engine and settings as the rest of the site.
   p.base = DDF Value from the pipeline; p.ddf = the value every tab uses (your override when set, applied by the engine after
   the pipeline). A source that does not list a player is null: no dot, "—" in the table, never 0. */
const E=()=>window.DDF&&window.DDF.engine;
const D=[];
let yours=new Set(),prior=null,priorState='loading';
const EXTRA=[['avg','Trade chart average · indexed','#5c6a76','14 4'],['usat','USA Today (analyst chart) · indexed','#8a6d1d','6 3'],['fp','FantasyPros (analyst chart) · indexed','#2f8f9d','1 4'],['espn','ESPN projections · adjusted','#9a3d6b','10 4 2 4'],['cbsros','CBS rest of season projections · adjusted','#5b6b2f','12 3'],['razzball','Razzball projections · adjusted','#6b5b95','3 3']];
function load(){const e=E();if(!e||!e.controls())return;
 const list=e.players().filter(r=>r.ddf!==null).slice().sort((a,b)=>b.ddf-a.ddf);
 const meanOf=(r,ks)=>{const v=ks.map(k=>r[k]).filter(x=>typeof x==='number'&&isFinite(x));return v.length?v.reduce((a,b)=>a+b,0)/v.length:null};
 D.length=0;list.forEach(r=>D.push({avg:meanOf(r,['cbs','usat','fp','fc']),avgN:['cbs','usat','fp','fc'].filter(k=>typeof r[k]==='number'&&isFinite(r[k])).length,key:r.key,n:r.n,pos:r.pos,team:r.team,ddf:r.ddf,base:r.base===null?r.ddf:r.base,ov:r.ov,ovSpec:r.ovSpec,cbs:r.cbs,fc:r.fc,usat:r.usat,fp:r.fp,espn:r.espn,cbsros:r.cbsros,razzball:r.razzball,vaw:r.vaw,vawN:r.vawN,star:yours.has(r.key),chg:null,was:null}));
 if(prior&&prior.available){const cur=prior.currentValues||{},was=prior.values||{};D.forEach(p=>{const a=cur[p.key],b=was[p.key];if(typeof a==='number'&&isFinite(a)&&typeof b==='number'&&isFinite(b)){p.chg=a-b;p.was=b;p.now=a}})}
}
function applyOverrides(){load()}
/* context chips and Customize > Your league settings (the engine applies them; ddf-engine.js saves them where the live pages read them) */
const SCORING={standard:'Standard',half_ppr:'Half PPR',ppr:'Full PPR'};
const SLOTS=[['QB','QB',1,5],['RB','RB',1,5],['WR','WR',1,5],['TE','TE',1,5],['FLEX','FLEX',1,5],['BENCH','Bench',0,14]];
const MON=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
function syncChips(){const e=E();if(!e||!e.controls())return;const st=e.settings(),m=e.meta(),sf=(st.roster.SUPERFLEX||0)>0;
 let d='';if(m.asOf){const [y,mo,da]=m.asOf.split('-').map(Number);d='AS OF '+MON[mo-1]+' '+da+' '+y}
 $('vchip-week').textContent=[m.week?'WEEK '+m.week:'',d].filter(Boolean).join(' · ')||'Current values';
 $('vchip-scoring').textContent=SCORING[st.scoring]||st.scoring;$('vchip-scoring').hidden=false;
 $('vchip-teams').textContent=st.teams+' teams';$('vchip-teams').hidden=false;$('vchip-sf').hidden=!sf;
 $('set-scoring').value=st.scoring;$('set-teams').value=String(st.teams);$('set-sf').checked=sf;
 const box=$('set-slots');if(!box.dataset.built){box.dataset.built='1';box.innerHTML=SLOTS.map(([k,l,lo,hi])=>`<label class="vset-slot">${l}<input type="number" id="slot-${k}" data-slot="${k}" min="${lo}" max="${hi}" step="1" inputmode="numeric" aria-label="${l} slots"></label>`).join('')}
 SLOTS.forEach(([k])=>{const i=$('slot-'+k);if(i&&document.activeElement!==i)i.value=st.roster[k]});
 $('star-legend').hidden=!D.some(p=>p.star)}
function applySetting(partial,what){const e=E();if(!e||!e.controls())return;
 try{e.apply(partial);$('set-status').textContent=what+' updated. Every value on this page is recomputed.'}catch(err){$('set-status').textContent='That setting was not accepted.'}}
$('set-scoring').addEventListener('change',()=>applySetting({scoring:$('set-scoring').value},'Scoring'));
$('set-teams').addEventListener('change',()=>applySetting({teams:+$('set-teams').value},'Teams'));
$('set-sf').addEventListener('change',()=>applySetting({superflex:$('set-sf').checked},'Superflex'));
let slotT=null;$('set-slots').addEventListener('input',e=>{const i=e.target.closest('[data-slot]');if(!i)return;const v=Math.round(+i.value);if(!isFinite(v)||i.value==='')return;clearTimeout(slotT);slotT=setTimeout(()=>applySetting({roster:{[i.dataset.slot]:Math.max(+i.min,Math.min(+i.max,v))}},i.getAttribute('aria-label').replace(' slots',' slots')),300)});
/* Value above waivers = VORP before DDF's starter/bench weighting: per trade chart max(0, native - waiver line) x pie / surplusTotal
   (the engine's row.vorp, getInspection), averaged over the four charts that price the player, as DDF Value averages their
   adjusted values. Overrides change DDF Value only, not this. A player no chart prices shows n/a. */
const NAMES={avg:'Trade chart average (indexed)',ddf:'DDF',cbs:'CBS (indexed)',fc:'Live market (FantasyCalc, indexed)',vaw:'Value above waivers',usat:'USA Today (indexed)',fp:'FantasyPros (indexed)',espn:'ESPN (adjusted)',cbsros:'CBS ROS (adjusted)',razzball:'Razzball (adjusted)'};
const num=v=>typeof v==='number'&&isFinite(v);
const fx=v=>num(v)?v.toFixed(1):'—';
const vawOf=p=>num(p.vaw)?p.vaw:null;
const vawTxt=p=>{const v=vawOf(p);return v===null?'n/a':v.toFixed(1)};
const pv=(p,k)=>k==='vaw'?vawOf(p):num(p[k])?p[k]:null;
const val=(p,k)=>{const v=k==='dcbs'?dCbs(p):pv(p,k);return v===null?-1e9:v};
const gapOf=p=>num(p.cbs)&&num(p.fc)?p.ddf-(p.cbs+p.fc)/2:num(p.cbs)?p.ddf-p.cbs:num(p.fc)?p.ddf-p.fc:null;
/* R6-CX-02: the card's gap label names the charts gapOf actually used. */
const gapLabel=p=>num(p.cbs)&&num(p.fc)?'DDF minus CBS/FantasyCalc average':num(p.cbs)?'DDF minus CBS':num(p.fc)?'DDF minus FantasyCalc':'DDF minus CBS/FantasyCalc average';
const dCbs=p=>num(p.cbs)?p.ddf-p.cbs:null;
const sg=v=>num(v)?(v>=0?'+':'−')+Math.abs(v).toFixed(1):'—';
const vpAttr=s=>String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
const vpLeague=()=>{const v=window.DDFValues;return !!(v&&v.bs&&v.bs.isLeague&&v.bs.isLeague())};
function vpActs(p,cls){const n=vpAttr(p.n);return `<span class="vp-acts ${cls||''}"><button type="button" class="vp-act" data-act="own" data-n="${n}" aria-label="Set your own value for ${n}">Set your own value</button>${vpLeague()?`<button type="button" class="vp-act" data-act="bs" data-n="${n}" aria-label="Buy / Sell view for ${n}">Buy / Sell view</button>`:''}</span>`}
function ovCell(p){const n=vpAttr(p.n);return `<td class="ovcol"><button type="button" class="vp-act" data-act="own" data-n="${n}" aria-label="${p.ov?'Edit your value for ':'Set your own value for '}${n}">${p.ov?'Edit':'Set'}</button>${vpLeague()?`<button type="button" class="vp-act" data-act="bs" data-n="${n}" aria-label="Buy / Sell view for ${n}">Buy/Sell</button>`:''}</td>`}
const POS_ORDER=['QB','RB','WR','TE'];
let firstDraw=true,quiet=false,sortKey='ddf',shown=[],geo=[],hl=null,pinned=null,cardIdx=null,anchorEl=null,hideT=null,focusIdx=0,W=960;
let H=370,PL=95,PR=915,rot=false,fsOpen=false;
const SHORT={ddf:'DDF',cbs:'CBS',fc:'FantasyCalc',usat:'USA Today',fp:'FantasyPros',espn:'ESPN',cbsros:'CBS ROS',razzball:'Razzball',vaw:'Above waivers',avg:'Trade chart average'};
let lastSeries=[],selName=null,selIdx=null;
function rankKey(){return $('rank').value}
function render(){
 const lo=+$('low').value,hi=+$('high').value;let min=+$('min-value').value,max=+$('max-value').value;
 if(max<=min){max=min+1;$('max-value').value=max.toFixed(1)}
 $('low-number').value=lo;$('high-number').value=hi;
 const rk=rankKey(),q=$('search').value.toLowerCase(),ps=$('position').value;
 const pool=D.filter(p=>p.n.toLowerCase().includes(q)&&(ps==='All positions'||p.pos===ps)&&(rk==='ddf'||pv(p,rk)!==null)).sort((a,b)=>val(b,rk)-val(a,rk)).map((p,i)=>({p,rank:i+1}));
 syncRankMax(pool.length);
 shown=pool.filter(o=>o.rank>=lo&&o.rank<=hi);
 const n=shown.length,box=$('vchart').parentElement.clientWidth||960;if(fsOpen){W=Math.max(300,box);H=Math.max(150,$('vchart').parentElement.clientHeight||300)}else{W=box<600?420:960;H=370}const narrow=!fsOpen&&W<960,fs=fsOpen?13:narrow?19:12.5,L=fsOpen?58:narrow?76:95,R=W-(fsOpen?22:narrow?24:45);PL=L;PR=R;const BL=H-70,PH=H-100;
 $('vchart').setAttribute('viewBox','0 0 '+W+' '+H);
 const x=i=>n<2?(L+R)/2:L+i*(R-L)/(n-1),y=v=>BL-(v-min)*PH/(max-min);
 const series=[['ddf','#176c4d',''],['cbs','#e07832','8 6'],['fantasycalc','#4a5fc1','2 5']].filter(s=>$(s[0]).checked).map(s=>[s[0]==='fantasycalc'?'fc':s[0],s[1],s[2]]);
 EXTRA.forEach(([k,,color,dash])=>{const b=$('src-'+k);if(b&&b.checked)series.push([k,color,dash])});
 if($('vaw-on').checked&&$('vaw-chart').checked)series.push(['vaw','#7a4fa8','9 3 2 3']);
 const prim=series.length?series[0][0]:'ddf';lastSeries=series;
 let svg='<defs><clipPath id="plot"><rect x="'+(L-40)+'" y="0" width="'+(W-L+40)+'" height="'+(H-58)+'"/></clipPath></defs>';
 const step=(max-min)<=40?5:(max-min)<=100?10:25;
 for(let v=Math.ceil(min/step)*step;v<=max+1e-9;v+=step)svg+=`<path d="M${L-20} ${y(v)}H${W-10}" stroke="#dbe0dc"/><text x="${L-26}" y="${y(v)+4}" text-anchor="end" font-size="${fs}">${+v.toFixed(1)}</text>`;
 svg+=`<path d="M${L-20} ${BL}H${W-10}" stroke="#142b25"/><text transform="translate(${fsOpen||narrow?9:16} ${(H-40)/2}) rotate(-90)" text-anchor="middle" font-size="${fs+1}" font-family="Archivo,sans-serif" font-weight="600" fill="#142b25">Value</text><text x="${(L+R)/2}" y="${H-8}" text-anchor="middle" font-size="${fs+1}" font-family="Archivo,sans-serif" font-weight="600" fill="#142b25">Player rank</text>`;
 const few=n<=6,anchor=i=>n<2?'middle':i===0?'start':i===n-1?'end':'middle',dx=i=>anchor(i)==='start'?-8:anchor(i)==='end'?8:0;
 const label=p=>fsOpen?p.n.split(' ')[0][0]+'. '+p.n.split(' ').slice(1).join(' '):narrow?p.n.split(' ').slice(-1)[0].replace('III',p.n.split(' ')[1]):p.n;
 const r=n>12?3.5:5;
 svg+='<g clip-path="url(#plot)">';
 series.forEach(([k,color,dash])=>{
  if(n>1){let pen=false;const d=shown.map((o,i)=>{const v=pv(o.p,k);if(v===null){pen=false;return ''}const c=(pen?'L':'M')+x(i)+' '+y(v);pen=true;return c}).filter(Boolean).join(' ');if(d)svg+=`<path class="${dash?'vline-d':'vline'}" pathLength="1" d="${d}" fill="none" stroke="${color}" stroke-width="3" stroke-dasharray="${dash}"/>`}
  shown.forEach((o,i)=>{const v=pv(o.p,k);if(v!==null)svg+=`<circle class="vdot" style="--i:${i}" cx="${x(i)}" cy="${y(v)}" r="${r}" fill="${color}"/>`});
  if(k==='ddf'){const placed=[];
   const others=series.filter(q=>q[0]!=='ddf').map(q=>q[0]);
   const segs=[];series.forEach(([kk])=>{for(let i=0;i<n-1;i++){const a=pv(shown[i].p,kk),b=pv(shown[i+1].p,kk);if(a!==null&&b!==null)segs.push([x(i),y(a),x(i+1),y(b)])}});
   const hitsLine=(l,t,rr,bb)=>segs.some(([x1,y1,x2,y2])=>{for(let q=0;q<=14;q++){const px=x1+(x2-x1)*q/14,py=y1+(y2-y1)*q/14;if(px>l-3&&px<rr+3&&py>t-3&&py<bb+3)return true}return false});
   shown.map((o,i)=>({o,i,pri:o.p.n===hl?0:few?1:(o.p.star&&(o.p.ddf>=30||n<=12))?2:(fsOpen&&n<=60)?8:9})).filter(c=>c.pri<9).sort((a,b)=>a.pri-b.pri||b.o.p.ddf-a.o.p.ddf).forEach(({o,i,pri})=>{
    const t=(o.p.star?'★ ':'')+label(o.p)+' '+o.p.ddf.toFixed(1),w=t.length*fs*.62,px=x(i),py=y(o.p.ddf);
    const otherAbove=others.length&&others.some(kk=>pv(o.p,kk)!==null&&pv(o.p,kk)>o.p.ddf);
    const below=py+fs+9,above=py-9;
    const cand={ur:[px+9,above],ul:[px-9-w,above],lr:[px+9,below],ll:[px-9-w,below]};
    const order=otherAbove?['ll','lr','ul','ur']:['ur','ul','lr','ll'];
    let pick=null;
    for(const c of order){const [l,yy]=cand[c];if(l<L-18||l+w>W-6||yy<fs||yy>BL-4)continue;if(hitsLine(l,yy-fs+2,l+w,yy+3))continue;if(placed.some(q=>l<q.r+4&&l+w>q.l-4&&Math.abs(yy-q.y)<fs+3))continue;pick=[l,yy];break}
    if(!pick){if(pri>0)return;pick=cand[order[0]];pick=[Math.max(L-18,Math.min(pick[0],W-6-w)),pick[1]]}
    placed.push({l:pick[0],r:pick[0]+w,y:pick[1]});
    svg+=`<text x="${pick[0]}" y="${pick[1]}" text-anchor="start" paint-order="stroke" stroke="#fff" stroke-width="4" stroke-linejoin="round" font-size="${fs}" font-weight="700" fill="#176c4d">${t}</text>`})}
  else if(few)shown.forEach((o,i)=>{const v=pv(o.p,k);if(v!==null)svg+=`<text x="${x(i)}" y="${y(v)+22}" text-anchor="middle" font-size="${fs}" fill="#12202c">${v.toFixed(1)}</text>`});
  if(k==='ddf')shown.forEach((o,i)=>{if(!o.p.ov)return;const px=x(i),py=y(o.p.ddf),pb=y(o.p.base),s=narrow?11:8;
   svg+=`<g class="vovr" aria-hidden="true"><path d="M${px} ${pb}V${py}" stroke="#a83e12" stroke-width="1.5" stroke-dasharray="3 3"/><circle cx="${px}" cy="${pb}" r="${r+1}" fill="#fff" stroke="#a83e12" stroke-width="1.5"/><path d="M${px} ${py-s}L${px+s} ${py}L${px} ${py+s}L${px-s} ${py}Z" fill="#a83e12" stroke="#fff" stroke-width="2"/><text x="${px+s+4}" y="${py+(pb<py?fs+6:-s-2)}" font-size="${fs}" font-family="Archivo,sans-serif" font-weight="700" fill="#a83e12" paint-order="stroke" stroke="#fff" stroke-width="4" stroke-linejoin="round">Override</text></g>`});
 });
 if(!few&&!series.some(s=>s[0]==='ddf')){shown.forEach((o,i)=>{if(o.p.n===hl)svg+=`<text x="${x(i)+dx(i)}" y="${y(pv(o.p,prim)||0)-16}" text-anchor="${anchor(i)}" paint-order="stroke" stroke="#fff" stroke-width="4" font-size="${fs}" font-weight="700" fill="#142b25">${label(o.p)}</text>`})}
 shown.forEach((o,i)=>{if(o.p.n===hl)svg+=`<circle cx="${x(i)}" cy="${y(pv(o.p,prim)||0)}" r="11" fill="none" stroke="#e96528" stroke-width="3"/>`});
 if(focusIdx>=n)focusIdx=Math.max(0,n-1);
 geo=shown.map((o,i)=>({i,x:x(i),ys:series.filter(s=>pv(o.p,s[0])!==null).map(s=>y(pv(o.p,s[0])))}));
 shown.forEach((o,i)=>svg+=`<circle class="values-hit" data-i="${i}" cx="${x(i)}" cy="${y(pv(o.p,prim)||0)}" r="10" role="button" tabindex="${i===focusIdx?0:-1}" aria-label="${o.p.n}, rank ${o.rank}, ${o.p.ov?'your value '+o.p.ddf.toFixed(1)+' (override; DDF '+o.p.base.toFixed(1)+')':'DDF '+o.p.ddf.toFixed(1)}. Press Enter for details."/>`);
 svg+='</g>';
 const tstep=Math.ceil(n/(fsOpen?12:narrow?9:14));
 shown.forEach((o,i)=>{if(i%tstep===0||i===n-1)svg+=`<text x="${x(i)}" y="${H-42}" text-anchor="middle" font-size="${fs+1}">${o.rank}</text>`});
 $('vchart').innerHTML=svg;
 selIdx=selName===null?null:shown.findIndex(o=>o.p.n===selName);if(selIdx<0)selIdx=null;if(fsOpen){drawCursor();setReadout(selIdx)}
 $('chart-summary').textContent='Chart data, '+n+' players by '+(NAMES[rk]||rk)+': '+shown.map(o=>'#'+o.rank+' '+o.p.n+' '+series.map(q=>NAMES[q[0]]+' '+(pv(o.p,q[0])===null?'n/a':pv(o.p,q[0]).toFixed(1))+(q[0]==='ddf'&&o.p.ov?' (your override; DDF '+o.p.base.toFixed(1)+')':'')).join(', ')).join('; ')+'. The table below lists the same values.';
 if(firstDraw){firstDraw=false;$('vchart').classList.add('vdraw');setTimeout(()=>$('vchart').classList.remove('vdraw'),2200)}
 renderTable();
 const cap=$('player-count').value==='All'?' (all players)':'';
 $('count').textContent=D.length?n+' of '+D.length+' in view'+cap:(document.body.classList.contains('values-live')?'No players':'Loading values…');
 if(cardIdx!==null){if(pinned!==null&&shown[cardIdx]&&anchorEl&&anchorEl.closest('tbody'))placeAfter();else hideCard(true)}
}
/* Group by position: off (default) = one flat list by the sort column with a position chip; on = position header rows (JEG-1621). */
const GROUP_KEY='ddf:values:groupByPosition';
let groupByPos=false;
try{groupByPos=localStorage.getItem(GROUP_KEY)==='1'}catch(e){}
function syncGroupBtn(){const b=$('group-pos');if(b)b.setAttribute('aria-pressed',String(groupByPos))}
const gb=$('group-pos');
if(gb)gb.addEventListener('click',()=>{groupByPos=!groupByPos;try{localStorage.setItem(GROUP_KEY,groupByPos?'1':'0')}catch(e){}syncGroupBtn();hideCard(true);renderTable()});
syncGroupBtn();
function cols(){const c=[['ddf','DDF'],['cbs','CBS (indexed)']];if($('fantasycalc').checked)c.push(['fc','Live market (FantasyCalc, indexed)']);EXTRA.forEach(([k])=>{const b=$('src-'+k);if(b&&b.checked)c.push([k,NAMES[k]])});if($('vaw-on').checked)c.push(['vaw','<span class="vaw-wide">Value above waivers</span><span class="vaw-narrow" aria-hidden="true">Above waivers</span>']);c.push(['dcbs','DDF vs CBS']);return c}
function renderTable(){
 const c=cols();if(!c.some(k=>k[0]===sortKey))sortKey='ddf';
 $('head').innerHTML='<tr><th scope="col" class="pl">Player</th>'+c.map(([k,t])=>`<th scope="col" class="num" aria-sort="${k===sortKey?'descending':'none'}"><button type="button" class="sort" data-key="${k}">${t} <span class="arrow" aria-hidden="true">${k===sortKey?'▼':''}</span></button></th>`).join('')+'<th scope="col" class="ovcol">Override</th></tr>';
 const rows=shown.map((o,i)=>({o,i})).sort((a,b)=>val(b.o.p,sortKey)-val(a.o.p,sortKey));
 const grouped=groupByPos;
 const rowHtml=({o,i})=>{const p=o.p;return `<tr data-i="${i}" tabindex="0" class="${p.n===hl?'values-hl':''}${p.ov?' ov-row':''}" aria-label="${p.n}${grouped?'':', '+p.pos}${p.ov?', your override':''}, details on focus"><td class="pl"><span class="pn">${p.star?'<span class="pstar" aria-label="Your player">★</span> ':''}${p.n}</span>${grouped?'':` <span class="pos pos-${p.pos}">${p.pos}</span>`}</td>`+c.map(([k])=>k==='ddf'&&p.ov?`<td class="num ovcell"><span class="ov-was">DDF ${p.base.toFixed(1)} →</span> <span class="ov-now">Yours ${p.ddf.toFixed(1)}</span></td>`:k==='dcbs'?`<td class="num ${dCbs(p)===null?'':dCbs(p)>=0?'dpos':'dneg'}">${sg(dCbs(p))}</td>`:k==='vaw'?`<td class="num vaw-cell${vawOf(p)===null?' vaw-na':''}"${vawOf(p)===null?' title="No trade chart prices this player"':''}>${vawTxt(p)}</td>`:`<td class="num"${k==='avg'?' style="white-space:nowrap"':''}>${fx(p[k])}${k==='avg'&&num(p.avg)?` <span class="avg-n">${p.avgN}/4</span>`:''}</td>`).join('')+ovCell(p)+'</tr>'};
 if(!grouped){$('rows').innerHTML=rows.map(rowHtml).join('');return}
 const groups=[...new Set(rows.map(r=>r.o.p.pos))].sort((a,b)=>{const x=POS_ORDER.indexOf(a),y=POS_ORDER.indexOf(b);return (x<0?99:x)-(y<0?99:y)||String(a).localeCompare(String(b))});
 $('rows').innerHTML=groups.map(g=>{const gr=rows.filter(r=>r.o.p.pos===g);return `<tr class="pos-grp"><th scope="rowgroup" colspan="${c.length+2}" class="pos-${g}">${g} <span class="pos-n">${gr.length}</span></th></tr>`+gr.map(rowHtml).join('')}).join('');
}
/* player card */
function cardHTML(o){const p=o.p,g=gapOf(p),v=$('vaw-on').checked,row=(t,x)=>`<dt>${t}</dt><dd>${fx(x)}</dd>`;
 const href=E()&&E().buildHref?E().buildHref(p.star?{give:[p]}:{get:[p]}):'build.html';
 return `<div class="vc-head"><div><div class="vc-name">${p.star?'★ ':''}${p.n}</div><div class="vc-sub">${p.pos}${p.team?' · '+p.team:''}</div></div><button type="button" class="vc-close" aria-label="Close player card">×</button></div><dl><dt>Rank</dt><dd>#${o.rank}</dd>${p.ov?`<dt>DDF value</dt><dd>${p.base.toFixed(1)}</dd><dt>Your value (override)</dt><dd class="vc-neg">${p.ddf.toFixed(1)}</dd>`:`<dt>DDF value</dt><dd>${p.ddf.toFixed(1)}</dd>`}${row('CBS Sports indexed',p.cbs)}${row('USA Today indexed',p.usat)}${row('FantasyPros indexed',p.fp)}${row('Live market (FantasyCalc) indexed',p.fc)}<dt>Trade chart average (${p.avgN}/4 charts)</dt><dd>${fx(p.avg)}</dd><dt>${gapLabel(p)}</dt><dd class="${g===null?'':g>=0?'vc-pos':'vc-neg'}">${sg(g)}</dd>${num(p.chg)?`<dt>Since last week</dt><dd>${sg(p.chg)}</dd>`:''}${v?`<dt>Value above waivers</dt><dd>${vawTxt(p)}</dd>`:''}</dl>${vpActs(p)}<a class="vc-link" href="${href}">Open in Build a Trade</a>`}
function placeAfter(){const c=$('values-card');if(!anchorEl||!document.contains(anchorEl)){return}const a=anchorEl.getBoundingClientRect(),w=c.offsetWidth,h=c.offsetHeight,vw=document.documentElement.clientWidth;let top=a.top-h-10;if(top<8)top=a.bottom+10;if(top+h>innerHeight-8)top=Math.max(8,innerHeight-h-8);let left=a.left+a.width/2-w/2;left=Math.max(8,Math.min(left,vw-w-8));c.style.top=top+'px';c.style.left=left+'px'}
function refocus(a){if(a&&document.contains(a)){quiet=true;a.focus();quiet=false}}
function showCard(i,el,pin){if(fsOpen){fsSelect(i);return}clearTimeout(hideT);if(quiet)return;const o=shown[i];if(!o)return;const c=$('values-card');if(pinned!==null&&!pin&&pinned!==i)return;cardIdx=i;anchorEl=el;if(pin)pinned=i;document.querySelectorAll('.values-hit.on').forEach(h=>h.classList.remove('on'));const he=hitEl(i);if(he)he.classList.add('on');c.innerHTML=cardHTML(o);c.hidden=false;placeAfter()}
function hideCard(force){clearTimeout(hideT);if(!force&&pinned!==null)return;pinned=null;cardIdx=null;document.querySelectorAll('.values-hit.on').forEach(h=>h.classList.remove('on'));$('values-card').hidden=true}
function softHide(){clearTimeout(hideT);hideT=setTimeout(()=>hideCard(false),220)}
function hitEl(i){return $('vchart').querySelector('.values-hit[data-i="'+i+'"]')}
function rowEl(i){return $('rows').querySelector('tr[data-i="'+i+'"]')}
function toSvg(cx,cy){const b=$('vchart').getBoundingClientRect();if(rot){const k=W/b.height;return{x:(cy-b.top)*k,y:(b.right-cx)*k,k}}const k=W/b.width;return{x:(cx-b.left)*k,y:(cy-b.top)*k,k}}
function idxAt(cx,cy){const n=shown.length;if(n<2)return 0;return Math.max(0,Math.min(n-1,Math.round((toSvg(cx,cy).x-PL)/(PR-PL)*(n-1))))}
function pickAt(cx,cy){const t=toSvg(cx,cy),sx=t.x,sy=t.y,lim=22*t.k;let best=null,bd=lim;geo.forEach(g=>{g.ys.forEach(y=>{const d=Math.hypot(g.x-sx,y-sy);if(d<bd){bd=d;best=g.i}})});return best}
/* chart interaction */
let start=null,startY=0,captured=false,dragged=false;const chart=$('vchart');
chart.addEventListener('pointerdown',e=>{if(fsOpen){fsDown(e);return}start=e.clientX;startY=e.clientY;captured=false;dragged=false});
chart.addEventListener('pointermove',e=>{
 if(fsOpen){fsMove(e);return}
 if(start!==null){if(!captured&&Math.abs(e.clientX-start)>8){captured=true;dragged=true;hideCard(true);try{chart.setPointerCapture(e.pointerId)}catch(_){}}return}
 if(e.pointerType==='mouse'){const i=pickAt(e.clientX,e.clientY);if(i!==null){showCard(i,hitEl(i),false);chart.style.cursor='pointer'}else{chart.style.cursor='';if(cardIdx!==null)softHide()}}});
chart.addEventListener('pointerleave',e=>{if(start===null&&e.pointerType==='mouse'&&cardIdx!==null)softHide()});
chart.addEventListener('pointerup',e=>{if(fsOpen){fsUp(e);return}if(start===null)return;const s=start;start=null;
 if(dragged){const n=shown.length;if(n>1){const a=idxAt(s,e.clientY),z=idxAt(e.clientX,e.clientY);$('low').value=Math.min(shown[a].rank,shown[z].rank);$('high').value=Math.max(shown[a].rank,shown[z].rank);render()}return}
 const i=pickAt(e.clientX,e.clientY);if(i===null){hideCard(true);return}
 if(pinned===i){hideCard(true)}else{pinned=null;showCard(i,hitEl(i),true);focusIdx=i}});
chart.addEventListener('pointercancel',e=>{start=null;if(fsOpen)fsUp(e,true)});
chart.addEventListener('focusin',e=>{const t=e.target.closest&&e.target.closest('.values-hit');if(t){focusIdx=+t.dataset.i;if(pinned===null)showCard(focusIdx,t,false)}});
chart.addEventListener('focusout',e=>{if(pinned===null)softHide()});
chart.addEventListener('keydown',e=>{const t=e.target.closest&&e.target.closest('.values-hit');if(!t)return;const i=+t.dataset.i,n=shown.length;
 if(e.key==='ArrowRight'||e.key==='ArrowLeft'||e.key==='Home'||e.key==='End'){e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?n-1:Math.max(0,Math.min(n-1,i+(e.key==='ArrowRight'?1:-1)));t.tabIndex=-1;const nt=hitEl(j);nt.tabIndex=0;focusIdx=j;nt.focus()}
 else if(e.key==='Enter'||e.key===' '){e.preventDefault();pinned=null;showCard(i,t,true);$('values-card').focus()}});
/* table interaction */
const rows=$('rows');
rows.addEventListener('mouseover',e=>{const tr=e.target.closest('tr[data-i]');if(tr&&e.sourceCapabilities?.firesTouchEvents!==true)showCard(+tr.dataset.i,tr,false)});
rows.addEventListener('mouseleave',()=>{if(cardIdx!==null)softHide()});
rows.addEventListener('focusin',e=>{const tr=e.target.closest('tr[data-i]');if(tr&&pinned===null)showCard(+tr.dataset.i,tr,false)});
rows.addEventListener('focusout',()=>{if(pinned===null)softHide()});
rows.addEventListener('click',e=>{if(e.target.closest('.vp-act'))return;const tr=e.target.closest('tr[data-i]');if(!tr)return;const i=+tr.dataset.i;if(pinned===i){hideCard(true)}else{pinned=null;showCard(i,tr,true)}});
rows.addEventListener('keydown',e=>{if(e.target.closest('.vp-act'))return;const tr=e.target.closest('tr[data-i]');if(tr&&(e.key==='Enter'||e.key===' ')){e.preventDefault();pinned=null;showCard(+tr.dataset.i,tr,true);$('values-card').focus()}});
const card=$('values-card');
card.addEventListener('mouseenter',()=>clearTimeout(hideT));
card.addEventListener('mouseleave',()=>{if(pinned===null)softHide()});
card.addEventListener('click',e=>{if(e.target.closest('.vc-close')){const a=anchorEl;hideCard(true);refocus(a)}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!card.hidden){const a=anchorEl;hideCard(true);refocus(a)}});
document.addEventListener('pointerdown',e=>{if(pinned!==null&&!card.contains(e.target)&&!chart.contains(e.target)&&!rows.contains(e.target))hideCard(true)});
addEventListener('scroll',()=>{if(cardIdx===null)return;if(pinned!==null)placeAfter();else hideCard(true)},{passive:true});
addEventListener('resize',()=>{if(cardIdx!==null&&pinned!==null)placeAfter()});

/* ---- Full screen landscape view (JEG-1636) ----
   The chart, its sliders and its source boxes move into #vfs (the same elements, so every handler keeps working) and move back on close.
   iPhone Safari cannot lock orientation, so a portrait phone gets the overlay turned 90 degrees with CSS; where screen.orientation.lock
   works (Android Chrome, in fullscreen) the page is really landscape. Page scroll is locked while open, so drags and pinches reach the chart. */
let fsTool='inspect',fsY=0,fsSaved=null,fsSlots=[];const fsPts=new Map();let fsPinch=null,fsDrag=null,fsRaf=0,fsPushed=false;
const FS_NODES=()=>['.series','.chart-layout','.rank-controls','.rank-nudge','.count-row','.group-row'].map(q=>document.querySelector('.values-section '+q));
function toNum(i,d){const el=$(i),v=i.includes('value'),mx=v?100:(+el.max||1e9);const nv=Math.max(v?0:1,Math.min(mx,(+el.value||0)+d));el.value=v?nv.toFixed(1):nv;return el}
function fsLayout(){const o=$('vfs'),iw=innerWidth,ih=innerHeight;rot=ih>iw;o.classList.toggle('vfs-rot',rot);
 o.style.width=(rot?ih:iw)+'px';o.style.height=(rot?iw:ih)+'px';o.style.transform=rot?'translateX('+iw+'px) rotate(90deg)':'none'}
function fsRelayout(){if(!fsOpen)return;fsLayout();render()}
function drawCursor(){const old=chart.querySelector('#vfs-cur');if(old)old.remove();if(!fsOpen)return;
 let g='';if(fsDrag&&fsDrag.moved&&geo.length){const a=geo[idxAt(fsDrag.x,fsDrag.y)],z=geo[idxAt(fsDrag.cx,fsDrag.cy)];if(a&&z){const l=Math.min(a.x,z.x),r=Math.max(a.x,z.x);g+=`<rect x="${l}" y="0" width="${Math.max(2,r-l)}" height="${H-70}" fill="#176c4d" opacity=".16"/>`}}
 if(selIdx!==null&&geo[selIdx]){const q=geo[selIdx];g+=`<path d="M${q.x} 0V${H-70}" stroke="#e96528" stroke-width="1.5" stroke-dasharray="4 3"/>`+q.ys.map(y=>`<circle cx="${q.x}" cy="${y}" r="8" fill="none" stroke="#e96528" stroke-width="3"/>`).join('')}
 if(g)chart.insertAdjacentHTML('beforeend','<g id="vfs-cur" pointer-events="none">'+g+'</g>')}
function setReadout(i){const r=$('vfs-readout'),o=i===null?null:shown[i];
 if(!o){r.innerHTML='<span class="ro-idle">'+(shown.length>60?'Tap or drag on the chart to read a player. Zoom in to label names on the chart.':'Tap or drag on the chart to read a player.')+'</span>';return}
 const p=o.p;r.innerHTML=`<strong class="ro-name">${p.star?'★ ':''}${p.n}</strong><span class="ro-meta">${p.pos}${p.team?' · '+p.team:''} · rank ${o.rank}</span>`+lastSeries.map(([k,c])=>{const v=pv(p,k);return `<span class="ro-chip"><i style="background:${c}"></i>${SHORT[k]||k} <b>${v===null?'n/a':v.toFixed(1)}</b>${k==='avg'?' <small>('+p.avgN+'/4)</small>':''}</span>`}).join('')}
function fsSelect(i){const o=shown[i];if(!o)return;selName=o.p.n;selIdx=i;focusIdx=i;drawCursor();setReadout(i)}
function fsDown(e){try{chart.setPointerCapture(e.pointerId)}catch(_){}fsPts.set(e.pointerId,{x:e.clientX,y:e.clientY});
 if(fsPts.size>=2){const [a,b]=[...fsPts.values()];fsDrag=null;const mid=shown[idxAt((a.x+b.x)/2,(a.y+b.y)/2)];fsPinch={d0:Math.hypot(a.x-b.x,a.y-b.y)||1,lo:+$('low').value,hi:+$('high').value,mid:mid?mid.rank:+$('low').value,total:+$('high').max||1};return}
 if(fsTool==='zoom')fsDrag={x:e.clientX,y:e.clientY,cx:e.clientX,cy:e.clientY,moved:false};else fsSelect(idxAt(e.clientX,e.clientY))}
function fsMove(e){const pt=fsPts.get(e.pointerId);if(!pt)return;pt.x=e.clientX;pt.y=e.clientY;
 if(fsPinch&&fsPts.size>=2){const [a,b]=[...fsPts.values()],f=(Math.hypot(a.x-b.x,a.y-b.y)||1)/fsPinch.d0,m=fsPinch.mid,t=fsPinch.total;
  let lo=Math.round(m-(m-fsPinch.lo)/f),hi=Math.round(m+(fsPinch.hi-m)/f);lo=Math.max(1,lo);hi=Math.min(t,hi);if(hi-lo<2){hi=Math.min(t,lo+2);lo=Math.max(1,hi-2)}
  $('low').value=lo;$('high').value=hi;if(!fsRaf)fsRaf=requestAnimationFrame(()=>{fsRaf=0;render()});return}
 if(fsDrag){fsDrag.cx=e.clientX;fsDrag.cy=e.clientY;if(Math.abs(e.clientX-fsDrag.x)+Math.abs(e.clientY-fsDrag.y)>10)fsDrag.moved=true;drawCursor();return}
 if(fsTool==='inspect'&&fsPts.size===1)fsSelect(idxAt(e.clientX,e.clientY))}
function fsUp(e,cancel){fsPts.delete(e.pointerId);if(fsPinch){if(fsPts.size<2)fsPinch=null;if(fsPts.size===0)fsDrag=null;return}
 if(fsDrag){const d=fsDrag;fsDrag=null;if(!cancel&&d.moved&&shown.length>1){const a=shown[idxAt(d.x,d.y)],z=shown[idxAt(e.clientX,e.clientY)];$('low').value=Math.min(a.rank,z.rank);$('high').value=Math.max(a.rank,z.rank);render()}else if(!cancel&&!d.moved)fsSelect(idxAt(e.clientX,e.clientY));else drawCursor()}}
function fsLock(){fsY=window.scrollY;const b=document.body.style;fsSaved={position:b.position,top:b.top,left:b.left,right:b.right,width:b.width};
 b.position='fixed';b.top=-fsY+'px';b.left='0';b.right='0';b.width='100%';document.documentElement.classList.add('vfs-lock')}
function fsUnlock(){if(!fsSaved)return;const b=document.body.style;Object.assign(b,fsSaved);fsSaved=null;document.documentElement.classList.remove('vfs-lock');window.scrollTo(0,fsY)}
let fsNodes=[];
function fsMove2(toOverlay){const nodes=toOverlay?(fsNodes=FS_NODES()):fsNodes;
 if(toOverlay){fsSlots=nodes.map(n=>{if(!n)return null;const c=document.createComment('vfs');n.parentNode.insertBefore(c,n);return c});
  nodes.forEach((n,i)=>{if(!n)return;(i===1?$('vfs-chart'):$('vfs-drawer')).appendChild(n)})}
 else{nodes.forEach((n,i)=>{const c=fsSlots[i];if(n&&c&&c.parentNode)c.parentNode.replaceChild(n,c)});fsSlots=[]}}
function fsOpenNow(){if(fsOpen)return;hideCard(true);fsOpen=true;selName=null;selIdx=null;fsTool='inspect';syncTool();
 const o=$('vfs');o.hidden=false;o.classList.remove('vfs-ctrl-open');$('vfs-ctrl').setAttribute('aria-expanded','false');
 fsMove2(true);fsLock();try{history.pushState({vfs:1},'');fsPushed=true}catch(_){fsPushed=false}
 const sc=window.screen&&screen.orientation;
 const go=()=>{fsLayout();render();$('vfs-close').focus()};
 go();
 if(sc&&sc.lock&&document.documentElement.requestFullscreen&&matchMedia('(pointer:coarse)').matches){document.documentElement.requestFullscreen().then(()=>sc.lock('landscape')).then(()=>setTimeout(fsRelayout,350),()=>{})}
}
function fsCloseNow(){if(!fsOpen)return;fsOpen=false;fsPts.clear();fsPinch=null;fsDrag=null;const o=$('vfs');
 try{if(document.fullscreenElement)document.exitFullscreen();if(screen.orientation&&screen.orientation.unlock)screen.orientation.unlock()}catch(_){}
 fsMove2(false);o.hidden=true;o.style.width='';o.style.height='';o.style.transform='';rot=false;fsUnlock();render();const b=$('vfs-open');if(b)b.focus({preventScroll:true})}
function fsClose(){const had=fsOpen;fsCloseNow();if(had&&fsPushed&&history.state&&history.state.vfs){fsPushed=false;history.back()}}
function syncTool(){document.querySelectorAll('#vfs [data-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===fsTool)))}
$('vfs-open').addEventListener('click',fsOpenNow);
$('vfs-close').addEventListener('click',fsClose);
$('vfs-reset').addEventListener('click',()=>{$('reset').click()});
$('vfs-ctrl').addEventListener('click',()=>{const o=$('vfs'),on=!o.classList.contains('vfs-ctrl-open');o.classList.toggle('vfs-ctrl-open',on);$('vfs-ctrl').setAttribute('aria-expanded',String(on));requestAnimationFrame(render)});
document.querySelectorAll('#vfs [data-tool]').forEach(b=>b.addEventListener('click',()=>{fsTool=b.dataset.tool;syncTool()}));
addEventListener('popstate',()=>{if(fsOpen){fsPushed=false;fsCloseNow()}});
addEventListener('resize',fsRelayout);addEventListener('orientationchange',()=>setTimeout(fsRelayout,200));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&fsOpen&&!e.defaultPrevented)fsClose()});
$('vfs').addEventListener('touchmove',e=>{if(!e.target.closest('#vfs-drawer'))e.preventDefault()},{passive:false});
/* Touch sliders (phones, both views): the two handles share one 44px track. A touch drives the nearest handle; when the handles sit
   together, the first move decides (toward the high end moves the high handle). Keyboard and screen readers use the real inputs. */
const touchSliders=()=>matchMedia('(pointer:coarse),(max-width:760px)').matches;
function dualDrag(box,lowId,highId,vertical){const lo=$(lowId),hi=$(highId);let cur=null,pend=null,id=null,startP=0;
 const thumb=26,frac=e=>{const r=box.getBoundingClientRect(),len=vertical?r.height:r.width,p=vertical?r.bottom-e.clientY:e.clientX-r.left;return Math.max(0,Math.min(1,(p-thumb/2)/Math.max(1,len-thumb)))};
 const fr=i=>{const mn=+i.min,mx=+i.max;return mx>mn?(+i.value-mn)/(mx-mn):0};
 const setv=(i,f)=>{const mn=+i.min,mx=+i.max,st=+i.step||1;let v=mn+f*(mx-mn);v=Math.round(v/st)*st;v=Math.max(mn,Math.min(mx,+v.toFixed(2)));if(+i.value!==v){i.value=v;i.dispatchEvent(new Event('input',{bubbles:true}))}};
 box.addEventListener('pointerdown',e=>{if(!touchSliders()||(e.pointerType==='mouse'&&e.button!==0))return;e.preventDefault();id=e.pointerId;try{box.setPointerCapture(id)}catch(_){}
  const f=frac(e),dl=Math.abs(f-fr(lo)),dh=Math.abs(f-fr(hi)),len=vertical?box.getBoundingClientRect().height:box.getBoundingClientRect().width;
  startP=vertical?e.clientY:e.clientX;
  if(Math.abs(fr(hi)-fr(lo))*len<thumb+4&&Math.min(dl,dh)*len<thumb){pend=true;cur=null}else{pend=false;cur=dl<=dh?lo:hi;setv(cur,f)}});
 box.addEventListener('pointermove',e=>{if(e.pointerId!==id)return;const f=frac(e);
  if(pend){const d=(vertical?startP-e.clientY:e.clientX-startP);if(Math.abs(d)<3)return;cur=d>0?hi:lo;pend=false}
  if(cur)setv(cur,f)});
 const end=e=>{if(e.pointerId===id){id=null;cur=null;pend=null}};box.addEventListener('pointerup',end);box.addEventListener('pointercancel',end)}
dualDrag(document.querySelector('.dual-h'),'low','high',false);dualDrag(document.querySelector('.dual-v'),'value-low','value-high',true);
/* Nudge buttons: -/+ for the rank range and the value range, with hold to repeat */
document.querySelectorAll('.rank-nudge [data-t]').forEach(b=>{let tm=null,iv=null,n=0;const step=()=>{const big=n>8?5:1;n++;const el=toNum(b.dataset.t,+b.dataset.d*big*(b.dataset.t.includes('value')?1:1));if(el.oninput)el.oninput()};
 const stop=()=>{clearTimeout(tm);clearInterval(iv);tm=iv=null};
 b.addEventListener('pointerdown',e=>{e.preventDefault();n=0;step();tm=setTimeout(()=>{iv=setInterval(step,90)},380)});
 ['pointerup','pointerleave','pointercancel','blur'].forEach(t=>b.addEventListener(t,stop));
 b.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();n=0;step()}})});
/* controls */
['search','position','rank','ddf','cbs','fantasycalc'].forEach(id=>$(id).addEventListener('input',()=>{hideCard(true);render()}));
document.addEventListener('change',e=>{if(e.target&&e.target.id&&e.target.id.startsWith('src-')){hideCard(true);render()}});
document.querySelectorAll('.segmented [data-count]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.segmented [data-count]').forEach(o=>o.setAttribute('aria-checked',String(o===b)));$('player-count').value=b.dataset.count;$('low').value=1;$('high').value=countHigh();hideCard(true);render()});
$('head').addEventListener('click',e=>{const b=e.target.closest('.sort');if(b){sortKey=b.dataset.key;renderTable();const nb=$('head').querySelector('[data-key="'+sortKey+'"]');if(nb)nb.focus()}});
let rw=0;addEventListener('resize',()=>{const w=chart.parentElement.clientWidth;if((w<600)!==(rw<600)){rw=w;render()}});
function syncRankMax(total){if(!total)return;const m=total;['low','high','low-number','high-number'].forEach(id=>{$(id).max=m});if(+$('high').value>m)$('high').value=m;if(+$('low').value>m)$('low').value=m;$('low-number').value=$('low').value;$('high-number').value=$('high').value}
function countHigh(){const c=$('player-count').value;return c==='All'?1e6:+c}
['low','high','low-number','high-number'].forEach(id=>$(id).oninput=()=>{const first=id.startsWith('low');const v=Math.max(1,Math.min(+$(id).max||1,+$(id).value||1));$(first?'low':'high').value=v;if(+$('low').value>+$('high').value)$(first?'high':'low').value=v;hideCard(true);render()});
['value-high','value-low','max-value','min-value'].forEach(id=>$(id).oninput=()=>{const upper=id==='value-high'||id==='max-value';$(upper?'max-value':'min-value').value=(+$(id).value).toFixed(1);$(upper?'value-high':'value-low').value=$(id).value;hideCard(true);render()});
function resetZoom(){$('low').value=1;$('high').value=countHigh();$('min-value').value='0.0';$('max-value').value='100.0';$('value-low').value=0;$('value-high').value=100}
$('reset').onclick=()=>{resetZoom();hl=null;hideCard(true);render()};
/* value above waivers */
function syncVaw(){const on=$('vaw-on').checked,sel=$('rank');let opt=sel.querySelector('option[value=vaw]');
 if(on&&!opt){opt=document.createElement('option');opt.value='vaw';opt.textContent='Value above waivers';sel.appendChild(opt)}
 if(!on&&opt){if(sel.value==='vaw')sel.value='ddf';opt.remove()}
 const ch=$('vaw-chart');ch.disabled=!on;if(!on)ch.checked=false;$('vaw-legend').hidden=!(on&&ch.checked);
 $('vaw-note').textContent=on?'Shown as a column, in the player card and in Rank by. The average of the four trade charts’ values above waivers at your league settings, as DDF Value by default averages their adjusted values. Your overrides change DDF Value, not this.':'Off. Turn it on to add a Value above waivers column and a Rank by option.';
 hideCard(true);render()}
$('vaw-on').addEventListener('change',syncVaw);$('vaw-chart').addEventListener('change',syncVaw);
/* Esc closes an open (i) first, leaving Customize open */
window.addEventListener('keydown',e=>{if(e.key!=='Escape')return;const i=document.querySelector('.values-more .vinfo[open]');if(!i)return;e.stopPropagation();i.open=false;i.querySelector('summary').focus()},true);
/* risers and fallers */
function li(p){const up=p.chg>=0;return `<li><span class="vr-name">${p.n}<small>${p.pos}</small></span><span class="vr-was" title="DDF Value last week and now">${p.was.toFixed(1)} → ${p.now.toFixed(1)}</span><span class="vr-delta ${up?'up':'down'}"><span class="vr-arr" aria-hidden="true">${up?'▲':'▼'}</span> ${up?'+':'−'}<span data-countup="${Math.abs(p.chg).toFixed(1)}" data-decimals="1">${Math.abs(p.chg).toFixed(1)}</span><span class="sr" style="position:absolute;left:-9999px">${up?' up':' down'}</span></span><button type="button" data-n="${p.n}" aria-label="Inspect ${p.n} on the chart">Inspect</button></li>`}
/* Risers and fallers: the engine prices last week's saved inputs at your current settings (getPriorWeek('ddf_value'));
   the change is this week's pipeline DDF Value minus that, per player (v2/movers.js rule: same series, |change| >= 0.05). */
function renderRisers(){const movers=D.filter(p=>num(p.chg)&&Math.abs(p.chg)>=0.05),up=movers.filter(p=>p.chg>0).sort((a,b)=>b.chg-a.chg),down=movers.filter(p=>p.chg<0).sort((a,b)=>a.chg-b.chg);
 const none=t=>`<li class="vr-none">${t}</li>`,why=priorState==='loading'?'Loading last week’s values…':prior&&prior.reason?'No change to show: '+prior.reason+'.':'No change to show this week.';
 const wk=prior&&prior.available&&prior.priorWeek?` (week ${prior.priorWeek} to week ${prior.currentWeek||prior.priorWeek+1})`:'';$('risers-wk').textContent=wk;
 $('risers').innerHTML=up.length?up.slice(0,5).map(li).join(''):none(why);$('fallers').innerHTML=down.length?down.slice(0,5).map(li).join(''):none(why)}
document.querySelector('.values-risers').addEventListener('click',e=>{const b=e.target.closest('button[data-n]');if(!b)return;
 hl=b.dataset.n;$('search').value='';$('position').value='All positions';resetZoom();hideCard(true);render();
 const i=shown.findIndex(o=>o.p.n===hl),el=hitEl(i);chart.scrollIntoView({block:'center',behavior:'smooth'});
 setTimeout(()=>{const j=shown.findIndex(o=>o.p.n===hl);if(j>=0){pinned=null;showCard(j,hitEl(j),true);focusIdx=j}},450)});
document.addEventListener('click',e=>{const b=e.target.closest('.vp-act');if(!b)return;const g=window.DDFValues&&window.DDFValues.go;if(g)g(b.dataset.act==='bs'?'buy-sell':'overrides',{player:b.dataset.n})});
/* AI chat module (same logic as index.html) */
$('copy-prompt').addEventListener('click',function(){var phone=window.matchMedia('(pointer: coarse)').matches||window.matchMedia('(max-width: 768px)').matches;var src=document.getElementById(phone?'prompt-text-short':'prompt-text').textContent;window.DDF.copyText(src,document.getElementById('copy-status'),'Prompt copied.')});
syncVaw();

window.DDFValues={D,render,fs:{open:fsOpenNow,close:fsClose,isOpen:()=>fsOpen},applyOverrides,hideCard:()=>hideCard(true),setYours:set=>{yours=new Set([...set].map(String));D.forEach(p=>p.star=yours.has(p.key));render()}};
/* R7-CX-03: Sources & methodology names the reader's value basis (Values > Overrides) when it is not the default; read
   the way the Overrides tab reads it (engine basisInfo). No computation. */
function basisNoteText(){const b=E()&&E().basisInfo?E().basisInfo():null;
 if(!b||b.isDefault)return'';
 if(b.fellBackToDefault)return' None of the sources in your current basis is available this week, so the DDF Value shown uses the default.';
 const names={cbs:'CBS Sports',usatoday:'USA Today',fantasypros:'FantasyPros',fantasycalc:'FantasyCalc'};(b.sourceStates||[]).forEach(s=>{if(!names[s.key])names[s.key]=s.label});const nm=k=>names[k]||k;
 if(b.mode==='single')return' Your current basis is '+nm(b.source)+' only, so the DDF Value shown is '+nm(b.source)+'’s adjusted value at your league settings.';
 const pc=b.percents||{},keys=Object.keys(pc).filter(k=>pc[k]>0).sort((x,y)=>pc[y]-pc[x]);
 return' Your current basis is a blend ('+keys.map(k=>pc[k]+'% '+nm(k)).join(' + ')+'), so the DDF Value shown is that weighted average of their adjusted values at your league settings.'}
function syncBasisNote(){const t=basisNoteText();document.querySelectorAll('.basis-now').forEach(el=>{el.textContent=t})}
/* start: wait for the engine, then render; re-read after every rebuild (settings, basis, overrides) */
const V0=window.DDFValues;
V0.ready=(E()?E().ready:Promise.reject(new Error('no engine'))).then(()=>{
 const lg=E().league();if(lg&&lg.mine){const t=lg.teams.find(t=>t.id===lg.mine);if(t)yours=new Set(t.keys)}
 load();syncChips();resetZoom();render();renderRisers();syncBasisNote();document.body.classList.add('values-live');
 E().on(()=>{load();syncChips();render();renderRisers();syncBasisNote();document.dispatchEvent(new CustomEvent('ddf:values-change'))});
 const pw=()=>{priorState='loading';E().priorWeek().then(r=>{prior=r;priorState='ok'},()=>{prior=null;priorState='failed'}).then(()=>{load();renderRisers();render()})};
 pw();E().on(()=>{clearTimeout(V0._pw);V0._pw=setTimeout(pw,250)});
 return V0;
});
V0.ready.catch(()=>{$('chart-summary').textContent='';$('values-error').hidden=false;$('count').textContent=''});
})();
