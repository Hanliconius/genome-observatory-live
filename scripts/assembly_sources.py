#!/usr/bin/env python3
"""Build one version-deduplicated NCBI inventory for every dashboard builder.

Datasets supplies enriched reports. Entrez Assembly supplies independently
discovered, current GenBank records while Datasets indexing catches up.
The complete merged JSONL is temporary; only pending reports and the audit
are persisted. No source count is ever added to another source count.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'cache/assembly_index_pending.json'
AUDIT=ROOT/'data/audits/assembly_sources.json'
GROUPS={'Metazoa':'Animals','Viridiplantae':'Plants','Fungi':'Fungi'}
BASE=['datasets','summary','genome','taxon']
FLAGS=['--assembly-source','GenBank','--assembly-level','chromosome,complete','--as-json-lines']
EUTILS='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'


def stem(accession):
    return str(accession).split('.')[0]


def version(accession):
    m=re.fullmatch(r'GCA_\d+\.(\d+)',str(accession))
    if not m:raise ValueError('Not a versioned GenBank accession: '+str(accession))
    return int(m.group(1))


def read_jsonl(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip():yield json.loads(line)


def datasets_reports(taxon,ids_only=False):
    cmd=BASE+[taxon]+FLAGS+(['--report','ids_only'] if ids_only else [])
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
    if p.returncode:raise RuntimeError('Datasets failed: '+p.stderr[-1500:])
    return [json.loads(x) for x in p.stdout.splitlines() if x.strip()]


def request(endpoint,params,json_result=False):
    # Fail closed on a source error; do not publish a partial discovery query.
    for attempt in range(3):
        try:
            r=requests.get(EUTILS+endpoint,params=params,timeout=90)
            r.raise_for_status();result=r.json() if json_result else ET.fromstring(r.content)
            if json_result and result.get('error'):raise RuntimeError(str(result['error']))
            time.sleep(.4)
            return result
        except (requests.RequestException,ValueError,ET.ParseError):
            if attempt==2:raise
            time.sleep(1+attempt)


def summaries(ids):
    rows=[];ids=sorted(set(str(x) for x in ids))
    for start in range(0,len(ids),100):
        result=request('esummary.fcgi',dict(db='assembly',id=','.join(ids[start:start+100]),retmode='json',report='full'),True)['result']
        batch=[result[x] for x in result['uids']]
        if any(x.get('error') for x in batch):raise RuntimeError('Assembly summary contains an unresolved UID')
        rows.extend(batch)
    if len(rows)!=len(ids):raise RuntimeError('Incomplete Assembly summary response')
    return rows


def discover(after,until,held_ids=()):
    ds=lambda d:d.replace('-','/')
    date_terms=' OR '.join(f'"{ds(after)}"[{field}]:"{ds(until)}"[{field}]' for field in ('GRLS','SRDT','UPDT'))
    term='txid2759[Organism:exp] AND latest_genbank[filter] AND ("chromosome level"[filter] OR "complete genome"[filter]) AND ('+date_terms+')'
    ids=[];start=0;total=None
    while total is None or start<total:
        result=request('esearch.fcgi',dict(db='assembly',term=term,retmode='json',retmax=1000,retstart=start),True)['esearchresult']
        if result.get('errorlist'):raise RuntimeError('Invalid Assembly query: '+str(result['errorlist']))
        total=int(result['count']);ids.extend(result['idlist']);start+=1000
        if total>9999:raise RuntimeError('Assembly discovery exceeds Entrez retrieval limit; narrow the date window')
    if len(set(ids))!=total:raise RuntimeError('Assembly search pagination was incomplete')
    return summaries(set(ids)|set(held_ids)),dict(query=term,matched_uids=total,held_uids_rechecked=len(set(held_ids)))


def taxonomy(ids):
    result={};ids=sorted(set(str(x) for x in ids if x))
    for start in range(0,len(ids),100):
        root=request('efetch.fcgi',dict(db='taxonomy',id=','.join(ids[start:start+100]),retmode='xml'))
        for t in root.findall('Taxon'):
            lineage=t.findtext('Lineage','');name=t.findtext('ScientificName','')
            group=next((v for k,v in GROUPS.items() if k in lineage.split('; ')),'Other')
            result[t.findtext('TaxId')]=dict(name=name,eukaryote='Eukaryota' in lineage.split('; '),group=group)
    if set(ids)-set(result):raise RuntimeError('Assembly taxon lineage could not be verified')
    return result


def iso_date(value):
    value=str(value or '')[:10].replace('/','-')
    try:date.fromisoformat(value)
    except ValueError:raise ValueError('Invalid source release date: '+value)
    return value


def assembly_report(row,taxon):
    acc=row.get('synonym',{}).get('genbank') or row.get('assemblyaccession','')
    props=set(row.get('propertylist',[]))
    if (not re.fullmatch(r'GCA_\d+\.\d+',acc) or 'latest_genbank' not in props
            or row.get('assemblystatus') not in ('Chromosome','Complete Genome')
            or not taxon['eukaryote']):return None
    stats={}
    root=ET.fromstring('<Meta>'+row.get('meta','')+'</Meta>')
    mapping={'total_length':'total_sequence_length','chromosome_count':'total_number_of_chromosomes',
             'contig_count':'number_of_contigs','scaffold_count':'number_of_scaffolds',
             'contig_n50':'contig_n50','scaffold_n50':'scaffold_n50'}
    for x in root.findall('.//Stat'):
        if x.get('sequence_tag')=='all' and x.get('category') in mapping:
            stats[mapping[x.get('category')]]=int(x.text)
    info=dict(assembly_level=row['assemblystatus'],assembly_name=row.get('assemblyname',''),
              release_date=iso_date(row['seqreleasedate']),assembly_status='current',
              submitter=row.get('submitterorganization',''))
    if row.get('biosampleaccn'):info['biosample']=dict(accession=row['biosampleaccn'])
    projects=row.get('gb_bioprojects') or []
    if projects and projects[0].get('bioprojectaccn'):info['bioproject_accession']=projects[0]['bioprojectaccn']
    return dict(accession=acc,current_accession=acc,source_database='SOURCE_DATABASE_GENBANK',
                organism=dict(organism_name=taxon['name'],tax_id=int(row['taxid'])),
                assembly_info=info,assembly_stats=stats,
                _observatory=dict(sources=['assembly_index'],metadata_pending=True,assembly_uid=str(row['uid']),
                                  group=taxon['group'],sequence_release_date=info['release_date'],
                                  assembly_publication_date=iso_date(row['asmreleasedate_genbank'])))


def enrich_biosamples(reports):
    # Geography remains available while the bundled Datasets report is pending.
    by_id={}
    for r in reports:
        acc=r['assembly_info'].get('biosample',{}).get('accession')
        if acc:by_id.setdefault(acc,[]).append(r)
    ids=sorted(by_id)
    for start in range(0,len(ids),100):
        root=request('efetch.fcgi',dict(db='biosample',id=','.join(ids[start:start+100]),retmode='xml'))
        for sample in root.findall('.//BioSample'):
            acc=sample.get('accession');matches=by_id.get(acc,[])
            if not matches:continue
            attributes=[dict(name=x.get('harmonized_name') or x.get('attribute_name'),value=x.text or '') for x in sample.findall('Attributes/Attribute')]
            for r in matches:
                r['assembly_info']['biosample'].update(attributes=attributes)
                r['_observatory']['biosample_enriched']=True


def prefer_present(old,new):
    """Refresh known values without erasing same-version metadata with blanks."""
    result=copy.deepcopy(old)
    for k,v in new.items():
        if isinstance(v,dict) and isinstance(result.get(k),dict):result[k]=prefer_present(result[k],v)
        elif v is not None and v!='' and v!=[] and v!={}:result[k]=copy.deepcopy(v)
    return result


def merge_reports(datasets,index):
    """Highest version wins; Datasets enriches the same version exactly once."""
    by_stem={};duplicates=0;conflicts=[]
    for source,reports in [('assembly_index',index),('datasets',datasets)]:
        for raw in reports:
            r=copy.deepcopy(raw);acc=r['accession'];ver=version(acc)
            info=r.get('assembly_info',{})
            if info.get('assembly_level','').lower() not in ('chromosome','complete genome','complete'):continue
            iso_date(info.get('release_date'))
            state=info.get('assembly_status','current').lower()
            if state in ('replaced','suppressed','withdrawn'):continue
            meta=r.setdefault('_observatory',{});meta.setdefault('sources',[source])
            if source=='datasets':meta['metadata_pending']=False
            key=stem(acc);old=by_stem.get(key)
            if old and version(old['accession'])>ver:duplicates+=1;continue
            if old and version(old['accession'])==ver:
                duplicates+=1
                if old['assembly_info']['release_date']!=info['release_date']:
                    conflicts.append(dict(accession=acc,index_date=old['assembly_info']['release_date'],datasets_date=info['release_date']))
                # Datasets is authoritative for bundled metadata on the same
                # accession/version. Preserve the discovery trail underneath.
                trail=dict(old.get('_observatory',{}));trail.update(meta)
                trail['sources']=sorted(set(old['_observatory']['sources'])|set(meta['sources']))
                r=prefer_present(old,r)
                r['_observatory']=trail
            elif old:duplicates+=1
            by_stem[key]=r
    result=sorted(by_stem.values(),key=lambda r:r['accession'])
    assert len(result)==len({stem(r['accession']) for r in result})
    return result,dict(overlapping_or_superseded_rows_removed=duplicates,date_conflicts=conflicts)


def prepare(output,datasets_jsonl=None):
    today=datetime.now(timezone.utc).date();after=(today-timedelta(days=30)).isoformat()
    ds=list(read_jsonl(datasets_jsonl)) if datasets_jsonl else datasets_reports('Eukaryota')
    previous=json.loads((ROOT/'data/dashboard.json').read_text())
    if len(ds)<previous['summary']['all']['assemblies']*.8:raise RuntimeError('Datasets inventory unexpectedly incomplete')
    held=json.loads(CACHE.read_text()) if CACHE.exists() else []
    rows,query=discover(after,today.isoformat(),[r['_observatory']['assembly_uid'] for r in held])
    # Taxonomy supplies exact scientific names, not the display label's common name.
    ds_by_acc={r['accession']:r for r in ds}
    tax=taxonomy([r['taxid'] for r in rows if (r.get('synonym',{}).get('genbank') or r.get('assemblyaccession')) not in ds_by_acc])
    index=[]
    held_by_acc={r['accession']:r for r in held}
    for row in rows:
        acc=row.get('synonym',{}).get('genbank') or row.get('assemblyaccession')
        known=ds_by_acc.get(acc)
        t=(dict(name=known['organism']['organism_name'],eukaryote=True,group='Other') if known else tax[str(row['taxid'])])
        r=assembly_report(row,t)
        if r:index.append(prefer_present(held_by_acc.get(r['accession'],{}),r))
    ds_accessions={r['accession'] for r in ds}
    pending=[r for r in index if r['accession'] not in ds_accessions]
    enrich_biosamples(pending)
    # Small identifier-only responses classify the complete Datasets inventory.
    groups={}
    for taxon,group in GROUPS.items():
        for r in datasets_reports(taxon,True):groups[stem(r['accession'])]=group
    for r in ds:r.setdefault('_observatory',{})['group']=groups.get(stem(r['accession']),'Other')
    merged,audit=merge_reports(ds,index)
    current_pending=[r for r in merged if r['_observatory'].get('metadata_pending')]
    audit.update(query,generated_at=datetime.now(timezone.utc).isoformat(),datasets_rows=len(ds),assembly_index_rows=len(index),
                 merged_assemblies=len(merged),unique_accession_stems=len({stem(r['accession']) for r in merged}),
                 pending_metadata_accessions=[r['accession'] for r in current_pending],
                 pending_records=[dict(accession=r['accession'],species=r['organism']['organism_name'],
                                      release_date=r['assembly_info']['release_date'],level=r['assembly_info']['assembly_level']) for r in current_pending],
                 previous_dashboard_assemblies=previous['summary']['all']['assemblies'])
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.partial')
    with temporary.open('w') as f:
        for r in merged:f.write(json.dumps(r,separators=(',',':'))+'\n')
    temporary.replace(output)
    CACHE.write_text(json.dumps(current_pending,separators=(',',':'))+'\n')
    AUDIT.write_text(json.dumps(audit,indent=2)+'\n')
    print('Shared inventory:',len(ds),'Datasets rows +',len(index),'Assembly records →',len(merged),'unique GenBank accessions;',len(current_pending),'awaiting Datasets metadata')
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--datasets-jsonl');a=p.parse_args()
    prepare(a.output,a.datasets_jsonl)
