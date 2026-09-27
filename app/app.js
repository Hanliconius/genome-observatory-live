const D='../data/dashboard.json';
const TAXA_INDEX_URL='../data/taxa/index.json';
const IUCN_URL='../data/status/iucn.json';
const el=id=>document.getElementById(id);
const fmt=n=>new Intl.NumberFormat('en-US').format(n||0);
const fmt1=n=>Number(n||0).toFixed(1);
let DATA, range='week', TAXA_INDEX=null, TAXA_LOADING=null, IUCN_DATA=null, IUCN_LOADING=null, statusMode='threatened';

const COLORS={Animals:'#2e6ea6',Plants:'#5aa17a',Fungi:'#d59a38',Other:'#8b75b3'};
const IUCN_COLORS={'Vulnerable':'#5aa17a','Endangered':'#d59a38','Critically endangered':'#8b75b3','Extinct in the wild':'#d59a38','Extinct':'#111815'};
const RANGE={week:{label:'Past week',rate:'Deposits per day'},year:{label:'Past year',rate:'Deposits per day'},all:{label:'All time',rate:'Deposits per year'}};

fetch(D).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{DATA=d;render()}).catch(err=>{console.error(err);el('updated').textContent='data unavailable'});

document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); range=b.dataset.range; render();
}));

document.querySelectorAll('.section-tab').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.section-tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  const view=b.dataset.view;
  el('overview-view').hidden=view!=='overview';
  el('taxa-view').hidden=view!=='taxa';
  el('status-view').hidden=view!=='status';
  if(view==='taxa'){
    el('range-label').textContent='Taxa explorer';
    loadTaxaIndex();
  }else if(view==='status'){
    el('range-label').textContent='IUCN · '+(statusMode==='threatened'?'Threatened':'Extinct');
    loadIucn();
  }else if(DATA){
    el('range-label').textContent=RANGE[range].label;
  }
}));

document.querySelectorAll('.status-tab').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.status-tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  statusMode=b.dataset.status;
  el('range-label').textContent='IUCN · '+(statusMode==='threatened'?'Threatened':'Extinct');
  renderStatus();
}));

el('taxon-search').addEventListener('input',e=>renderTaxonMatches(e.target.value));
el('taxon-search').addEventListener('keydown',e=>{
  if(e.key==='Enter'){
    const firstResult=el('taxon-results').querySelector('button[data-taxid]');
    if(firstResult){e.preventDefault();firstResult.click();}
  }
});

function render(){
  const s=DATA.summary[range];
  el('updated').textContent=new Date(DATA.generated_at).toLocaleString([], {dateStyle:'medium',timeStyle:'short'});
  if(!el('overview-view').hidden) el('range-label').textContent=RANGE[range].label;
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

function prettyDate(ds){
  if(!ds)return '—';
  const d=new Date(ds+'T12:00:00');
  return Number.isNaN(d.getTime())?ds:d.toLocaleDateString([], {year:'numeric',month:'short',day:'numeric'});
}

function renderMiniBars(rows,targetId='daily-bars'){
  const m=Math.max(1,...rows.map(x=>x.assemblies||0));
  el(targetId).innerHTML=rows.map(x=>`<i title="${esc(x.date)}: ${x.assemblies}" style="height:${Math.max(4,100*(x.assemblies||0)/m)}%"></i>`).join('');
}

function renderNewest(){
  const x=DATA.featured_assembly || DATA.recent_assemblies?.find(x=>x.image?.thumb_url) || DATA.recent_assemblies?.[0];
  if(!x){el('newest-card').innerHTML='<div class="image-placeholder">No recent assembly metadata available</div>';return;}
  const image=x.image?.thumb_url
    ? `<img class="taxon-image" src="${x.image.thumb_url}" alt="${esc(x.organism_name)}" loading="lazy">`
    : '<div class="image-placeholder">No Wikimedia image found for species, genus, or family</div>';
  const taxon=[x.family,x.genus].filter(Boolean).join(' · ');
  const details=[
    x.common_name ? esc(x.common_name) : null,
    x.chromosome_count ? fmt(x.chromosome_count)+' chromosomes' : null,
    x.total_sequence_length ? fmt1(x.total_sequence_length/1e6)+' Mb genome' : null
  ].filter(Boolean).join(' · ');
  el('newest-card').innerHTML=`${image}<div>
    <h3>${esc(x.organism_name)}</h3>
    ${details?`<p class="featured-details">${details}</p>`:''}
    <p>${esc(x.assembly_level||'Assembly')} · ${esc(x.accession||'')}</p>
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

function drawDonut(svgId,legendId,rows,unit,periodLabel,palette=COLORS){
  const svg=el(svgId), legend=el(legendId);
  const total=rows.reduce((a,b)=>a+b.count,0);
  const r=86,c=2*Math.PI*r;
  let offset=0;
  let html=`<circle class="donut-bg" cx="120" cy="120" r="${r}"></circle>`;
  rows.forEach(x=>{
    const frac=total?x.count/total:0;
    const dash=frac*c;
    html+=`<circle class="donut-seg" data-group="${esc(x.group)}" data-count="${x.count}" data-total="${total}" data-period="${esc(periodLabel)}" cx="120" cy="120" r="${r}" stroke="${palette[x.group]||COLORS.Other}" stroke-dasharray="${dash} ${c-dash}" stroke-dashoffset="${-offset}"></circle>`;
    offset+=dash;
  });
  html+=`<text class="donut-center-main" x="120" y="116">${fmt(total)}</text><text class="donut-center-sub" x="120" y="137">${unit}</text>`;
  svg.innerHTML=html;
  legend.innerHTML=rows.map(x=>`<div class="donut-row"><i class="dot" style="background:${palette[x.group]||COLORS.Other}"></i><span>${x.group}</span><span class="n">${fmt(x.count)}</span><span class="pct">${total?fmt1(100*x.count/total):'0.0'}%</span></div>`).join('');
  attachDonutHover(svg);
}

function attachDonutHover(svg){
  const tip=el('chart-tooltip');
  if(!tip)return;
  svg.querySelectorAll('.donut-seg').forEach(seg=>{
    const show=ev=>{
      const count=Number(seg.dataset.count||0),total=Number(seg.dataset.total||0),pct=total?100*count/total:0;
      tip.innerHTML=`<strong>${esc(seg.dataset.group)}</strong><span>${fmt(count)} assemblies</span><span>${fmt1(pct)}% · ${esc(seg.dataset.period)}</span>`;
      tip.hidden=false;seg.classList.add('is-hovered');positionTooltip(ev,tip);
    };
    const hide=()=>{tip.hidden=true;seg.classList.remove('is-hovered');};
    seg.onpointerenter=show;seg.onpointermove=show;seg.onpointerleave=hide;
  });
}

function renderPipeline(){
  el('pipeline-list').innerHTML=(DATA.annotations.in_progress||[]).slice(0,7).map(x=>`<div class="list-row"><strong><em>${esc(x.species)}</em></strong><span>${esc(x.status||'')}</span></div>`).join('')||'<p class="note">No annotation runs listed.</p>';
  el('recent-annotation-list').innerHTML=(DATA.annotations.recent_completed||[]).slice(0,7).map(x=>`<div class="list-row"><strong><em>${esc(x.species)}</em></strong><span>${esc(x.release_date||'')}</span></div>`).join('')||'<p class="note">No recent annotations listed.</p>';
}

function renderGroups(){
  const rows=normalizedGroups(DATA.groups_week),total=rows.reduce((a,b)=>a+b.count,0)||1;
  el('group-table').innerHTML=rows.map(x=>`<div class="table-row"><strong>${x.group}</strong><span>${fmt(x.count)}</span><span>${fmt1(100*x.count/total)}%</span></div>`).join('');
}

function renderMilestones(){
  const rows=DATA.milestones||[],target=el('milestone-table');
  if(!target)return;
  target.innerHTML=rows.length
    ? rows.map(x=>`<div class="table-row milestone-row"><strong>${fmt(x.threshold)}</strong><span class="milestone-date">${prettyDate(x.date)}</span><span></span></div>`).join('')
    : '<p class="note">No milestones recorded yet.</p>';
}

function renderRecent(){
  const rows=DATA.recent_assemblies||[];
  el('recent-list').innerHTML=`<div class="header"><span>Date</span><span>Species</span><span>Common name</span><span>Assembly</span><span>Level</span><span>Accession</span></div>`+
  rows.slice(0,18).map(x=>`<div class="row"><span class="muted">${esc(x.release_date||'')}</span><span class="species">${esc(x.organism_name||'')}</span><span class="muted">${esc(x.common_name||'—')}</span><span class="muted">${esc(x.assembly_name||'')}</span><span>${esc(x.assembly_level||'')}</span><span class="muted">${esc(x.accession||'')}</span></div>`).join('');
}

function renderRate(){
  let rows,labels;
  if(range==='week'){rows=DATA.daily.slice(-7);labels=rows.map(x=>new Date(x.date+'T12:00:00').toLocaleDateString([], {weekday:'short'}));}
  else if(range==='year'){rows=DATA.daily.slice(-365);labels=rows.map(x=>x.date);}
  else{rows=(DATA.yearly||[]).map(x=>({date:String(x.year),assemblies:x.assemblies}));labels=rows.map(x=>x.date);}
  el('rate-title').textContent=RANGE[range].rate;
  drawLineChart('rate-chart',rows,'assemblies',labels,range);
}

function renderCumulative(){
  let a=0,f=0;
  const rows=(DATA.yearly||[]).map(x=>({year:String(x.year),assemblies:(a+=Number(x.assemblies||0)),first:(f+=Number(x.first_time_species||0))}));
  drawDualChart('cumulative-chart',rows);
}

async function loadIucn(){
  if(IUCN_DATA){renderStatus();return;}
  if(IUCN_LOADING)return IUCN_LOADING;
  el('status-loading').textContent='Loading IUCN genome history…';
  el('status-loading').hidden=false;
  el('status-content').hidden=true;
  IUCN_LOADING=fetch(IUCN_URL)
    .then(r=>{if(!r.ok)throw Error(r.status);return r.json();})
    .then(d=>{IUCN_DATA=d;renderStatus();})
    .catch(err=>{
      console.error(err);
      el('status-loading').textContent='IUCN-derived genome history is unavailable until the next data refresh.';
    })
    .finally(()=>{IUCN_LOADING=null;});
  return IUCN_LOADING;
}

function dailyWindow(rows,days,generatedAt){
  const sparse=new Map((rows||[]).map(x=>[x.date,Number(x.assemblies||0)]));
  const anchor=generatedAt?new Date(generatedAt):new Date();
  const end=new Date(Date.UTC(anchor.getUTCFullYear(),anchor.getUTCMonth(),anchor.getUTCDate()));
  const out=[];
  for(let i=days-1;i>=0;i--){
    const d=new Date(end);d.setUTCDate(end.getUTCDate()-i);
    const ds=d.toISOString().slice(0,10);
    out.push({date:ds,assemblies:sparse.get(ds)||0});
  }
  return out;
}

function renderStatus(){
  if(!IUCN_DATA)return;
  const s=IUCN_DATA[statusMode];
  if(!s)return;
  const label=statusMode==='threatened'?'Threatened':'Extinct';
  const last7=dailyWindow(s.recent_daily,7,IUCN_DATA.generated_at);
  el('status-loading').hidden=true;
  el('status-content').hidden=false;
  el('status-primary-label').textContent=label+' · all time';
  el('status-assemblies').textContent=fmt(s.summary.assemblies);
  el('status-species').textContent=fmt(s.summary.species);
  el('status-first').textContent=fmt(s.summary.first_time_species);
  el('status-pipeline').textContent=fmt(s.annotations?.in_progress?.length||0);
  el('status-completed').textContent=fmt(s.annotations?.recent_completed?.length||0);
  el('status-rate').textContent=fmt1(last7.reduce((a,b)=>a+(b.assemblies||0),0)/7);
  el('status-hero-count').textContent=fmt(s.summary.assemblies);
  el('status-hero-species').textContent=fmt(s.summary.species);
  el('status-hero-first').textContent=fmt(s.summary.first_time_species);
  el('status-hero-title').textContent=label+' species genome deposits';
  renderMiniBars(last7,'status-daily-bars');

  const x=(s.recent_assemblies||[]).find(x=>x.image?.thumb_url)||(s.recent_assemblies||[])[0];
  if(!x){
    el('status-newest-card').innerHTML='<div class="image-placeholder">No recent matching assembly metadata available</div>';
  }else{
    const image=x.image?.thumb_url
      ? `<img class="taxon-image" src="${x.image.thumb_url}" alt="${esc(x.organism_name)}" loading="lazy">`
      : '<div class="image-placeholder">No cached Wikimedia image available</div>';
    const details=[
      x.common_name?esc(x.common_name):null,
      x.chromosome_count?fmt(x.chromosome_count)+' chromosomes':null,
      x.total_sequence_length?fmt1(x.total_sequence_length/1e6)+' Mb genome':null
    ].filter(Boolean).join(' · ');
    el('status-newest-card').innerHTML=`${image}<div>
      <h3>${esc(x.organism_name)}</h3>
      ${details?`<p class="featured-details">${details}</p>`:''}
      <p>${esc(x.iucn_status||label)} · ${esc(x.assembly_level||'Assembly')} · ${esc(x.accession||'')}</p>
      <p>Released ${esc(x.release_date||'')}</p>
      ${x.image?.credit?`<p class="credit">Image credit: ${x.image.credit}</p>`:''}
    </div>`;
  }

  drawDonut('status-donut-iucn','status-donut-iucn-legend',s.iucn_breakdown||[],'assemblies','IUCN status',IUCN_COLORS);
  drawDonut('status-donut-groups','status-donut-groups-legend',normalizedGroups(s.groups_all),'assemblies','All time',COLORS);

  const yearly=(s.yearly||[]).map(x=>({date:String(x.year),assemblies:Number(x.assemblies||0)}));
  drawLineChart('status-rate-chart',yearly,'assemblies',yearly.map(x=>x.date),'all');

  let a=0,f=0;
  const cumulative=(s.yearly||[]).map(x=>({
    year:String(x.year),
    assemblies:(a+=Number(x.assemblies||0)),
    first:(f+=Number(x.first_time_species||0))
  }));
  drawDualChart('status-cumulative-chart',cumulative);

  el('status-pipeline-list').innerHTML=(s.annotations?.in_progress||[]).slice(0,7).map(x=>`<div class="list-row"><strong><em>${esc(x.species)}</em></strong><span>${esc(x.status||'')}</span></div>`).join('')||'<p class="note">No matching annotation runs listed.</p>';
  el('status-recent-annotation-list').innerHTML=(s.annotations?.recent_completed||[]).slice(0,7).map(x=>`<div class="list-row"><strong><em>${esc(x.species)}</em></strong><span>${esc(x.release_date||'')}</span></div>`).join('')||'<p class="note">No matching recent annotations listed.</p>';

  const groups=normalizedGroups(s.groups_all),gtotal=groups.reduce((a,b)=>a+b.count,0)||1;
  el('status-group-table').innerHTML=groups.map(x=>`<div class="table-row"><strong>${x.group}</strong><span>${fmt(x.count)}</span><span>${fmt1(100*x.count/gtotal)}%</span></div>`).join('');

  const milestones=s.milestones||[];
  el('status-milestone-table').innerHTML=milestones.length
    ? milestones.map(x=>`<div class="table-row milestone-row"><strong>${fmt(x.threshold)}</strong><span class="milestone-date">${prettyDate(x.date)}</span><span></span></div>`).join('')
    : '<p class="note">No assembly-count milestones crossed yet.</p>';

  const recent=s.recent_assemblies||[];
  el('status-recent-list').innerHTML=`<div class="header"><span>Date</span><span>Species</span><span>IUCN status</span><span>Assembly</span><span>Level</span><span>Accession</span></div>`+
    recent.slice(0,18).map(x=>`<div class="row"><span class="muted">${esc(x.release_date||'')}</span><span class="species">${esc(x.organism_name||'')}</span><span class="muted">${esc(x.iucn_status||'—')}</span><span class="muted">${esc(x.assembly_name||'')}</span><span>${esc(x.assembly_level||'')}</span><span class="muted">${esc(x.accession||'')}</span></div>`).join('');

  const source=IUCN_DATA.source||{};
  el('status-source-note').textContent=(source.scope||'IUCN Red List categories')+' · '+(source.matching||'species-name matching');
}

async function loadTaxaIndex(){
  if(TAXA_INDEX){renderTaxonMatches(el('taxon-search').value);return;}
  if(TAXA_LOADING)return TAXA_LOADING;
  el('taxon-results').innerHTML='<div class="taxon-loading">Loading phylum/order index…</div>';
  TAXA_LOADING=fetch(TAXA_INDEX_URL)
    .then(r=>{if(!r.ok)throw Error(r.status);return r.json();})
    .then(d=>{
      TAXA_INDEX=d;
      if(!d.taxa?.length){
        el('taxon-results').innerHTML='<div class="taxon-loading">Taxonomy index is being built. Try again after the next data refresh.</div>';
        return;
      }
      renderTaxonMatches(el('taxon-search').value);
    })
    .catch(err=>{
      console.error(err);
      el('taxon-results').innerHTML='<div class="taxon-loading">Taxonomy index unavailable.</div>';
    })
    .finally(()=>{TAXA_LOADING=null;});
  return TAXA_LOADING;
}

function renderTaxonMatches(raw){
  if(!TAXA_INDEX?.taxa?.length)return;
  const q=String(raw||'').trim().toLowerCase();
  let rows=TAXA_INDEX.taxa;
  if(q){
    rows=rows.filter(x=>x.name.toLowerCase().includes(q));
    rows.sort((a,b)=>{
      const ae=a.name.toLowerCase()===q?0:a.name.toLowerCase().startsWith(q)?1:2;
      const be=b.name.toLowerCase()===q?0:b.name.toLowerCase().startsWith(q)?1:2;
      return ae-be || Number(b.assemblies||0)-Number(a.assemblies||0) || a.name.localeCompare(b.name);
    });
  }else{
    rows=rows.filter(x=>x.rank==='order').sort((a,b)=>Number(b.assemblies||0)-Number(a.assemblies||0));
  }
  rows=rows.slice(0,12);
  const box=el('taxon-results');
  box.innerHTML=(q?'':'<div class="taxon-results-label">Most sequenced orders</div>')+
    rows.map(x=>{
      const context=[x.class,x.phylum].filter(Boolean).join(' · ');
      return `<button type="button" data-taxid="${x.taxid}" class="taxon-result"><span><strong>${esc(x.name)}</strong><small>${esc(x.rank)}${context?' · '+esc(context):''}</small></span><span>${fmt(x.assemblies)}</span></button>`;
    }).join('');
  box.querySelectorAll('button[data-taxid]').forEach(btn=>btn.addEventListener('click',()=>{
    const meta=TAXA_INDEX.taxa.find(x=>String(x.taxid)===btn.dataset.taxid);
    if(meta)selectTaxon(meta);
  }));
}

async function selectTaxon(meta){
  el('taxon-search').value=meta.name;
  el('taxon-results').innerHTML='';
  el('taxon-empty').innerHTML='<p>Loading '+esc(meta.name)+'…</p>';
  el('taxon-empty').hidden=false;
  el('taxon-content').hidden=true;
  try{
    const r=await fetch(`../data/taxa/${meta.taxid}.json`);
    if(!r.ok)throw Error(r.status);
    const t=await r.json();
    renderTaxon(t);
  }catch(err){
    console.error(err);
    el('taxon-empty').innerHTML='<p>Taxon history unavailable for '+esc(meta.name)+'.</p>';
  }
}

function renderTaxon(t){
  el('taxon-empty').hidden=true;
  el('taxon-content').hidden=false;
  el('taxon-rank').textContent=t.rank;
  el('taxon-name').textContent=t.name;
  const lineage=[];
  if(t.phylum?.name && t.phylum.name!==t.name)lineage.push(t.phylum.name);
  if(t.class?.name && t.class.name!==t.name)lineage.push(t.class.name);
  if(t.rank==='order')lineage.push(t.name);
  el('taxon-lineage').textContent=lineage.join(' → ');

  el('taxon-assemblies').textContent=fmt(t.stats?.assemblies);
  el('taxon-species').textContent=fmt(t.stats?.species);
  el('taxon-first').textContent=prettyDate(t.stats?.first_deposit);
  el('taxon-year-assemblies').textContent=fmt(t.stats?.past_year_assemblies);
  el('taxon-year-species').textContent=fmt(t.stats?.past_year_species);

  let ca=0,cf=0;
  const cumulative=(t.yearly||[]).map(x=>({
    year:String(x.year),
    assemblies:(ca+=Number(x.assemblies||0)),
    first:(cf+=Number(x.first_time_species||0))
  }));
  drawDualChart('taxon-cumulative-chart',cumulative);

  const sparse=new Map((t.recent_daily||[]).map(x=>[x.date,Number(x.assemblies||0)]));
  const anchor=TAXA_INDEX?.generated_at?new Date(TAXA_INDEX.generated_at):new Date();
  const end=new Date(Date.UTC(anchor.getUTCFullYear(),anchor.getUTCMonth(),anchor.getUTCDate()));
  const recent=[];
  for(let i=364;i>=0;i--){
    const d=new Date(end);d.setUTCDate(end.getUTCDate()-i);
    const ds=d.toISOString().slice(0,10);
    recent.push({date:ds,assemblies:sparse.get(ds)||0});
  }
  drawLineChart('taxon-recent-chart',recent,'assemblies',recent.map(x=>x.date),'year');
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
  const d=new Date(label+'T12:00:00');
  return Number.isNaN(d.getTime())?label:d.toLocaleDateString([], {month:'short',day:'numeric'});
}

function drawLineChart(id,rows,key,labels,mode){
  const svg=el(id);if(!svg||!rows.length){if(svg)svg.innerHTML='';return;}
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
  const svg=el(id);if(!svg||!rows.length){if(svg)svg.innerHTML='';return;}
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
  const tip=el('chart-tooltip');if(!tip||!rows.length)return;
  const {L,R,T,B,w,h,max}=geom,guide=svg.querySelector('.hover-guide'),dots=[...svg.querySelectorAll('.hover-dot')];

  const move=ev=>{
    const rect=svg.getBoundingClientRect(),px=(ev.clientX-rect.left)/rect.width*w,innerW=w-L-R;
    const frac=Math.max(0,Math.min(1,(px-L)/innerW)),i=Math.round(frac*(rows.length-1));
    const x=L+innerW*(rows.length===1?.5:i/(rows.length-1));
    guide.setAttribute('x1',x);guide.setAttribute('x2',x);guide.setAttribute('visibility','visible');

    const values=keys.map((key,j)=>{
      const v=Number(rows[i][key]||0),y=T+(h-T-B)*(1-v/(max||1));
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
    tip.hidden=false;positionTooltip(ev,tip);
  };

  const leave=()=>{guide.setAttribute('visibility','hidden');dots.forEach(d=>d.setAttribute('visibility','hidden'));tip.hidden=true;};
  svg.onpointermove=move;svg.onpointerleave=leave;
}

function positionTooltip(ev,tip){
  const pad=14;
  let left=ev.clientX+16,top=ev.clientY+16;
  const tw=tip.offsetWidth,th=tip.offsetHeight;
  if(left+tw+pad>window.innerWidth)left=ev.clientX-tw-16;
  if(top+th+pad>window.innerHeight)top=ev.clientY-th-16;
  tip.style.left=left+'px';tip.style.top=top+'px';
}
