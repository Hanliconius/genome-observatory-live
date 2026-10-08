const D='../data/dashboard.json';
const TAXA_INDEX_URL='../data/taxa/index.json';
const IUCN_URL='../data/status/iucn.json';
const COUNTRY_URL='../data/countries.json';
const SEQUENCING_COUNTRY_URL='../data/sequencing_countries.json';
const COUNTRY_TAXA_URL='../data/taxa/country_orders.json';
const GENOMETRICS_URL='../data/genometrics.json';
const WORLD_URL='https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';
const el=id=>document.getElementById(id);
const fmt=n=>new Intl.NumberFormat('en-US').format(n||0);
const fmt1=n=>Number(n||0).toFixed(1);
let DATA, range='week', TAXA_INDEX=null, TAXA_LOADING=null, TAXON_SELECTED={left:null,right:null}, TAXON_CACHE=new Map(), IUCN_DATA=null, IUCN_LOADING=null, statusMode='threatened', COUNTRY_DATA=null, COUNTRY_LOADING=null, COUNTRY_TAXA_DATA=null, COUNTRY_TAXA_LOADING=null, SEQ_COUNTRY_DATA=null, SEQ_COUNTRY_LOADING=null, GENOMETRICS_DATA=null, GENOMETRICS_LOADING=null, WORLD_DATA=null, WORLD_LOADING=null, selectedCountry=null, countryFacet='origin';

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
  'Partial / different label':'#d59a38',
  // Karyotype concordance: green = close, amber = moderate, red = substantial difference.
  'Within 5%':'#4b9774',
  'Within 20%':'#d59a38',
  '>20% different':'#b85c5c'
};
const METHOD_TREND_COLORS=[
  '#2e6ea6','#5aa17a','#d59a38','#8b75b3','#b85c5c',
  '#3f8f9d','#8a6f4d','#657786','#9a5f87','#4d7a52'
];
const RANGE={week:{label:'Past week',rate:'Deposits per business day'},year:{label:'Past year',rate:'Deposits per business day'},all:{label:'All time',rate:'Deposits per year'}};

fetch(D+'?refresh='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{DATA=d;render()}).catch(err=>{console.error(err);el('updated').textContent='data unavailable'});

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
  renderCountryCompanion();
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

['left','right'].forEach(side=>{
  el('taxon-search-'+side).addEventListener('input',e=>renderTaxonMatches(e.target.value,side));
  el('taxon-search-'+side).addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      const firstResult=el('taxon-results-'+side).querySelector('button[data-taxid]');
      if(firstResult){e.preventDefault();firstResult.click();}
    }
  });
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
  const last30=reportingLagRows(DATA.daily).slice(-30);
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
  renderWeatherMap();
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

// Show all available NCBI records, including the most recent dates.
const REPORTING_LAG_DAYS=0;
function reportingLagRows(rows,generatedAt=DATA?.generated_at){
  const anchor=generatedAt?new Date(generatedAt):new Date();
  const cutoff=new Date(Date.UTC(anchor.getUTCFullYear(),anchor.getUTCMonth(),anchor.getUTCDate()));
  cutoff.setUTCDate(cutoff.getUTCDate()-REPORTING_LAG_DAYS);
  const ds=cutoff.toISOString().slice(0,10);
  return (rows||[]).filter(x=>String(x.date||'')<=ds);
}
function recentBusinessDays(rows,n,generatedAt=DATA?.generated_at){
  return businessDayRows(reportingLagRows(rows,generatedAt)).slice(-n);
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
  const bySpecies=new Map();
  rows.forEach(x=>{
    const species=String(x.organism_name||'').trim()||String(x.accession||'');
    const key=species+'\u0000'+String(x.release_date||'');
    if(!bySpecies.has(key))bySpecies.set(key,[]);
    bySpecies.get(key).push(x);
  });
  const speciesRows=[...bySpecies.values()].slice(0,18);
  const accessionLinks=xs=>xs.map(x=>{
    const acc=esc(x.accession||'');
    const url=assemblyUrl(x.accession);
    return url ? `<a class="assembly-link" href="${url}" target="_blank" rel="noopener">${acc}</a>` : acc;
  }).join('<br>');
  const uniqueText=(xs,key)=>[...new Set(xs.map(x=>String(x[key]||'').trim()).filter(Boolean))].map(esc).join('<br>');
  el('recent-list').innerHTML=`<div class="header"><span>Date</span><span>Species</span><span>Common name</span><span>Assembly</span><span>Level</span><span>Accession</span></div>`+
  speciesRows.map(xs=>{
    const x=xs[0];
    const dateText=esc(x.release_date||'');
    return `<div class="row"><span class="muted">${dateText}</span><span class="species">${assemblySpeciesLink(x)}</span><span class="muted">${esc(x.common_name||'—')}</span><span class="muted">${uniqueText(xs,'assembly_name')}</span><span>${uniqueText(xs,'assembly_level')}</span><span class="muted">${accessionLinks(xs)}</span></div>`;
  }).join('');
}

function renderWeatherMap(){
  const svg=el('weather-map');
  if(!svg||!DATA)return;
  const source=reportingLagRows(DATA.daily||[]);
  const lastRecorded=el('weather-last-recorded');
  if(!source.length){svg.innerHTML='';if(lastRecorded)lastRecorded.textContent='No daily deposit data available.';return;}
  if(lastRecorded){
    const latest=source.findLast(x=>Number(x.assemblies||0)>0);
    const generated=DATA.generated_at?new Date(DATA.generated_at).toLocaleDateString([], {month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}):'unknown';
    lastRecorded.textContent='Newest recorded deposit date: '+(latest?latest.date:'none in available history')+' · Data refreshed: '+generated+' (UTC). Recent empty days may still be backfilled by NCBI.';
  }

  const end=new Date(source[source.length-1].date+'T12:00:00Z');
  const rawStart=new Date(end);
  rawStart.setUTCDate(rawStart.getUTCDate()-364);
  const displayStart=new Date(rawStart);
  displayStart.setUTCDate(displayStart.getUTCDate()-displayStart.getUTCDay());

  const byDate=new Map(source.map(x=>[String(x.date),x]));
  const nonzero=source
    .filter(x=>new Date(x.date+'T12:00:00Z')>=rawStart&&Number(x.assemblies||0)>0)
    .map(x=>Number(x.assemblies||0))
    .sort((a,b)=>a-b);
  const q=p=>nonzero.length?nonzero[Math.min(nonzero.length-1,Math.floor((nonzero.length-1)*p))]:0;
  const cuts=[q(.2),q(.4),q(.6),q(.8)];
  const level=v=>{
    if(v<=0)return 0;
    let n=1;
    cuts.forEach(c=>{if(v>c)n++;});
    return Math.min(5,n);
  };

  const msDay=86400000;
  const totalDays=Math.floor((end-displayStart)/msDay)+1;
  const weeks=Math.ceil(totalDays/7);
  const w=860,h=150,L=34,R=8,T=26,B=14;
  const cell=Math.min(14,(w-L-R)/Math.max(1,weeks));
  const box=Math.max(5,cell-2.4);
  let html='';

  ['Mon','Wed','Fri'].forEach((lab,i)=>{
    const dow=[1,3,5][i];
    html+=`<text class="weather-day-label" x="0" y="${(T+dow*cell+box*.76).toFixed(2)}">${lab}</text>`;
  });

  let lastMonth='';
  for(let d=new Date(displayStart),i=0;d<=end;d.setUTCDate(d.getUTCDate()+1),i++){
    const ds=d.toISOString().slice(0,10);
    const week=Math.floor(i/7),dow=d.getUTCDay();
    const x=L+week*cell,y=T+dow*cell;
    const row=byDate.get(ds)||{};
    const assemblies=Number(row.assemblies||0);
    const species=Number(row.species||0);
    const first=Number(row.first_time_species||0);
    const inWindow=d>=rawStart;
    if(inWindow){
      html+=`<rect class="weather-cell weather-level-${level(assemblies)}" data-date="${ds}" data-assemblies="${assemblies}" data-species="${species}" data-first="${first}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${box.toFixed(2)}" height="${box.toFixed(2)}" rx="2"></rect>`;
    }
    const month=d.toLocaleDateString('en-US',{month:'short',timeZone:'UTC'});
    if(d.getUTCDate()<=7&&month!==lastMonth&&inWindow){
      html+=`<text class="weather-month-label" x="${x.toFixed(2)}" y="13">${month}</text>`;
      lastMonth=month;
    }
  }
  svg.innerHTML=html;

  const tip=el('chart-tooltip');
  svg.querySelectorAll('.weather-cell').forEach(cellEl=>{
    const show=ev=>{
      tip.innerHTML=`<strong>${esc(prettyDate(cellEl.dataset.date))}</strong><span>${fmt(Number(cellEl.dataset.assemblies||0))} assemblies</span><span>${fmt(Number(cellEl.dataset.species||0))} species represented · ${fmt(Number(cellEl.dataset.first||0))} first-time species</span>`;
      tip.hidden=false;cellEl.classList.add('is-hovered');positionTooltip(ev,tip);
    };
    const hide=()=>{tip.hidden=true;cellEl.classList.remove('is-hovered');};
    cellEl.onpointerenter=show;cellEl.onpointermove=show;cellEl.onpointerleave=hide;
  });
}

function renderRate(){
  let rows,labels;
  if(range==='week'){
    rows=recentBusinessDays(DATA.daily,10);
    labels=rows.map(x=>new Date(x.date+'T12:00:00').toLocaleDateString([], {weekday:'short',month:'numeric',day:'numeric'}));
  }
  else if(range==='year'){
    rows=businessDayRows(reportingLagRows(DATA.daily).slice(-365));
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
  GENOMETRICS_LOADING=fetch(GENOMETRICS_URL+'?refresh='+Date.now(),{cache:'no-store'})
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


function drawTopSpecies(svgId,rows){
  const svg=el(svgId);rows=rows||[];
  if(!svg||!rows.length){if(svg)svg.innerHTML='';return;}
  const w=520,h=470,L=178,R=34,T=12,B=18,iw=w-L-R;
  const rowH=(h-T-B)/rows.length,max=Math.max(1,...rows.map(x=>Number(x.assemblies||0)));
  let html='';
  rows.forEach((r,i)=>{
    const n=Number(r.assemblies||0),y=T+i*rowH+4,bh=Math.max(8,rowH-9),bw=iw*n/max;
    html+=`<text class="genometrics-rank-label" x="${L-10}" y="${(y+bh*.72).toFixed(2)}" text-anchor="end">${esc(r.species)}</text>`;
    html+=`<rect class="genometrics-hist-bar genometrics-rank-bar" data-label="${esc(r.species)}" data-count="${n}" x="${L}" y="${y.toFixed(2)}" width="${Math.max(1,bw).toFixed(2)}" height="${bh.toFixed(2)}" rx="2"></rect>`;
    html+=`<text class="genometrics-rank-count" x="${Math.min(w-R+4,L+bw+6).toFixed(2)}" y="${(y+bh*.72).toFixed(2)}">${fmt(n)}</text>`;
  });
  svg.innerHTML=html;
  const tip=el('chart-tooltip');
  svg.querySelectorAll('.genometrics-rank-bar').forEach(bar=>{
    const show=ev=>{tip.innerHTML=`<strong><em>${esc(bar.dataset.label)}</em></strong><span>${fmt(Number(bar.dataset.count||0))} chromosome-scale / complete assemblies</span>`;tip.hidden=false;bar.classList.add('is-hovered');positionTooltip(ev,tip);};
    const hide=()=>{tip.hidden=true;bar.classList.remove('is-hovered');};
    bar.onpointerenter=show;bar.onpointermove=show;bar.onpointerleave=hide;
  });
}

function drawGenometricTrend(svgId,legendId,trend,seriesKey,reportedKey,periodLabel){
  const svg=el(svgId),legend=el(legendId);
  if(!svg||!legend)return;
  const rows=(trend?.years||[]).filter(x=>Number(x?.[reportedKey]||0)>0);
  let series=(trend?.[seriesKey]||[]).slice(0,10);
  if(seriesKey==='technology_series'){
    // Backward-safe: never render proximity-ligation as a primary sequencing technology.
    // Also collapse older PacBio subcategories into one platform-level series.
    const hadPacBio=series.some(name=>name==='PacBio'||name==='PacBio HiFi'||name==='PacBio (HiFi not specified)'||name==='PacBio (other / unspecified)');
    series=series.filter(name=>name!=='Hi-C / proximity'&&!['PacBio','PacBio HiFi','PacBio (HiFi not specified)','PacBio (other / unspecified)'].includes(name));
    if(hadPacBio)series.unshift('PacBio');
  }else if(seriesKey==='proximity_series'&&!series.length){
    // Older generated JSON stored proximity counts inside technology.
    const hasLegacy=rows.some(row=>Number((row.technology||{})['Hi-C / proximity']||0)>0);
    if(hasLegacy)series=['Hi-C / proximity'];
  }
  if(!rows.length||!series.length){
    svg.innerHTML='<text class="genometrics-trend-empty" x="260" y="165" text-anchor="middle">Trend data unavailable until the next completed genometrics refresh.</text>';
    legend.innerHTML='';
    return;
  }

  const w=520,h=330,L=50,R=12,T=18,B=52,iw=w-L-R,ih=h-T-B;
  const years=rows.map(x=>Number(x.year));
  const xmin=Math.min(...years),xmax=Math.max(...years);
  const x=yr=>L+(xmax===xmin?iw/2:(yr-xmin)/(xmax-xmin)*iw);
  const y=p=>T+ih-(Math.max(0,Math.min(100,p))/100)*ih;
  const countFor=(row,name)=>{
    if(seriesKey==='technology_series'){
      const tech=row.technology||{};
      if(name==='PacBio'){
        if(tech.PacBio!=null)return Number(tech.PacBio||0);
        return Number(tech['PacBio HiFi']||0)+
          Number(tech['PacBio (HiFi not specified)']||0)+
          Number(tech['PacBio (other / unspecified)']||0);
      }
      return Number(tech[name]||0);
    }
    if(seriesKey==='assembler_series')return Number((row.assemblers||{})[name]||0);
    if(seriesKey==='proximity_series'){
      if(row.proximity!=null)return Number(row.proximity||0);
      return Number((row.technology||{})['Hi-C / proximity']||0);
    }
    return 0;
  };
  let html='';

  [0,25,50,75,100].forEach(p=>{
    const yy=y(p);
    html+='<line class="genometrics-trend-grid" x1="'+L+'" x2="'+(w-R)+'" y1="'+yy+'" y2="'+yy+'"></line>';
    html+='<text class="genometrics-trend-axis-label" x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end">'+p+'%</text>';
  });
  html+='<line class="genometrics-trend-axis" x1="'+L+'" x2="'+(w-R)+'" y1="'+(T+ih)+'" y2="'+(T+ih)+'"></line>';

  let tickYears=years.filter(yr=>yr%5===0);
  if(!tickYears.length)tickYears=[xmin,xmax];
  if(xmin<tickYears[0]-2)tickYears.unshift(xmin);
  if(xmax>tickYears[tickYears.length-1]+2)tickYears.push(xmax);
  [...new Set(tickYears)].forEach(yr=>{
    const xx=x(yr);
    html+='<line class="genometrics-trend-tick" x1="'+xx+'" x2="'+xx+'" y1="'+(T+ih)+'" y2="'+(T+ih+5)+'"></line>';
    html+='<text class="genometrics-trend-axis-label" x="'+xx+'" y="'+(h-19)+'" text-anchor="middle">'+yr+'</text>';
  });

  series.forEach((name,si)=>{
    const color=METHOD_TREND_COLORS[si%METHOD_TREND_COLORS.length];
    const pts=rows.map(row=>{
      const denom=Number(row[reportedKey]||0);
      const count=countFor(row,name);
      return {year:Number(row.year),count,denom,pct:denom?100*count/denom:0};
    });
    const path=pts.map((p,i)=>(i?'L ':'M ')+x(p.year).toFixed(2)+' '+y(p.pct).toFixed(2)).join(' ');
    html+='<path class="genometrics-trend-line" d="'+path+'" style="stroke:'+color+'"></path>';
    pts.forEach(p=>{
      html+='<circle class="genometrics-trend-point" data-year="'+p.year+'" cx="'+x(p.year).toFixed(2)+'" cy="'+y(p.pct).toFixed(2)+'" r="3.2" style="fill:'+color+'"></circle>';
    });
  });

  rows.forEach((row,i)=>{
    const xx=x(Number(row.year));
    const left=i===0?L:(x(Number(rows[i-1].year))+xx)/2;
    const right=i===rows.length-1?w-R:(xx+x(Number(rows[i+1].year)))/2;
    html+='<rect class="genometrics-trend-hit" data-row-index="'+i+'" x="'+left.toFixed(2)+'" y="'+T+'" width="'+Math.max(1,right-left).toFixed(2)+'" height="'+ih+'"></rect>';
  });
  svg.innerHTML=html;

  const latest=rows[rows.length-1];
  const latestDenom=Number(latest[reportedKey]||0);
  legend.innerHTML=series.map((name,si)=>{
    const color=METHOD_TREND_COLORS[si%METHOD_TREND_COLORS.length];
    const count=countFor(latest,name);
    const pct=latestDenom?100*count/latestDenom:0;
    return '<span><i style="background:'+color+'"></i><b>'+esc(name)+'</b><em>'+fmt1(pct)+'% in '+latest.year+'</em></span>';
  }).join('');

  const tip=el('chart-tooltip');
  const clearHover=()=>{
    tip.hidden=true;
    svg.querySelectorAll('.genometrics-trend-point.is-hovered').forEach(p=>p.classList.remove('is-hovered'));
    svg.querySelectorAll('.genometrics-trend-guide').forEach(g=>g.remove());
  };
  svg.querySelectorAll('.genometrics-trend-hit').forEach(hit=>{
    const idx=Number(hit.dataset.rowIndex);
    const row=rows[idx];
    const show=ev=>{
      svg.querySelectorAll('.genometrics-trend-point.is-hovered').forEach(p=>p.classList.remove('is-hovered'));
      svg.querySelectorAll('.genometrics-trend-point[data-year="'+row.year+'"]').forEach(p=>p.classList.add('is-hovered'));
      svg.querySelectorAll('.genometrics-trend-guide').forEach(g=>g.remove());
      const guide=document.createElementNS('http://www.w3.org/2000/svg','line');
      guide.setAttribute('class','genometrics-trend-guide');
      guide.setAttribute('x1',x(Number(row.year)));guide.setAttribute('x2',x(Number(row.year)));
      guide.setAttribute('y1',T);guide.setAttribute('y2',T+ih);
      svg.insertBefore(guide,svg.querySelector('.genometrics-trend-hit'));

      const denom=Number(row[reportedKey]||0);
      const detail=series.map(name=>{
        const count=countFor(row,name);
        const pct=denom?100*count/denom:0;
        return '<span><b>'+esc(name)+'</b>: '+fmt1(pct)+'% ('+fmt(count)+'/'+fmt(denom)+')</span>';
      }).join('');
      tip.innerHTML='<strong>'+esc(row.year)+' · '+esc(periodLabel)+'</strong>'+detail;
      tip.hidden=false;
      positionTooltip(ev,tip);
    };
    hit.onpointerenter=show;
    hit.onpointermove=show;
    hit.onpointerleave=clearHover;
  });
}


function drawGenomeArchitecture(svgId,legendId,arch){
  const svg=el(svgId),legend=el(legendId);
  const pts=(arch?.species_points||[]).filter(p=>Number(p.chromosomes)>0&&Number(p.size_mb)>0);
  if(!svg||!pts.length){
    if(svg)svg.innerHTML='';
    if(legend)legend.innerHTML='';
    return;
  }

  const w=520,h=390,L=58,R=14,T=16,B=48,iw=w-L-R,ih=h-T-B;
  const logs=pts.map(p=>({x:Math.log10(Number(p.chromosomes)),y:Math.log10(Number(p.size_mb))}));
  let xmin=Math.min(...logs.map(p=>p.x)),xmax=Math.max(...logs.map(p=>p.x));
  let ymin=Math.min(...logs.map(p=>p.y)),ymax=Math.max(...logs.map(p=>p.y));
  xmin=Math.floor(xmin*2)/2;xmax=Math.ceil(xmax*2)/2;
  ymin=Math.floor(ymin);ymax=Math.ceil(ymax);
  if(xmax<=xmin)xmax=xmin+1;if(ymax<=ymin)ymax=ymin+1;
  const X=v=>L+(Math.log10(v)-xmin)/(xmax-xmin)*iw;
  const Y=v=>T+ih-(Math.log10(v)-ymin)/(ymax-ymin)*ih;

  const xTicks=[1,2,5,10,20,50,100,200,500,1000,2000].filter(v=>Math.log10(v)>=xmin&&Math.log10(v)<=xmax);
  const yTicks=[.1,.3,1,3,10,30,100,300,1000,3000,10000,30000,100000,300000].filter(v=>Math.log10(v)>=ymin&&Math.log10(v)<=ymax);
  const sizeLabel=v=>v>=1000?(v/1000)+' Gb':v+' Mb';

  let html='';
  xTicks.forEach(v=>{
    const x=X(v);
    html+=`<line class="genometrics-arch-grid" x1="${x}" x2="${x}" y1="${T}" y2="${T+ih}"></line><text class="genometrics-arch-tick" x="${x}" y="${h-24}" text-anchor="middle">${v}</text>`;
  });
  yTicks.forEach(v=>{
    const y=Y(v);
    html+=`<line class="genometrics-arch-grid" x1="${L}" x2="${L+iw}" y1="${y}" y2="${y}"></line><text class="genometrics-arch-tick" x="${L-7}" y="${y+3}" text-anchor="end">${sizeLabel(v)}</text>`;
  });
  html+=`<line class="genometrics-arch-axis" x1="${L}" x2="${L+iw}" y1="${T+ih}" y2="${T+ih}"></line><line class="genometrics-arch-axis" x1="${L}" x2="${L}" y1="${T}" y2="${T+ih}"></line>`;
  html+=`<text class="genometrics-arch-axis-label" x="${L+iw/2}" y="${h-4}" text-anchor="middle">Reported chromosome count · log scale</text><text class="genometrics-arch-axis-label" transform="translate(12 ${T+ih/2}) rotate(-90)" text-anchor="middle">Genome size · log scale</text>`;

  pts.forEach(p=>{
    const group=p.group||'Other';
    html+=`<circle class="genometrics-arch-point" cx="${X(Number(p.chromosomes)).toFixed(2)}" cy="${Y(Number(p.size_mb)).toFixed(2)}" r="2.4" fill="${COLORS[group]||COLORS.Other}" data-species="${esc(p.species)}" data-group="${esc(group)}" data-class="${esc(p.class||'')}" data-chromosomes="${Number(p.chromosomes)}" data-size="${Number(p.size_mb)}"></circle>`;
  });
  svg.innerHTML=html;

  const groups=['Animals','Plants','Fungi','Other'].filter(g=>pts.some(p=>(p.group||'Other')===g));
  legend.innerHTML=groups.map(g=>`<span><i style="background:${COLORS[g]}"></i>${g}</span>`).join('');

  const tip=el('chart-tooltip');
  svg.querySelectorAll('.genometrics-arch-point').forEach(p=>{
    const show=ev=>{
      const cls=p.dataset.class?` · ${esc(p.dataset.class)}`:'';
      tip.innerHTML=`<strong><i>${esc(p.dataset.species)}</i></strong><span>${fmt(Number(p.dataset.chromosomes))} chromosomes · ${fmt1(Number(p.dataset.size))} Mb</span><span>${esc(p.dataset.group)}${cls}</span>`;
      tip.hidden=false;p.classList.add('is-hovered');positionTooltip(ev,tip);
    };
    const hide=()=>{tip.hidden=true;p.classList.remove('is-hovered');};
    p.onpointerenter=show;p.onpointermove=show;p.onpointerleave=hide;
  });
}

function drawGenomeSizeByTaxon(svgId,dist){
  const svg=el(svgId);
  if(!svg)return;
  const rows=(dist?.classes||[]).slice(0,10);
  if(!rows.length){
    svg.innerHTML='<text x="260" y="200" text-anchor="middle" class="genometrics-arch-tick">No qualifying taxa in this group</text>';
    return;
  }
  const bins=dist.bin_labels||rows[0].bins.map(x=>x.label);
  const group=rows[0].group||'Other';
  const color=COLORS[group]||COLORS.Other;
  const w=520,h=460,L=137,R=15,T=20,B=48,iw=w-L-R;
  const rowH=(h-T-B)/10;
  const bw=iw/bins.length;
  let html='';
  const tickPos=[0,2,4,6,8,10,12].filter(i=>i<=bins.length);
  const axisNames={0:'<1 Mb',2:'3 Mb',4:'30 Mb',6:'300 Mb',8:'3 Gb',10:'30 Gb',12:'≥100 Gb'};
  tickPos.forEach(i=>{
    const x=L+i*bw;
    html+=`<line class="genometrics-arch-grid" x1="${x.toFixed(2)}" y1="${T-6}" x2="${x.toFixed(2)}" y2="${h-B+5}"></line>`;
    html+=`<text class="genometrics-dist-tick" x="${x.toFixed(2)}" y="${h-25}" text-anchor="middle">${axisNames[i]||''}</text>`;
  });
  const tip=el('chart-tooltip');
  rows.forEach((row,ri)=>{
    const counts=(row.bins||[]).map(x=>Number(x.count||0));
    const total=Number(row.species||0);
    const peak=Math.max(1,...counts);
    const mid=T+(ri+.5)*rowH;
    const amplitude=rowH*.41;
    const samples=[0,...counts,0];
    const points=samples.map((v,i)=>({
      x:L+(i-.5)*bw,
      y:mid-amplitude*(v/peak)
    }));
    const smooth=(ps)=>{
      let d=`M${ps[0].x.toFixed(2)},${ps[0].y.toFixed(2)}`;
      for(let i=0;i<ps.length-1;i++){
        const p=ps[i],q=ps[i+1],mx=(p.x+q.x)/2;
        d+=` C${mx.toFixed(2)},${p.y.toFixed(2)} ${mx.toFixed(2)},${q.y.toFixed(2)} ${q.x.toFixed(2)},${q.y.toFixed(2)}`;
      }
      return d;
    };
    const outline=smooth(points);
    const last=points[points.length-1];
    html+=`<text class="genometrics-dist-label" x="${L-9}" y="${mid-2}" text-anchor="end">${esc(row.taxon)}</text>`;
    html+=`<text class="genometrics-dist-n" x="${L-9}" y="${mid+11}" text-anchor="end">n=${fmt(total)} · median ${fmt1(row.median_mb||0)} Mb</text>`;
    html+=`<path class="genometrics-dist-ribbon" d="${outline} L${last.x.toFixed(2)},${mid.toFixed(2)} L${points[0].x.toFixed(2)},${mid.toFixed(2)} Z" fill="${color}" fill-opacity=".73"></path>`;
    html+=`<path class="genometrics-dist-ribbon-edge" d="${outline}" fill="none" stroke="${color}"></path>`;
    counts.forEach((n,i)=>{
      html+=`<rect class="genometrics-dist-ribbon-hit" data-taxon="${esc(row.taxon)}" data-label="${esc(row.bins?.[i]?.label||bins[i]||'')}" data-count="${n}" data-total="${total}" x="${(L+i*bw).toFixed(2)}" y="${(mid-rowH*.55).toFixed(2)}" width="${bw.toFixed(2)}" height="${rowH.toFixed(2)}"></rect>`;
    });
  });
  html+=`<text class="genometrics-arch-axis-label" x="${L+iw/2}" y="${h-5}" text-anchor="middle">Genome size · shared logarithmic scale</text>`;
  svg.innerHTML=html;
  svg.querySelectorAll('.genometrics-dist-ribbon-hit').forEach(hit=>{
    const show=ev=>{
      const n=Number(hit.dataset.count||0),total=Number(hit.dataset.total||0);
      tip.innerHTML=`<strong>${esc(hit.dataset.taxon)}</strong><span>${esc(hit.dataset.label)}</span><span>${fmt(n)} species · ${total?fmt1(100*n/total):'0.0'}% of taxon</span>`;
      tip.hidden=false;positionTooltip(ev,tip);
    };
    hit.onpointerenter=show;
    hit.onpointermove=show;
    hit.onpointerleave=()=>{tip.hidden=true;};
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
  const topSpecies=d.top_species_by_assemblies?.species||[];
  drawTopSpecies('genometrics-top-species',topSpecies);
  el('genometrics-top-species-denominator').textContent='Ranked across all '+fmt(q.assemblies||0)+' tracked chromosome-level and complete GenBank assembly deposits.';
  el('genometrics-quality-denominator').textContent=
    fmt(q.assembly_size_available||0)+' assemblies contribute genome size; '+fmt(q.chromosome_count_available||0)+' have an NCBI-reported chromosome count.';

  const arch=d.genome_architecture||{};
  drawGenomeArchitecture('genometrics-size-chrom-scatter','genometrics-architecture-legend',arch);
  el('genometrics-architecture-denominator').textContent=
    fmt(arch.scatter_species||0)+' species have both NCBI assembly size and reported chromosome-count metadata; each species is represented once.';
  const dist=arch.size_distribution_by_class||{};
  for(const group of ['Animals','Plants','Fungi']){
    const id=group.toLowerCase();
    const current=dist.groups?.[group]||{
      classes:(dist.classes||[]).filter(x=>x.group===group),
      represented_species:(dist.classes||[]).filter(x=>x.group===group).reduce((n,x)=>n+Number(x.species||0),0)
    };
    drawGenomeSizeByTaxon('genometrics-size-'+id,{...current,bin_labels:dist.bin_labels});
    el('genometrics-size-'+id+'-denominator').textContent=
      fmt(current.represented_species||0)+' species across '+(current.classes||[]).length+
      ' classes. Colour intensity scales to the fraction of species in each genome-size bin.';
  }

  const methods=d.methods_through_time||{};
  drawGenometricTrend(
    'genometrics-tech-trend','genometrics-tech-legend',methods,
    'technology_series','tech_reported','primary sequencing technology'
  );
  drawGenometricTrend(
    'genometrics-proximity-trend','genometrics-proximity-legend',methods,
    'proximity_series','assemblies','Hi-C / proximity use'
  );
  drawGenometricTrend(
    'genometrics-assembler-trend','genometrics-assembler-legend',methods,
    'assembler_series','assembler_reported','assembly method'
  );
  const tracked=Number(q.assemblies||0);
  const techN=Number(methods.technology_metadata_assemblies||0);
  const proximityN=Number(methods.proximity_assemblies||0);
  const asmN=Number(methods.assembler_metadata_assemblies||0);
  el('genometrics-tech-denominator').textContent=
    fmt(techN)+' of '+fmt(tracked)+' tracked assemblies report sequencing-technology metadata'+
    (tracked?' ('+fmt1(100*techN/tracked)+'%). ':'; ')+
    'Hi-C/proximity methods are excluded from this panel; lines can overlap when hybrid primary sequencing was reported.';
  el('genometrics-proximity-denominator').textContent=
    fmt(proximityN)+' of '+fmt(tracked)+' tracked assemblies explicitly report Hi-C or another recognized proximity-ligation method in NCBI sequencing metadata'+
    (tracked?' ('+fmt1(100*proximityN/tracked)+'%). ':'; ')+
    'The yearly line is the fraction of all qualifying assembly deposits released in that year that explicitly report proximity data.';
  el('genometrics-assembler-denominator').textContent=
    fmt(asmN)+' of '+fmt(tracked)+' tracked assemblies report a specific assembly method'+
    (tracked?' ('+fmt1(100*asmN/tracked)+'%). ':'; ')+
    'Software versions and spelling variants are normalized into named assembler families; an assembly can mention more than one family.';


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
  end.setUTCDate(end.getUTCDate()-REPORTING_LAG_DAYS);
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
  const recentBySpecies=new Map();
  recent.forEach(x=>{
    const species=String(x.organism_name||'').trim()||String(x.accession||'');
    const key=species+'\u0000'+String(x.release_date||'');
    if(!recentBySpecies.has(key))recentBySpecies.set(key,[]);
    recentBySpecies.get(key).push(x);
  });
  const recentSpeciesRows=[...recentBySpecies.values()].slice(0,18);
  const recentAccessionLinks=xs=>xs.map(x=>{
    const acc=esc(x.accession||'');
    const url=assemblyUrl(x.accession);
    return url ? `<a class="assembly-link" href="${url}" target="_blank" rel="noopener">${acc}</a>` : acc;
  }).join('<br>');
  const recentUniqueText=(xs,key)=>[...new Set(xs.map(x=>String(x[key]||'').trim()).filter(Boolean))].map(esc).join('<br>');
  el('status-recent-list').innerHTML=`<div class="header"><span>Date</span><span>Species</span><span>Common name</span><span>IUCN status</span><span>Assembly</span><span>Level</span><span>Accession</span></div>`+
    recentSpeciesRows.map(xs=>{
      const x=xs[0];
      return `<div class="row"><span class="muted">${esc(x.release_date||'')}</span><span class="species">${assemblySpeciesLink(x)}</span><span class="muted">${recentUniqueText(xs,'common_name')||'—'}</span><span class="muted">${recentUniqueText(xs,'iucn_status')||'—'}</span><span class="muted">${recentUniqueText(xs,'assembly_name')}</span><span>${recentUniqueText(xs,'assembly_level')}</span><span class="muted">${recentAccessionLinks(xs)}</span></div>`;
    }).join('');

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
  const desc=el('country-facet-description');
  const mapTitle=el('country-map-title');
  if(countryFacet==='sequencing'){
    if(desc)desc.textContent='Country reflects the inferred sequencing or genome-producing institute. Recent colour shows the trailing 30-day pace.';
    if(mapTitle)mapTitle.textContent='Institute-associated activity';
  }else if(countryFacet==='alltime'){
    if(desc)desc.textContent='Country reflects BioSample geographic origin. Colour shows the all-time number of qualifying chromosome/complete genome deposits.';
    if(mapTitle)mapTitle.textContent='All-time sample origins';
  }else{
    if(desc)desc.textContent='Country reflects the NCBI BioSample geographic-location field. Colour shows the trailing 30-day deposition pace; ocean and sea localities appear as markers.';
    if(mapTitle)mapTitle.textContent='Sample-origin activity';
  }
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
    const countryN=Number(c.assemblies_assigned_to_country||0);
    const marineN=Number(c.assemblies_assigned_to_marine_locality||0);
    const resolved=Number(c.assemblies_geographically_resolved||countryN+marineN);
    const total=Number(c.assemblies_scanned||0);
    const pct=total?100*resolved/total:0;
    el('country-map-status').textContent=
      fmt(resolved)+' of '+fmt(total)+' assemblies have a resolved geographic origin ('+
      fmt1(pct)+'%): '+fmt(countryN)+' assigned to countries'+
      (marineN?' and '+fmt(marineN)+' to controlled ocean/sea localities.':'.');
  }
}

async function loadCountries(){
  updateCountryFacetText();
  if(COUNTRY_DATA && WORLD_DATA){
    if(!COUNTRY_TAXA_DATA){
      try{
        const r=await fetch(COUNTRY_TAXA_URL+'?refresh='+Date.now(),{cache:'no-store'});
        if(r.ok)COUNTRY_TAXA_DATA=await r.json();
      }catch(err){console.warn('Country taxon summary unavailable',err);}
    }
    if(countryFacet==='sequencing'&&!SEQ_COUNTRY_DATA) await loadSequencingCountries();
    renderCountryMap();
    renderCountryCompanion();
    renderCountryMatches(el('country-search').value);
    if(selectedCountry) renderCountryDetail(selectedCountry);
    updateCountryCoverageText();
    return;
  }
  if(COUNTRY_LOADING)return COUNTRY_LOADING;
  el('country-map-status').textContent='Loading country data and map…';
  COUNTRY_LOADING=Promise.all([
    fetch(COUNTRY_URL+'?refresh='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json();}),
    fetch(COUNTRY_TAXA_URL+'?refresh='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json();}),
    (window.d3 && window.topojson)
      ? d3.json(WORLD_URL)
      : Promise.reject(new Error('Map libraries unavailable'))
  ])
    .then(async([countries,countryTaxa,world])=>{
      COUNTRY_DATA=countries;
      COUNTRY_TAXA_DATA=countryTaxa;
      WORLD_DATA=world;
      if(countryFacet==='sequencing') await loadSequencingCountries();
      renderCountryMap();
      renderCountryCompanion();
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
  SEQ_COUNTRY_LOADING=fetch(SEQUENCING_COUNTRY_URL+'?refresh='+Date.now(),{cache:'no-store'})
    .then(r=>{if(!r.ok)throw Error(r.status);return r.json();})
    .then(d=>{SEQ_COUNTRY_DATA=d;renderCountryCompanion();return d;})
    .catch(err=>{
      console.error(err);
      el('country-map-status').textContent='Sequencing-center country data are unavailable until the next data refresh.';
      throw err;
    })
    .finally(()=>{SEQ_COUNTRY_LOADING=null;});
  return SEQ_COUNTRY_LOADING;
}

function renderCountryCompanion(){
  const svg=el('country-companion-chart');
  const title=el('country-companion-title');
  const kicker=el('country-companion-kicker');
  const desc=el('country-companion-description');
  const note=el('country-companion-note');
  if(!svg||!title||!kicker||!desc||!note)return;

  let rows=[],valueKey='assemblies',valueLabel='assemblies',context='';

  if(countryFacet==='sequencing'){
    const countryRow=selectedCountry && selectedCountry.top_institutes ? selectedCountry : null;
    rows=(countryRow?.top_institutes||SEQ_COUNTRY_DATA?.top_institutes||[]).slice(0,10);
    kicker.textContent='Institute ranking';
    title.textContent=countryRow ? 'Top institutes in '+countryRow.name : 'Top 10 institutes';
    desc.textContent=countryRow
      ? 'Resolved sequencing-institute associations for assemblies linked to '+countryRow.name+'.'
      : 'Assemblies associated with each resolved sequencing institute; SRA sequencing-center names are preferred.';
    valueKey='assemblies';
    valueLabel='associated assemblies';
    context='institute';
    const denominator=countryRow
      ? Number(countryRow.assemblies||0)
      : Number(SEQ_COUNTRY_DATA?.coverage?.assemblies_with_resolved_institute_country||0);
    note.textContent=countryRow
      ? fmt(denominator)+' institute-linked assemblies are associated with '+countryRow.name+'.'
      : fmt(denominator)+' assemblies have a resolved institute-country association.';
  }else if(countryFacet==='origin'){
    const countryRows=selectedCountry
      ? (COUNTRY_TAXA_DATA?.countries?.[selectedCountry.iso3]||[])
      : (COUNTRY_TAXA_DATA?.origin_orders||[]);
    rows=countryRows.slice(0,10);
    kicker.textContent='Taxonomic composition';
    title.textContent=selectedCountry
      ? 'Orders represented in '+selectedCountry.name
      : 'Top orders by species represented';
    desc.textContent=selectedCountry
      ? 'Distinct species represented among assemblies whose BioSample origin resolves to '+selectedCountry.name+'.'
      : 'Distinct species represented among assemblies with a resolved BioSample country.';
    valueKey='species';
    valueLabel='species represented';
    context='taxon';
    note.textContent=selectedCountry
      ? 'Click another country to update this taxonomic profile.'
      : 'Click a country on the map to show its taxonomic composition.';
  }else{
    rows=(COUNTRY_DATA?.countries||[])
      .slice()
      .sort((a,b)=>Number(b.assemblies||0)-Number(a.assemblies||0))
      .slice(0,10);
    kicker.textContent='Country ranking';
    title.textContent='Top 10 sample-origin countries';
    desc.textContent='All-time chromosome/complete genome assemblies with a resolved BioSample country.';
    valueKey='assemblies';
    valueLabel='assemblies';
    context='country';
    note.textContent='All-time totals; marine-only locality records are shown on the map but are not countries.';
  }

  if(!rows.length){
    svg.innerHTML='<text class="country-companion-empty" x="260" y="225" text-anchor="middle">Ranking unavailable until the next data refresh.</text>';
    return;
  }

  drawCountryCompanionBars(svg,rows,valueKey,valueLabel,context);
}

function drawCountryCompanionBars(svg,rows,valueKey,valueLabel,context){
  const w=520,h=450,L=205,R=56,T=14,B=18,iw=w-L-R;
  const rowH=(h-T-B)/Math.max(1,rows.length);
  const max=Math.max(1,...rows.map(x=>Number(x[valueKey]||0)));
  const scale=v=>iw*Number(v||0)/max;
  let out='';
  rows.forEach((r,i)=>{
    const y=T+i*rowH+5;
    const bh=Math.max(12,rowH-11);
    const bw=scale(r[valueKey]);
    out+='<text class="country-companion-label" x="'+(L-10)+'" y="'+(y+bh/2+4)+'" text-anchor="end">'+esc(r.name)+'</text>';
    out+='<rect class="country-companion-bar" data-index="'+i+'" x="'+L+'" y="'+y.toFixed(2)+'" width="'+Math.max(1,bw).toFixed(2)+'" height="'+bh.toFixed(2)+'" rx="2"></rect>';
    out+='<text class="country-companion-value" x="'+Math.min(w-R+4,L+bw+7).toFixed(2)+'" y="'+(y+bh/2+4)+'">'+fmt(r[valueKey])+'</text>';
  });
  svg.innerHTML=out;

  const tip=el('chart-tooltip');
  svg.querySelectorAll('.country-companion-bar').forEach(bar=>{
    const row=rows[Number(bar.dataset.index)];
    const show=ev=>{
      let body='<strong>'+esc(row.name)+'</strong><span>'+fmt(row[valueKey])+' '+esc(valueLabel)+'</span>';
      if(context==='taxon')body+='<span>'+fmt(row.assemblies)+' assemblies</span>';
      if(context==='country')body+='<span>'+fmt(row.species)+' species represented</span>';
      if(context==='institute'&&row.country)body+='<span>'+esc(row.country)+'</span>';
      tip.innerHTML=body;
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

  if(countryFacet!=='sequencing'){
    const marine=(COUNTRY_DATA?.marine_localities||[]);
    const marineMax=Math.max(0,...marine.map(valueOf));
    const radius=d3.scaleSqrt()
      .domain([0,Math.max(1,marineMax)])
      .range([3.5,13]);
    svg.append('g')
      .attr('class','marine-marker-layer')
      .selectAll('circle')
      .data(marine.filter(x=>valueOf(x)>0))
      .join('circle')
      .attr('class','marine-marker')
      .attr('cx',d=>projection([Number(d.lon),Number(d.lat)])[0])
      .attr('cy',d=>projection([Number(d.lon),Number(d.lat)])[1])
      .attr('r',d=>radius(valueOf(d)))
      .on('pointerenter pointermove',function(ev,d){
        d3.select(this).classed('is-hovered',true);
        const primary=alltime
          ? '<span>'+fmt(d.assemblies)+' assemblies · all time</span>'
          : '<span>'+countryRateLabel(valueOf(d))+' genomes per business day</span><span>'+fmt(d.window_assemblies)+' assemblies · past 30 days</span>';
        tip.innerHTML='<strong>'+esc(d.name)+'</strong>'+primary+'<span>'+fmt(d.species)+' species represented</span><span>INSDC ocean/sea geo_loc_name</span>';
        tip.hidden=false;positionTooltip(ev,tip);
      })
      .on('pointerleave',function(){
        d3.select(this).classed('is-hovered',false);
        tip.hidden=true;
      });
  }

  el('country-map').setAttribute('aria-label',alltime
    ? 'World map of all-time genome deposits by sample-origin country'
    : 'World map of genomes deposited per business day by country');
  el('country-map-legend').innerHTML=
    '<span>'+(alltime?'Total genome deposits · all time':'Genomes per business day · trailing 30-day pace')+'</span>'+
    '<div class="map-gradient"></div>'+
    '<div class="map-legend-ticks"><span>0</span><span>'+(alltime?fmt(maxValue):countryRateLabel(maxValue))+'</span></div>'+
    (countryFacet==='sequencing'?'':'<div class="marine-legend-key"><i></i><span>Ocean / sea locality · marker size reflects the same time view</span></div>');
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
  renderCountryCompanion();
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

async function ensureWorldData(){
  if(WORLD_DATA)return WORLD_DATA;
  if(WORLD_LOADING)return WORLD_LOADING;
  if(!window.d3||!window.topojson)throw new Error('Map libraries unavailable');
  WORLD_LOADING=d3.json(WORLD_URL)
    .then(world=>{WORLD_DATA=world;return world;})
    .finally(()=>{WORLD_LOADING=null;});
  return WORLD_LOADING;
}

async function loadTaxaIndex(){
  if(TAXA_INDEX){
    renderTaxonMatches(el('taxon-search-left').value,'left');
    renderTaxonMatches(el('taxon-search-right').value,'right');
    ensureWorldData().then(()=>renderTaxonComparison()).catch(()=>{});
    return;
  }
  if(TAXA_LOADING)return TAXA_LOADING;
  ['left','right'].forEach(side=>{
    el('taxon-results-'+side).innerHTML='<div class="taxon-loading">Loading phylum/order index…</div>';
  });
  TAXA_LOADING=Promise.all([
    fetch(TAXA_INDEX_URL+'?refresh='+Date.now(),{cache:'no-store'})
      .then(r=>{if(!r.ok)throw Error(r.status);return r.json();}),
    ensureWorldData().catch(err=>{console.warn('Taxon map unavailable',err);return null;})
  ])
    .then(([d])=>{
      TAXA_INDEX=d;
      if(!d.taxa?.length){
        ['left','right'].forEach(side=>{
          el('taxon-results-'+side).innerHTML='<div class="taxon-loading">Taxonomy index is being built. Try again after the next data refresh.</div>';
        });
        return;
      }
      renderTaxonMatches(el('taxon-search-left').value,'left');
      renderTaxonMatches(el('taxon-search-right').value,'right');
    })
    .catch(err=>{
      console.error(err);
      ['left','right'].forEach(side=>{
        el('taxon-results-'+side).innerHTML='<div class="taxon-loading">Taxonomy index unavailable.</div>';
      });
    })
    .finally(()=>{TAXA_LOADING=null;});
  return TAXA_LOADING;
}

function renderTaxonMatches(raw,side){
  if(!TAXA_INDEX?.taxa?.length)return;
  const q=String(raw||'').trim().toLowerCase();
  let rows=TAXA_INDEX.taxa.slice();
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
  const box=el('taxon-results-'+side);
  box.innerHTML=(q?'':'<div class="taxon-results-label">Most sequenced orders</div>')+
    rows.map(x=>{
      const context=[x.class,x.phylum].filter(Boolean).join(' · ');
      return '<button type="button" data-taxid="'+x.taxid+'" class="taxon-result"><span><strong>'+esc(x.name)+'</strong><small>'+esc(x.rank)+(context?' · '+esc(context):'')+'</small></span><span>'+fmt(x.assemblies)+'</span></button>';
    }).join('');
  box.querySelectorAll('button[data-taxid]').forEach(btn=>btn.addEventListener('click',()=>{
    const meta=TAXA_INDEX.taxa.find(x=>String(x.taxid)===btn.dataset.taxid);
    if(meta)selectTaxon(meta,side);
  }));
}

async function selectTaxon(meta,side){
  el('taxon-search-'+side).value=meta.name;
  el('taxon-results-'+side).innerHTML='';
  el('taxon-empty-'+side).innerHTML='<p>Loading '+esc(meta.name)+'…</p>';
  el('taxon-empty-'+side).hidden=false;
  el('taxon-content-'+side).hidden=true;
  try{
    let t=TAXON_CACHE.get(String(meta.taxid));
    if(!t){
      const r=await fetch('../data/taxa/'+meta.taxid+'.json?refresh='+Date.now(),{cache:'no-store'});
      if(!r.ok)throw Error(r.status);
      t=await r.json();
      TAXON_CACHE.set(String(meta.taxid),t);
    }
    TAXON_SELECTED[side]=t;
    renderTaxonComparison();
  }catch(err){
    console.error(err);
    el('taxon-empty-'+side).innerHTML='<p>Taxon history unavailable for '+esc(meta.name)+'.</p>';
  }
}

function taxonLineage(t){
  const lineage=[];
  if(t?.phylum?.name && t.phylum.name!==t.name)lineage.push(t.phylum.name);
  if(t?.class?.name && t.class.name!==t.name)lineage.push(t.class.name);
  if(t?.rank==='order')lineage.push(t.name);
  return lineage.join(' → ');
}

function taxonYears(selected){
  const ys=selected.flatMap(t=>(t?.yearly||[]).map(x=>Number(x.year))).filter(Number.isFinite);
  if(!ys.length)return [];
  const lo=Math.min(...ys),hi=Math.max(...ys);
  return Array.from({length:hi-lo+1},(_,i)=>lo+i);
}

function taxonCumulativeRows(t,years){
  if(!t)return [];
  const by=new Map((t.yearly||[]).map(x=>[Number(x.year),x]));
  let assemblies=0,first=0;
  return years.map(year=>{
    const r=by.get(year)||{};
    assemblies+=Number(r.assemblies||0);
    first+=Number(r.first_time_species||0);
    return {year:String(year),assemblies,first};
  });
}

function taxonRecentRows(t){
  if(!t)return [];
  const sparse=new Map((t.recent_daily||[]).map(x=>[x.date,Number(x.assemblies||0)]));
  const anchor=TAXA_INDEX?.generated_at?new Date(TAXA_INDEX.generated_at):new Date();
  const end=new Date(Date.UTC(anchor.getUTCFullYear(),anchor.getUTCMonth(),anchor.getUTCDate()));
  const recent=[];
  for(let i=364;i>=0;i--){
    const d=new Date(end);d.setUTCDate(end.getUTCDate()-i);
    const ds=d.toISOString().slice(0,10);
    recent.push({date:ds,assemblies:sparse.get(ds)||0});
  }
  return businessDayRows(recent);
}

function renderTaxonComparison(){
  const selected=[TAXON_SELECTED.left,TAXON_SELECTED.right].filter(Boolean);
  if(!selected.length)return;

  const years=taxonYears(selected);
  const cumulative={
    left:taxonCumulativeRows(TAXON_SELECTED.left,years),
    right:taxonCumulativeRows(TAXON_SELECTED.right,years)
  };
  const recent={
    left:taxonRecentRows(TAXON_SELECTED.left),
    right:taxonRecentRows(TAXON_SELECTED.right)
  };

  const cumulativeMax=niceMax(Math.max(0,...['left','right'].flatMap(side=>
    cumulative[side].flatMap(x=>[Number(x.assemblies||0),Number(x.first||0)])
  )));
  const recentMax=niceMax(Math.max(0,...['left','right'].flatMap(side=>
    recent[side].map(x=>Number(x.assemblies||0))
  )));
  const mapMax=Math.max(1,...selected.flatMap(t=>(t.countries||[]).map(c=>Number(c.assemblies||0))));
  const marineMax=Math.max(1,...selected.flatMap(t=>(t.marine_localities||[]).map(c=>Number(c.assemblies||0))));

  ['left','right'].forEach(side=>{
    const t=TAXON_SELECTED[side];
    if(!t)return;
    el('taxon-empty-'+side).hidden=true;
    el('taxon-content-'+side).hidden=false;
    el('taxon-rank-'+side).textContent=t.rank;
    el('taxon-name-'+side).textContent=t.name;
    el('taxon-lineage-'+side).textContent=taxonLineage(t);
    el('taxon-assemblies-'+side).textContent=fmt(t.stats?.assemblies);
    el('taxon-species-'+side).textContent=fmt(t.stats?.species);
    el('taxon-first-'+side).textContent=prettyDate(t.stats?.first_deposit);
    el('taxon-year-assemblies-'+side).textContent=fmt(t.stats?.past_year_assemblies);
    el('taxon-year-species-'+side).textContent=fmt(t.stats?.past_year_species);

    drawDualChart('taxon-cumulative-chart-'+side,cumulative[side],cumulativeMax);
    drawLineChart(
      'taxon-recent-chart-'+side,recent[side],'assemblies',
      recent[side].map(x=>x.date),'year',recentMax
    );
    drawTaxonOriginMap(side,t,mapMax,marineMax);
  });
}

function drawTaxonOriginMap(side,t,sharedMax,sharedMarineMax){
  const svgEl=el('taxon-map-'+side);
  const legend=el('taxon-map-legend-'+side);
  const status=el('taxon-map-status-'+side);
  if(!svgEl)return;
  if(!WORLD_DATA||!window.d3||!window.topojson){
    svgEl.innerHTML='';
    legend.innerHTML='';
    status.textContent='World map unavailable.';
    return;
  }

  const rows=t.countries||[];
  const byNumeric=new Map(rows.map(c=>[String(c.iso_n3||'').padStart(3,'0'),c]));
  const svg=d3.select(svgEl);
  svg.selectAll('*').remove();
  const width=520,height=285;
  const geo=topojson.feature(WORLD_DATA,WORLD_DATA.objects.countries);
  const projection=d3.geoNaturalEarth1().fitExtent([[5,5],[width-5,height-5]],geo);
  const path=d3.geoPath(projection);
  const scale=d3.scaleSequentialSqrt([0,Math.max(1,sharedMax)],d3.interpolateBlues);
  const tip=el('chart-tooltip');

  svg.append('path').datum({type:'Sphere'}).attr('class','map-ocean').attr('d',path);
  svg.append('g').selectAll('path')
    .data(geo.features)
    .join('path')
    .attr('class','taxon-country-shape')
    .attr('d',path)
    .attr('fill',d=>{
      const c=byNumeric.get(String(d.id??'').padStart(3,'0'));
      return c?scale(Number(c.assemblies||0)):'#e3e6ea';
    })
    .on('pointerenter pointermove',function(ev,d){
      d3.select(this).classed('is-hovered',true);
      const c=byNumeric.get(String(d.id??'').padStart(3,'0'));
      const name=c?.name||d.properties?.name||'Country';
      tip.innerHTML=c
        ? '<strong>'+esc(name)+'</strong><span>'+fmt(c.assemblies)+' '+esc(t.name)+' assemblies with this BioSample origin</span>'
        : '<strong>'+esc(name)+'</strong><span>No assigned '+esc(t.name)+' assembly origins</span>';
      tip.hidden=false;positionTooltip(ev,tip);
    })
    .on('pointerleave',function(){
      d3.select(this).classed('is-hovered',false);
      tip.hidden=true;
    });

  const marine=t.marine_localities||[];
  const marineRadius=d3.scaleSqrt()
    .domain([0,Math.max(1,sharedMarineMax)])
    .range([3,10]);
  svg.append('g')
    .attr('class','marine-marker-layer')
    .selectAll('circle')
    .data(marine)
    .join('circle')
    .attr('class','marine-marker taxon-marine-marker')
    .attr('cx',d=>projection([Number(d.lon),Number(d.lat)])[0])
    .attr('cy',d=>projection([Number(d.lon),Number(d.lat)])[1])
    .attr('r',d=>marineRadius(Number(d.assemblies||0)))
    .on('pointerenter pointermove',function(ev,d){
      d3.select(this).classed('is-hovered',true);
      tip.innerHTML='<strong>'+esc(d.name)+'</strong><span>'+fmt(d.assemblies)+' '+esc(t.name)+' assemblies with this BioSample origin</span><span>INSDC ocean/sea geo_loc_name</span>';
      tip.hidden=false;positionTooltip(ev,tip);
    })
    .on('pointerleave',function(){
      d3.select(this).classed('is-hovered',false);
      tip.hidden=true;
    });

  legend.innerHTML='<span>Country assemblies · shared fill scale</span><div class="map-gradient"></div><div class="map-legend-ticks"><span>0</span><span>'+fmt(sharedMax)+'</span></div>'+
    '<div class="marine-legend-key"><i></i><span>Ocean / sea locality · shared marker-size scale</span></div>';
  const countryAssigned=Number(t.stats?.origin_country_assemblies??t.stats?.origin_assigned_assemblies??0);
  const marineAssigned=Number(t.stats?.origin_marine_assemblies||0);
  const resolved=Number(t.stats?.origin_resolved_assemblies||countryAssigned+marineAssigned);
  const total=Number(t.stats?.assemblies||0);
  status.textContent=resolved
    ? fmt(resolved)+' of '+fmt(total)+' assemblies have resolved geographic origin ('+fmt1(100*resolved/Math.max(1,total))+'%): '+fmt(countryAssigned)+' country, '+fmt(marineAssigned)+' ocean/sea.'
    : 'No resolved BioSample geographic-origin data are available for this taxon yet.';
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

function drawLineChart(id,rows,key,labels,mode,forcedMax=null){
  const svg=el(id);if(!svg||!rows.length){if(svg)svg.innerHTML='';return;}
  const w=860,h=320,L=60,R=18,T=12,B=42,iw=w-L-R,ih=h-T-B;
  const vals=rows.map(x=>Number(x[key]||0)),max=forcedMax==null?niceMax(Math.max(...vals)):Math.max(1,Number(forcedMax));
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

function drawDualChart(id,rows,forcedMax=null){
  const svg=el(id);if(!svg||!rows.length){if(svg)svg.innerHTML='';return;}
  const w=860,h=320,L=60,R=18,T=12,B=42,iw=w-L-R,ih=h-T-B;
  const max=forcedMax==null?niceMax(Math.max(...rows.flatMap(x=>[Number(x.assemblies||0),Number(x.first||0)]))):Math.max(1,Number(forcedMax));
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
