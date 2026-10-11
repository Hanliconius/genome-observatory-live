#!/usr/bin/env python3
"""Combine MapVEu surveillance taxa with an explicitly curated disease list."""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from audit_full_history import iterate_ncbi
from build_iucn import normalize_assembly
from build_vectors import build as build_vectors

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / 'data/status/pathogens.tsv'
OUT = ROOT / 'data/status/vectors.json'
MAPVEU = 'https://veupathdb.org/veupathdb/app/static-content/faq.html'


def binomial(name):
    parts = str(name or '').split()
    if len(parts) < 2 or any(x in parts for x in ('x', '×', 'cf.', 'aff.', 'sp.', 'spp.', 'hybrid', 'complex')):
        return None
    name = ' '.join(parts[:2])
    return name if re.fullmatch(r'[A-Z][a-z]+ [a-z][a-z-]+', name) else None


def aggregate(rows, species, dashboard, vector_source):
    rows = sorted({x['accession']: x for x in rows}.values(), key=lambda x: (x['release_date'], x['accession']))
    first = {}
    by_species = defaultdict(list)
    daily, yearly, genera, groups, first_year = Counter(), Counter(), Counter(), Counter(), Counter()
    for x in rows:
        n = x['species_name']
        first.setdefault(n, x['release_date'])
        by_species[n].append(x)
        daily[x['release_date']] += 1
        yearly[x['release_date'][:4]] += 1
        genera[n.split()[0]] += 1
        groups[x['vector_type']] += 1
    first_year.update(d[:4] for d in first.values())
    inventory = []
    for item in species:
        x = dict(item)
        matches = by_species[x['species']]
        x.update(assemblies=len(matches), first_release=first.get(x['species']),
                 latest_release=matches[-1]['release_date'] if matches else None,
                 tax_ids=sorted({r['tax_id'] for r in matches if r.get('tax_id')}))
        inventory.append(x)
    inventory.sort(key=lambda x: x['species'])
    types = []
    source_types = {g['name']: g for g in vector_source['type_summary']}
    for name in dict.fromkeys(x['vector_type'] for x in inventory):
        xs = [x for x in inventory if x['vector_type'] == name]
        origin = source_types.get(name, {})
        types.append({'name': name, 'taxon': origin.get('taxon', name),
                      'source_url': origin.get('source_url', xs[0].get('source_url')),
                      'assemblies': groups[name], 'source_species': len(xs),
                      'genome_species': sum(x['assemblies'] > 0 for x in xs)})
    cutoff = (date.today() - timedelta(days=369)).isoformat()
    def annotation_match(x):
        return binomial(x.get('species')) in first
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': {'dataset': 'MapVEu surveillance + curated CDC parasites and WHO-priority fungi',
                   'species_names': len(inventory), 'taxon_labels': vector_source['source']['taxon_labels'],
                   'sample_rows': vector_source['source']['sample_rows'], 'export_date': vector_source['source']['export_date'],
                   'scope': 'MapVEu vector/surveillance taxa plus a selected catalogue of human and zoonotic parasites and WHO-priority fungi. This is not an exhaustive list of pathogens. Vector-list membership does not establish transmission.',
                   'matching': 'Scientific binomials, with only explicitly listed aliases; parasite strain/subspecies names roll up to species. Genome counts use current GenBank chromosome/complete assemblies.',
                   'curated_list': '../data/status/pathogens.tsv'},
        'summary': {'assemblies': len(rows), 'species': len(first), 'first_time_species': len(first)},
        'species_inventory': inventory, 'type_summary': types,
        'type_breakdown': [{'group': g['name'], 'count': g['assemblies']} for g in types if g['assemblies']],
        'genus_breakdown': [{'group': g, 'count': n} for g,n in genera.most_common()],
        'yearly': [{'year': y, 'assemblies': yearly[y], 'first_time_species': first_year[y]} for y in sorted(yearly)],
        'recent_daily': [{'date': d, 'assemblies': n} for d,n in sorted(daily.items()) if d >= cutoff],
        'recent_assemblies': list(reversed([x for x in rows if x['release_date'] >= cutoff]))[:200],
        'latest_assembly': rows[-1] if rows else None,
        'annotations': {k: [x for x in dashboard.get('annotations',{}).get(k,[]) if annotation_match(x)] for k in ('in_progress','recent_completed')},
    }
    assert sum(g['assemblies'] for g in types) == len(rows)
    assert sum(x['assemblies'] for x in inventory) == len(rows)
    return payload


def build(reports):
    reports = list(reports)
    vector = build_vectors(reports=reports)
    dashboard = json.loads((ROOT / 'data/dashboard.json').read_text())
    cache = {x['accession']: x for x in dashboard.get('recent_assemblies', [])}
    with LIST.open() as f:
        curated = list(csv.DictReader(f, delimiter='\t'))
    lookup = {}
    species = []
    for item in curated:
        if not binomial(item['species']): raise ValueError('Invalid curated species: '+item['species'])
        for name in [item['species']]+item['aliases'].split('|'):
            if not name: continue
            if name.casefold() in lookup and lookup[name.casefold()]['species'] != item['species']:
                raise ValueError('Ambiguous alias: '+name)
            lookup[name.casefold()] = item
        species.append(dict(item, vector_type=item['group'], role='Pathogen / parasite', sample_rows=0))
    rows = []
    for report in reports:
        x = normalize_assembly(report)
        n = binomial(x['organism_name'])
        item = lookup.get((n or '').casefold())
        if not item or not x['accession'].startswith('GCA_') or len(x['release_date']) != 10: continue
        if x['assembly_level'].lower() not in ('chromosome','complete genome','complete'): continue
        meta = cache.get(x['accession'], {})
        x.update({k:meta[k] for k in ('common_name','image') if meta.get(k)})
        x.update(species_name=item['species'], vector_type=item['group'], role='Pathogen / parasite',
                 disease=item['disease'], source_url=item['source_url'],
                 tax_id=str(report.get('tax_id') or report.get('organism',{}).get('tax_id') or ''))
        rows.append(x)
    vector_species = [dict(x, role='Vector / surveillance', disease='Vector surveillance', source_url=MAPVEU) for x in vector['species_inventory']]
    vector_types = {x['species']: x['vector_type'] for x in vector_species}
    vector_rows = [dict(x, vector_type=vector_types[x['species_name']], role='Vector / surveillance', disease='Vector surveillance', source_url=MAPVEU) for x in vector['assembly_inventory']]
    all_species = {x['species']: x for x in vector_species+species}
    all_rows = vector_rows+rows
    payload = aggregate(all_rows, list(all_species.values()), dashboard, vector)
    views = {}
    for name, chosen in {
        'vectors': {x['vector_type'] for x in vector_species},
        'protists': {'Protist parasites'},
        'worms': {'Parasitic nematodes','Parasitic flatworms','Other parasitic worms'},
        'fungi': {'Pathogenic fungi','Fungal parasites'},
    }.items():
        views[name] = aggregate([x for x in all_rows if x['vector_type'] in chosen],
                               [x for x in all_species.values() if x['vector_type'] in chosen], dashboard, vector)
    payload['views'] = views
    payload['audit'] = {'ncbi_assemblies_scanned': len(reports), 'curated_species': len(curated)}
    assert views['vectors']['summary'] == vector['summary'], 'Existing vector totals changed'
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--reports-jsonl', help='Qualifying inventory snapshot for offline checks')
    args = p.parse_args()
    result = build(iterate_ncbi(args.reports_jsonl))
    OUT.write_text(json.dumps(result, separators=(',', ':'), ensure_ascii=False)+'\n')
    print('Pathogens & vectors:',result['summary'], 'curated species:',result['audit']['curated_species'])
    print({name: view['summary'] for name, view in result['views'].items()})
