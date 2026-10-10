#!/usr/bin/env python3
"""Build the source-defined MapVEu vector/surveillance genome view."""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from audit_full_history import iterate_ncbi
from build_iucn import normalize_assembly

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / 'data/status/mapveu_species.tsv'
OUT = ROOT / 'data/status/vectors.json'


def add_type_summaries(payload):
    config = json.loads((ROOT / 'data/status/vector_types.json').read_text())
    lookup = {}
    for group in config['types']:
        for genus in group['genera']:
            if genus in lookup:
                raise ValueError('Duplicate vector-type genus: ' + genus)
            lookup[genus] = group['name']
    groups = {g['name']: dict(g, assemblies=0, source_species=0,
                             genome_species=0, sample_rows=0) for g in config['types']}
    groups['Other / unresolved'] = {'name': 'Other / unresolved',
        'taxon': 'Unmapped source genus labels', 'genera': [], 'source_url': None,
        'assemblies': 0, 'source_species': 0, 'genome_species': 0, 'sample_rows': 0}
    for item in payload['species_inventory']:
        genus = item['species'].split()[0]
        name = lookup.get(genus, 'Other / unresolved')
        item['vector_type'] = name
        group = groups[name]
        group['source_species'] += 1
        group['genome_species'] += int(item['assemblies'] > 0)
        group['assemblies'] += item['assemblies']
        group['sample_rows'] += item['sample_rows']
        if name == 'Other / unresolved' and genus not in group['genera']:
            group['genera'].append(genus)
    for item in payload['recent_assemblies']:
        item['vector_type'] = lookup.get(item['species_name'].split()[0], 'Other / unresolved')
    if payload.get('latest_assembly'):
        item = payload['latest_assembly']
        item['vector_type'] = lookup.get(item['species_name'].split()[0], 'Other / unresolved')
    payload['type_summary'] = [g for g in groups.values() if g['source_species']]
    payload['type_breakdown'] = [{'group': g['name'], 'count': g['assemblies']}
                                 for g in payload['type_summary'] if g['assemblies']]
    payload['source']['type_grouping'] = config['definition']
    return payload


def species_name(value):
    # Do not turn genus, hybrid, complex or uncertain labels into species.
    value = ' '.join(value.split())
    if re.fullmatch(r'[A-Z][a-z]+ [a-z][a-z-]+(?: [a-z][a-z-]+)?', value):
        if not set(value.split()[1:]) & {'sp', 'spp', 'group', 'complex', 'unknown', 'cf', 'aff'}:
            return ' '.join(value.split()[:2])
    return None


def build(inventory=None):
    with LABELS.open() as f:
        labels = list(csv.DictReader(f, delimiter='\t'))
    accepted = defaultdict(list)
    excluded = []
    for item in labels:
        key = species_name(item['species_label'])
        if key:
            accepted[key.casefold()].append(item)
        else:
            excluded.append(item['species_label'])
    dashboard = json.loads((ROOT / 'data/dashboard.json').read_text())
    cached = {x['accession']: x for x in dashboard.get('recent_assemblies', [])}
    if inventory:
        with Path(inventory).open() as f:
            reports = list(csv.DictReader(f))
    else:
        reports = iterate_ncbi()
    rows = {}
    scanned = 0
    for report in reports:
        scanned += 1
        x = normalize_assembly(report)
        key = species_name(x['organism_name'])
        if not key or key.casefold() not in accepted:
            continue
        if not x['accession'].startswith('GCA_') or len(x['release_date']) != 10:
            continue
        meta = cached.get(x['accession'], {})
        x.update({k: meta[k] for k in ('common_name', 'image', 'chromosome_count', 'total_sequence_length', 'assembly_level', 'assembly_name') if meta.get(k)})
        x['species_name'] = key
        x['tax_id'] = str(report.get('tax_id') or report.get('organism', {}).get('tax_id') or '')
        x['source_labels'] = [r['species_label'] for r in accepted[key.casefold()]]
        rows[x['accession']] = x
    rows = sorted(rows.values(), key=lambda x: (x['release_date'], x['accession']))
    first = {}
    daily = Counter()
    yearly = Counter()
    genera = Counter()
    by_species = defaultdict(list)
    for x in rows:
        first.setdefault(x['species_name'], x['release_date'])
        daily[x['release_date']] += 1
        yearly[x['release_date'][:4]] += 1
        genera[x['species_name'].split()[0]] += 1
        by_species[x['species_name']].append(x)
    first_year = Counter(d[:4] for d in first.values())
    cutoff = (date.today() - timedelta(days=369)).isoformat()
    names = set(first)
    def ann_match(x):
        return species_name(x.get('species', '')) in names
    species = []
    for key, source_rows in sorted(accepted.items()):
        name = species_name(source_rows[0]['species_label'])
        xs = by_species.get(name, [])
        species.append({'species': name, 'assemblies': len(xs),
                        'sample_rows': sum(int(r['sample_rows']) for r in source_rows),
                        'source_labels': [r['species_label'] for r in source_rows],
                        'tax_ids': sorted({x['tax_id'] for x in xs if x['tax_id']}),
                        'first_release': first.get(name),
                        'latest_release': xs[-1]['release_date'] if xs else None})
    return add_type_summaries({
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': {'dataset': 'MapVEu / VectorBase surveillance sample export',
                   'export_date': '2026-10-10', 'sample_rows': 1834448,
                   'taxon_labels': len(labels), 'species_names': len(accepted),
                   'excluded_labels': excluded,
                   'scope': 'Source-defined vectors and related surveillance taxa; inclusion does not establish disease transmission.',
                   'matching': 'Exact scientific binomial-name matching; named subspecies roll up to species. Genus, group, complex and uncertain labels excluded. Synonyms are not inferred.',
                   'inventory': 'Current GenBank chromosome-scale and complete eukaryotic assemblies'},
        'summary': {'assemblies': len(rows), 'species': len(first), 'first_time_species': len(first)},
        'yearly': [{'year': y, 'assemblies': yearly[y], 'first_time_species': first_year[y]} for y in sorted(yearly)],
        'recent_daily': [{'date': d, 'assemblies': n} for d, n in sorted(daily.items()) if d >= cutoff],
        'groups_all': [{'group': 'Animals', 'count': len(rows)}],
        'genus_breakdown': [{'group': g, 'count': n} for g, n in genera.most_common()],
        'recent_assemblies': list(reversed([x for x in rows if x['release_date'] >= cutoff]))[:200],
        'latest_assembly': rows[-1] if rows else None,
        'annotations': {k: [x for x in dashboard.get('annotations', {}).get(k, []) if ann_match(x)] for k in ('in_progress', 'recent_completed')},
        'species_inventory': species, 'audit': {'ncbi_assemblies_scanned': scanned},
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', help='Archived qualifying NCBI inventory CSV for offline validation')
    args = parser.parse_args()
    result = build(args.inventory)
    OUT.write_text(json.dumps(result, separators=(',', ':'), ensure_ascii=False) + '\n')
    print(f"Vector/surveillance view: {result['summary']['assemblies']} assemblies, {result['summary']['species']} species; {result['source']['species_names']} source species names")
