#!/usr/bin/env python3
"""Explicit, auditable catalogue refresh; not run during daily genome updates."""
import argparse
import csv
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from build_agriculture import taxon_key
from audit_full_history import iterate_ncbi

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / 'data/status'
TODAY = date.today().isoformat()
FIELDS = ['species','section','group','disease','source_url','aliases','notes','tax_id']
MEMBER_FIELDS = ['species','tax_id','source_id','original_name','source_role','assigned_role','host_or_commodity','evidence_url','reference_urls','basis','matching_scope']


def read_tsv(path):
    with path.open() as f: return list(csv.DictReader(f, delimiter='\t'))


def write_tsv(path, rows, fields):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t', lineterminator='\n', extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def cache_get(cache, key, url):
    p = cache / key
    if not p.exists():
        r = requests.get(url, timeout=90); r.raise_for_status(); p.write_bytes(r.content)
    return p.read_bytes()


def collect_candidates(cache, reports, existing):
    candidates, sources, rejected = [], {}, []
    def register(sid, name, url, version, scope, filename=None, license=''):
        content = cache_get(cache, filename, url) if filename else b''
        sources[sid] = dict(source_id=sid,name=name,url=url,version=version,retrieved_at=TODAY,scope=scope,license=license,
                            sha256=hashlib.sha256(content).hexdigest() if content else '',country='United States' if sid in ('ag100_targets','ag100_releases','caps_2026','aphis_vet') else '')
        return content
    def add(sid, name, section='', group='', role='', host='', url='', refs='', basis='species-listed', tid='', match_name=''):
        if not taxon_key(match_name or name) and not tid:
            rejected.append(dict(source_id=sid,original_name=name,reason='Not an explicit species or named hybrid'));return
        candidates.append(dict(source_id=sid,original_name=name,section=section,group=group,disease=role,host_or_commodity=host,
                               evidence_url=url or sources[sid]['url'],reference_urls=refs,basis=basis,tax_id=str(tid),match_name=match_name or name))
    legacy_sources = {
        'fao_crops':('FAO crops','https://www.fao.org/4/a0135e/A0135E10.htm','Agricultural census botanical crop entries'),
        'fao_livestock':('FAO livestock','https://www.fao.org/livestock-systems/global-distributions/en/','Livestock and poultry'),
        'fao_aquaculture':('FAO aquaculture','https://www.fao.org/4/W2333E/W2333E00.htm','Selected cultured aquatic species'),
        'eppo':('EPPO','https://gd.eppo.int/datasheets/','Selected legacy records plus the complete public datasheet index; plant health, forestry and invasive weeds'),
        'woah':('WOAH','https://www.woah.org/en/what-we-do/animal-health-and-welfare/animal-diseases/','Selected livestock disease records'),
    }
    for sid,(name,url,scope) in legacy_sources.items(): register(sid,name,url,'legacy catalogue reviewed 2026-10-11',scope)
    for x in existing:
        url=x['source_url'];sid='eppo' if 'eppo.int' in url else 'woah' if 'woah.org' in url else 'fao_livestock' if 'livestock-systems' in url else 'fao_aquaculture' if 'W2333E' in url else 'fao_crops'
        add(sid,x['species'],x['section'],x['group'],x['disease'],url=url,tid=x.get('tax_id') or (re.search(r'wwwtax.cgi\?id=(\d+)',x.get('notes','')).group(1) if re.search(r'wwwtax.cgi\?id=(\d+)',x.get('notes','')) else ''),basis='retained curated species')
    raw=register('ag100_targets','Ag100Pest targets','https://i5k.github.io/ag100pest','2021-03-09 target table','USDA agricultural arthropod project targets; includes biological-control associates','ag100pest.html')
    for tr in BeautifulSoup(raw,'html.parser').select('table tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all('td')]
        if len(cells)==4:
            order,family,name,common=cells
            add('ag100_targets',name,'pests','Livestock arthropod pests' if order=='Ixodida' else 'Insect pests',common,basis='Ag100Pest target; primary role reviewed separately')
    register('ag100_releases','Ag100Pest BioProject','https://www.ncbi.nlm.nih.gov/bioproject/PRJNA555319',TODAY,'Species in qualifying GenBank reports whose BioProject lineage includes PRJNA555319; complements the older target list')
    for r in reports:
        ai=r.get('assembly_info',{});projects=[p for lineage in ai.get('bioproject_lineage',[]) for p in lineage.get('bioprojects',[])]
        if any(p.get('accession')=='PRJNA555319' for p in projects):
            name=r['organism']['organism_name'];project=next((p for p in projects if p.get('accession')!='PRJNA555319'),{})
            add('ag100_releases',name,'pests','', 'USDA Ag100Pest genome project',url='https://www.ncbi.nlm.nih.gov/bioproject/'+project.get('accession','PRJNA555319'),tid=r['organism'].get('tax_id',''),basis='Verified BioProject ancestry in NCBI assembly metadata')
    raw=register('caps_2026','USDA CAPS 2026','https://approvedmethods.ceris.purdue.edu/2026','2026','US national priority plant-pest surveillance; includes crop, forestry and ornamental hosts','caps_2026.html')
    for tr in BeautifulSoup(raw,'html.parser').select('table tr'):
        cells=tr.find_all('td')
        if len(cells)<4: continue
        name=cells[1].get_text(' ',strip=True);a=cells[0].find('a',href=True)
        add('caps_2026',name,role=cells[2].get_text(' ',strip=True),host=cells[3].get_text(' ',strip=True),url=requests.compat.urljoin(sources['caps_2026']['url'],a['href']) if a else '')
    raw=register('aphis_vet','USDA APHIS veterinary','https://www.aphis.usda.gov/animal-product-import/organisms-vectors/livestock-poultry-pathogens','2026-09-03','Partial regulated livestock/poultry agents and vectors list; species-level eukaryotes only','aphis_vet.html')
    soup=BeautifulSoup(raw,'html.parser');main=soup.find('main') or soup
    for li in main.select('li'):
        original=li.get_text(' ',strip=True)
        if re.match(r'^[A-Z][a-z]+ [a-z]',original):
            add('aphis_vet',original,host='Livestock / poultry',role='Regulated veterinary agent or vector',basis='Species-level entry on APHIS veterinary list')
    raw=cache_get(cache,'eppo_datasheets.html',sources['eppo']['url']);sources['eppo'].update(version='datasheet index snapshot '+TODAY,retrieved_at=TODAY,sha256=hashlib.sha256(raw).hexdigest())
    type_groups={'Insecta':('pests','Insect pests'),'Acari':('pests','Mite pests'),'Nematoda':('pests','Nematode pests'),'Gastropoda':('pests','Mollusc pests'),'Plantae':('pests','Weeds'),'Fungi':('pathogens','Fungal plant pathogens'),'Chromista':('pathogens','Oomycete plant pathogens')}
    for tr in BeautifulSoup(raw,'html.parser').select('table tr'):
        cells=tr.find_all('td')
        if len(cells)<2:continue
        typ=cells[0].get_text(' ',strip=True);name=cells[1].get_text(' ',strip=True)
        if typ not in type_groups:
            rejected.append(dict(source_id='eppo',original_name=name,reason='Source group outside eukaryotic scope'));continue
        section,group=type_groups[typ];a=cells[1].find('a',href=True)
        add('eppo',name,section,group,'EPPO plant-health datasheet',url=requests.compat.urljoin(sources['eppo']['url'],a['href']) if a else '')
    # Published PHI-base snapshot is paired with listed agricultural hosts.
    import zipfile
    metadata_url='https://zenodo.org/api/records/21196331'
    metadata=json.loads(cache_get(cache,'phibase_metadata.json',metadata_url))
    register('phibase_5_6','PHI-base 5.6','https://zenodo.org/records/21196331','5.6 (2026-07-04)','Experimentally studied interactions involving listed agricultural hosts; bacteria and non-agricultural hosts excluded',license='CC-BY-4.0')
    archive=cache/'phi-base_v5.6.zip'
    cache_get(cache,archive.name,metadata['files'][0]['links']['self']);sources['phibase_5_6']['sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as z: data=json.loads(z.read('phi-base_v5.6/phi-base_v5.6.json'))
    hosts={taxon_key(n) for x in existing if x['section']=='organisms' for n in [x['species']]+x['aliases'].split('|')}
    for session in data['curation_sessions'].values():
        organisms=session.get('organisms',{});genotypes=session.get('genotypes',{})
        for m in session.get('metagenotypes',{}).values():
            if m.get('type')!='pathogen-host':continue
            ht=str(genotypes.get(m.get('host_genotype'),{}).get('organism_taxonid',''));pt=str(genotypes.get(m.get('pathogen_genotype'),{}).get('organism_taxonid',''))
            host=organisms.get(ht,{}).get('full_name','');pathogen=organisms.get(pt,{}).get('full_name','')
            if not taxon_key(host) or taxon_key(host) not in hosts or not pathogen:continue
            refs='|'.join('https://pubmed.ncbi.nlm.nih.gov/'+p.split(':')[1]+'/' for p in sorted(session.get('publications',{})) if p.startswith('PMID:'))
            plant=next((x['group'] not in ('Livestock & poultry','Aquaculture','Farmed insects') for x in existing if taxon_key(x['species'])==taxon_key(host) or taxon_key(host) in [taxon_key(a) for a in x['aliases'].split('|')]),True)
            add('phibase_5_6',pathogen,'pathogens','plant' if plant else 'animal','Experimentally studied agricultural-host interaction',host,url='https://phi5.phi-base.org/',refs=refs,tid=pt,basis='PHI-base pathogen-host record; agricultural-host filter; primary role overrides retained')
    sources['ncbi_taxonomy']=dict(source_id='ncbi_taxonomy',name='NCBI Taxonomy',url='https://www.ncbi.nlm.nih.gov/taxonomy',version=TODAY,retrieved_at=TODAY,scope='Name resolution and eukaryotic lineage checks; not evidence of agricultural role',license='',sha256='')
    country_sources=STATUS/'agriculture_country_sources.tsv'
    if country_sources.exists():
        sources.update({x['source_id']:x for x in read_tsv(country_sources)})
        for x in read_tsv(STATUS/'agriculture_country_candidates.tsv'):
            if x['group']=='excluded':
                rejected.append(dict(source_id=x['source_id'],original_name=x['original_name'],reason=x['basis']));continue
            add(x['source_id'],x['original_name'],x['section'],x['group'],x['disease'],x['host_or_commodity'],x['evidence_url'],x['reference_urls'],x['basis'],x['tax_id'],x['match_name'])
    return candidates,sources,rejected


def taxonomy(cache,candidates):
    names=sorted({taxon_key(x.get('match_name') or x['original_name']) for x in candidates if taxon_key(x.get('match_name') or x['original_name'])})
    ids={x['tax_id'] for x in candidates if x.get('tax_id')}
    signature=hashlib.sha256(json.dumps([names,sorted(ids)]).encode()).hexdigest()[:12]
    path=cache/('ag_taxonomy_'+signature+'.xml')
    if not path.exists():
        root=ET.Element('TaxaSet');known_ids=set();known_names=set()
        snapshots=sorted(cache.glob('ag_taxonomy_*.xml'),key=lambda p:p.stat().st_mtime,reverse=True)
        if snapshots:
            for t in ET.parse(snapshots[0]).getroot().findall('Taxon'):
                root.append(t);known_ids.add(t.findtext('TaxId'))
                for n in [t.findtext('ScientificName')]+[x.text for x in t.findall('OtherNames/*') if x.text and not list(x)]:
                    if taxon_key(n):known_names.add(taxon_key(n))
        missing_names=[n for n in names if n not in known_names]
        print('Taxonomy: checking',len(missing_names),'new/unresolved names; reusing',len(known_ids),'cached records',flush=True)
        for start in range(0,len(missing_names),150):
            term=' OR '.join('"'+n+'"[All Names]' for n in missing_names[start:start+150])
            r=requests.post('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',data={'db':'taxonomy','term':term,'retmax':2000,'retmode':'json'},timeout=90);r.raise_for_status();ids.update(r.json()['esearchresult']['idlist']);time.sleep(.4)
        ids=sorted(ids-known_ids)
        for start in range(0,len(ids),150):
            r=requests.post('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',data={'db':'taxonomy','id':','.join(ids[start:start+150]),'retmode':'xml'},timeout=90);r.raise_for_status()
            root.extend(ET.fromstring(r.content).findall('Taxon'));time.sleep(.4)
        ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    by_id,by_name,canonical_names={},defaultdict(dict),defaultdict(dict)
    for t in ET.parse(path).getroot().findall('Taxon'):
        leaf_id=t.findtext('TaxId');rank=t.findtext('Rank');name=t.findtext('ScientificName');ancestors=t.findall('LineageEx/Taxon')
        if rank=='species':species_id,species_name=leaf_id,name
        else:
            species=next((a for a in reversed(ancestors) if a.findtext('Rank')=='species'),None)
            if species is None:continue
            species_id,species_name=species.findtext('TaxId'),species.findtext('ScientificName')
        if not taxon_key(species_name):continue
        info=dict(species=species_name,tax_id=species_id,lineage=t.findtext('Lineage','')+'; '+name,eukaryote='Eukaryota' in t.findtext('Lineage',''))
        by_id[leaf_id]=info
        canonical_names[taxon_key(species_name)][species_id]=info
        for n in [name]+[x.text for x in t.findall('OtherNames/*') if x.text and not list(x)]:
            key=taxon_key(n)
            if key:by_name[key][species_id]=info
    # Prefer the current canonical species name over a partial match to a
    # synonym of another species (e.g. an old trinomial containing this binomial).
    for key,choices in canonical_names.items():
        by_name[key]=choices
    return by_id,by_name,path


def category(x,t):
    lineage=t['lineage'];group=x['group'];section=x['section']
    if x['source_id']=='aphis_vet':
        if 'Arthropoda' in lineage:return 'pests','Livestock arthropod pests'
        if 'Fungi' in lineage:return 'pathogens','Fungal livestock pathogens'
        if any(k in lineage for k in ('Nematoda','Platyhelminthes')):return 'pathogens','Livestock helminth pathogens'
        return 'pathogens','Livestock protist pathogens'
    if x['source_id']=='caps_2026' or group in ('plant','animal'):
        if 'Fungi' in lineage:return 'pathogens','Fungal plant pathogens' if group!='animal' else 'Fungal livestock pathogens'
        if 'Oomycetes' in lineage:return 'pathogens','Oomycete plant pathogens'
        if group=='animal':return 'pathogens','Livestock protist pathogens'
        if x['source_id']=='phibase_5_6':return 'pathogens','Protist plant pathogens'
        if 'Nematoda' in lineage:return 'pests','Nematode pests'
        if 'Viridiplantae' in lineage:return 'pests','Weeds'
        if 'Acari' in lineage:return 'pests','Mite pests'
        if 'Mollusca' in lineage:return 'pests','Mollusc pests'
        if 'Chordata' in lineage:return 'pests','Vertebrate pests'
        return 'pests','Insect pests'
    if not group and x['source_id']=='ag100_releases':return 'pests','Livestock arthropod pests' if any(k in lineage for k in ('Ixodida','Ixodidae','Argasidae')) else 'Insect pests'
    return section,group


def reconcile(existing,candidates,by_id,by_name,overrides,rejected):
    catalogue={}; legacy={taxon_key(x['species']):x for x in existing};members=[]
    for x in candidates:
        key=taxon_key(x.get('match_name') or x['original_name']);choices=by_name.get(key,{})
        t=by_id.get(x['tax_id']) if x['tax_id'] else next(iter(choices.values())) if len(choices)==1 else None
        if not t or not t['eukaryote']:
            rejected.append(dict(source_id=x['source_id'],original_name=x['original_name'],reason='Non-eukaryotic, ambiguous or unresolved species'));continue
        name=t['species'];override=overrides.get(name) or overrides.get(key)
        if override and override['section']=='exclude':
            rejected.append(dict(source_id=x['source_id'],original_name=x['original_name'],reason=override['notes']));continue
        section,group=category(x,t)
        if override:section,group=override['section'],override['group']
        if section not in ('organisms','pests','pathogens') or not group:
            rejected.append(dict(source_id=x['source_id'],original_name=x['original_name'],reason='Agricultural display role unresolved; requires review'));continue
        if name not in catalogue:
            catalogue[name]=dict(species=name,section=section,group=group,disease=override['role'] if override else x['disease'],source_url=override['evidence_url'] if override else x['evidence_url'],aliases='',notes='Source-defined agricultural relevance; one primary display role per species.',tax_id=t['tax_id'])
        item=catalogue[name]
        if key in legacy and x['basis']=='retained curated species':
            item.update(legacy[key],species=name)
        item['tax_id']=t['tax_id']
        if override:item.update(section=section,group=group,disease=override['role'],notes=override['notes'])
        # An original name becomes a matching alias only when NCBI resolves it unambiguously to this same species.
        aliases=set(item['aliases'].split('|'))-{''}
        if key and key!=taxon_key(name) and len(choices)==1 and t['tax_id'] in choices:aliases.add(key[0].upper()+key[1:])
        aliases.discard(name);item['aliases']='|'.join(sorted(aliases))
        members.append(dict(species=name,tax_id=t['tax_id'],source_id=x['source_id'],original_name=x['original_name'],source_role=x['section'] or 'source-listed agent',assigned_role=item['section'],host_or_commodity=x['host_or_commodity'],evidence_url=x['evidence_url'],reference_urls=x['reference_urls'],basis=x['basis'],matching_scope='Species; original infraspecific qualifiers retained here'))
    # Keep source-specific host/publication evidence while collapsing repeated genes and assemblies.
    merged={}
    for m in members:
        key=(m['species'],m['source_id'],m['original_name'],m['host_or_commodity'],m['evidence_url'])
        if key not in merged:merged[key]=m
        else:merged[key]['reference_urls']='|'.join(sorted(set(merged[key]['reference_urls'].split('|')+m['reference_urls'].split('|'))-{''}))
    for name,x in overrides.items():
        if name in catalogue and x['section']!='exclude':
            item=catalogue[name];members_record=dict(species=name,tax_id=item.get('tax_id',''),source_id='role_review',original_name=name,source_role=x['role'],assigned_role=item['section'],host_or_commodity=x['role'],evidence_url=x['evidence_url'],reference_urls='',basis=x['notes'],matching_scope='Species');merged[(name,'role_review','', '', '')]=members_record
    # Each accession and canonical species has one primary display role across all tabs.
    for m in merged.values():m['assigned_role']=catalogue[m['species']]['section']
    return sorted(catalogue.values(),key=lambda x:(x['section'],x['group'],x['species'])),sorted(merged.values(),key=lambda x:(x['species'],x['source_id'],x['host_or_commodity']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache-dir',type=Path,required=True);p.add_argument('--reports-jsonl',required=True);args=p.parse_args();args.cache_dir.mkdir(parents=True,exist_ok=True)
    existing=read_tsv(STATUS/'agriculture.tsv')
    # Refresh added sources from their snapshots; retain only the original curated baseline.
    membership_path=STATUS/'agriculture_memberships.tsv'
    if membership_path.exists():
        retained={x['species'] for x in read_tsv(membership_path) if x['basis']=='retained curated species'}
        existing=[x for x in existing if x['species'] in retained]
    reports=list(iterate_ncbi(args.reports_jsonl));candidates,sources,rejected=collect_candidates(args.cache_dir,reports,existing)
    by_id,by_name,taxonomy_file=taxonomy(args.cache_dir,candidates)
    overrides={x['species']:x for x in read_tsv(STATUS/'agriculture_role_overrides.tsv')}
    catalogue,members=reconcile(existing,candidates,by_id,by_name,overrides,rejected)
    sources['role_review']=dict(source_id='role_review',name='Role evidence',url='https://github.com/Hanliconius/genome-observatory-live/blob/main/data/status/agriculture_role_overrides.tsv',version=TODAY,retrieved_at=TODAY,scope='Explicit primary role review backed by USDA, FAO, national programme and other primary evidence links',license='',sha256='')
    sources['ncbi_taxonomy']['sha256']=hashlib.sha256(taxonomy_file.read_bytes()).hexdigest()
    write_tsv(STATUS/'agriculture.tsv',catalogue,FIELDS);write_tsv(STATUS/'agriculture_memberships.tsv',members,MEMBER_FIELDS)
    write_tsv(STATUS/'agriculture_sources.tsv',list(sources.values()),['source_id','name','url','version','retrieved_at','country','license','sha256','scope'])
    unique=sorted({(r['source_id'],r['original_name'],r['reason']) for r in rejected})
    write_tsv(STATUS/'agriculture_exclusions.tsv',[dict(source_id=a,original_name=b,reason=c) for a,b,c in unique],['source_id','original_name','reason'])
    print('Reviewed catalogue:',len(catalogue),'taxa;',len(members),'source memberships;',len(unique),'excluded source labels')
