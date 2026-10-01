const D='../data/dashboard.json';
const TAXA_INDEX_URL='../data/taxa/index.json';
const IUCN_URL='../data/status/iucn.json';
const COUNTRY_URL='../data/countries.json';
const SEQUENCING_COUNTRY_URL='../data/sequencing_countries.json';
const GENOMETRICS_URL='../data/genometrics.json';
const WORLD_URL='https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';
const el=id=>document.getElementById(id);
const fmt=n=>new Intl.NumberFormat('en-US').format(n||0);
const fmt1=n=>Number(n||0).toFixed(1);
let DATA, range='week', TAXA_INDEX=null, TAXA_LOADING=null, IUCN_DATA=null, IUCN_LOADING=null, statusMode='threatened', COUNTRY_DATA=null, COUNTRY_LOADING=null, SEQ_COUNTRY_DATA=null, SEQ_COUNTRY_LOADING=null, GENOMETRICS_DATA=null, GENOMETRICS_LOADING=null, WORLD_DATA=null, selectedCountry=null, countryFacet='origin';

const COLORS={Animals:'#2e6ea6',Plants:'#5aa17a',Fungi:'#d59a38',Other:'#8b75b3'};
const IUCN_COLORS={'Vulnerable':'#5aa17a','Endangered':'#d59a38','Critically endangered':'#8b75b3','Extinct in the wild':'#d59a38','Extinct':'#111815'};
const GENOMETRIC_COLORS={
  'Associated':'#2e6ea6',
  'Not associated':'#d8dfdb',
  'Plastid associated':'#5aa17a',
  'No plastid associated':'#d8dfdb',
  'XY labelled':'#2e6ea6',
  'ZW labelled':'#8b75b3',
  'Other / partial label':'#d59a38',
  'No X/Y/Z/W label':'#d8dfdb',
  'No sex-chromosome label':'#d8dfdb',
  'Expected label(s) found':'#2e6ea6',
  'Partial / different label':'#d59a38'
};
const METHOD_TREND_COLORS=[
  '#2e6ea6','#5aa17a','#d59a38','#8b75b3','#b85c5c',
  '#3f8f9d','#8a6f4d','#657786','#9a5f87','#4d7a52'
];
const RANGE={week:{label:'Past week',rate:'Deposits per business day'},year:{label:'Past year',rate:'Deposits per business day'},all:{label:'All time',rate:'Deposits per year'}};

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
  el('countries-view').hidden=view!=='countries';
  el('genometrics-view').hidden=view!=='genometrics';
  if(view==='taxa'){
    el('range-label').textContent='Taxa explorer';
    loadTaxaIndex();
  }else if(view==='status'){
    el('range-label').textContent='IUCN · '+(statusMode==='threatened'?'Threatened':'Extinct');
    loadIucn();
  }else if(view==='countries'){
    el('range-label').textContent='By country';
    loadCountries();
  }else if(view==='genometrics'){
    el('range-label').textContent='Genometrics';
    loadGenometrics();
  }else if(DATA){
    el('range-label').textContent=RANGE[range].label;
  }
}));

document.querySelectorAll('.status-tab[data-status]').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.status-tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  statusMode=b.dataset.status;
  el('range-label').textContent='IUCN · '+(statusMode==='threatened'?'Threatened':'Extinct');
  renderStatus();
}));

document.querySelectorAll('.country-facet-tab').forEach(b=>b.addEventListener('click',async()=>{
  document.querySelectorAll('.country-facet-tab').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  countryFacet=b.dataset.countryFacet;
  selectedCountry=null;
  el('country-search').value='';
  el('country-content').hidden=true;
  el('country-empty').hidden=false;
  updateCountryFacetText();
  if(countryFacet==='sequencing') await loadSequencingCountries();
  renderCountryMap();
  renderCountryMatches('');
  updateCountryCoverageText();
}));

el('country-search').addEventListener('input',e=>renderCountryMatches(e.target.value));
el('country-search').addEventListener('keydown',e=>{
  if(e.key==='Enter'){
    const firstResult=el('country-results').querySelector('button[data-iso3]');
    if(firstResult){e.preventDefault();firstResult.click();}
  }
});

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
  const last30=DATA.daily.slice(-30);
  const currentPace=businessDayPace(last30);
  el('top-rate').textContent=fmt1(currentPace);
  el('primary-label').textContent=RANGE[range].label;
  el('assemblies-count').textContent=fmt(s.assemblies);
  el('species-count').textContent=fmt(s.species);
  el('first-count').textContent=fmt(s.first_time_species);
  renderYearlyBars('hero-yearly-chart',DATA.yearly||[]);
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

function assemblyUrl(accession){
  const acc=String(accession||'').trim();
  return acc ? 'https://www.ncbi.nlm.nih.gov/datasets/genome/'+encodeURIComponent(acc)+'/' : '';
}

function assemblySpeciesLink(x){
  const name=esc(x?.organism_name||'');
  const url=assemblyUrl(x?.accession);
  return url
    ? `<a class="assembly-link" href="${url}" target="_blank" rel="noopener" title="Open ${esc(x.accession)} at NCBI">${name}</a>`
    : name;
}

function prettyDate(ds){
  if(!ds)return '—';
  const d=new Date(ds+'T12:00:00');
  return Number.isNaN(d.getTime())?ds:d.toLocaleDateString([], {year:'numeric',month:'short',day:'numeric'});
}

function isBusinessDate(ds){
  const d=new Date(String(ds||'')+'T12:00:00');
  if(Number.isNaN(d.getTime()))return false;
  const day=d.getDay();
  return day>=1&&day<=5;
}

function businessDayRows(rows){
  return (rows||[]).filter(x=>isBusinessDate(x.date));
}

function recentBusinessDays(rows,n){
  return businessDayRows(rows).slice(-n);
}

function businessDayPace(rows){
  const xs=rows||[];
  const businessDays=businessDayRows(xs).length;
  const assemblies=xs.reduce((a,b)=>a+Number(b.assemblies||0),0);
  return businessDays?assemblies/businessDays:0;
}

function paceChange(current,previous){
  if(!previous)return current?'New activity':'—';
  const pct=100*(current-previous)/previous;
  return (pct>0?'+':'')+fmt1(pct)+'%';
}

function renderYearlyBars(svgId,rows){
  const svg=el(svgId);
  rows=(rows||[]).slice(-5);
  if(!svg||!rows.length){if(svg)svg.innerHTML='';return;}
  const vals=rows.map(x=>Number(x.assemblies||0));
  const max=Math.max(1,...vals);
  const w=860,h=170,L=8,R=8,T=8,B=26,iw=w-L-R,ih=h-T-B;
  const gap=Math.max(1.5,Math.min(5,iw/rows.length*.18));
  const bw=Math.max(2,(iw-gap*(rows.length-1))/rows.length);
  let html='';
  rows.forEach((r,i)=>{
    const v=Number(r.assemblies||0);
    const bh=ih*v/max;
    const x=L+i*(bw+gap);
    const y=T+ih-bh;
    html+=`<rect class="hero-year-bar" data-year="${esc(r.year)}" data-count="${v}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${bw.toFixed(2)}" height="${Math.max(1,bh).toFixed(2)}" rx="1"></rect>`;
  });
  const tickCount=Math.min(6,rows.length);
  const tickIdx=[...new Set([...Array(tickCount).keys()].map(i=>Math.round(i*(rows.length-1)/Math.max(1,tickCount-1))))];
  tickIdx.forEach(i=>{
    const x=L+i*(bw+gap)+bw/2;
    const lab=String(rows[i].year);
    html+=`<text class="hero-year-tick" x="${x.toFixed(2)}" y="${h-7}" text-anchor="middle">${esc(lab)}</text>`;
  });
  svg.innerHTML=html;
  const tip=el('chart-tooltip');
  svg.querySelectorAll('.hero-year-bar').forEach(bar=>{
    const show=ev=>{
      tip.innerHTML=`<strong>${esc(bar.dataset.year)}</strong><span>${fmt(Number(bar.dataset.count||0))} assemblies</span>`;
      tip.hidden=false;
      bar.classList.add('is-hovered');
      positionTooltip(ev,tip);
    };
    const hide=()=>{tip.hidden=true;bar.classList.remove('is-hovered');};
    bar.onpointerenter=show;
    bar.onpointermove=show;
    bar.onpointerleave=hide;
  });
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
    <h3>${assemblySpeciesLink(x)}</h3>
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
  rows.slice(0,18).map(x=>`<div class="row"><span class="muted">${esc(x.release_date||'')}</span><span class="species">${assemblySpeciesLink(x)}</span><span class="muted">${esc(x.common_name||'—')}</span><span class="muted">${esc(x.assembly_name||'')}</span><span>${esc(x.assembly_level||'')}</span><span class="muted">${esc(x.accession||'')}</span></div>`).join('');
}

function renderRate(){
  let rows,labels;
  if(range==='week'){
    rows=recentBusinessDays(DATA.daily,10);
    labels=rows.map(x=>new Date(x.date+'T12:00:00').toLocaleDateString([], {weekday:'short',month:'numeric',day:'numeric'}));
  }
  else if(range==='year'){
    rows=businessDayRows(DATA.daily.slice(-365));
    labels=rows.map(x=>x.date);
  }
  else{rows=(DATA.yearly||[]).map(x=>({date:String(x.year),assemblies:x.assemblies}));labels=rows.map(x=>x.date);}
  el('rate-title').textContent=range==='week'?'Deposits per business day · last 10 business days':RANGE[range].rate;
  drawLineChart('rate-chart',rows,'assemblies',labels,range);
}

function renderCumulative(){
  let a=0,f=0;
  const rows=(DATA.yearly||[]).map(x=>({year:String(x.year),assemblies:(a+=Number(x.assemblies||0)),first:(f+=Number(x.first_time_species||0))}));
  drawDualChart('cumulative-chart',rows);
}

async function loadGenometrics(){
  if(GENOMETRICS_DATA){renderGenometrics();return;}
  if(GENOMETRICS_LOADING)return GENOMETRICS_LOADING;
  el('genometrics-loading').hidden=false;
  el('genometrics-loading').textContent='Loading genometrics…';
  el('genometrics-content').hidden=true;
  GENOMETRICS_LOADING=fetch(GENOMETRICS_URL)
    .then(r=>{if(!r.ok)throw Error(r.status);return r.json();})
    .then(d=>{GENOMETRICS_DATA=d;renderGenometrics();})
    .catch(err=>{
      console.error(err);
      el('genometrics-loading').textContent='Genometrics are unavailable until the next completed metadata refresh.';
    })
    .finally(()=>{GENOMETRICS_LOADING=null;});
  return GENOMETRICS_LOADING;
}

function drawGenometricDonut(svgId,legendId,rows,centerMain,centerSub,periodLabel){
  const svg=el(svgId),legend=el(legendId);
  const total=rows.reduce((a,b)=>a+Number(b.count||0),0);
  const r=86,c=2*Math.PI*r;
  let offset=0;
  let html=`<circle class="donut-bg" cx="120" cy="120" r="${r}"></circle>`;
  rows.forEach(x=>{
    const count=Number(x.count||0),frac=total?count/total:0,dash=frac*c;
    html+=`<circle class="donut-seg" data-group="${esc(x.group)}" data-count="${count}" data-total="${total}" data-period="${esc(periodLabel)}" cx="120" cy="120" r="${r}" stroke="${GENOMETRIC_COLORS[x.group]||COLORS.Other}" stroke-dasharray="${dash} ${c-dash}" stroke-dashoffset="${-offset}"></circle>`;
    offset+=dash;
  });
  html+=`<text class="donut-center-main genometrics-center-main" x="120" y="116">${esc(centerMain)}</text><text class="donut-center-sub" x="120" y="137">${esc(centerSub)}</text>`;
  svg.innerHTML=html;
  legend.innerHTML=rows.map(x=>{
    const count=Number(x.count||0),pct=total?100*count/total:0;
    return `<div class="donut-row"><i class="dot" style="background:${GENOMETRIC_COLORS[x.group]||COLORS.Other}"></i><span>${esc(x.group)}</span><span class="n">${fmt(count)}</span><span class="pct">${fmt1(pct)}%</span></div>`;
  }).join('');
  attachDonutHover(svg);
}

function renderSexExpectedObserved(comp){
  const holder=el('genometrics-sex-comparison');
  const denominator=el('genometrics-sex-comparison-denominator');
  const groups=(comp?.groups||[]).filter(x=>Number(x.assemblies||0)>0);
  if(!groups.length){
    holder.hidden=true;
    denominator.textContent='Expected-vs-observed comparison unavailable until the next completed genometrics refresh.';
    return;
  }

  holder.hidden=false;
  const statuses=['Expected label(s) found','Partial / different label','No sex-chromosome label'];
  holder.innerHTML=groups.map(row=>{
    const total=Number(row.assemblies||0);
    const by=Object.fromEntries((row.observed||[]).map(x=>[x.group,Number(x.count||0)]));
    const segs=statuses.map(status=>{
      const n=by[status]||0,pct=total?100*n/total:0;
      return n?`<span class="sex-compare-seg" style="width:${pct}%;background:${GENOMETRIC_COLORS[status]||COLORS.Other}" title="${esc(status)}: ${fmt(n)} (${fmt1(pct)}%)"></span>`:'';
    }).join('');
    const expected=by['Expected label(s) found']||0;
    const expectedPct=total?100*expected/total:0;
    return `<div class="sex-compare-row">
      <div class="sex-compare-rowhead"><strong>${esc(row.expected)}</strong><span>${fmt(total)} assemblies · ${fmt1(expectedPct)}% expected labels found</span></div>
      <div class="sex-compare-track" aria-label="${esc(row.expected)}: ${fmt1(expectedPct)} percent carry expected labels">${segs}</div>
    </div>`;
  }).join('')+
  `<div class="sex-compare-legend">${statuses.map(status=>`<span><i style="background:${GENOMETRIC_COLORS[status]||COLORS.Other}"></i>${esc(status)}</span>`).join('')}</div>`;

  denominator.textContent=
    fmt(comp.matched_assemblies)+' tracked genome deposits from '+fmt(comp.matched_species)+
    ' species matched an unambiguous Tree of Sex karyotype (snapshot '+esc(comp.source_snapshot||'')+').';
}

function drawGenometricHistogram(svgId,rows,periodLabel){
  const svg=el(svgId);
  rows=rows||[];
  if(!svg||!rows.length){if(svg)svg.innerHTML='';return;}
  const w=520,h=210,L=8,R=8,T=12,B=48,iw=w-L-R,ih=h-T-B;
  const max=Math.max(1,...rows.map(x=>Number(x.count||0)));
  const gap=Math.max(2,Math.min(6,iw/rows.length*.16));
  const bw=(iw-gap*(rows.length-1))/rows.length;
  let html='';
  rows.forEach((r,i)=>{
    const v=Number(r.count||0),bh=ih*v/max,x=L+i*(bw+gap),y=T+ih-bh;
    html+=`<rect class="genometrics-hist-bar" data-label="${esc(r.label)}" data-count="${v}" data-period="${esc(periodLabel)}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${bw.toFixed(2)}" height="${Math.max(1,bh).toFixed(2)}" rx="2"></rect>`;
    html+=`<text class="genometrics-hist-tick" x="${(x+bw/2).toFixed(2)}" y="${h-12}" text-anchor="end" transform="rotate(-38 ${(x+bw/2).toFixed(2)} ${h-12})">${esc(r.label)}</text>`;
  });
  svg.innerHTML=html;
  const tip=el('chart-tooltip');
  svg.querySelectorAll('.genometrics-hist-bar').forEach(bar=>{
    const show=ev=>{
      tip.innerHTML=`<strong>${esc(bar.dataset.label)}</strong><span>${fmt(Number(bar.dataset.count||0))} assemblies</span><span>${esc(bar.dataset.period)}</span>`;
      tip.hidden=false;bar.classList.add('is-hovered');positionTooltip(ev,tip);
    };
    const hide=()=>{tip.hidden=true;bar.classList.remove('is-hovered');};
    bar.onpointerenter=show;bar.onpointermove=show;bar.onpointerleave=hide;
  });
}


function drawGenometricTrend(svgId,legendId,trend,seriesKey,reportedKey,periodLabel){
  const svg=el(svgId),legend=el(legendId);
  if(!svg||!legend)return;
  const rows=(trend?.years||[]).filter(x=>Number(x?.[reportedKey]||0)>0);
  const series=(trend?.[seriesKey]||[]).slice(0,10);
  if(!rows.length||!series.length){
    svg.innerHTML='<text class="genometrics-trend-empty" x="450" y="165" text-anchor="middle">Trend data unavailable until the next completed genometrics refresh.</text>';
    legend.innerHTML='';
    return;
  }

  const w=900,h=330,L=58,R=18,T=18,B=52,iw=w-L-R,ih=h-T-B;
  const years=rows.map(x=>Number(x.year));
  const xmin=Math.min(...years),xmax=Math.max(...years);
  const x=yr=>L+(xmax===xmin?iw/2:(yr-xmin)/(xmax-xmin)*iw);
  const y=p=>T+ih-(Math.max(0,Math.min(100,p))/100)*ih;
  let html='';

  [0,25,50,75,100].forEach(p=>{
    const yy=y(p);
    html+='<line class="genometrics-trend-grid" x1="'+L+'" x2="'+(w-R)+'" y1="'+yy+'" y2="'+yy+'"></line>';
    html+='<text class="genometrics-trend-axis-label" x="'+(L-10)+'" y="'+(yy+4)+'" text-anchor="end">'+p+'%</text>';
  });
  html+='<line class="genometrics-trend-axis" x1="'+L+'" x2="'+(w-R)+'" y1="'+(T+ih)+'" y2="'+(T+ih)+'"></line>';

  let tickYears=years.filter((yr,i)=>i===0||i===years.length-1||yr%5===0);
  if(tickYears.length>8){
    tickYears=tickYears.filter((yr,i)=>i===0||i===tickYears.length-1||yr%10===0);
  }
  [...new Set(tickYears)].forEach(yr=>{
    const xx=x(yr);
    html+='<line class="genometrics-trend-tick" x1="'+xx+'" x2="'+xx+'" y1="'+(T+ih)+'" y2="'+(T+ih+5)+'"></line>';
    html+='<text class="genometrics-trend-axis-label" x="'+xx+'" y="'+(h-19)+'" text-anchor="middle">'+yr+'</text>';
  });

  const valueField=seriesKey==='technology_series'?'technology':'assemblers';
  series.forEach((name,si)=>{
    const color=METHOD_TREND_COLORS[si%METHOD_TREND_COLORS.length];
    const pts=rows.map(row=>{
      const denom=Number(row[reportedKey]||0);
      const count=Number((row[valueField]||{})[name]||0);
      return {year:Number(row.year),count,denom,pct:denom?100*count/denom:0};
    });
    const path=pts.map((p,i)=>(i?'L ':'M ')+x(p.year).toFixed(2)+' '+y(p.pct).toFixed(2)).join(' ');
    html+='<path class="genometrics-trend-line" d="'+path+'" style="stroke:'+color+'"></path>';
    pts.forEach(p=>{
      html+='<circle class="genometrics-trend-point" data-series="'+esc(name)+'" data-year="'+p.year+'" data-count="'+p.count+'" data-denom="'+p.denom+'" data-pct="'+p.pct.toFixed(3)+'" data-period="'+esc(periodLabel)+'" cx="'+x(p.year).toFixed(2)+'" cy="'+y(p.pct).toFixed(2)+'" r="3.2" style="fill:'+color+'"></circle>';
    });
  });
  svg.innerHTML=html;

  const latest=rows[rows.length-1];
  const latestMap=latest[valueField]||{};
  const latestDenom=Number(latest[reportedKey]||0);
  legend.innerHTML=series.map((name,si)=>{
    const color=METHOD_TREND_COLORS[si%METHOD_TREND_COLORS.length];
    const count=Number(latestMap[name]||0);
    const pct=latestDenom?100*count/latestDenom:0;
    return '<span><i style="background:'+color+'"></i><b>'+esc(name)+'</b><em>'+fmt1(pct)+'% in '+latest.year+'</em></span>';
  }).join('');

  const tip=el('chart-tooltip');
  svg.querySelectorAll('.genometrics-trend-point').forEach(dot=>{
    const show=ev=>{
      tip.innerHTML='<strong>'+esc(dot.dataset.series)+' · '+esc(dot.dataset.year)+'</strong><span>'+fmt1(Number(dot.dataset.pct||0))+'% of assemblies with '+esc(dot.dataset.period)+' metadata</span><span>'+fmt(Number(dot.dataset.count||0))+' of '+fmt(Number(dot.dataset.denom||0))+' metadata-bearing assemblies</span>';
      tip.hidden=false;
      dot.classList.add('is-hovered');
      positionTooltip(ev,tip);
    };
    const hide=()=>{tip.hidden=true;dot.classList.remove('is-hovered');};
    dot.onpointerenter=show;dot.onpointermove=show;dot.onpointerleave=hide;
  });
}

function renderGenometrics(){
  if(!GENOMETRICS_DATA)return;
  const d=GENOMETRICS_DATA;
  const mito=d.mitochondrial_association||{};
  const plastid=d.plastid_association||{};
  const sex=d.sex_chromosome_labels||{};
  el('genometrics-loading').hidden=true;
  el('genometrics-content').hidden=false;
  el('genometrics-updated').textContent='Updated '+new Date(d.generated_at).toLocaleString([], {dateStyle:'medium',timeStyle:'short'});

  const mitoRows=[
    {group:'Associated',count:Number(mito.associated||0)},
    {group:'Not associated',count:Number(mito.not_associated||0)}
  ];
  drawGenometricDonut(
    'genometrics-mito-donut','genometrics-mito-legend',mitoRows,
    fmt1(mito.percentage||0)+'%','associated','Mitochondrial association'
  );
  el('genometrics-mito-denominator').textContent=
    fmt(mito.associated)+' of '+fmt(mito.denominator)+' tracked genome deposits have an associated mitochondrial genome.';

  const plastidRows=[
    {group:'Plastid associated',count:Number(plastid.associated||0)},
    {group:'No plastid associated',count:Number(plastid.not_associated||0)}
  ];
  drawGenometricDonut(
    'genometrics-plastid-donut','genometrics-plastid-legend',plastidRows,
    fmt1(plastid.percentage||0)+'%','associated','Plastid association'
  );
  el('genometrics-plastid-denominator').textContent=
    fmt(plastid.associated)+' of '+fmt(plastid.denominator)+' Viridiplantae genome deposits have an associated plastid/chloroplast genome.';

  const sexRows=(sex.categories||[]).map(x=>({group:x.group,count:Number(x.count||0)}));
  const sexTotal=Number(sex.denominator||sexRows.reduce((a,b)=>a+b.count,0));
  const noLabel=sexRows.find(x=>x.group==='No sex-chromosome label')?.count
    ?? sexRows.find(x=>x.group==='No X/Y/Z/W label')?.count
    ?? 0;
  const anyPct=sexTotal?100*(sexTotal-noLabel)/sexTotal:0;
  drawGenometricDonut(
    'genometrics-sex-donut','genometrics-sex-legend',sexRows,
    fmt1(anyPct)+'%','any label','Sex-chromosome labelling'
  );
  el('genometrics-sex-denominator').textContent=
    fmt(sexTotal-noLabel)+' of '+fmt(sexTotal)+' tracked genome deposits contain an explicit sex-chromosome-style label.';

  renderSexExpectedObserved(d.sex_chromosome_expected_vs_observed||null);

  const kar=d.karyotype_audit||{};
  const karRows=(kar.categories||[]).map(x=>({group:x.group,count:Number(x.count||0)}));
  const karTotal=karRows.reduce((sum,x)=>sum+x.count,0);
  drawGenometricDonut(
    'genometrics-karyotype-donut','genometrics-karyotype-legend',karRows,
    fmt(kar.matched_species||0),'species','Karyotype agreement'
  );
  el('genometrics-karyotype-denominator').textContent=
    fmt(kar.matched_assemblies||0)+' assemblies from '+fmt(kar.matched_species||0)+' species had both an NCBI chromosome count and Tree of Sex karyotype count.';

  const q=d.assembly_quality||{};
  const mb=v=>v==null?'—':fmt1(Number(v)/1e6)+' Mb';
  el('genometrics-quality-stats').innerHTML=
    `<div><strong>${mb(q.median_assembly_size_bp)}</strong><span>median assembly size</span></div>
     <div><strong>${mb(q.median_contig_n50_bp)}</strong><span>median contig N50</span></div>
     <div><strong>${q.median_chromosomes_reported==null?'—':fmt1(q.median_chromosomes_reported)}</strong><span>median chromosomes reported</span></div>`;
  drawGenometricHistogram('genometrics-size-hist',q.assembly_size_histogram||[],'Genome size');
  drawGenometricHistogram('genometrics-chrom-hist',q.chromosome_count_histogram||[],'Reported chromosome count');
  el('genometrics-quality-denominator').textContent=
    fmt(q.assembly_size_available||0)+' assemblies contribute genome size; '+fmt(q.chromosome_count_available||0)+' have an NCBI-reported chromosome count.';

  const methods=d.methods_through_time||{};
  drawGenometricTrend(
    'genometrics-tech-trend','genometrics-tech-legend',methods,
    'technology_series','tech_reported','sequencing-technology'
  );
  drawGenometricTrend(
    'genometrics-assembler-trend','genometrics-assembler-legend',methods,
    'assembler_series','assembler_reported','assembly-method'
  );
  const tracked=Number(q.assemblies||0);
  const techN=Number(methods.technology_metadata_assemblies||0);
  const asmN=Number(methods.assembler_metadata_assemblies||0);
  el('genometrics-tech-denominator').textContent=
    fmt(techN)+' of '+fmt(tracked)+' tracked assemblies report sequencing-technology metadata'+
    (tracked?' ('+fmt1(100*techN/tracked)+'%). ':'; ')+
    'Lines are yearly percentages among metadata-bearing assemblies and can overlap for hybrid sequencing strategies.';
  el('genometrics-assembler-denominator').textContent=
    fmt(asmN)+' of '+fmt(tracked)+' tracked assemblies report a specific assembly method'+
    (tracked?' ('+fmt1(100*asmN/tracked)+'%). ':'; ')+
    'Software versions and spelling variants are normalized into named assembler families; an assembly can mention more than one family.';

  const traits=kar.tree_of_sex_traits||{};
  const traitRows=(title,rows)=>`<div class="trait-block"><strong>${esc(title)}</strong>${(rows||[]).slice(0,5).map(x=>`<span><b>${esc(x.group)}</b> ${fmt(x.count)}</span>`).join('')}</div>`;
  el('genometrics-traits').innerHTML=
    traitRows('Ploidy',(traits.top_ploidy||[]))+traitRows('Sexual system',(traits.top_sexual_system||[]));
  el('genometrics-traits-denominator').textContent=
    'Reference coverage among tracked species: '+fmt(traits.ploidy_species||0)+' with ploidy and '+fmt(traits.sexual_system_species||0)+' with sexual-system records in the Tree of Sex snapshot.';
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
  const last60=dailyWindow(s.recent_daily,60,IUCN_DATA.generated_at);
  const last30=last60.slice(-30);
  const currentPace=businessDayPace(last30);
  el('status-loading').hidden=true;
  el('status-content').hidden=false;
  el('status-primary-label').textContent=label+' · all time';
  el('status-assemblies').textContent=fmt(s.summary.assemblies);
  el('status-species').textContent=fmt(s.summary.species);
  el('status-first').textContent=fmt(s.summary.first_time_species);
  el('status-pipeline').textContent=fmt(s.annotations?.in_progress?.length||0);
  el('status-completed').textContent=fmt(s.annotations?.recent_completed?.length||0);
  el('status-rate').textContent=fmt1(currentPace);
  el('status-hero-count').textContent=fmt(s.summary.assemblies);
  el('status-hero-species').textContent=fmt(s.summary.species);
  el('status-hero-first').textContent=fmt(s.summary.first_time_species);
  el('status-hero-title').textContent=label+' species genome deposits';
  renderYearlyBars('status-hero-yearly-chart',s.yearly||[]);

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
      <h3>${assemblySpeciesLink(x)}</h3>
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
    recent.slice(0,18).map(x=>`<div class="row"><span class="muted">${esc(x.release_date||'')}</span><span class="species">${assemblySpeciesLink(x)}</span><span class="muted">${esc(x.iucn_status||'—')}</span><span class="muted">${esc(x.assembly_name||'')}</span><span>${esc(x.assembly_level||'')}</span><span class="muted">${esc(x.accession||'')}</span></div>`).join('');

  const source=IUCN_DATA.source||{};
  el('status-source-note').textContent=(source.scope||'IUCN Red List categories')+' · '+(source.matching||'species-name matching');
}

function activeCountryData(){
  return countryFacet==='sequencing' ? SEQ_COUNTRY_DATA : COUNTRY_DATA;
}

function countryMapIsAllTime(){
  return countryFacet==='alltime';
}

function updateCountryFacetText(){
  const sequencing=countryFacet==='sequencing';
  const alltime=countryMapIsAllTime();
  el('country-facet-description').textContent=sequencing
    ? 'Institute country uses a resolved SRA sequencing center when available; otherwise it falls back to the NCBI assembly submitter. Common unambiguous center aliases are curated, with other organization names resolved through ROR. Colour shows the trailing 30-day business-day pace. Assemblies can count in more than one country when resolved SRA centers span countries.'
    : alltime
      ? 'Country is inferred from the NCBI BioSample geographic-location field. Colour shows the total number of chromosome/complete genome deposits assigned to each country across the full record.'
      : 'Country is inferred from the NCBI BioSample geographic-location field. Colour shows the mean chromosome/complete genome deposits per business day over the trailing 30 days.';
  el('country-search-description').textContent=sequencing
    ? 'Search a country, or click it on the map, to see the cumulative history of institute-associated genome assemblies linked to that country.'
    : alltime
      ? 'Search a country, or click it on the map, to explore its all-time genome-deposition history.'
      : 'Search a country, or click it on the map, to reproduce the cumulative All-time view for that country.';
  el('country-all-label').textContent=sequencing?'All-time institute-linked assemblies':'All-time assemblies';
  el('country-assembly-legend').textContent=sequencing?'Institute-associated assemblies':'Assemblies';
  el('country-species-legend').textContent=sequencing?'First-time species linked to institute country':'First-time species in country';
}

function updateCountryCoverageText(){
  const data=activeCountryData();
  if(!data)return;
  const c=data.coverage||{};
  if(countryFacet==='sequencing'){
    const resolved=Number(c.assemblies_with_resolved_institute_country||c.assemblies_with_resolved_center_country||0);
    const total=Number(c.assemblies_scanned||0);
    const pct=total?100*resolved/total:0;
    const viaSra=Number(c.assemblies_resolved_by_sra_center||c.assemblies_with_resolved_center_country||0);
    const viaSubmitter=Number(c.assemblies_resolved_by_submitter_fallback||0);
    const centers=Number(c.distinct_centers_resolved_to_country||0);
    const totalCenters=Number(c.distinct_sra_centers||0);
    el('country-map-status').textContent=
      fmt(resolved)+' of '+fmt(total)+' assemblies linked to an institute country ('+
      fmt1(pct)+'%). '+fmt(viaSra)+' use resolved SRA sequencing centers; '+
      fmt(viaSubmitter)+' use the assembly-submitter fallback. '+
      fmt(centers)+' of '+fmt(totalCenters)+' distinct SRA center names resolve via ROR or curated aliases.'+
      (Number(c.assemblies_with_multiple_center_countries||0)
        ? ' '+fmt(c.assemblies_with_multiple_center_countries)+' assemblies link to centers in multiple countries.'
        : '');
  }else{
    const pct=100*Number(c.fraction_assigned||0);
    el('country-map-status').textContent=
      fmt(c.assemblies_assigned_to_country)+' of '+
      fmt(c.assemblies_scanned)+' assemblies assigned to a country ('+
      fmt1(pct)+'%).';
  }
}

async function loadCountries(){
  updateCountryFacetText();
  if(COUNTRY_DATA && WORLD_DATA){
    if(countryFacet==='sequencing'&&!SEQ_COUNTRY_DATA) await loadSequencingCountries();
    renderCountryMap();
    renderCountryMatches(el('country-search').value);
    if(selectedCountry) renderCountryDetail(selectedCountry);
    updateCountryCoverageText();
    return;
  }
  if(COUNTRY_LOADING)return COUNTRY_LOADING;
  el('country-map-status').textContent='Loading country data and map…';
  COUNTRY_LOADING=Promise.all([
    fetch(COUNTRY_URL).then(r=>{if(!r.ok)throw Error(r.status);return r.json();}),
    (window.d3 && window.topojson)
      ? d3.json(WORLD_URL)
      : Promise.reject(new Error('Map libraries unavailable'))
  ])
    .then(async([countries,world])=>{
      COUNTRY_DATA=countries;
      WORLD_DATA=world;
      if(countryFacet==='sequencing') await loadSequencingCountries();
      renderCountryMap();
      renderCountryMatches(el('country-search').value);
      updateCountryCoverageText();
    })
    .catch(err=>{
      console.error(err);
      el('country-map-status').textContent='Country data or map unavailable.';
    })
    .finally(()=>{COUNTRY_LOADING=null;});
  return COUNTRY_LOADING;
}

async function loadSequencingCountries(){
  if(SEQ_COUNTRY_DATA)return SEQ_COUNTRY_DATA;
  if(SEQ_COUNTRY_LOADING)return SEQ_COUNTRY_LOADING;
  el('country-map-status').textContent='Loading sequencing-center country data…';
  SEQ_COUNTRY_LOADING=fetch(SEQUENCING_COUNTRY_URL)
    .then(r=>{if(!r.ok)throw Error(r.status);return r.json();})
    .then(d=>{SEQ_COUNTRY_DATA=d;return d;})
    .catch(err=>{
      console.error(err);
      el('country-map-status').textContent='Sequencing-center country data are unavailable until the next data refresh.';
      throw err;
    })
    .finally(()=>{SEQ_COUNTRY_LOADING=null;});
  return SEQ_COUNTRY_LOADING;
}

function countryByNumeric(id){
  const data=activeCountryData();
  const key=String(id??'').padStart(3,'0');
  return data?.countries?.find(x=>String(x.iso_n3).padStart(3,'0')===key)||null;
}

function countryRateValue(c){
  return Number(c?.genomes_per_business_day??c?.genomes_per_day??0);
}

function countryRateLabel(v){
  const n=Number(v||0);
  return n<1?n.toFixed(2):n.toFixed(1);
}

function renderCountryMap(){
  const data=activeCountryData();
  if(!data||!WORLD_DATA||!window.d3||!window.topojson)return;
  const svg=d3.select('#country-map');
  svg.selectAll('*').remove();
  const width=1100,height=570;
  const geo=topojson.feature(WORLD_DATA,WORLD_DATA.objects.countries);
  const projection=d3.geoNaturalEarth1().fitExtent([[8,8],[width-8,height-8]],geo);
  const path=d3.geoPath(projection);
  const alltime=countryMapIsAllTime();
  const valueOf=x=>alltime?Number(x.assemblies||0):countryRateValue(x);
  const maxValue=Math.max(0,...data.countries.map(valueOf));
  const scale=d3.scaleSequentialSqrt([0,Math.max(maxValue,alltime?1:0.01)],d3.interpolateBlues);
  const tip=el('chart-tooltip');

  svg.append('path')
    .datum({type:'Sphere'})
    .attr('class','map-ocean')
    .attr('d',path);

  svg.append('g')
    .selectAll('path')
    .data(geo.features)
    .join('path')
    .attr('class','country-shape')
    .attr('d',path)
    .attr('fill',d=>{
      const c=countryByNumeric(d.id);
      return c?scale(valueOf(c)):'#e3e6ea';
    })
    .attr('data-country-id',d=>String(d.id??''))
    .on('pointerenter pointermove',function(ev,d){
      const c=countryByNumeric(d.id);
      d3.select(this).classed('is-hovered',true);
      const name=c?.name||d.properties?.name||'Country';
      if(c){
        const primary=alltime
          ? `<span>${fmt(c.assemblies)} assemblies · all time</span>`
          : `<span>${countryRateLabel(countryRateValue(c))} genomes per business day</span><span>${fmt(c.window_assemblies)} assemblies · past 30 days</span>`;
        const base=`<strong>${esc(name)}</strong>${primary}${alltime?'':`<span>${fmt(c.assemblies)} assemblies · all time</span>`}<span>${fmt(c.species)} species represented</span>`;
        const institutes=countryFacet==='sequencing' && (c.top_institutes?.length||c.top_centers?.length)
          ? '<span>Top institutes: '+(c.top_institutes||c.top_centers).slice(0,3).map(x=>esc(x.name)).join(' · ')+'</span>'
          : '';
        tip.innerHTML=base+institutes;
      }else{
        tip.innerHTML=`<strong>${esc(name)}</strong><span>No ${countryFacet==='sequencing'?'resolved institute-country':'country-assigned'} genome records</span>`;
      }
      tip.hidden=false;positionTooltip(ev,tip);
    })
    .on('pointerleave',function(){
      d3.select(this).classed('is-hovered',false);
      tip.hidden=true;
    })
    .on('click',function(ev,d){
      const c=countryByNumeric(d.id);
      if(c)selectCountry(c);
    });

  el('country-map').setAttribute('aria-label',alltime
    ? 'World map of all-time genome deposits by sample-origin country'
    : 'World map of genomes deposited per business day by country');
  el('country-map-legend').innerHTML=
    '<span>'+(alltime?'Total genome deposits · all time':'Genomes per business day · trailing 30-day pace')+'</span>'+
    '<div class="map-gradient"></div>'+
    '<div class="map-legend-ticks"><span>0</span><span>'+(alltime?fmt(maxValue):countryRateLabel(maxValue))+'</span></div>';
}

function renderCountryMatches(raw){
  const data=activeCountryData();
  if(!data?.countries?.length)return;
  const q=String(raw||'').trim().toLowerCase();
  let rows=data.countries.slice();
  if(q){
    rows=rows.filter(x=>
      x.name.toLowerCase().includes(q)||
      x.iso2.toLowerCase()===q||
      x.iso3.toLowerCase()===q
    );
    rows.sort((a,b)=>{
      const an=a.name.toLowerCase(),bn=b.name.toLowerCase();
      const ae=an===q?0:an.startsWith(q)?1:2;
      const be=bn===q?0:bn.startsWith(q)?1:2;
      return ae-be||(countryMapIsAllTime()
        ? Number(b.assemblies||0)-Number(a.assemblies||0)
        : countryRateValue(b)-countryRateValue(a))||an.localeCompare(bn);
    });
  }else{
    rows.sort((a,b)=>countryMapIsAllTime()
      ? Number(b.assemblies||0)-Number(a.assemblies||0)
      : countryRateValue(b)-countryRateValue(a)||Number(b.assemblies||0)-Number(a.assemblies||0));
  }
  rows=rows.slice(0,12);
  const box=el('country-results');
  const context=countryFacet==='sequencing'?'linked assemblies':'all-time assemblies';
  const heading=countryMapIsAllTime()?'Most sequenced · all time':'Most active · trailing 30 days';
  box.innerHTML=(q?'':'<div class="taxon-results-label">'+heading+'</div>')+
    rows.map(x=>`<button type="button" data-iso3="${esc(x.iso3)}" class="taxon-result"><span><strong>${esc(x.name)}</strong><small>${esc(x.iso3)} · ${fmt(x.assemblies)} ${context}</small></span><span>${countryMapIsAllTime()?fmt(x.assemblies):countryRateLabel(countryRateValue(x))+'/business day'}</span></button>`).join('');
  box.querySelectorAll('button[data-iso3]').forEach(btn=>btn.addEventListener('click',()=>{
    const meta=data.countries.find(x=>x.iso3===btn.dataset.iso3);
    if(meta)selectCountry(meta);
  }));
}

function selectCountry(meta){
  selectedCountry=meta;
  el('country-search').value=meta.name;
  el('country-results').innerHTML='';
  renderCountryDetail(meta);
  document.querySelectorAll('.country-shape').forEach(p=>p.classList.remove('is-selected'));
  const target=[...document.querySelectorAll('.country-shape')].find(p=>{
    const c=countryByNumeric(p.dataset.countryId);
    return c?.iso3===meta.iso3;
  });
  if(target)target.classList.add('is-selected');
}

function renderCountryDetail(c){
  el('country-empty').hidden=true;
  el('country-content').hidden=false;
  el('country-name').textContent=c.name;
  el('country-code').textContent=(countryFacet==='sequencing'?'Institute provenance · ':'Sample origin · ')+c.iso3;
  el('country-rate').textContent=countryRateLabel(countryRateValue(c));
  el('country-week').textContent=fmt(c.window_assemblies);
  el('country-assemblies').textContent=fmt(c.assemblies);
  el('country-species').textContent=fmt(c.species);

  let a=0,f=0;
  const rows=(c.yearly||[]).map(x=>({
    year:String(x.year),
    assemblies:(a+=Number(x.assemblies||0)),
    first:(f+=Number(x.first_time_species||0))
  }));
  drawDualChart('country-cumulative-chart',rows);
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
  const recentBusiness=businessDayRows(recent);
  drawLineChart('taxon-recent-chart',recentBusiness,'assemblies',recentBusiness.map(x=>x.date),'year');
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
