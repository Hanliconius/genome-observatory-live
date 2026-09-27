const D='../data/dashboard.json';
const fmt=n=>new Intl.NumberFormat('en-US').format(n||0);
const el=id=>document.getElementById(id);
let DATA,range='week';

fetch(D).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{DATA=d;render()}).catch(err=>{el('updated').textContent='data unavailable';console.error(err)});

document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');range=b.dataset.range;render()}));

function render(){
 const s=DATA.summary[range];
 el('updated').textContent=(DATA.demo_seed?'awaiting first live refresh · ':'updated ')+new Date(DATA.generated_at).toLocaleString([], {dateStyle:'medium',timeStyle:'short'});
 el('primary-label').textContent=range==='week'?'NEW CHROMOSOME-SCALE ASSEMBLIES':range==='year'?'CHROMOSOME-SCALE ASSEMBLIES · PAST YEAR':'CHROMOSOME-SCALE ASSEMBLIES · ALL TIME';
 el('assemblies-count').textContent=fmt(s.assemblies); el('species-count').textContent=fmt(s.species); el('first-count').textContent=fmt(s.first_time_species);
 el('pipeline-count').textContent=fmt(DATA.annotations.in_progress.length); el('completed-count').textContent=fmt(DATA.annotations.recent_completed.length);
 renderMiniBars(DATA.daily.slice(-7)); renderPipeline(); renderNewest(); renderGroups(); renderRecent(); renderRate(); renderCumulative();
}
function renderMiniBars(rows){const m=Math.max(1,...rows.map(x=>x.assemblies));el('daily-bars').innerHTML=rows.map(x=>`<i title="${x.date}: ${x.assemblies}" style="height:${Math.max(4,100*x.assemblies/m)}%"></i>`).join('')}
function renderPipeline(){el('pipeline-list').innerHTML=DATA.annotations.in_progress.slice(0,6).map(x=>`<div class="pipeline-row"><span><em>${x.species}</em></span><span>${x.status}</span></div>`).join('');el('recent-annotation-list').innerHTML=DATA.annotations.recent_completed.slice(0,5).map(x=>`<div class="pipeline-row"><span><em>${x.species}</em></span><span>${x.release_date}</span></div>`).join('')}
function renderNewest(){const x=DATA.recent_assemblies[0]; if(!x){el('newest-card').innerHTML='<div class="image-placeholder"></div><div><h2>Waiting for live data</h2></div>';return;}const img=x.image?.thumb_url?`<img class="taxon-image" src="${x.image.thumb_url}" alt="${x.organism_name}" loading="lazy">`:'<div class="image-placeholder"></div>';el('newest-card').innerHTML=`${img}<div><h2>${x.organism_name}</h2><p>${x.assembly_level} · ${x.accession} · ${(x.total_sequence_length/1e6).toFixed(1)} Mb</p><p>${x.family||x.genus||''}</p>${x.image?.credit?`<p class="credit">${x.image.credit}</p>`:''}</div>`}
function renderGroups(){const rows=DATA.groups_week||[];const m=Math.max(1,...rows.map(x=>x.count));el('group-bars').innerHTML=rows.map(x=>`<div class="group-row"><span>${x.group}</span><span class="group-track"><i class="group-fill" style="width:${100*x.count/m}%"></i></span><b>${x.count}</b></div>`).join('')}
function renderRecent(){el('recent-list').innerHTML=DATA.recent_assemblies.slice(0,16).map(x=>`<div class="recent-row"><span class="meta">${x.release_date}</span><span class="species">${x.organism_name}</span><span class="meta">${x.assembly_name||''}</span><span>${x.assembly_level}</span><span class="meta">${x.accession}</span></div>`).join('')}
function points(rows,key,w=800,h=220,pad=18){if(!rows.length)return'';const vals=rows.map(r=>Number(r[key]||0)),max=Math.max(1,...vals),min=Math.min(0,...vals);return rows.map((r,i)=>{const x=pad+(w-pad*2)*(i/Math.max(1,rows.length-1));const y=pad+(h-pad*2)*(1-(vals[i]-min)/(max-min||1));return `${x.toFixed(1)},${y.toFixed(1)}`}).join(' ')}
function renderRate(){let rows=range==='week'?DATA.daily.slice(-7):range==='year'?DATA.daily.slice(-365):DATA.yearly;const p=points(rows,'assemblies');el('rate-chart').innerHTML=`<line class="grid-line" x1="18" y1="220" x2="782" y2="220"/><polygon class="area-a" points="18,220 ${p} 782,220"/><polyline class="series-a" points="${p}"/>`;const last7=DATA.daily.slice(-7);el('rate7').textContent=(last7.reduce((a,b)=>a+b.assemblies,0)/Math.max(1,last7.length)).toFixed(1);el('rate-title').textContent=range==='all'?'Assemblies deposited per year':'Chromosome-scale genomes deposited per day'}
function renderCumulative(){const rows=DATA.yearly;let ca=0,cf=0;const cum=rows.map(r=>({year:r.year,a:(ca+=r.assemblies),f:(cf+=r.first_time_species)}));el('cumulative-chart').innerHTML=`<line class="grid-line" x1="18" y1="220" x2="782" y2="220"/><polyline class="series-a" points="${points(cum,'a')}"/><polyline class="series-b" points="${points(cum,'f')}"/>`}
