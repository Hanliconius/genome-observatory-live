#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess, time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
DASH=DATA/'dashboard.json'; DAYS_RECENT=int(os.getenv('RECENT_DAYS','370')); OVERLAP=int(os.getenv('OVERLAP_DAYS','14'))
UA='EukaryoteGenomeWatch/0.3 (public research dashboard; contact via repository)'
S=requests.Session(); S.headers.update({'User-Agent':UA})

def run(*args):
    p=subprocess.run(args,text=True,capture_output=True,check=True); return p.stdout

def get_reports(after:str):
    cmd=['datasets','summary','genome','taxon','Eukaryota','--assembly-source','GenBank','--assembly-level','chromosome,complete','--released-after',after,'--as-json-lines']
    out=run(*cmd); return [json.loads(x) for x in out.splitlines() if x.strip()]

def count_all(taxon:str):
    cmd=['datasets','summary','genome','taxon',taxon,'--assembly-source','GenBank','--assembly-level','chromosome,complete','--as-json-lines']
    out=run(*cmd)
    return sum(1 for x in out.splitlines() if x.strip())

def count_since(taxon:str, after:str):
    cmd=['datasets','summary','genome','taxon',taxon,'--assembly-source','GenBank','--assembly-level','chromosome,complete','--released-after',after,'--as-json-lines']
    out=run(*cmd)
    return sum(1 for x in out.splitlines() if x.strip())

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
    common=first(r,'organism.common_name','organism.commonName','common_name','commonName')
    taxid=first(r,'organism.tax_id','organism.taxId','tax_id','organism.taxid')
    release=str(first(r,'assembly_info.release_date','assemblyInfo.releaseDate','assembly.release_date','release_date',default=''))[:10]
    level=first(r,'assembly_info.assembly_level','assemblyInfo.assemblyLevel','assembly_level',default='')
    name=first(r,'assembly_info.assembly_name','assemblyInfo.assemblyName','assembly_name',default='')
    length=first(r,'assembly_stats.total_sequence_length','assemblyStats.totalSequenceLength','assembly_stats.total_sequence_length_bp','total_sequence_length',default=0) or 0
    chromosomes=first(r,'assembly_stats.total_number_of_chromosomes','assemblyStats.totalNumberOfChromosomes','total_number_of_chromosomes',default=0) or 0
    return {'accession':acc,'organism_name':org,'common_name':common,'tax_id':taxid,'release_date':release,'assembly_level':level,'assembly_name':name,'total_sequence_length':int(length or 0),'chromosome_count':int(chromosomes or 0)}

def taxonomy(taxid):
    if not taxid:return {}
    try:
        # Use the same current NCBI Datasets taxonomy fields shown on the NCBI
        # site: curator_common_name first, then group_name (formerly BLAST name).
        payload=json.loads(run('datasets','summary','taxonomy','taxon',str(taxid)))
        tx=first(payload,'reports.0.taxonomy',default={}) or {}
        if not tx:return {}
        out={'_source':'datasets_taxonomy_v1'}
        common=tx.get('curator_common_name')
        group=tx.get('group_name') or tx.get('blast_name')
        if common:
            out['fallback_common_name']=common
            out['fallback_common_name_source']='curator_common_name'
        elif group:
            out['fallback_common_name']=group
            out['fallback_common_name_source']='group_name'
        classification=tx.get('classification') or {}
        for rank in ('genus','family','phylum','kingdom'):
            name=(classification.get(rank) or {}).get('name')
            if name: out[rank]=name
        return out
    except (subprocess.CalledProcessError,json.JSONDecodeError,TypeError,ValueError):
        return {}
def broad_group(tx):
    lineage=' '.join(tx.values()).lower()
    if any(x in lineage for x in ['metazoa','animalia']):return 'Animals'
    if any(x in lineage for x in ['viridiplantae','plantae']):return 'Plants'
    if 'fungi' in lineage:return 'Fungi'
    return 'Other'

def commons_file_info(title):
    api='https://commons.wikimedia.org/w/api.php'
    try:
        q=S.get(api,params={'action':'query','titles':title,'prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':900,'format':'json','origin':'*'},timeout=25).json()
        for p in ((q.get('query') or {}).get('pages') or {}).values():
            ii=(p.get('imageinfo') or [{}])[0]; thumb=ii.get('thumburl')
            if not thumb: continue
            meta=ii.get('extmetadata') or {}
            lic=(meta.get('LicenseShortName') or {}).get('value','')
            artist=re.sub('<[^>]+>','',(meta.get('Artist') or {}).get('value','')).strip()
            return {'thumb_url':thumb,'page_url':ii.get('descriptionurl',''),'credit':' · '.join(x for x in [artist,lic] if x),'matched_name':title}
    except Exception: pass
    return None

def wikidata_image(name):
    if not name: return None
    api='https://www.wikidata.org/w/api.php'
    try:
        hits=S.get(api,params={'action':'wbsearchentities','search':name,'language':'en','type':'item','limit':5,'format':'json'},timeout=25).json().get('search',[])
        for hit in hits:
            qid=hit.get('id')
            if not qid: continue
            ent=(S.get(api,params={'action':'wbgetentities','ids':qid,'props':'claims','format':'json'},timeout=25).json().get('entities') or {}).get(qid) or {}
            p18=(ent.get('claims') or {}).get('P18') or []
            filename=first(p18[0],'mainsnak.datavalue.value') if p18 else None
            if filename:
                info=commons_file_info('File:'+filename)
                if info:
                    info['matched_name']=name
                    return info
    except Exception: pass
    return None

def commons_search(name):
    api='https://commons.wikimedia.org/w/api.php'
    try:
        q=S.get(api,params={'action':'query','generator':'search','gsrsearch':f'intitle:"{name}" filetype:bitmap','gsrnamespace':6,'gsrlimit':6,'prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':900,'format':'json','origin':'*'},timeout=25).json()
        for p in ((q.get('query') or {}).get('pages') or {}).values():
            ii=(p.get('imageinfo') or [{}])[0]; thumb=ii.get('thumburl')
            if not thumb: continue
            meta=ii.get('extmetadata') or {}
            lic=(meta.get('LicenseShortName') or {}).get('value','')
            artist=re.sub('<[^>]+>','',(meta.get('Artist') or {}).get('value','')).strip()
            return {'thumb_url':thumb,'page_url':ii.get('descriptionurl',''),'credit':' · '.join(x for x in [artist,lic] if x),'matched_name':name}
    except Exception: pass
    return None

def commons_image(names):
    for name in [n for n in names if n]:
        info=wikidata_image(name) or commons_search(name)
        if info: return info
        time.sleep(.1)
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

def accession_stem(accession):
    # GCA_123456789.1 -> GCA_123456789; versions of the same
    # GenBank assembly accession are not independent deposit records.
    return str(accession or '').split('.', 1)[0]


def reconstruct_full_history(reports, old, cutoff):
    """Make a complete, checkable baseline from current NCBI records.

    Historical dates, earliest species dates and retained recent accessions
    must come from the SAME full inventory. Nothing is written until update
    finishes and validates its output.
    """
    by_accession={}
    for raw in reports:
        rec=normalise(raw)
        accession=rec['accession']
        day=rec['release_date']
        if not accession or not rec['organism_name'] or not day:
            raise RuntimeError('Full inventory contains an incomplete assembly')
        date.fromisoformat(day)
        if accession in by_accession:
            raise RuntimeError('Duplicate accession in full inventory: '+accession)
        by_accession[accession]=rec

    previous=int(old.get('summary',{}).get('all',{}).get('assemblies',0) or 0)
    if not by_accession or (previous and len(by_accession)<previous*.8):
        raise RuntimeError('Full inventory is unexpectedly incomplete; refusing reconciliation')

    # Reuse existing enriched display metadata when an accession is unchanged.
    cached={x.get('accession'):x for x in old.get('recent_assemblies',[]) if x.get('accession')}
    for accession,rec in by_accession.items():
        if accession in cached:
            extra=cached[accession]
            for key in ('genus','family','phylum','group','image'):
                if extra.get(key): rec[key]=extra[key]
            if not rec.get('common_name'): rec['common_name']=extra.get('common_name')

    daily=defaultdict(lambda:{'assemblies':0,'species':set()})
    first_seen={}
    for rec in by_accession.values():
        day=rec['release_date']
        name=rec['organism_name']
        daily[day]['assemblies']+=1
        daily[day]['species'].add(name)
        if name not in first_seen or day<first_seen[name]:
            first_seen[name]=day
    first_dates=Counter(first_seen.values())
    historical=[{'date':day,'assemblies':row['assemblies'],
                 'species':len(row['species']),
                 'first_time_species':first_dates[day]}
                for day,row in sorted(daily.items())]
    old['daily']=historical
    old['species_first_seen']=first_seen
    old['recent_assemblies']=[x for x in by_accession.values()
                              if x['release_date']>=cutoff]
    # Recompute all-time kingdom counts after an inventory reconciliation.
    old['groups_all']=None
    return len(by_accession),historical,first_seen


def main():
    old=load(); today=date.today(); after=(today-timedelta(days=OVERLAP)).isoformat()
    cutoff=(today-timedelta(days=DAYS_RECENT)).isoformat()
    old_recent=old.get('recent_assemblies',[])
    oldest=min((x.get('release_date','9999-99-99') for x in old_recent),default='9999-99-99')
    metadata_version=int(old.get('metadata_schema_version',0) or 0)
    need_year_backfill=(not old_recent) or oldest>(today-timedelta(days=DAYS_RECENT-30)).isoformat() or metadata_version<2
    full_reconcile=os.getenv('FULL_RECONCILE','0')=='1'
    if full_reconcile:
        from audit_full_history import iterate_ncbi
        count, expected_daily, expected_first=reconstruct_full_history(
            iterate_ncbi(),old,cutoff)
        print(f'Full-history NCBI inventory: {count} assemblies, '
              f'{len(expected_first)} organisms, {len(expected_daily)} dates')
    query_after=cutoff if need_year_backfill or full_reconcile else after
    incoming=(list(old['recent_assemblies']) if full_reconcile else
              [normalise(r) for r in get_reports(query_after)])
    incoming=[x for x in incoming if x['accession'] and x['release_date']]
    byacc={x['accession']:x for x in old_recent if x.get('release_date','')<query_after}
    # Retire old accession versions when the NCBI response provides a new one.
    # Ordinary incremental updates cannot detect unrelated withdrawals outside
    # the overlap window; the quarterly full reconciliation handles those.
    incoming_stems={accession_stem(x['accession']) for x in incoming}
    for accession in list(byacc):
        if accession_stem(accession) in incoming_stems:
            del byacc[accession]
    image_cache=old.get('image_cache',{})
    tax_cache={k:v for k,v in (old.get('taxonomy_cache') or {}).items() if isinstance(v,dict) and v.get('_source')=='datasets_taxonomy_v1'}
    old_byacc={x.get('accession'):x for x in old_recent if x.get('accession')}
    for x in incoming:
        if x['release_date']>=after:
            tid=str(x.get('tax_id') or '')
            if tid not in tax_cache: tax_cache[tid]=taxonomy(x.get('tax_id'))
            tx=tax_cache[tid]
            previous=old_byacc.get(x['accession'],{})
            x.update({k:(tx.get(k) or previous.get(k)) for k in ('genus','family','phylum')})
            x['group']=broad_group(tx) if tx else previous.get('group','Other')
            if not x.get('common_name'):
                x['common_name']=tx.get('fallback_common_name') or previous.get('common_name')
            key=x['organism_name']
            if not image_cache.get(key): image_cache[key]=commons_image([x['organism_name'],tx.get('genus'),tx.get('family')])
            x['image']=image_cache.get(key)
        stem=accession_stem(x['accession'])
        for obsolete in [a for a in byacc if accession_stem(a)==stem and a!=x['accession']]:
            del byacc[obsolete]
        byacc[x['accession']]=x
    recent=sorted([x for x in byacc.values() if x['release_date']>=cutoff],key=lambda z:(z['release_date'],z['accession']),reverse=True)

    # Backfill the rows most likely to appear in the rolling metadata table.
    # NCBI's BlastName is intentionally broad (for example "beetles" or "snakes")
    # and mirrors the fallback label shown by NCBI when no species common name exists.
    for x in recent[:60]:
        if x.get('common_name'):
            continue
        tid=str(x.get('tax_id') or '')
        if not tid:
            continue
        if tid not in tax_cache:
            tax_cache[tid]=taxonomy(x.get('tax_id'))
        tx=tax_cache[tid]
        if tx.get('fallback_common_name'):
            x['common_name']=tx['fallback_common_name']

    daily={r['date']:r for r in old.get('daily',[]) if r['date']<after}
    grouped=defaultdict(list)
    for x in recent:
        if x['release_date']>=after:grouped[x['release_date']].append(x)
    first_seen=old.get('species_first_seen',{})
    for ds,xs in grouped.items():
        orgs={x['organism_name'] for x in xs}
        for o in orgs:
            if o not in first_seen or ds<first_seen[o]:
                first_seen[o]=ds
        # Rebuilding a previously recorded day must still credit the first
        # release of species whose earliest date is exactly this day.
        new=sum(first_seen[o]==ds for o in orgs)
        daily[ds]={'date':ds,'assemblies':len(xs),'species':len(orgs),'first_time_species':new}
    start=min([date.fromisoformat(x) for x in daily] or [today]);cur=start
    while cur<=today:
        ds=cur.isoformat();daily.setdefault(ds,{'date':ds,'assemblies':0,'species':0,'first_time_species':0});cur+=timedelta(days=1)
    daily_rows=sorted(daily.values(),key=lambda r:r['date'])
    yearly_map=defaultdict(lambda:{'assemblies':0,'species':0,'first_time_species':0})
    for r in daily_rows:
        y=r['date'][:4];yearly_map[y]['assemblies']+=r['assemblies'];yearly_map[y]['species']+=r['species'];yearly_map[y]['first_time_species']+=r['first_time_species']
    yearly=[{'year':y,**v} for y,v in sorted(yearly_map.items())]

    def period_summary(days):
        cutoff_date=(today-timedelta(days=days-1)).isoformat()
        rr=[r for r in daily_rows if r['date']>=cutoff_date]
        xs=[x for x in recent if x['release_date']>=cutoff_date]
        return {
            'assemblies':sum(r['assemblies'] for r in rr),
            'species':len({x['organism_name'] for x in xs}),
            'first_time_species':sum(r['first_time_species'] for r in rr)
        }

    all_summary={
        'assemblies':sum(r['assemblies'] for r in daily_rows),
        'species':len(first_seen),
        'first_time_species':len(first_seen)
    }
    # Historical assembly-count milestones. Start with 10, 100, 1,000 and
    # 10,000, then add each further 10,000 automatically as it is crossed.
    total_assemblies=all_summary['assemblies']
    milestone_targets=[x for x in (10,100,1000,10000) if x<=total_assemblies]
    milestone_targets += list(range(20000,(total_assemblies//10000)*10000+1,10000))
    milestones=[]
    cumulative=0
    target_i=0
    for row in daily_rows:
        cumulative += int(row.get('assemblies',0) or 0)
        while target_i<len(milestone_targets) and cumulative>=milestone_targets[target_i]:
            milestones.append({'threshold':milestone_targets[target_i],'date':row['date']})
            target_i += 1

    # Choose the newest recent assembly for which Wikimedia can provide an image.
    # Re-resolve each candidate in chronological order (species -> genus -> family)
    # so stale cache state cannot select the card. If the newest species has no
    # image, continue down the current genome list until one does.
    featured=None
    for x in recent[:40]:
        key=x['organism_name']
        tx={k:x.get(k) for k in ('genus','family','phylum') if x.get(k)}
        if not tx.get('genus') or not tx.get('family'):
            tid=str(x.get('tax_id') or '')
            if tid not in tax_cache: tax_cache[tid]=taxonomy(x.get('tax_id'))
            tx={**tax_cache.get(tid,{}),**tx}
            x.update({k:tx.get(k) for k in ('genus','family','phylum') if tx.get(k)})
            if not x.get('group'): x['group']=broad_group(tx)
        image=commons_image([x['organism_name'],tx.get('genus'),tx.get('family')])
        if image:
            image_cache[key]=image
            x['image']=image
            featured=x
            break
        # A previous cached image may be stale or no longer resolve; do not let it
        # keep this species featured when the current Wikimedia lookup failed.
        x['image']=None

    groups=Counter(x.get('group','Other') for x in recent if x['release_date']>=(today-timedelta(days=6)).isoformat())

    year_cutoff=(today-timedelta(days=364)).isoformat()
    year_total=period_summary(365)['assemblies']
    year_animals=count_since('Metazoa',year_cutoff)
    year_plants=count_since('Viridiplantae',year_cutoff)
    year_fungi=count_since('Fungi',year_cutoff)
    groups_year=[
        {'group':'Animals','count':year_animals},
        {'group':'Plants','count':year_plants},
        {'group':'Fungi','count':year_fungi},
        {'group':'Other','count':max(0,year_total-year_animals-year_plants-year_fungi)}
    ]

    groups_all=old.get('groups_all')
    if not groups_all:
        animals=count_all('Metazoa')
        plants=count_all('Viridiplantae')
        fungi=count_all('Fungi')
        total=all_summary['assemblies']
        groups_all=[
            {'group':'Animals','count':animals},
            {'group':'Plants','count':plants},
            {'group':'Fungi','count':fungi},
            {'group':'Other','count':max(0,total-animals-plants-fungi)}
        ]
    out={'generated_at':datetime.now(timezone.utc).isoformat(),'metadata_schema_version':2,'summary':{'week':period_summary(7),'year':period_summary(365),'all':all_summary},'daily':daily_rows,'yearly':yearly,'groups_week':[{'group':k,'count':v} for k,v in groups.most_common()],'groups_year':groups_year,'groups_all':groups_all,'milestones':milestones,'featured_assembly':featured,'recent_assemblies':recent,'annotations':annotation_status(),'species_first_seen':first_seen,'image_cache':image_cache,'taxonomy_cache':tax_cache}
    if full_reconcile:
        expected_by_date={row['date']:row for row in expected_daily}
        actual_by_date={row['date']:row for row in daily_rows}
        for ds,ref in expected_by_date.items():
            if any(int(actual_by_date.get(ds,{}).get(k,-1))!=ref[k]
                   for k in ('assemblies','species','first_time_species')):
                raise RuntimeError('Reconciliation mismatch on date '+ds)
        if (all_summary['assemblies']!=count or
                all_summary['species']!=len(expected_first) or
                first_seen!=expected_first):
            raise RuntimeError('Reconciliation failed source inventory invariants')
        current_recent={x['accession'] for x in recent}
        source_recent={x['accession'] for x in old_recent if x['release_date']>=cutoff}
        if current_recent!=source_recent:
            raise RuntimeError('Reconciliation recent accession mismatch')
        print('PASS: full-history assembly, species, daily and recent-accession invariants')
    write(out);print(f"wrote {DASH}: {len(recent)} recent assemblies, {len(daily_rows)} daily summaries, year_backfill={need_year_backfill}")
if __name__=='__main__':main()


