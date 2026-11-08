#!/usr/bin/env python3
"""Resolve recorded provenance from direct organisations and explicit parent links.

Offline: never infer lab leadership from a sequencing centre, repository or parent.
Historical genome context is independent and is not changed by this resolver.
"""
import copy
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RESEARCH = r'\buniver(?:sit|is|sty)|(?:parasitology|mycology|biology|genetics|genomics).{0,40}department|\blab\b|[a-z]lab\b|school of|\bcentre\b|\bcenter\b|\bcentro\b|universit|universty|\bcollege\b|institut|institiut|academ|laborator|\bresearch\b|museum|botanic|herbarium|natural history|\bcsiro\b|\busda\b|\bcnrs\b|\binrae?\b|\bnih\b|\bnhgri\b|centre national de la recherche|agricultur.*research|centro.*gen[oó]mic|center for.*genom|centre for.*genom'
# Narrow aliases: do not expand ambiguous short names such as SC, BSC or EBI.
ALIASES = [
    (r'^disafa_plant_genetics$', 'DISAFA, University of Turin', 'https://www.anemone.unito.it/'),
    (r'^NIAB$', 'NIAB crop science organisation', 'https://www.niab.com/about'),
    (r'^NDSU$', 'North Dakota State University', 'https://www.ndsu.edu/'),
    (r'^NWAFU$', 'Northwest A&F University', 'https://en.nwsuaf.edu.cn/'),
    (r'^IDSSE$', 'Institute of Deep-sea Science and Engineering, CAS', 'https://english.idsse.cas.cn/'),
    (r'^NCGR$', 'National Center for Genome Resources', 'https://www.ncgr.org/'),
    (r'^LSHTM$', 'London School of Hygiene & Tropical Medicine', 'https://www.lshtm.ac.uk/aboutus'),
    (r'^Cornell$', 'Cornell University', 'https://www.cornell.edu/'),
    (r'^Virginia Tech$', 'Virginia Polytechnic Institute and State University', 'https://www.vt.edu/'),
    (r'\bJohn Innes Centre\b', 'John Innes Centre', 'https://www.jic.ac.uk/'),
    (r'\bFiocruz\b', 'Oswaldo Cruz Foundation', 'https://portal.fiocruz.br/en'),
    (r'\bvib\s*[/ -]?\s*ku\s*leuven\b', 'VIB / KU Leuven', 'https://vib.sites.vib.be/en/research-and-impact/research-centers/vib-ku-leuven-center-neuroscience'),
    (r'\bmpipz\b', 'Max Planck Institute for Plant Breeding Research', 'https://www.mpipz.mpg.de/'),
    (r'\bkaust\b', 'King Abdullah University of Science and Technology', 'https://www.kaust.edu.sa/en/about/'),
    (r'\beth\s+z[uü]rich\b', 'ETH Zurich', 'https://ethz.ch/en.html'),
    (r'\buc\s+(berkeley|davis|santa cruz|san diego|los angeles)\b', 'University of California', 'https://www.universityofcalifornia.edu/campuses-locations'),
]
PUBLIC = r'government of|agriculture and agrifood canada|fisheries and oceans canada|national forestry and grassland administration|national science and technology development agency|\baafc\b|ministry|general directorate of public health|department of (agriculture|health)|agriculture and agri.food|centers? for disease control|national center for emerging and zoonotic infectious diseases'
COMMERCIAL = r'\bllc\b|philip morris|celera genomics|\binscripta\b|\bltd\b|\blimited\b|\binc\b|\bcorporation\b|\bcompany\b|\bgmbh\b|\bco[., ]+ltd\b'
REPOSITORY = r'\bembl[ -]ebi\b|european bioinformatics institute|indian biological data centre|national center for biotechnology information|\bncbi\b|\bddbj\b|\bmaizegdb\b'


def match(pattern, text):
    return bool(re.search(pattern, text, re.I))


def display_bucket(row, threshold=5):
    if row['programme_labels']:
        return 'programme'
    if row['production_labels']:
        return 'centre'
    if row.get('repository_origin'):
        return 'repository'
    if row['research_submitter']:
        return 'candidate' if row['project_species'] is not None and row['project_species'] <= threshold else 'research'
    if row.get('public_origin'):
        return 'public'
    if row.get('commercial_origin'):
        return 'commercial'
    return 'unresolved'


def resolve_record(original, projects, programmes, production):
    row = copy.deepcopy(original)
    row.setdefault('original_bucket', original['bucket'])
    row.setdefault('original_research_submitter', any(x in original['institution_types'] for x in ['University', 'Research institute', 'Museum / garden']))
    row.setdefault('original_programme_labels', original['programme_labels'][:])
    row.setdefault('original_production_labels', original['production_labels'][:])
    bp = row['bioproject']
    meta = projects.get(bp, {})
    row['project_description'] = meta.get('description', '')
    row['project_metadata_date'] = meta.get('fetched_at', '')
    row['project_organisations'] = sorted(set(filter(None, meta.get('organisations', []))))
    names = [(row['accession'], 'assembly submitter', row['submitter'])] if row['submitter'] else []
    names += [(bp, 'BioProject organisation', name) for name in row['project_organisations']]
    evidence = row['programme_evidence'][:]
    # Include original lineage plus cache links; cycles and shared ancestors visited once.
    visited = set()
    pending = ([bp] if bp else []) + row.get('parent_projects', [])
    while pending:
        acc = pending.pop()
        if acc in visited:
            continue
        visited.add(acc)
        parent = projects.get(acc, {})
        text = ' '.join([parent.get('title', ''), parent.get('description', ''), *parent.get('organisations', [])])
        for label, pattern in programmes.items():
            if match(pattern, text):
                evidence.append({'label': label, 'source': acc,
                    'field': 'direct BioProject metadata' if acc == bp else 'linked parent BioProject metadata'})
        pending.extend(parent.get('parents', []))
    for source, field, name in names:
        for label, pattern in programmes.items():
            if match(pattern, name):
                evidence.append({'label': label, 'source': source, 'field': field})
    row['programme_evidence'] = [dict(zip(('label', 'source', 'field'), entry)) for entry in
        sorted({(e['label'], e['source'], e['field']) for e in evidence})]
    row['programme_labels'] = sorted({e['label'] for e in row['programme_evidence']})
    row['parent_projects'] = sorted((visited | set(row.get('parent_projects', []))) - {bp})
    institution_evidence = []
    production_evidence = []
    flags = {'research': bool(row['original_research_submitter']), 'public': False, 'commercial': False, 'repository': False}
    for source, field, name in names:
        for label, pattern in production.items():
            if match(pattern, name):
                production_evidence.append({'label': label, 'source': source, 'field': field, 'value': name})
        # A repository name establishes a submission role, not scientific leadership.
        if match(REPOSITORY, name):
            types = ['repository']
        else:
            types = [kind for kind, pattern in [('research', RESEARCH), ('public', PUBLIC), ('commercial', COMMERCIAL)] if match(pattern, name)]
        for pattern, label, url in ALIASES:
            if match(pattern, name):
                if 'research' not in types:
                    types.append('research')
                institution_evidence.append({'type': 'research', 'source': source, 'field': field,
                    'value': name, 'alias': label, 'alias_url': url})
        for kind in types:
            flags[kind] = True
            institution_evidence.append({'type': kind, 'source': source, 'field': field, 'value': name})
    row['organisation_evidence'] = institution_evidence
    row['production_evidence'] = production_evidence
    row['production_labels'] = sorted(set(row['production_labels']) | {e['label'] for e in production_evidence})
    row['research_submitter'] = flags['research']
    row['public_origin'] = flags['public']
    row['commercial_origin'] = flags['commercial']
    row['repository_origin'] = flags['repository']
    row['bucket'] = display_bucket(row)
    return row


def resolve_payload(payload, projects, programmes, production):
    result = copy.deepcopy(payload)
    result.setdefault('original_classification', result.get('classification', ''))
    result['classification'] = 'Explicit programme > production-centre origin > repository role > research origin at any size (low-output subset shown separately) > public agency > commercial organisation > unresolved. Direct organisation names and narrow documented aliases are origin evidence, not verified leadership or team size.'
    result['records'] = [resolve_record(r, projects, programmes, production) for r in payload['records']]
    result['provenance_resolution'] = {
        'resolved_at': datetime.now(timezone.utc).isoformat(),
        'method': 'Explicit linked programme metadata; direct BioProject organisations and assembly submitters; narrow institution aliases. Institutional origin does not verify leadership or team size.',
        'before_unresolved': sum(r.get('original_bucket', r['bucket']) == 'unresolved' for r in result['records']),
        'after_unresolved': sum(r['bucket'] == 'unresolved' for r in result['records']),
        'buckets': dict(Counter(r['bucket'] for r in result['records'])),
        'history_unknown': sum(r['novelty'] == 'unknown' for r in result['records']),
    }
    return result


def main():
    from build_goat_project_stats import ROOT, OUT, CACHE, PROGRAMMES, PRODUCTION, read_gz, write_gz
    payload = resolve_payload(read_gz(OUT), read_gz(CACHE), PROGRAMMES, PRODUCTION)
    write_gz(OUT, payload)
    print(json.dumps(payload['provenance_resolution'], indent=2))


if __name__ == '__main__':
    main()
