#!/usr/bin/env python3
"""Cache all-level GenBank context for the unlinked GoaT analysis only.

Scan NCBI's six eukaryote group assembly summaries, including replaced historical
records. Suppressed records are excluded. This never changes the main inventory.
"""
import gzip
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ['vertebrate_mammalian', 'vertebrate_other', 'invertebrate', 'plant', 'fungi', 'protozoa']

def fetch(task):
    group, historical = task
    filename = 'assembly_summary_historical.txt' if historical else 'assembly_summary.txt'
    url = f'https://ftp.ncbi.nlm.nih.gov/genomes/genbank/{group}/{filename}'
    rows = []
    with urllib.request.urlopen(url, timeout=120) as response:
        fields = None
        for raw in response:
            line = raw.decode().rstrip('\n')
            if line.lstrip('# ').startswith('assembly_accession\t'):
                fields = line.lstrip('# ').split('\t')
            elif line and not line.startswith('#'):
                if fields is None: raise ValueError('Missing assembly-summary header')
                r = dict(zip(fields, line.split('\t')))
                if r.get('version_status') == 'suppressed': continue
                if r.get('genome_rep') != 'Full': continue
                rows.append({k: r.get(k, '') for k in ['assembly_accession', 'species_taxid', 'taxid',
                    'seq_rel_date', 'assembly_level', 'version_status', 'organism_name', 'bioproject']})
    print(group, filename, len(rows), flush=True)
    return url, rows

def main():
    species = {}; stems = {}; sources = []; project_species = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for url, rows in pool.map(fetch, [(g, h) for g in GROUPS for h in (False, True)]):
            sources.append({'url': url, 'records': len(rows)})
            for r in rows:
                day = r['seq_rel_date'].replace('/', '-')
                if len(day) != 10 or day == '0001-01-01': continue
                acc = r['assembly_accession']; key = r['species_taxid']
                if r['bioproject'] and r['bioproject'] != 'na':
                    project_species.setdefault(r['bioproject'], set()).add(key)
                event = {'date': day, 'accession': acc, 'level': r['assembly_level']}
                rec = species.setdefault(key, {'first': event, 'first_lower': None, 'first_high': None})
                if (day, acc) < (rec['first']['date'], rec['first']['accession']): rec['first'] = event
                if r['assembly_level'] in ('Chromosome', 'Complete Genome'):
                    if rec['first_high'] is None or (day, acc) < (rec['first_high']['date'], rec['first_high']['accession']): rec['first_high'] = event
                if r['assembly_level'] in ('Contig', 'Scaffold'):
                    if rec['first_lower'] is None or (day, acc) < (rec['first_lower']['date'], rec['first_lower']['accession']): rec['first_lower'] = event
                    stem = acc.split('.')[0]
                    if stem not in stems or (day, acc) < (stems[stem]['date'], stems[stem]['accession']): stems[stem] = event
    data = {'updated_at': datetime.now(timezone.utc).isoformat(), 'sources': sources,
        'species': species, 'lower_by_stem': stems,
        'project_species': {k: len(v) for k, v in project_species.items()},
        'definition': 'Current and replaced Full GenBank assemblies across all assembly levels; suppressed and Partial records excluded. Dates are NCBI assembly-summary seq_rel_date.'}
    out = ROOT / 'cache/goat_all_level_history.json.gz'
    out.parent.mkdir(exist_ok=True)
    with gzip.GzipFile(filename=str(out), mode='wb', mtime=0) as f:
        f.write(json.dumps(data, separators=(',', ':'), sort_keys=True).encode())
    print('Historical all-level species', len(species), flush=True)

if __name__ == '__main__': main()
