#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess, time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
DASH=DATA/'dashboard.json'; DAYS_RECENT=int(os.getenv('RECENT_DAYS','90')); OVERLAP=int(os.getenv('OVERLAP_DAYS','14'))
UA='EukaryoteGenomeWatch/0.1 (public research dashboard; contact via repository)'
S=requests.Session(); S.headers.update({'User-Agent':UA})

def run(*args):
    p=subprocess.run(args,text=True,capture_output=True,check=True); return p.stdout

def get_reports(after:str):
    cmd=['datasets','summary','genome','taxon','Eukaryota','--assembly-source','GenBank','--assembly-level','chromosome,complete','--released-after',after,'--as-json-lines']
    out=run(*cmd); return [json.loads(x) for x in out.splitlines() if x.strip()]

def first(d,*paths,default=None):
    for path in paths:
        x=d
        try:
            for k in path.split('.'): x=x[int(k)] if isinstance(x,list) else x[k]
            if x not in (None,''): return x
        except (KeyError,IndexError,TypeError,ValueError): pass
    return default

def normalise(r):
    acc=first(r,'accession','assembly.accession','assembly_info.assembly_accession',default='')
    org=first(r,'organism.organism_name','organism_name','organism.name',default='Unknown')
    taxid=first(r,'organism.tax_id','tax_id','organism.taxid')
    release=str(first(r,'assembly_info.release_date','assembly.release_date','release_date',default=''))[:10]
    level=first(r,'assembly_info.assembly_level','assembly_level',default='')
    name=first(r,'assembly_info.assembly_name','assembly_name',default='')
    length=first(r,'assembly_stats.total_sequence_length','assembly_stats.total_sequence_length_bp','total_sequence_length',default=0) or 0
    return {'accession':acc,'organism_name':org,'tax_id':taxid,'release_date':release,'assembly_level':level,'assembly_name':name,'total_sequence_length':int(length or 0)}

def taxonomy(taxid):
    if not taxid:return {}
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
    txt=S.get(url,params={'db':'taxonomy','id':taxid},timeout=30).text
    soup=BeautifulSoup(txt,'xml'); out={}
    for t in soup.select('LineageEx Taxon'):
        rank=(t.Rank.text if t.Rank else '').lower(); name=t.ScientificName.text if t.ScientificName else ''
        if rank in {'genus','family','phylum','kingdom','superkingdom'}: out[rank]=name
    return out

def broad_group(tx):
    lineage=' '.join(tx.values()).lower()
    if any(x in lineage for x in ['metazoa','animalia']):return 'Animals'
    if any(x in lineage for x in ['viridiplantae','plantae']):return 'Plants'
    if 'fungi' in lineage:return 'Fungi'
    return 'Other'

def commons_image(names):
    api='https://commons.wikimedia.org/w/api.php'
    for name in [n for n in names if n]:
        try:
            q=S.get(api,params={'action':'query','generator':'search','gsrsearch':f'intitle:"{name}" filetype:bitmap','gsrnamespace':6,'gsrlimit':6,'prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':900,'format':'json','origin':'*'},timeout=25).json()
            pages=(q.get('query') or {}).get('pages') or {}
            for p in pages.values():
                ii=(p.get('imageinfo') or [{}])[0]; meta=ii.get('extmetadata') or {}; thumb=ii.get('thumburl')
                if not thumb: continue
                lic=(meta.get('LicenseShortName') or {}).get('value',''); artist=re.sub('<[^>]+>','',(meta.get('Artist') or {}).get('value','')).strip()
                credit=' · '.join(x for x in [artist,lic] if x)
                return {'thumb_url':thumb,'page_url':ii.get('descriptionurl',''),'credit':credit,'matched_name':name}
        except Exception: pass
        time.sleep(.15)
    return None

def annotation_status():
    html=S.get('https://www.ncbi.nlm.nih.gov/refseq/annotation_euk/status/',timeout=30).text
    soup=BeautifulSoup(html,'lxml'); tables=soup.find_all('table')
    out={'in_progress':[],'recent_completed':[]}
    for table in tables:
        heads=[th.get_text(' ',strip=True) for th in table.find_all('th')]
        rows=[]
        for tr in table.find_all('tr'):
            cells=[x.get_text(' ',strip=True) for x in tr.find_all(['td','th'])]
            if not cells or cells==heads:continue
            if len(cells)>=len(heads): rows.append(dict(zip(heads,cells)))
        if heads and 'Status' in heads:
            for r in rows: out['in_progress'].append({'species':re.sub(r'\s*\([^)]*\)\s*$','',r.get('Species','')),'status':r.get('Status',''),'freeze_date':r.get('Freeze Date',''),'assembly':r.get('RefSeq assembly(ies)','')})
        elif heads and 'Release Date' in heads:
            for r in rows: out['recent_completed'].append({'species':re.sub(r'\s*\([^)]*\)\s*$','',r.get('Species','')),'release_date':r.get('Release Date',''),'assembly':r.get('RefSeq assembly(ies)','')})
    return out

def load():
    if DASH.exists(): return json.loads(DASH.read_text())
    return {'recent_assemblies':[],'daily':[],'yearly':[],'species_first_seen':{},'image_cache':{}}

def write(d): DASH.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n")

def main():
    old=load(); today=date.today(); after=(today-timedelta(days=OVERLAP)).isoformat()
    incoming=[normalise(r) for r in get_reports(after)]
    incoming=[x for x in incoming if x['accession'] and x['release_date']]
    byacc={x['accession']:x for x in old.get('recent_assemblies',[]) if x.get('release_date','')<after}
    image_cache=old.get('image_cache',{})
    for x in incoming:
        tx=taxonomy(x.get('tax_id')); x.update({k:tx.get(k) for k in ('genus','family','phylum')});x['group']=broad_group(tx)
        key=x['organism_name']
        if key not in image_cache: image_cache[key]=commons_image([x['organism_name'],tx.get('genus'),tx.get('family')])
        x['image']=image_cache.get(key);byacc[x['accession']]=x
    cutoff=(today-timedelta(days=DAYS_RECENT)).isoformat(); recent=sorted([x for x in byacc.values() if x['release_date']>=cutoff],key=lambda z:(z['release_date'],z['accession']),reverse=True)

    daily={r['date']:r for r in old.get('daily',[]) if r['date']<after}
    grouped=defaultdict(list)
    for x in recent:
        if x['release_date']>=after:grouped[x['release_date']].append(x)
    first_seen=old.get('species_first_seen',{})
    for ds,xs in grouped.items():
        orgs={x['organism_name'] for x in xs};new=0
        for o in orgs:
            if o not in first_seen or ds<first_seen[o]: first_seen[o]=ds;new+=1
        daily[ds]={'date':ds,'assemblies':len(xs),'species':len(orgs),'first_time_species':new}
    start=min([date.fromisoformat(x) for x in daily] or [today]);cur=start
    while cur<=today:
        ds=cur.isoformat();daily.setdefault(ds,{'date':ds,'assemblies':0,'species':0,'first_time_species':0});cur+=timedelta(days=1)
    daily_rows=sorted(daily.values(),key=lambda r:r['date'])
    yearly_map=defaultdict(lambda:{'assemblies':0,'species':0,'first_time_species':0})
    for r in daily_rows:
        y=r['date'][:4];yearly_map[y]['assemblies']+=r['assemblies'];yearly_map[y]['species']+=r['species'];yearly_map[y]['first_time_species']+=r['first_time_species']
    yearly=[{'year':y,**v} for y,v in sorted(yearly_map.items())]

    def smry(days=None):
        rr=daily_rows if days is None else [r for r in daily_rows if r['date']>=(today-timedelta(days=days-1)).isoformat()]
        return {'assemblies':sum(r['assemblies'] for r in rr),'species':sum(r['species'] for r in rr),'first_time_species':sum(r['first_time_species'] for r in rr)}

    groups=Counter(x.get('group','Other') for x in recent if x['release_date']>=(today-timedelta(days=6)).isoformat())
    out={'generated_at':datetime.now(timezone.utc).isoformat(),'summary':{'week':smry(7),'year':smry(365),'all':smry()},'daily':daily_rows[-8000:],'yearly':yearly,'groups_week':[{'group':k,'count':v} for k,v in groups.most_common()],'recent_assemblies':recent,'annotations':annotation_status(),'species_first_seen':first_seen,'image_cache':image_cache}
    write(out);print(f"wrote {DASH}: {len(recent)} recent assemblies, {len(daily_rows)} daily summaries")
if __name__=='__main__':main()
