const D='../data/dashboard.json';
const el=id=>document.getElementById(id);
const fmt=n=>new Intl.NumberFormat('en-US').format(n||0);
const fmt1=n=>Number(n||0).toFixed(1);
let DATA, range='week';

const COLORS={Animals:'#2e6ea6',Plants:'#5aa17a',Fungi:'#d59a38',Other:'#8b75b3'};
const RANGE={week:{label:'Past week',rate:'Deposits per day'},year:{label:'Past year',rate:'Deposits per day'},all:{label:'All time',rate:'Deposits per year'}};

fetch(D).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{DATA=d;render()}).catch(err=>{console.error(err);el('updated').textContent='data unavailable'});

document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); range=b.dataset.range; render();
}));

function render(){
  const s=DATA.summary[range];
  el('updated').textContent=new Date(DATA.generated_at).toLocaleString([], {dateStyle:'medium',timeStyle:'short'});
  el('range-label').textContent=RANGE[range].label;
  el('top-assemblies').textContent=fmt(s.assemblies);
  el('top-species').textContent=fmt(s.species);
  el('top-first').textContent=fmt(s.first_time_species);
  el('top-pipeline').textContent=fmt(DATA.annotations.in_progress.length);
  el('top-completed').textContent=fmt(DATA.annotations.recent_completed.length);
  const last7=DATA.daily.slice(-7);
  el('top-rate').textContent=fmt1(last7.reduce((a,b)=>a+(b.assemblies||0),0)/Math.max(1,last7.length));
  el('primary-label').textContent=RANGE[range].label;
  el('assemblies-count').textContent=fmt(s.assemblies);
  el('species-count').textContent=fmt(s.species);
  el('first-count').textContent=fmt(s.first_time_species);

  renderMiniBars(last7);
  renderNewest();
  renderDonuts();
  renderPipeline();
  renderGroups();
  renderMilestones();
  renderRecent();
  renderRate();
  renderCumulative();
}

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

function renderMiniBars(rows){
  const m=Math.max(1,...rows.map(x=>x.assemblies||0));
  el('daily-bars').innerHTML=rows.map(x=>`<i title="${esc(x.date)}: ${x.assemblies}" style="height:${Math.max(4,100*(x.assemblies||0)/m)}%"></i>`).join('');
}

function renderNewest(){
  const x=DATA.featured_assembly || DATA.recent_assemblies?.find(x=>x.image?.thumb_url) || DATA.recent_assemblies?.[0];
  if(!x){el('newest-card').innerHTML='<div class="image-placeholder">No recent assembly metadata available</div>';return;}
  const image=x.image?.thumb_url
    ? `<img class="taxon-image" src="${x.image.thumb_url}" alt="${esc(x.organism_name)}" loading="lazy">`
    : '<div class="image-placeholder">No Wikimedia image found for species, genus, or family</div>';
  const taxon=[x.family,x.genus].filter(Boolean).join(' · ');
  el('newest-card').innerHTML=`${image}<div>
    <h3>${esc(x.organism_name)}</h3>
    <p>${esc(x.assembly_level||'Assembly')} · ${esc(x.accession||'')} · ${x.total_sequence_length?fmt1(x.total_sequence_length/1e6)+' Mb':'size unavailable'}</p>
    ${taxon?`<p>${esc(taxon)}</p>`:''}
    <p>Released ${esc(x.release_date||'')}</p>
    ${x.image?.credit?`<p class="credit">Image credit: ${x.image.credit}</p>`:''}
  </div>`;
}

function normalizedGroups(rows){
  const map={Animals:0,Plants:0,Fungi:0,Other:0};
  (rows||[]).forEach(x=>{map[x.group in map?x.group:'Other']+=(x.count||0)});
  return Object.entries(map).map(([group,count])=>({group,count}));
}

function renderDonuts(){
  const useYear=range==='year';
  const currentRows=useYear ? normalizedGroups(DATA.groups_year) : normalizedGroups(DATA.groups_week);
  const currentLabel=useYear ? 'Past year' : 'Past week';
  el('donut-current-label').textContent=currentLabel;
  drawDonut('donut-week','donut-week-legend',currentRows,'assemblies',currentLabel);
  drawDonut('donut-all','donut-all-legend',normalizedGroups(DATA.groups_all),'assemblies','All time');
}

function drawDonut(svgId,legendId,rows,unit,periodLabel){
  const svg=el(svgId), legend=el(legendId);
  const total=rows.reduce((a,b)=>a+b.count,0);
  const r=86,c=2*Math.PI*r;
  let offset=0;
  let html=`<circle class="donut-bg" cx="120" cy="120" r="${r}"></circle>`;
  rows.forEach(x=>{
    const frac=total?x.count/total:0;
    const dash=frac*c;
    html+=`<circle class="donut-seg" data-group="${esc(x.group)}" data-count="${x.count}" data-total="${total}" data-period="${esc(periodLabel)}" cx="120" cy="120" r="${r}" stroke="${COLORS[x.group]}" stroke-dasharray="${dash} ${c-dash}" stroke-dashoffset="${-offset}"></circle>`;
    offset+=dash;
  });
  html+=`<text class="donut-center-main" x="120" y="116">${fmt(total)}</text><text class="donut-center-sub" x="120" y="137">${unit}</text>`;
  svg.innerHTML=html;
  legend.innerHTML=rows.map(x=>`<div class="donut-row"><i class="dot" style="background:${COLORS[x.group]}"></i><span>${x.group}</span><span class="n">${fmt(x.count)}</span><span class="pct">${total?fmt1(100*x.count/total):'0.0'}%</span></div>`).join('');
  attachDonutHover(svg);
}

function attachDonutHover(svg){
  const tip=el('chart-tooltip');
  if(!tip) return;
  svg.querySelectorAll('.donut-seg').forEach(seg=>{
    const show=(ev)=>{
      const count=Number(seg.dataset.count||0);
      const total=Number(seg.dataset.total||0);
      const pct=total?100*count/total:0;
      tip.innerHTML=`<strong>${esc(seg.dataset.group)}</strong><span>${fmt(count)} assemblies</span><span>${fmt1(pct)}% · ${esc(seg.dataset.period)}</span>`;
      tip.hidden=false;
      seg.classList.add('is-hovered');
      let left=ev.clientX+16, top=ev.clientY+16;
      const tw=tip.offsetWidth, th=tip.offsetHeight, pad=14;
      if(left+tw+pad>window.innerWidth) left=ev.clientX-tw-16;
      if(top+th+pad>window.innerHeight) top=ev.clientY-th-16;
      tip.style.left=left+'px'; tip.style.top=top+'px';
    };
    const hide=()=>{tip.hidden=true;seg.classList.remove('is-hovered');};
    seg.onpointerenter=show;
    seg.onpointermove=show;
    seg.onpointerleave=hide;
  });
}

function renderPipeline(){
  el('pipeline-list').innerHTML=(DATA.annotations.in_progress||[]).slice(0,7).map(x=>`<div class="list-row"><strong><em>${esc(x.species)}</em></strong><span>${esc(x.status||'')}</span></div>`).join('')||'<p class="note">No annotation runs listed.</p>';
  el('recent-annotation-list').innerHTML=(DATA.annotations.recent_completed||[]).slice(0,7).map(x=>`<div class="list-row"><strong><em>${esc(x.species)}</em></strong><span>${esc(x.release_date||'')}</span></div>`).join('')||'<p class="note">No recent annotations listed.</p>';
}

function renderGroups(){
  const rows=normalizedGroups(DATA.groups_week), total=rows.reduce((a,b)=>a+b.count,0)||1;
  el('group-table').innerHTML=rows.map(x=>`<div class="table-row"><strong>${x.group}</strong><span>${fmt(x.count)}</span><span>${fmt1(100*x.count/total)}%</span></div>`).join('');
}

function renderMilestones(){
  const rows=DATA.milestones||[];
  const target=el('milestone-table');
  if(!target) return;
  target.innerHTML=rows.length
    ? rows.map(x=>`<div class="table-row milestone-row"><strong>${fmt(x.threshold)}</strong><span class="milestone-date">${new Date(x.date+'T12:00:00').toLocaleDateString([], {year:'numeric',month:'short',day:'numeric'})}</span><span></span></div>`).join('')
    : '<p class="note">No milestones recorded yet.</p>';
}

function renderRecent(){
  const rows=DATA.recent_assemblies||[];
  el('recent-list').innerHTML=`<div class="header"><span>Date</span><span>Species</span><span>Common name</span><span>Assembly</span><span>Level</span><span>Accession</span></div>`+
  rows.slice(0,18).map(x=>`<div class="row"><span class="muted">${esc(x.release_date||'')}</span><span class="species">${esc(x.organism_name||'')}</span><span class="muted">${esc(x.common_name||'—')}</span><span class="muted">${esc(x.assembly_name||'')}</span><span>${esc(x.assembly_level||'')}</span><span class="muted">${esc(x.accession||'')}</span></div>`).join('');
}

function renderRate(){
  let rows, labels;
  if(range==='week'){rows=DATA.daily.slice(-7); labels=rows.map(x=>new Date(x.date+'T12:00:00').toLocaleDateString([], {weekday:'short'}));}
  else if(range==='year'){rows=DATA.daily.slice(-365); labels=rows.map(x=>x.date);}
  else {rows=(DATA.yearly||[]).map(x=>({date:String(x.year),assemblies:x.assemblies})); labels=rows.map(x=>x.date);}
  el('rate-title').textContent=RANGE[range].rate;
  drawLineChart('rate-chart',rows,'assemblies',labels,range);
}

function renderCumulative(){
  let a=0,f=0;
  const rows=(DATA.yearly||[]).map(x=>({year:String(x.year),assemblies:(a+=Number(x.assemblies||0)),first:(f+=Number(x.first_time_species||0))}));
  drawDualChart('cumulative-chart',rows);
}

function niceMax(v){
  if(v<=0)return 1;
  const p=Math.pow(10,Math.floor(Math.log10(v))),s=v/p;
  return (s<=1?1:s<=2?2:s<=5?5:10)*p;
}

function xTicks(n,mode){
  if(n<=1)return[0];
  if(mode==='week')return [...Array(n).keys()];
  const target=mode==='year'?5:6,step=Math.max(1,Math.floor((n-1)/(target-1))),out=[];
  for(let i=0;i<n;i+=step)out.push(i);
  if(out[out.length-1]!==n-1)out.push(n-1);
  return [...new Set(out)];
}

function xLabel(mode,label){
  if(mode==='week'||mode==='all')return label;
  const d=new Date(label+'T12:00:00'); return Number.isNaN(d.getTime())?label:d.toLocaleDateString([], {month:'short',day:'numeric'});
}

function drawLineChart(id,rows,key,labels,mode){
  const svg=el(id); if(!rows.length){svg.innerHTML='';return;}
  const w=860,h=320,L=60,R=18,T=12,B=42,iw=w-L-R,ih=h-T-B;
  const vals=rows.map(x=>Number(x[key]||0)),max=niceMax(Math.max(...vals));
  const pts=rows.map((x,i)=>[L+iw*(rows.length===1?.5:i/(rows.length-1)),T+ih*(1-Number(x[key]||0)/max)]);
  let html='';
  for(let i=0;i<=4;i++){const val=max*i/4,y=T+ih*(1-i/4);html+=`<line class="gridline" x1="${L}" y1="${y}" x2="${w-R}" y2="${y}"></line><text class="tick-label" x="${L-8}" y="${y+4}" text-anchor="end">${fmt(Math.round(val))}</text>`;}
  html+=`<line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${h-B}"></line><line class="axis" x1="${L}" y1="${h-B}" x2="${w-R}" y2="${h-B}"></line>`;
  xTicks(rows.length,mode).forEach(i=>{const x=L+iw*(rows.length===1?.5:i/(rows.length-1));html+=`<line class="axis" x1="${x}" y1="${h-B}" x2="${x}" y2="${h-B+5}"></line><text class="tick-label" x="${x}" y="${h-18}" text-anchor="middle">${esc(xLabel(mode,labels[i]))}</text>`;});
  const poly=pts.map(p=>p.map(v=>v.toFixed(1)).join(',')).join(' ');
  html+=`<polygon class="area-a" points="${L},${h-B} ${poly} ${w-R},${h-B}"></polygon><polyline class="series-a" points="${poly}"></polyline>`;
  html+=`<line class="hover-guide" x1="0" y1="${T}" x2="0" y2="${h-B}" visibility="hidden"></line><circle class="hover-dot hover-dot-a" cx="0" cy="0" r="4" visibility="hidden"></circle>`;
  svg.innerHTML=html;
  attachChartHover(svg,rows,[key],labels,mode,{L,R,T,B,w,h,max});
}

function drawDualChart(id,rows){
  const svg=el(id); if(!rows.length){svg.innerHTML='';return;}
  const w=860,h=320,L=60,R=18,T=12,B=42,iw=w-L-R,ih=h-T-B;
  const max=niceMax(Math.max(...rows.flatMap(x=>[Number(x.assemblies||0),Number(x.first||0)])));
  let html='';
  for(let i=0;i<=4;i++){const val=max*i/4,y=T+ih*(1-i/4);html+=`<line class="gridline" x1="${L}" y1="${y}" x2="${w-R}" y2="${y}"></line><text class="tick-label" x="${L-8}" y="${y+4}" text-anchor="end">${fmt(Math.round(val))}</text>`;}
  html+=`<line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${h-B}"></line><line class="axis" x1="${L}" y1="${h-B}" x2="${w-R}" y2="${h-B}"></line>`;
  xTicks(rows.length,'all').forEach(i=>{const x=L+iw*(rows.length===1?.5:i/(rows.length-1));html+=`<line class="axis" x1="${x}" y1="${h-B}" x2="${x}" y2="${h-B+5}"></line><text class="tick-label" x="${x}" y="${h-18}" text-anchor="middle">${esc(rows[i].year)}</text>`;});
  const make=k=>rows.map((r,i)=>[L+iw*(rows.length===1?.5:i/(rows.length-1)),T+ih*(1-Number(r[k]||0)/max)].map(v=>v.toFixed(1)).join(',')).join(' ');
  html+=`<polyline class="series-a" points="${make('assemblies')}"></polyline><polyline class="series-b" points="${make('first')}"></polyline>`;
  html+=`<line class="hover-guide" x1="0" y1="${T}" x2="0" y2="${h-B}" visibility="hidden"></line><circle class="hover-dot hover-dot-a" cx="0" cy="0" r="4" visibility="hidden"></circle><circle class="hover-dot hover-dot-b" cx="0" cy="0" r="4" visibility="hidden"></circle>`;
  svg.innerHTML=html;
  attachChartHover(svg,rows,['assemblies','first'],rows.map(x=>x.year),'all',{L,R,T,B,w,h,max});
}

function attachChartHover(svg,rows,keys,labels,mode,geom){
  const tip=el('chart-tooltip');
  if(!tip || !rows.length) return;
  const {L,R,T,B,w,h,max}=geom;
  const guide=svg.querySelector('.hover-guide');
  const dots=[...svg.querySelectorAll('.hover-dot')];

  const move=(ev)=>{
    const rect=svg.getBoundingClientRect();
    const px=(ev.clientX-rect.left)/rect.width*w;
    const innerW=w-L-R;
    const frac=Math.max(0,Math.min(1,(px-L)/innerW));
    const i=Math.round(frac*(rows.length-1));
    const x=L+innerW*(rows.length===1?.5:i/(rows.length-1));
    guide.setAttribute('x1',x); guide.setAttribute('x2',x); guide.setAttribute('visibility','visible');

    const values=keys.map((key,j)=>{
      const v=Number(rows[i][key]||0);
      const y=T+(h-T-B)*(1-v/(max||1));
      if(dots[j]){dots[j].setAttribute('cx',x);dots[j].setAttribute('cy',y);dots[j].setAttribute('visibility','visible');}
      return v;
    });

    const title=mode==='week'
      ? new Date(rows[i].date+'T12:00:00').toLocaleDateString([], {weekday:'long',month:'short',day:'numeric'})
      : mode==='year'
        ? new Date(rows[i].date+'T12:00:00').toLocaleDateString([], {month:'short',day:'numeric',year:'numeric'})
        : labels[i];

    tip.innerHTML=keys.length===1
      ? `<strong>${esc(title)}</strong><span>${fmt(values[0])} assemblies</span>`
      : `<strong>${esc(title)}</strong><span>${fmt(values[0])} cumulative assemblies</span><span>${fmt(values[1])} first-time species</span>`;
    tip.hidden=false;

    const pad=14;
    let left=ev.clientX+16, top=ev.clientY+16;
    const tw=tip.offsetWidth, th=tip.offsetHeight;
    if(left+tw+pad>window.innerWidth) left=ev.clientX-tw-16;
    if(top+th+pad>window.innerHeight) top=ev.clientY-th-16;
    tip.style.left=left+'px'; tip.style.top=top+'px';
  };

  const leave=()=>{
    guide.setAttribute('visibility','hidden');
    dots.forEach(d=>d.setAttribute('visibility','hidden'));
    tip.hidden=true;
  };

  svg.onpointermove=move;
  svg.onpointerleave=leave;
}
