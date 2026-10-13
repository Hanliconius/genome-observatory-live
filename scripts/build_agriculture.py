#!/usr/bin/env python3
"""Build separate agriculture views from an explicitly curated species catalogue."""
import argparse
import csv
import json
import re
from pathlib import Path
from audit_full_history import iterate_ncbi
from build_iucn import normalize_assembly
from build_pathogens import aggregate, binomial
from build_countries import geo_loc_name

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / 'data/status/agriculture.tsv'
OUT = ROOT / 'data/status/agriculture.json'
SECTIONS = {'organisms': 'Agricultural organisms', 'pests': 'Agricultural pests', 'pathogens': 'Agricultural pathogens'}


def taxon_key(name):
    name = re.sub(r'\s+', ' ', str(name or '').replace('×', 'x')).strip()
    # Only named cultivated hybrids explicitly in the list may match.
    parts = name.split()
    if len(parts) >= 3 and parts[1] == 'x' and re.fullmatch(r'[A-Z][a-z]+ x [a-z][a-z-]+', ' '.join(parts[:3])):
        if any(x in parts[3:] for x in ('x', 'sp.', 'cf.', 'aff.', 'hybrid')): return ''
        return ' '.join(parts[:3]).casefold()
    return (binomial(name) or '').casefold()


def build(reports, catalogue=None):
    reports = list(reports)
    sources, memberships = [], []
    if catalogue is None:
        with LIST.open() as f:
            catalogue = list(csv.DictReader(f, delimiter='\t'))
        with (ROOT / 'data/status/agriculture_sources.tsv').open() as f:
            sources = list(csv.DictReader(f, delimiter='\t'))
        with (ROOT / 'data/status/agriculture_memberships.tsv').open() as f:
            memberships = list(csv.DictReader(f, delimiter='\t'))
        registry = {x['source_id']:x for x in sources}
        for item in catalogue:
            grouped = {}
            for m in memberships:
                if m['species'] != item['species']: continue
                source = registry[m['source_id']]
                evidence = grouped.setdefault(m['source_id'],dict(source_id=m['source_id'],name=source['name'],url=m['evidence_url'],version=source['version'],hosts=set(),references=set()))
                if m['host_or_commodity']: evidence['hosts'].add(m['host_or_commodity'])
                evidence['references'].update(x for x in m['reference_urls'].split('|') if x)
            if not grouped: raise ValueError('Taxon has no recorded source membership: '+item['species'])
            item['sources'] = [dict(x,hosts=sorted(x['hosts']),references=sorted(x['references'])[:3]) for x in grouped.values()]
    lookup = {}
    for item in catalogue:
        if item['section'] not in SECTIONS or not taxon_key(item['species']):
            raise ValueError('Invalid agricultural catalogue entry: '+item['species'])
        for name in [item['species']] + item['aliases'].split('|'):
            if not name: continue
            key = taxon_key(name)
            if not key: raise ValueError('Invalid alias: '+name)
            if key in lookup and lookup[key]['species'] != item['species']:
                raise ValueError('Ambiguous agricultural alias: '+name)
            lookup[key] = item
    dashboard = json.loads((ROOT / 'data/dashboard.json').read_text())
    cache = {x['accession']:x for x in dashboard.get('recent_assemblies',[])}
    matched = []
    for report in reports:
        x = normalize_assembly(report)
        item = lookup.get(taxon_key(x['organism_name']))
        if not item or not x['accession'].startswith('GCA_') or len(x['release_date']) != 10: continue
        if x['assembly_level'].lower() not in ('chromosome','complete genome','complete'): continue
        meta = cache.get(x['accession'],{})
        x.update({k:meta[k] for k in ('common_name','image') if meta.get(k)})
        x.update(species_name=item['species'], vector_type=item['group'], role=SECTIONS[item['section']],
                 section=item['section'], disease=item['disease'], source_url=item['source_url'],
                 geo_loc_name=geo_loc_name(report),
                 tax_id=str(report.get('tax_id') or report.get('organism',{}).get('tax_id') or ''))
        matched.append(x)
    source = {'type_summary': [], 'source': {'taxon_labels': len(catalogue), 'sample_rows': 0, 'export_date': max((x['retrieved_at'] for x in sources),default='2026-10-11')}}
    views = {}
    for section,label in SECTIONS.items():
        species = [dict(x,vector_type=x['group'],role=label,sample_rows=0) for x in catalogue if x['section']==section]
        views[section] = aggregate([x for x in matched if x['section']==section],species,dashboard,source)
        views[section]['groups'] = {g: aggregate([x for x in matched if x['section']==section and x['vector_type']==g], [x for x in species if x['vector_type']==g], dashboard, source) for g in sorted({x['vector_type'] for x in species})}
        views[section]['source'].update(dataset='Union of curated FAO, EPPO, USDA Ag100Pest/CAPS/APHIS, WOAH and PHI-base records',
            scope=label+' in a source-linked union catalogue covering crops, livestock, aquaculture, forestry, stored products and plant-health priorities. One primary display role per taxon; documented biological-control organisms are separated from pests. This is not an exhaustive list.',
            matching='Current GenBank chromosome/complete assemblies. Species-level matching includes varieties, breeds and wild samples of listed taxa; only explicit aliases and named cultivated hybrids are included.',
            curated_list='../data/status/agriculture.tsv')
        for group in views[section]['groups'].values(): group['source'].update(views[section]['source'], species_names=len(group['species_inventory']))
        for view in [views[section]] + list(views[section]['groups'].values()):
            represented = {x['species'] for x in view['species_inventory'] if x['assemblies']}
            def annotation_match(x):
                item = lookup.get(taxon_key(x.get('species')))
                return item is not None and item['species'] in represented
            view['annotations'] = {k: [x for x in dashboard.get('annotations',{}).get(k,[]) if annotation_match(x)] for k in ('in_progress','recent_completed')}
    return {'generated_at': views['organisms']['generated_at'], 'views': views,
            'sources': sources,
            'audit': {'ncbi_assemblies_scanned':len(reports), 'curated_taxa':len(catalogue), 'source_memberships':len(memberships)}}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--reports-jsonl', help='Qualifying inventory snapshot for offline checks')
    args = p.parse_args()
    result = build(iterate_ncbi(args.reports_jsonl))
    OUT.write_text(json.dumps(result,separators=(',', ':'),ensure_ascii=False)+'\n')
    print('Agriculture:',{k:v['summary'] for k,v in result['views'].items()},'curated taxa:',result['audit']['curated_taxa'])
