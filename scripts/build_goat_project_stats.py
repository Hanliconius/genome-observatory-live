#!/usr/bin/env python3
"""Draft provenance analysis; separate programme evidence from project footprint.

Uses the same current, version-deduplicated chromosome/complete GenBank inventory
as the Observatory. Optional enrichment is cached; failures remain missing.
No missing consortium, funding, or publication field is interpreted as absence.
"""
import argparse
import gzip
import html
import json
import os
import re
import time
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'cache/goat_project_metadata.json.gz'
TAXONOMY = ROOT / 'cache/goat_species_metadata.json.gz'
OUT = ROOT / 'data/goat_project_stats.json.gz'
EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
REQUEST_LOCK = threading.Lock()
LAST_REQUEST = 0
# Match only explicit programme names/acronyms, not "genome project" generally.
PROGRAMMES = {
 'Darwin Tree of Life': r'darwin tree of life|\bdtol\b',
 'Vertebrate Genomes Project': r'vertebrate genomes project|\bvgp\b',
 'Earth BioGenome Project': r'earth biogenome project|\bebp\b',
 'ERGA / Biodiversity Genomics Europe': r'\berga\b|biodiversity genomics europe',
 'DNA Zoo': r'dna\s*zoo',
 'Bird 10,000 Genomes': r'\bb10k\b|bird 10[,. ]?000|10[,. ]?000 bird genomes',
 'Bat1K': r'\bbat\s*1k\b',
 'i5K': r'\bi5k\b|5[,. ]?000 arthropod genomes',
 'Ag100Pest': r'\bag100pest\b',
 'California Conservation Genomics': r'california conservation genomics|\bccgp\b',
 'Zoonomia': r'\bzoonomia\b|200 mammals project',
 '10KP': r'\b10kp\b|10[,. ]?000 plant genomes',
 '1001 Genomes': r'\b1001 genomes\b',
 'Human Pangenome Reference Consortium': r'human pangenome reference consortium|\bhprc\b',
 'Genome Reference Consortium': r'genome reference consortium',
 'Psyche': r'\bproject psyche\b|\bpsyche project\b',
 'ATLASea': r'\batlasea\b',
 'Canadian BioGenome Project': r'canadian biogenome project',
 'Bee100 / Beenome100': r'\bbeenome\s*100\b',
 'GAGA': r'global ant genomics alliance|\bgaga project\b',
}
PRODUCTION = {
 'Sanger': r'\bsanger\b', 'Genoscope': r'\bgenoscope\b',
 'Joint Genome Institute': r'joint genome institute|\bjgi\b',
 'BGI / CNGB': r'\bbgi\b|china national genebank|\bcngb\b',
 'Broad Institute': r'\bbroad institute\b',
 'Baylor Human Genome Sequencing Center': r'baylor.*genome sequencing',
 'UCSC Genomics Institute': r'ucsc genomics institute',
}

def read_gz(path):
    return json.load(gzip.open(path, 'rt')) if path.exists() else {}

def write_gz(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.partial')
    with gzip.GzipFile(filename=str(temp), mode='wb', mtime=0) as f:
        f.write(json.dumps(data, separators=(',', ':'), sort_keys=True).encode())
    temp.replace(path)

def request(endpoint, params):
    global LAST_REQUEST
    data = urllib.parse.urlencode(params).encode()
    for attempt in range(3):
        try:
            with REQUEST_LOCK:
                time.sleep(max(0, .4 - (time.monotonic() - LAST_REQUEST)))
                LAST_REQUEST = time.monotonic()
            req = urllib.request.Request(EUTILS + endpoint, data=data,
                headers={'User-Agent': 'GenomeObservatoryLive/1.0'})
            with urllib.request.urlopen(req, timeout=90) as r:
                result = r.read()
            return result
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

def clean(text):
    return ' '.join(re.sub('<[^>]+>', ' ', html.unescape(text or '')).split())

def parse_projects(raw):
    root = ET.fromstring(raw)
    result = {}
    for doc in root.findall('.//DocumentSummary'):
        p = doc.find('Project')
        if p is None:
            continue
        a = p.find('ProjectID/ArchiveID')
        if a is None or not a.get('accession'):
            continue
        acc = a.get('accession')
        d = p.find('ProjectDescr')
        grants = []
        for g in d.findall('Grant') if d is not None else []:
            grants.append({'id': g.get('GrantId', ''), 'agency': clean(g.findtext('Agency')),
                           'title': clean(g.findtext('Title'))})
        orgs = [clean(x.findtext('Name')) for x in doc.findall('Submission/Description/Organization')]
        parents = [x.get('accession') for x in doc.findall('ProjectLinks/Link/Hierarchical/MemberID') if x.get('accession')]
        result[acc] = {'title': clean(p.findtext('ProjectDescr/Title')),
            'description': clean(p.findtext('ProjectDescr/Description')),
            'organisations': sorted(set(filter(None, orgs))), 'grants': grants,
            'publications': sorted({x.get('id') for x in p.findall('ProjectDescr/Publication') if x.get('id')}),
            'parents': sorted(set(parents)),
            'fetched_at': datetime.now(timezone.utc).date().isoformat()}
    return result

def enrich_projects(projects, cache, limit=None):
    missing = sorted(set(projects) - set(cache), key=lambda x: (not x.startswith('PRJNA'), x))[:limit]
    def fetch_batch(batch):
        try:
            # Resolve exact accessions first: efetch can silently interpret a PRJEB
            # accession's numeric suffix as an unrelated NCBI UID.
            if all(x.startswith('PRJNA') for x in batch):
                ids = [x[5:] for x in batch]
            else:
                search = json.loads(request('esearch.fcgi', {'db': 'bioproject',
                    'term': ' OR '.join(x + '[Project Accession]' for x in batch),
                    'retmode': 'json', 'retmax': len(batch)}))['esearchresult']
                if search.get('errorlist') or int(search['count']) > len(batch):
                    raise ValueError('Invalid BioProject accession search')
                ids = search['idlist']
            if ids:
                fetched = parse_projects(request('efetch.fcgi',
                    {'db': 'bioproject', 'id': ','.join(ids), 'retmode': 'xml'}))
                # Never assign another accession's metadata to a missing record.
                return {k: v for k, v in fetched.items() if k in batch}
            return {}
        except Exception as e:
            print('BioProject batch unavailable:', str(e), flush=True)
            return {}
    # Three in-flight requests; global spacing stays below the unauthenticated limit.
    batches = [missing[i:i + 400] for i in range(0, len(missing), 400)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch_batch, batch) for batch in batches]
        for future in as_completed(futures):
            cache.update(future.result())
            write_gz(CACHE, cache)
            print('BioProjects enriched', len(cache), '/', len(projects), flush=True)
    return cache

def enrich_taxonomy(ids, cache):
    missing = sorted(set(str(x) for x in ids) - set(cache))
    for start in range(0, len(missing), 400):
        batch = missing[start:start + 400]
        root = ET.fromstring(request('efetch.fcgi', {'db': 'taxonomy', 'id': ','.join(batch), 'retmode': 'xml'}))
        for t in root.findall('Taxon'):
            lineage = t.findall('LineageEx/Taxon') + [t]
            species = next((x for x in reversed(lineage) if x.findtext('Rank') == 'species'), None)
            group = next((label for name, label in [('Metazoa', 'Animals'), ('Viridiplantae', 'Plants'), ('Fungi', 'Fungi')]
                          if any(x.findtext('ScientificName') == name for x in lineage)), 'Other eukaryotes')
            cache[t.findtext('TaxId')] = {'species_id': species.findtext('TaxId') if species is not None else None,
                'species_name': species.findtext('ScientificName') if species is not None else None, 'group': group}
        write_gz(TAXONOMY, cache)
        print('Taxa resolved', len(cache), flush=True)
    return cache

def normalise_org(value):
    return re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()

def species_key(report, taxonomy):
    tax = taxonomy.get(str(report['organism']['tax_id']), {})
    return tax.get('species_id') or 'unresolved:' + str(report['organism']['tax_id'])

def assemble(reports, projects, taxonomy):
    # Current accession stems are the counting unit: no GCF twins or version counts.
    unique = {}
    for r in reports:
        acc = r.get('accession', '')
        if not re.fullmatch(r'GCA_\d+\.\d+', acc):
            continue
        stem, version = acc.split('.')
        if stem not in unique or int(version) > int(unique[stem]['accession'].split('.')[1]):
            unique[stem] = r
    rows = sorted(unique.values(), key=lambda r: (r['assembly_info']['release_date'], r['accession']))
    project_species, submitter_species, grant_species = defaultdict(set), defaultdict(set), defaultdict(set)
    first = {}
    for r in rows:
        k = species_key(r, taxonomy)
        first.setdefault(k, r['accession'])
        info = r['assembly_info']; p = info.get('bioproject_accession', '')
        if p: project_species[p].add(k)
        sub = normalise_org(info.get('submitter'))
        if sub: submitter_species[sub].add(k)
        for g in projects.get(p, {}).get('grants', []):
            if g['id']: grant_species[(normalise_org(g['agency']), normalise_org(g['id']))].add(k)
    history = read_gz(ROOT / 'cache/goat_all_level_history.json.gz')
    centres = {}
    centre_path = ROOT / 'cache/sra_biosample_centers.json'
    if centre_path.exists(): centres = json.loads(centre_path.read_text())
    result = []
    for r in rows:
        info = r['assembly_info']; org = r['organism']; tax = taxonomy.get(str(org['tax_id']), {})
        p = info.get('bioproject_accession', ''); bp = projects.get(p, {})
        lineage = {x['accession']: x for line in info.get('bioproject_lineage', []) for x in line.get('bioprojects', [])}
        if p: lineage.setdefault(p, {'accession': p, 'title': bp.get('title', '')})
        evidence = []
        for acc, entry in lineage.items():
            meta = projects.get(acc, {})
            text = ' '.join([entry.get('title', ''), meta.get('title', ''), meta.get('description', '')])
            for label, pattern in PROGRAMMES.items():
                if re.search(pattern, text, re.I): evidence.append({'label': label, 'source': acc, 'field': 'BioProject title/description'})
        sub = info.get('submitter', '')
        for label, pattern in PROGRAMMES.items():
            if re.search(pattern, sub, re.I): evidence.append({'label': label, 'source': r['accession'], 'field': 'assembly submitter'})
        production = [label for label, pattern in PRODUCTION.items() if re.search(pattern, sub, re.I)]
        bs = info.get('biosample', {})
        centre_names = centres.get(bs.get('accession'), [])
        grants = bp.get('grants', [])
        grant_sizes = [len(grant_species[(normalise_org(g['agency']), normalise_org(g['id']))]) for g in grants if g['id']]
        university = bool(re.search(r'universit|\bcollege\b|\buniversidad\b|\buniversidade\b|\buniversit[eé]\b', sub, re.I))
        institute = bool(re.search(r'institut|academ|laborator|\bcsiro\b|\busda\b|\bcnrs\b|\binrae?\b|\bnih\b|\bnhgri\b', sub, re.I))
        museum = bool(re.search(r'museum|botanic|herbarium|natural history', sub, re.I))
        commercial = bool(re.search(r'\bltd\b|limited|\binc\b|corporation|\bco[., ]+ltd\b', sub, re.I))
        institution_types = [label for label, match in [('University', university), ('Research institute', institute),
                              ('Museum / garden', museum), ('Commercial name', commercial)] if match]
        research = university or institute or museum
        footprint = history.get('project_species', {}).get(p, len(project_species[p]) if p else None)
        # These are evidence summaries, not verified team-size labels.
        bucket = ('programme' if evidence else 'centre' if production else
                  'candidate' if research and footprint is not None and footprint <= 5 else 'unresolved')
        historical = history.get('species', {}).get(tax.get('species_id'), {})
        earlier = historical.get('first', {})
        day = info['release_date'][:10]
        first_qualifying = first[species_key(r, taxonomy)] == r['accession']
        old_version = history.get('lower_by_stem', {}).get(r['accession'].split('.')[0])
        same_stem_upgrade = bool(old_version and int(old_version['accession'].split('.')[1]) < int(r['accession'].split('.')[1]))
        if not tax.get('species_id') or not earlier:
            novelty = 'unknown'
        elif not first_qualifying or (historical.get('first_high') or {}).get('date', '9999') < day:
            novelty = 'additional'
        elif same_stem_upgrade:
            novelty = 'upgrade'
        elif earlier['date'] < day:
            novelty = 'upgrade' if (historical.get('first_lower') or {}).get('date', '9999') < day else 'earlier_high_level'
        elif (historical.get('first_lower') or {}).get('date') == day:
            novelty = 'unknown'
        else:
            novelty = 'first_ever'
        result.append({'accession': r['accession'], 'date': info['release_date'][:10],
            'species_id': tax.get('species_id'), 'species': tax.get('species_name') or org['organism_name'],
            'tax_id': org['tax_id'], 'species_resolved': bool(tax.get('species_id')),
            'group': tax.get('group', r.get('_observatory', {}).get('group', 'Unresolved')),
            'first': first[species_key(r, taxonomy)] == r['accession'],
            'first_day': info['release_date'][:10] == next_first_date(first[species_key(r, taxonomy)], unique),
            'submitter': sub, 'bioproject': p, 'project_title': bp.get('title') or lineage.get(p, {}).get('title', ''),
            'project_species': footprint, 'submitter_species': len(submitter_species[normalise_org(sub)]) if sub else None,
            'programme_labels': sorted({x['label'] for x in evidence}), 'programme_evidence': evidence,
            'production_labels': production, 'university_submitter': university,
            'research_submitter': research, 'institution_types': institution_types,
            'bucket': bucket, 'grants': grants, 'grant_species_max': max(grant_sizes) if grant_sizes else None,
            'novelty': novelty, 'earliest_all_level': earlier or None,
            'earliest_lower_level': historical.get('first_lower'),
            'same_stem_upgrade': same_stem_upgrade,
            'project_metadata': p in projects, 'publications': bp.get('publications', []),
            'owner': bs.get('owner', {}).get('name', ''), 'sra_centres': centre_names,
            'parent_projects': sorted(set(lineage) - {p})})
    return result

def next_first_date(accession, unique):
    return unique[accession.split('.')[0]]['assembly_info']['release_date'][:10]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--reports-jsonl', default=os.getenv('GENOME_REPORTS_JSONL'))
    ap.add_argument('--enrich', action='store_true'); ap.add_argument('--project-limit', type=int)
    a = ap.parse_args()
    if not a.reports_jsonl: raise ValueError('--reports-jsonl or GENOME_REPORTS_JSONL required')
    reports = [json.loads(x) for x in Path(a.reports_jsonl).read_text().splitlines() if x.strip()]
    # Supplement the Datasets discovery lag with the shared Assembly-index cache.
    pending = ROOT / 'cache/assembly_index_pending.json'
    if pending.exists():
        known = {r['accession'] for r in reports}
        reports += [r for r in json.loads(pending.read_text()) if r['accession'] not in known]
    projects = read_gz(CACHE); taxonomy = read_gz(TAXONOMY)
    wanted = {x['accession'] for r in reports for line in r.get('assembly_info', {}).get('bioproject_lineage', []) for x in line.get('bioprojects', [])}
    wanted |= {r['assembly_info']['bioproject_accession'] for r in reports if r.get('assembly_info', {}).get('bioproject_accession')}
    if a.enrich:
        taxonomy = enrich_taxonomy([r['organism']['tax_id'] for r in reports], taxonomy)
        projects = enrich_projects(wanted, projects, a.project_limit)
    rows = assemble(reports, projects, taxonomy)
    history = read_gz(ROOT / 'cache/goat_all_level_history.json.gz')
    payload = {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Current GenBank chromosome/complete eukaryote assemblies, one per accession stem; same discovery sources as Observatory.',
        'first_definition': 'One representative assembly per NCBI species at its earliest release in the current qualifying inventory; date ties broken by accession. Additional assemblies released that same day are flagged separately. Not necessarily the first genome at any assembly level, or historically withdrawn records.',
        'classification': 'Programme evidence > production-centre submitter > research institution submitter and <=5 species in direct BioProject > unresolved. Institutional types use transparent name patterns, not verified organisation identities. These display groups are provisional; overlapping source labels are retained. Low project output does not establish a small team.',
        'project_footprint': 'Distinct NCBI species in direct BioProjects across Full GenBank eukaryote assemblies at every level, including replaced records. This is observed output, not team size. Grant footprints are restricted to successfully enriched direct BioProjects in the chromosome-scale inventory.',
        'history': {k: v for k, v in history.items() if k not in ('species', 'lower_by_stem', 'project_species')},
        'coverage': {'assemblies': len(rows), 'species_resolved': sum(r['species_resolved'] for r in rows),
            'project_metadata': sum(r['project_metadata'] for r in rows), 'wanted_projects': len(wanted),
            'fetched_projects': len(set(projects) & wanted)}, 'records': rows}
    write_gz(OUT, payload)
    print('Wrote', len(rows), 'assemblies;', payload['coverage'], 'buckets', dict(Counter(r['bucket'] for r in rows)), flush=True)

if __name__ == '__main__': main()
