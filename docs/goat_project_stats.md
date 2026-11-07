# Draft genome-producing effort analysis

This analysis is shown only on the unlinked `app/goat-intent/` research preview.
It does not alter the main dashboard inventory, species counters, or navigation.
The project-provenance data are a dated snapshot, separate from the daily GoaT
intent tracker. There is no new scheduled job in this change.

## Scope and counting

- Current GenBank eukaryote assemblies at Chromosome or Complete Genome level.
- NCBI Datasets discovery supplemented with the existing Assembly-index pending
  cache, matching the main Observatory snapshot at the time of this draft.
- One accession stem; retain its highest version. RefSeq twins are excluded.
- NCBI Taxonomy resolves strain/subspecies taxids to species before computing
  species footprints and selecting one first qualifying assembly per species.
- Equal release dates are broken by accession for counting, not scientific priority.
- All-level historical records provide context, not additional headline assemblies.

## Earlier genomes and updates

`fetch_goat_assembly_history.py` scans the current and historical GenBank summaries
for vertebrate_mammalian, vertebrate_other, invertebrate, plant, fungi, and protozoa.
Full assemblies are included; suppressed and Partial records are excluded. Replaced
versions are retained as historical evidence. The source URLs and capture date are
embedded in the output.

Contribution labels are first-ever genome (no earlier all-level genome found),
first chromosome-scale genome with an earlier scaffold/contig reference, additional
assembly, and unresolved history. A separate overlapping flag identifies current
accessions with an older scaffold/contig version under the same accession stem.
A same-date older version establishes version ordering; unrelated same-date lower-
level records share the first species-release cohort without establishing within-day priority. Earlier historical chromosome assemblies
prevent calling a later assembly the first chromosome-scale reference.

These are record-based operational definitions, not a complete bibliographic
history. Release dates can precede an assembly revision; annual plots are not
claims about when assemblies first reached chromosome scale. Withdrawn/suppressed
records, taxonomic changes, and incomplete archival metadata remain limitations.

## Project evidence

Keep the following overlapping fields per assembly:

- Explicit programme names in linked BioProject titles/descriptions or the assembly
  submitter. The named-programme patterns are in `PROGRAMMES` in the builder.
- Selected production-centre submitters, independently of programme membership.
- Institution-name clues: university, research institute, museum/garden, commercial.
  These are text patterns, not verified ROR identities or lab leadership.
- Distinct species in the direct BioProject across all-level Full eukaryote GenBank
  assemblies, including replaced versions. Do not equate this with team size.
- BioProject grants (agency + ID), recorded publication identifiers, BioSample owner,
  cached SRA centre names, and linked parent projects.

The provisional display precedence is programme evidence, selected production
centre, research institution plus low-output direct project, then unresolved.
The client exposes 1/5/10/20-species cutoffs. A consortium can make one BioProject
per species, so low output alone cannot establish independent small-team effort.
A service provider or submitter is not necessarily the research lead.

Grant footprints count distinct species among successfully enriched direct
BioProjects in the qualifying chromosome-scale inventory. They are lower bounds,
not total grant productivity. Missing funding and missing fetched metadata are
not evidence of no funding. Publication authors/affiliations have not been mined.

## Reproduction

Use the same merged JSONL provided to existing Observatory builders, preferably
from the same snapshot. All scripts require only the Python standard library.

```bash
python scripts/fetch_goat_assembly_history.py
python scripts/build_goat_project_stats.py --reports-jsonl /path/to/merged.jsonl --enrich
python -m unittest discover -s tests -p test_goat_project_stats.py
```

`--enrich` caches exact BioProject metadata and NCBI Taxonomy species ancestry.
BioProject accession searches resolve ENA/DDBJ accessions to NCBI UIDs before fetch:
passing an ENA accession directly to efetch can return an unrelated numeric UID.
Returned accessions must match the requested accession set. Failed enrichment
stays missing. Source caches are under `cache/goat_*metadata.json.gz` and
`cache/goat_all_level_history.json.gz`; browser payload is
`data/goat_project_stats.json.gz`. Running without `--enrich` rebuilds offline.

Charts show annual counts/shares, contribution type, BioProject footprint,
overlapping evidence, observed grant footprint, and candidate research submitters.
The evidence table can be searched and exported without discarding source labels.

## Unresolved audit

The preview splits unresolved assemblies into mutually exclusive rule-failure
reasons: no direct BioProject; unavailable footprint; missing submitter; recognised
research submitter above the selected threshold; and unrecognised research names
with footprints below/above the threshold. Missing-data reasons take precedence.
Enrichment availability is reported separately because a footprint can be known
without enriched project metadata. The charts follow contribution/organism and
threshold controls. A reason selector narrows the top-15 submitter and BioProject
rankings; evidence rows can optionally follow that unresolved subset. CSV exports
retain the current display group and unresolved reason.

Rankings count distinct species among selected unresolved qualifying assemblies,
not total institution or BioProject output. Missing identifiers are reported but
excluded from rankings. Species can recur between ranks. No records are reclassified
and the underlying snapshot is unchanged.

## Larger BioProject origins

The unlinked preview includes a separate origin view for direct BioProjects with
more than five observed all-level species, in fixed 6–20 / 21–100 / >100 bands.
Origin does not depend on the low-output candidate cutoff. Programme evidence
retains precedence, followed by production-centre names, research-institution
names, other recorded organisations, and missing origin. Institution/centre name
patterns use the assembly submitter and cached BioProject organisation strings.
This is recorded organisational provenance, not verified scientific leadership.
The original display buckets are unchanged.

Charts count selected qualifying assemblies. The project table counts one direct
BioProject per row and reports both its all-level footprint and selected species/
assembly totals. Mixed projects retain every selected origin label. Origin filters
retain entire projects with any matching selected record. Search covers purpose,
organisations and identifiers. Descriptions, parent links, grants and a CSV retain
the evidence. Cached organisations/descriptions/capture dates from
`cache/goat_project_metadata.json.gz` are embedded as the JSON element
`project-origin-metadata`, for the projects above five species in the dated
`data/goat_project_stats.json.gz` snapshot. Regenerate that embedded map when
refreshing the provenance snapshot; it does not follow the daily intent refresh.
