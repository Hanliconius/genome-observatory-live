# Recovering unresolved GoAT analysis records

This is the stepwise procedure used to recover **recorded project origin** in the
unlinked GoAT research preview. It does not establish scientific leadership,
team size, programme independence or who funded the complete study.

## 1. Freeze the inventory and keep the original assignments

Use `data/goat_project_stats.json.gz` and the matching
`cache/goat_project_metadata.json.gz` snapshot. The provenance inventory is dated
31 October 2026; origin resolution was applied on 8 November 2026. The daily
GoAT intent capture and daily main-dashboard inventory are separate.

Keep every accession, species identity, assembly release date, BioProject species
footprint and genome-history label unchanged. Retain `original_bucket`,
`original_programme_labels`, `original_production_labels`, and
`original_research_submitter` so a new assignment can be compared with the
original rule. Missing metadata is not evidence of absence.

## 2. Follow explicit programme evidence

Start with programme evidence already attached to the assembly. Inspect the direct
BioProject's title, description and organisations, then follow recorded parent
BioProject links transitively. Visit every accession once to handle shared
ancestors and cycles. Match the explicit programme patterns in `PROGRAMMES` in
`scripts/build_goat_project_stats.py`.

Record each match as `programme_evidence`: label, source accession and source
field. A parent programme can supply membership evidence; **do not inherit its
institution as the direct scientific lead**. Generic terms such as “genome
project” do not establish consortium membership. In this pass, PRJNA483067 gains
an explicit Vertebrate Genomes Project assignment. Parent/metadata checks also
add programme labels to records that already had other programme assignments.

## 3. Recover direct organisational evidence

Read the assembly submitter and the direct BioProject `organisations` field.
Classify these strings with transparent rules, retaining the matched value,
source accession and field:

- Selected production-centre names use `PRODUCTION`, including Sanger, Genoscope,
  BGI/CNGB, JGI and other named centres in that dictionary.
- Repository names are treated as repository roles. EMBL-EBI or a data centre does
  not establish the research group's identity.
- University, institute, laboratory, museum, research-centre and similar name
  patterns provide research-origin evidence.
- Explicit government/public-agency names and commercial suffixes provide
  separate public or commercial origin clues.

The matched sources are retained in `organisation_evidence` and
`production_evidence`; `project_organisations` retains the original organisation
strings. Multiple roles may coexist. SRA centres, BioSample owners and grant
identifiers remain supporting fields and are not automatically substituted for
the scientific lead.

## 4. Resolve narrow institution aliases

Use the `ALIASES` list in `scripts/resolve_goat_provenance.py`. Each alias has a
bounded pattern, an expanded name and a supporting institutional or publication
URL. Examples include KAUST, MPIPZ, ETH Zurich, VIB/KU Leuven, NIAB, NDSU, LSHTM,
NCGR and the exact submitter `disafa_plant_genetics`.

For every match retain `alias` and `alias_url` alongside the original source
string. Do not globally expand ambiguous short strings. For example, “BSC” alone
remains unresolved: a plausible expansion is not enough to identify a particular
submission. Add a project-specific override only after a primary source explicitly
links that BioProject to the organisation; preserve both the accession and the
supporting URL. No such publication override was applied in this pass.

## 5. Keep origin independent of output size

Apply these display priorities to the overlapping evidence:

1. Explicit programme evidence.
2. Selected production-centre name.
3. Repository/archive role.
4. Research-origin evidence; show the low-output subset separately.
5. Public agency/government name.
6. Commercial organisation name.
7. Origin type unresolved.

The default low-output cutoff is five species in the **direct BioProject**, using
all-level Full GenBank eukaryote assemblies, including replaced records. The page
allows cutoffs of 1, 5, 10 or 20. A larger or unknown footprint retains research
origin; it no longer becomes unresolved solely because it exceeds the cutoff.
Low-output research origin remains a candidate for a focused effort, not a
verified small team. An institution may contain many labs; one programme may
create many small direct BioProjects.

## 6. Audit the recovered and remaining records

The Resolution audit tab counts the originally unresolved subset, shows the
recovered categories, and ranks the remaining submitters and BioProjects. In the
Funding & evidence tab, select **Recovered origin categories** or **Unresolved**
under Evidence rows. Search organisation strings or aliases, inspect each record's
source evidence, and download the filtered CSV.

Remaining reasons are mutually exclusive: no direct project, unavailable project
footprint, no recorded names, or recorded names whose organisational type remains
unclear. A recovered repository category still does not identify the scientific
lead. A recovered institution does not resolve team size.

Genome-history uncertainty is audited separately. Six records lack usable dated
historical context in this snapshot. Do not call them first-ever genomes merely
because an older record was not found. Publication authors/affiliations and
historical missing records were not systematically recovered in this pass.

## 7. Reproduce and validate

Run from the repository root. These commands use the existing local snapshot and
caches; they do not download genomes or launch a new inventory build.

```bash
python scripts/resolve_goat_provenance.py
python -m unittest discover -s tests -p 'test_goat*.py'
python - <<'PY'
import gzip, json
from collections import Counter
from pathlib import Path
p = json.load(gzip.open('data/goat_project_stats.json.gz', 'rt'))
rows = p['records']
assert len(rows) == len({r['accession'].split('.')[0] for r in rows})
print(json.dumps(p['provenance_resolution'], indent=2))
print('Recovered from original unresolved:', dict(Counter(
    r['bucket'] for r in rows
    if r['original_bucket'] == 'unresolved' and r['bucket'] != 'unresolved'
)))
print('Remaining genome-history gaps:', sum(r['novelty'] == 'unknown' for r in rows))
PY
```

The main provenance builder also invokes this resolver after creating a future
snapshot. The resolver is idempotent for record content and preserves the original
assignment; the resolution timestamp updates on each run. Tests cover source
attribution, parent cycles, size thresholds, repository roles, bounded aliases,
ambiguous abbreviations and count preservation. Before publishing a refreshed
snapshot, compare accessions, species, dates, footprints and genome-history fields
against its source inventory. The UI must preserve total counts when switching
tabs or changing display cutoffs.

## Result of the 8 November 2026 pass

At the default five-species cutoff, 2,751 of 19,416 assemblies were originally
unresolved. The following are disjoint final assignments among that subset:

| Recovered origin category | Assemblies |
| --- | ---: |
| Research origin, low-output project | 1,132 |
| Research origin, larger / unknown footprint | 719 |
| Public agency / government name | 172 |
| Production-centre origin | 111 |
| Commercial organisation name | 106 |
| Repository/archive origin | 90 |
| Explicit programme link | 1 |
| Still unresolved | 420 |

This recovers an origin category for 2,331 records (84.7% of the original
unresolved subset). It does not imply that 84.7% acquired verified lab identities.
