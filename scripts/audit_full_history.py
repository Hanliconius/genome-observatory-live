#!/usr/bin/env python3
"""Read-only, manual full-history reconciliation of Genome Observatory Live with NCBI.

NCBI remains authoritative for the current GenBank eukaryote chromosome/complete
assembly collection. Current live data store individual accessions only for the
recent period; older entries are compressed to daily aggregates. Consequently,
this audit compares old history at daily/species-first-seen resolution and
recent history at accession resolution. It NEVER modifies dashboard data.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NCBI_CMD = [
    'datasets', 'summary', 'genome', 'taxon', 'Eukaryota',
    '--assembly-source', 'GenBank', '--assembly-level',
    'chromosome,complete', '--as-json-lines',
]


def get(obj, *fields):
    for field in fields:
        part = obj
        for key in field.split('.'):
            if not isinstance(part, dict):
                part = None
                break
            part = part.get(key)
        if part is not None and part != '':
            return part
    return None


def normalize(obj):
    accession = get(obj, 'accession', 'assembly.accession', 'assembly_info.assembly_accession')
    name = get(obj, 'organism.organism_name', 'organism_name', 'organism.name')
    released = get(obj, 'assembly_info.release_date', 'assemblyInfo.releaseDate',
                   'assembly.release_date', 'release_date')
    taxid = get(obj, 'organism.tax_id', 'organism.taxId', 'tax_id')
    return {'accession':str(accession or ''),
            'organism_name':str(name or ''),
            'release_date':str(released or '')[:10],
            'tax_id':str(taxid or '')}


def iterate_ncbi(reports_jsonl=None):
    if reports_jsonl:
        with Path(reports_jsonl).open(encoding='utf-8') as fh:
            for number, line in enumerate(fh, 1):
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        raise RuntimeError(f'Malformed input JSON at line {number}: {e}') from e
        return

    # A temporary file avoids deadlock if the NCBI CLI writes extensive stderr
    # while stdout is streamed. Never load the entire NCBI response into RAM.
    with tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as err:
        process = subprocess.Popen(NCBI_CMD, stdout=subprocess.PIPE,
                                   stderr=err, text=True, encoding='utf-8')
        try:
            assert process.stdout is not None
            for number, line in enumerate(process.stdout, 1):
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        raise RuntimeError(f'Malformed NCBI JSON at line {number}: {e}') from e
            code = process.wait()
            if code:
                err.seek(0)
                raise RuntimeError(f'NCBI datasets exited {code}: {err.read()[-5000:]}')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()


def write_csv(path, headers, rows):
    with path.open('w', newline='', encoding='utf-8') as out:
        writer = csv.DictWriter(out, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def age_days(value, now):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return round((now - d).total_seconds() / 86400, 2)
    except (ValueError, TypeError):
        return None


def audit(dashboard_path, output_dir, reports_jsonl=None):
    now = datetime.now(timezone.utc)
    today = now.date()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(dashboard_path).resolve().parents[1]
    dashboard = json.loads(Path(dashboard_path).read_text(encoding='utf-8'))
    site_records = {
        str(x['accession']): x for x in dashboard.get('recent_assemblies', [])
        if x.get('accession')
    }
    # Match the retained interval used by the daily workflow.
    recent_days = 370
    recent_cutoff = (today - timedelta(days=recent_days)).isoformat()
    source = {}
    duplicates = []
    missing_fields = []
    scanned = 0
    for report in iterate_ncbi(reports_jsonl):
        scanned += 1
        record = normalize(report)
        accession = record['accession']
        released = record['release_date']
        if not accession or not record['organism_name'] or not released:
            missing_fields.append({'row_number':scanned, **record})
            continue
        try:
            date.fromisoformat(released)
        except ValueError:
            missing_fields.append({'row_number':scanned, **record})
            continue
        if accession in source:
            duplicates.append(record)
            continue
        source[accession] = record

    if not source:
        raise RuntimeError('NCBI returned no usable assembly records; refusing an empty audit')
    if missing_fields:
        write_csv(out / 'invalid_ncbi_records.csv',
                  ['row_number', 'accession', 'organism_name', 'release_date', 'tax_id'],
                  missing_fields)
        raise RuntimeError(f'NCBI returned {len(missing_fields)} incomplete or invalid rows; '
                           'see invalid_ncbi_records.csv. No reliable comparison possible.')
    previous_total = int(dashboard.get('summary', {}).get('all', {}).get('assemblies', 0) or 0)
    # Detect grossly incomplete upstream responses rather than reporting
    # thousands of spurious missing historical records.
    if previous_total and len(source) < previous_total * 0.80:
        raise RuntimeError(f'NCBI returned only {len(source)} records against '
                           f'{previous_total} previously counted; likely incomplete query')

    source_recent = {k: v for k, v in source.items() if v['release_date'] >= recent_cutoff}
    local_recent = {k: v for k, v in site_records.items()
                    if str(v.get('release_date', '')) >= recent_cutoff}
    missing_recent = [source_recent[k] for k in sorted(source_recent.keys() - local_recent.keys())]
    extra_recent = [local_recent[k] for k in sorted(local_recent.keys() - source_recent.keys())]
    changed_recent = []
    for k in sorted(source_recent.keys() & local_recent.keys()):
        current = source_recent[k]
        previous = local_recent[k]
        if (current['organism_name'] != previous.get('organism_name') or
                current['release_date'] != previous.get('release_date')):
            changed_recent.append({
                'accession':k,
                'ncbi_name':current['organism_name'],
                'dashboard_name':previous.get('organism_name', ''),
                'ncbi_release_date':current['release_date'],
                'dashboard_release_date':previous.get('release_date', ''),
            })

    per_date = defaultdict(lambda: {'assemblies':0, 'species':set()})
    source_first = {}
    for x in source.values():
        day = x['release_date']
        name = x['organism_name']
        per_date[day]['assemblies'] += 1
        per_date[day]['species'].add(name)
        if name not in source_first or day < source_first[name]:
            source_first[name] = day
    first_counts = Counter(source_first.values())
    ncbi_daily = {day:{'assemblies':a['assemblies'],
                       'species':len(a['species']),
                       'first_time_species':first_counts[day]}
                  for day, a in per_date.items()}
    dashboard_daily = {str(x['date']): x for x in dashboard.get('daily', [])}
    daily_diffs = []
    for day in sorted(set(ncbi_daily) | set(dashboard_daily)):
        current = ncbi_daily.get(day, {})
        previous = dashboard_daily.get(day, {})
        if any(int(current.get(k, 0) or 0) != int(previous.get(k, 0) or 0)
               for k in ('assemblies', 'species', 'first_time_species')):
            daily_diffs.append({
                'date':day,
                **{f'ncbi_{k}':int(current.get(k, 0) or 0)
                   for k in ('assemblies', 'species', 'first_time_species')},
                **{f'dashboard_{k}':int(previous.get(k, 0) or 0)
                   for k in ('assemblies', 'species', 'first_time_species')},
            })

    previous_first = dashboard.get('species_first_seen') or {}
    first_seen_diffs = []
    for name in sorted(source_first.keys() | previous_first.keys()):
        ncbi_day = source_first.get(name, '')
        previous_day = previous_first.get(name, '')
        if ncbi_day != previous_day:
            first_seen_diffs.append({
                'organism_name':name,
                'ncbi_first_release':ncbi_day,
                'dashboard_first_release':previous_day,
            })

    components = {
        'dashboard': 'data/dashboard.json',
        'genometrics': 'data/genometrics.json',
        'sample_countries': 'data/countries.json',
        'sequencing_countries': 'data/sequencing_countries.json',
        'taxa': 'data/taxa/index.json',
        'conservation_status': 'data/status/iucn.json',
    }
    freshness = []
    for component, filename in components.items():
        path = root / filename
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
                generated_at = payload.get('generated_at')
                days_old = age_days(generated_at, now)
                state = 'OK' if days_old is not None and days_old <= 3 else 'STALE'
            except (ValueError, OSError):
                generated_at = None
                days_old = None
                state = 'INVALID'
        else:
            generated_at = None
            days_old = None
            state = 'MISSING'
        freshness.append({'component':component, 'file':filename,
                          'generated_at':generated_at or '',
                          'age_days':days_old, 'status':state})

    inventory_cols = ['accession', 'organism_name', 'release_date', 'tax_id']
    write_csv(out / 'ncbi_full_inventory.csv', inventory_cols,
              (source[k] for k in sorted(source)))
    write_csv(out / 'missing_recent_accessions.csv', inventory_cols, missing_recent)
    write_csv(out / 'dashboard_only_recent_accessions.csv', inventory_cols, extra_recent)
    write_csv(out / 'changed_recent_metadata.csv',
              ['accession', 'ncbi_name', 'dashboard_name', 'ncbi_release_date',
               'dashboard_release_date'], changed_recent)
    write_csv(out / 'historical_daily_differences.csv',
              ['date', 'ncbi_assemblies', 'ncbi_species', 'ncbi_first_time_species',
               'dashboard_assemblies', 'dashboard_species',
               'dashboard_first_time_species'], daily_diffs)
    write_csv(out / 'first_seen_differences.csv',
              ['organism_name', 'ncbi_first_release', 'dashboard_first_release'],
              first_seen_diffs)
    write_csv(out / 'component_freshness.csv',
              ['component', 'file', 'generated_at', 'age_days', 'status'], freshness)
    write_csv(out / 'duplicate_ncbi_accessions.csv', inventory_cols, duplicates)

    result = {
        'audited_at':now.isoformat(),
        'source': 'NCBI Datasets: GenBank Eukaryota chromosome,complete',
        'ncbi_rows_scanned':scanned,
        'ncbi_unique_assemblies':len(source),
        'dashboard_all_assemblies':previous_total,
        'ncbi_species':len(source_first),
        'dashboard_all_species':int(dashboard.get('summary', {}).get('all', {}).get('species', 0) or 0),
        'comparison_recent_cutoff':recent_cutoff,
        'ncbi_recent_assemblies':len(source_recent),
        'dashboard_recent_assemblies':len(local_recent),
        'missing_recent_accessions':len(missing_recent),
        'dashboard_only_recent_accessions':len(extra_recent),
        'changed_recent_metadata':len(changed_recent),
        'historical_days_with_differences':len(daily_diffs),
        'species_first_release_differences':len(first_seen_diffs),
        'duplicate_ncbi_accessions':len(duplicates),
        'stale_or_missing_components':[x['component'] for x in freshness if x['status'] != 'OK'],
    }
    result['differences_detected'] = any([
        len(source) != previous_total,
        len(source_first) != result['dashboard_all_species'],
        missing_recent, extra_recent, changed_recent, daily_diffs,
        first_seen_diffs, duplicates, result['stale_or_missing_components'],
    ])
    (out / 'audit_summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    summary = [
        '# Genome Observatory Live — manual full-history audit',
        '',
        f'**Audit date:** {today.isoformat()} (UTC)',
        f'**Verdict:** {"DIFFERENCES FOUND — review report before reconciliation" if result["differences_detected"] else "NO DIFFERENCES DETECTED"}',
        '',
        '| Comparison | Current NCBI | Dashboard |',
        '| --- | ---: | ---: |',
        f'| All-time qualifying assemblies | {len(source):,} | {previous_total:,} |',
        f'| All-time organism names | {len(source_first):,} | {result["dashboard_all_species"]:,} |',
        f'| Recent accessions (release date >= {recent_cutoff}) | {len(source_recent):,} | {len(local_recent):,} |',
        '',
        f'- **Recent NCBI accessions absent from dashboard:** {len(missing_recent):,}',
        f'- **Recent dashboard accessions absent from NCBI:** {len(extra_recent):,}',
        f'- **Recent accessions with changed name/date:** {len(changed_recent):,}',
        f'- **Historical dates with changed aggregate counts:** {len(daily_diffs):,}',
        f'- **Species with differing earliest release dates:** {len(first_seen_diffs):,}',
        f'- **Duplicate accessions in NCBI response:** {len(duplicates):,}',
        f'- **Stale, missing, or invalid component data:** {", ".join(result["stale_or_missing_components"]) or "none"}',
        '',
        'This audit **does not change the site**. Download the workflow artifact for full CSV discrepancies and the NCBI accession inventory.',
        'A historical difference identifies a disagreement in current NCBI metadata vs saved snapshots, not necessarily a missed original deposit (withdrawals and corrections also cause differences).',
        '',
        '## Component freshness',
        '',
        '| Component | Generated (UTC) | Age (days) | Status |',
        '| --- | --- | ---: | --- |',
    ]
    for x in freshness:
        summary.append(f'| {x["component"]} | {x["generated_at"] or "—"} | '
                       f'{x["age_days"] if x["age_days"] is not None else "—"} | {x["status"]} |')
    summary.append('')
    (out / 'audit_report.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    print('\n'.join(summary))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dashboard', default=str(ROOT / 'data/dashboard.json'))
    ap.add_argument('--output-dir', default='audit-results')
    ap.add_argument('--reports-jsonl', help='For offline tests; otherwise query NCBI Datasets')
    args = ap.parse_args()
    audit(args.dashboard, args.output_dir, args.reports_jsonl)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'FULL AUDIT FAILED: {e}', file=sys.stderr)
        raise
