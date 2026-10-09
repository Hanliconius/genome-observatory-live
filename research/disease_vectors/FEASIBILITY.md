# Disease-vector genomics: data-source feasibility (research only)

**Status:** exploratory branch; no new dashboard tab and no changes to production classifications.

## Findings (9 October 2026)

- [VEuPathDB](https://veupathdb.org/veupathdb/app/static-content/about.html) includes VectorBase, but the VEuPathDB organism catalogue is not equivalent to an evidence-based catalogue of demonstrated disease vectors. It includes pathogens, hosts and related species.
- Current [VectorBase download pages](https://vectorbase.org/vectorbase/app/downloads/Current_Release/AalbopictusFoshan/) ask for a free login. Therefore an anonymous, stable species-list download usable by unattended GitHub Actions **has not been demonstrated**. Never store account credentials in this repository, and do not web-scrape login pages.
- [NCBI Datasets Taxonomy](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/how-tos/taxonomy/taxonomy/) provides a reproducible route to taxonomic identifiers once candidate vector species are known.
- If VEuPathDB grants an openly documented, anonymous organism-list API or reusable export, capture its endpoint, exact schema, retrieval timestamp, version, license and checksum before integrating. The only currently demonstrated local input is the NCBI audit inventory.

## Initial NCBI inventory screen

The 9 October 2026 full-history audit contains **18,884 qualifying assemblies**. Simple *genus* screens against it yield:

| Candidate group | Qualifying assemblies | Distinct organism names |
|---|---:|---:|
| Mosquito genera | 98 | 50 |
| Tick genera | 21 | 18 |
| Sand-fly genera | 5 | 5 |
| Tsetse flies | 2 | 1 |
| Triatomine bugs | 3 | 3 |
| Biting midges | 2 | 2 |
| Fleas (two exemplar genera) | 0 | 0 |
| Blackflies (Simulium) | 0 | 0 |
| Lice (Pediculus) | 0 | 0 |

**These are candidate screens, not established-vector species counts.** Genera lists are deliberately limited and non-exhaustive; their absence does not imply that no species in a vector group has a genome. Organism names may include subspecies. The counts come from the archived audit of *current* NCBI records, not a live API call, and may change.

## Reproduction

Download the ZIP artifact from [full-history audit run 37876937883](https://github.com/Hanliconius/genome-observatory-live/actions/runs/37876937883/artifacts/11592856991) and extract `ncbi_full_inventory.csv`.

```bash
python scripts/research_vector_candidates.py \
  --inventory ncbi_full_inventory.csv \
  --output candidate_vector_preview.json
```

The JSON is a screening artifact only. It does not publish to `data/`, and the current nightly site workflow does not invoke this research script.

Optionally provide an evidence-reviewed CSV:

```csv
scientific_name,ncbi_taxid,evidence_level,source_url
```

Permitted `evidence_level` values are `established`, `potential`, and `associated_only`. Each row must carry a species-level numeric NCBI taxid and a direct HTTPS citation supporting its classification. Do not seed the registry from *genus membership* or *VectorBase membership* alone. Exact taxid matches count as successful joins; matching scientific names with discordant IDs are only flagged for review.

## Minimum validation before a public tab

1. Obtain a **permitted, reproducible** vector/organism list, ideally a versioned export. If the only access is logged-in browsing, a manually reviewed, source-attributed registry is safer than automation.
2. Establish **species-level vector evidence** and a disease/pathogen association with primary literature or an authoritative public-health source; preserve the evidence source and date. Separate established, potential and merely genomics-associated organisms.
3. Map using numeric NCBI species taxids (handling subspecies and synonyms explicitly) and quantify unresolved names. Do not infer competence from genus, genome availability, or pathogen association alone.
4. Re-run matching against a fresh full NCBI inventory. Document species and assembly counts, zero-genome vector species, reference coverage, and any unresolved aliases.
5. Use a static, compact JSON registry and existing NCBI deposition data to generate charts. Keep the public tab behind a manual approval step until validation is satisfactory.

### Current decision

**Feasible for the existing static architecture; not ready to assert a comprehensive disease-vector dataset.** The next dependency is an evidence-backed species list and permissioned stable source access, not frontend work.
