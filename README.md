<p align="center">
  <img src="app/favicon.svg" width="96" height="96" alt="Genome Observatory Live logo">
</p>

# Genome Observatory Live

**A live, lightweight view of the growth of chromosome-scale eukaryotic genome sequencing.**

[**Open Genome Observatory Live →**](https://hanliconius.github.io/genome-observatory-live/app/)

Genome Observatory Live tracks chromosome-scale and complete eukaryotic genome assemblies entering the public NCBI/GenBank ecosystem, alongside RefSeq annotation activity and collection-wide metadata. It is designed as a compact public observatory: no sequence data are mirrored, the site is entirely static, and the dataset refreshes automatically on GitHub Actions.

Created by **Joe Hanly** · [GitHub](https://github.com/Hanliconius) · [Bluesky](https://bsky.app/profile/hanliconius.bsky.social)

> **What does “deposit” mean here?** A deposit is a qualifying public GenBank assembly record, not the date a genome was sequenced, published in a paper, or necessarily first made public by another INSDC partner. Release/indexing dates can therefore differ from publication dates and may lag availability elsewhere.

## What the observatory tracks

The core collection is **GenBank (GCA_) eukaryotic assemblies at `Chromosome` or `Complete Genome` level**. RefSeq partners are not counted a second time.

The dashboard currently includes:

- **Live deposition activity** — assemblies, species represented, first-time species, recent daily activity, annual totals, cumulative growth, and milestone dates.
- **Newest arrivals** — recent qualifying assemblies with organism metadata, common-name fallbacks, assembly links, and representative imagery when available.
- **RefSeq annotation activity** — eukaryotic annotations currently in progress and recently completed.
- **Genometrics** — assembly-length and chromosome-number distributions, contiguity statistics, three taxon-specific assembly-length ribbon panels, mitochondrial and plastid associations, sex-chromosome labels, karyotype comparisons, and observed-versus-expected sex-chromosome annotation.
- **Conservation status** — chromosome-scale genome deposition for threatened (VU/EN/CR) and extinct (EW/EX) taxa using the IUCN Red List.
- **Geography** — sample-origin geography plus a separate sequencing/institute-country view.
- **Taxonomic explorer** — searchable comparisons at phylum and order level, including historical and recent deposition activity, assembly-length distributions and sample-origin maps.

The site uses **Past week**, **Past year**, and **All time** views where appropriate. Rate-oriented geographical displays use a trailing **30-day calendar-day** window to avoid unstable very-short-window estimates.

## Definitions

| Metric | Meaning |
| --- | --- |
| **Assembly / deposit** | A public GenBank eukaryotic assembly with assembly level `Chromosome` or `Complete Genome`. |
| **Species** | Distinct organism names represented among qualifying assemblies in the selected interval. |
| **First-time species** | The first observed qualifying chromosome/complete GenBank assembly for that organism in the historical index. |
| **Genome deposits per day** | Deposition activity derived from public assembly release dates; this is not sequencing-machine throughput. |
| **In annotation** | Eukaryotic RefSeq annotation runs reported by NCBI as currently in progress. |
| **Recent annotations** | Recently completed NCBI eukaryotic RefSeq annotation runs. |

Because the observatory follows **public database records**, it should be interpreted as a measure of public genome-assembly/deposition activity rather than the date laboratory sequencing occurred.

## Data sources

Genome Observatory Live combines public metadata from several resources:

- [NCBI Datasets](https://www.ncbi.nlm.nih.gov/datasets/) — genome assembly metadata and sequence reports.
- [NCBI Assembly / GenBank](https://www.ncbi.nlm.nih.gov/assembly/) — public assembly records underlying the core collection.
- [NCBI Eukaryotic Genome Annotation](https://www.ncbi.nlm.nih.gov/refseq/annotation_euk/) — RefSeq annotation activity.
- [NCBI Taxonomy](https://www.ncbi.nlm.nih.gov/taxonomy) — taxonomic relationships used by the explorer and higher-level summaries.
- [NCBI SRA](https://www.ncbi.nlm.nih.gov/sra) — sequencing-center metadata used in the institute-country analysis.
- [Research Organization Registry (ROR)](https://ror.org/) — conservative resolution of organization names to countries.
- [IUCN Red List](https://www.iucnredlist.org/) — conservation categories for threatened and extinct views.
- [Tree of Sex](https://www.treeofsex.org/database) — comparative sex-chromosome, karyotype, ploidy, and sexual-system reference information used by selected Genometrics panels.
- [Wikimedia Commons](https://commons.wikimedia.org/) — representative organism imagery and attribution metadata.

### ENA, GenBank and INSDC

GenBank, the [European Nucleotide Archive (ENA)](https://www.ebi.ac.uk/ena/browser/home), and [DDBJ](https://www.ddbj.nig.ac.jp/) are partners in the [International Nucleotide Sequence Database Collaboration (INSDC)](https://www.insdc.org/). Sequence records are exchanged among the partners, but the observatory currently uses the **NCBI representation and NCBI assembly release metadata as its canonical feed**.

Consequently, the site is not currently an independent earliest-publication monitor across all three INSDC portals. An assembly first visible at ENA may not be reflected by the observatory until it is represented in the NCBI assembly data queried by the updater.

## Geography and provenance

The two geographic views answer different questions and should not be conflated.

**Sample country** is inferred from geographic information attached to the NCBI BioSample and is intended to represent where the biological material originated.

**Institute country** preferentially uses the SRA sequencing-center name associated with reads underlying an assembly. Center names are resolved using curated unambiguous aliases and ROR. When a usable sequencing-center country is unavailable, the current implementation falls back to the NCBI assembly submitter. This makes the institute view a **provenance approximation**, not a claim that every listed institute physically generated every base of sequence.

Assemblies can be associated with more than one institute country when their recorded sequencing centers span countries.

## Genometrics

The Genometrics section asks what can be learned about the *collection itself* from assembly metadata.

### Organelle association

Mitochondrial and plastid panels count an organelle only when NCBI assembly metadata explicitly associates that organelle genome with the tracked nuclear assembly. Missing association is therefore **not evidence that the organism lacks the organelle**.

### Sex chromosomes

Observed X/Y/Z/W and other explicitly identified sex-chromosome labels are extracted from NCBI sequence reports. “No observed label” means that an explicit sex-chromosome-style chromosome name was not found; it does not imply biological absence.

Expected systems use [Tree of Sex](https://www.treeofsex.org/database) records. Direct species evidence is preferred, with conservative concordant higher-taxon evidence used where implemented. The provenance level of an expectation is retained in the generated data.

### Karyotype

For species with suitable Tree of Sex chromosome-count information, the reported number of chromosomes in the NCBI assembly is compared with biological karyotype information. Because an assembly may represent a haploid chromosome complement whereas a literature karyotype is often reported as 2N, both interpretations are considered. These comparisons are descriptive audits rather than automatic assembly-quality judgments.

### Assembly architecture

Assembly-length and chromosome-number histograms describe the deposited collection. Assembly length and contig N50 come from NCBI assembly statistics. The genome-architecture scatterplot uses logarithmic axes; the three Animal/Plant/Fungi ribbon panels use separate linear Mb/Gb axes, with heights normalized within each taxon and high-end values beyond the visible range counted separately.

## Conservation views

Threatened and extinct panels join the tracked genome collection to current [IUCN Red List](https://www.iucnredlist.org/) categories.

- **Threatened:** Vulnerable (VU), Endangered (EN), and Critically Endangered (CR).
- **Extinct:** Extinct in the Wild (EW) and Extinct (EX).

These panels measure the availability of qualifying public genome assemblies for taxa carrying those classifications; they are not intended as assessments of conservation priorities.

## How it works

The project is deliberately small enough to run and host for free.

```text
NCBI / public reference metadata
            │
            ▼
      Python builders
            │
            ├── dashboard.json
            ├── genometrics.json
            ├── countries.json
            ├── sequencing_countries.json
            ├── status/
            └── taxa/
            │
            ▼
      static HTML / CSS / JS
            │
            ▼
         GitHub Pages
```

No genome sequence files are stored in this repository. Recent assembly metadata are retained in detail while older history is represented by compact aggregates. This keeps the repository and browser payload small even as the underlying public collection grows.

The updater deliberately re-queries an overlapping recent interval so that missed runs and retrospective NCBI metadata changes can be incorporated rather than permanently creating holes.

## Automatic refresh

The workflow in [`.github/workflows/update.yml`](.github/workflows/update.yml) runs on a **24-hour cadence** and can also be triggered manually. It:

1. installs the NCBI Datasets CLI and Python dependencies;
2. refreshes recent qualifying assemblies, annotation activity, and representative images;
3. rebuilds taxonomic, geographic, sequencing-provenance, conservation, and selected Genometrics datasets;
4. commits changed compact JSON data back to the repository; and
5. deploys the static site to GitHub Pages.

The dashboard displays its own latest data-generation timestamp, so a successful page load should not be assumed to mean the underlying metadata were refreshed at that instant.

## Quarterly full-history audit (manual only)

About four times per year (for example **January, April, July, and October**), open
[GitHub Actions → Full genome history audit (manual)](https://github.com/Hanliconius/genome-observatory-live/actions/workflows/full-history-audit.yml),
choose **Run workflow** on `main`, then inspect the run summary and download its artifact.

This **read-only** workflow fetches the entire current NCBI Datasets collection
of eukaryote GenBank chromosome/complete assemblies. It reports:

- Missing, extra, or changed individual accessions within the recent ~370-day detail window.
- Disagreements in historical per-day assembly counts, distinct organism counts, and first-time species counts.
- Differences in the earliest qualifying release date for each organism.
- Freshness of the dashboard, Genometrics, geography, taxonomy, and conservation JSON.
- A CSV inventory of every qualifying NCBI accession, plus discrepancy CSVs and a Markdown summary.

Because older dashboard data are deliberately stored as compact aggregates,
the audit **cannot name a missing historical accession based on the dashboard alone**;
it identifies discrepant historical dates and provides the full NCBI inventory for investigation.
NCBI withdrawals and retrospective metadata corrections can also produce legitimate
differences. Review discrepancies before making any corrections to the public dashboard.

The audit never commits data, triggers a refresh, or deploys Pages. Artifacts
are retained by GitHub Actions for **90 days**; download them if permanent
records are needed. A successful workflow run means the comparison completed,
**not necessarily that there were no differences**.

## Repository layout

```text
app/                         static dashboard application
cache/                       compact reusable metadata caches
data/
  dashboard.json             main time-series and recent-assembly data
  genometrics.json           collection-wide metadata metrics
  countries.json             BioSample geographic summaries
  sequencing_countries.json  sequencing/institute provenance summaries
  status/                    conservation-status summaries
  taxa/                      phylum/order explorer data
scripts/
  update.py                  primary NCBI refresh
  bootstrap_history.py       initial lifetime-history bootstrap
  build_taxa.py              taxonomic explorer
  build_countries.py         sample geography
  build_sequencing_countries.py
  build_genometrics.py
  build_iucn.py
.github/workflows/update.yml automated refresh + Pages deployment
```

## Running locally

Requirements:

- Python 3.12
- packages in `requirements.txt`
- [NCBI Datasets command-line tools](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/download-and-install/)

For a first deployment:

```bash
pip install -r requirements.txt
python scripts/bootstrap_history.py
python scripts/update.py
```

Then serve the repository root:

```bash
python -m http.server 8000
```

and open `http://localhost:8000/app/`.

The individual builders can also be run separately while developing particular dashboard sections.

## Reproducibility and limitations

A few boundaries are intentional:

- **NCBI-centric release timing.** The current live feed follows NCBI assembly metadata rather than independently reconciling the earliest public date across ENA, GenBank, and DDBJ.
- **Metadata quality matters.** Country, center, common-name, organelle, chromosome, and other summaries can only be as complete as their source metadata.
- **Taxon names change.** Historical database records and external resources may use synonyms or older classifications.
- **“First-time species” is operational.** It means first qualifying assembly observed in the indexed historical collection under the organism-name logic used here.
- **No raw sequence mirror.** This is an observatory of metadata and aggregate trends, not a genome archive.
- **Release is not publication.** A database release date should not be interpreted as a paper-publication date or the date sequencing was performed.

These constraints are kept visible because the project is intended to make the dynamics of public genome sequencing easier to inspect without implying more precision than the source databases provide.

## Pathogens & vectors

The **Pathogens & vectors** tab combines vector surveillance taxa with a curated catalogue of disease-causing protists, parasitic worms and selected pathogenic fungi. Separate **Pathogens** and **Vectors** subtabs keep their totals, composition, deposition history and species inventories distinct. Pathogens opens with all curated pathogens and parasites, with an additional filter for protists, worms or fungi; Vectors uses only the MapVEu surveillance catalogue.

Each subtab also has an all-time BioSample sample-origin map alongside the yearly and cumulative deposit charts, filterable by broad organism group. Countries and marine localities use the same parsing rules as the country explorer; assemblies without a resolved locality are reported explicitly. These maps show sequenced sample origins, not disease prevalence or species ranges.

The vector source remains the MapVEu/VectorBase sample export dated 10 October 2026 (1,834,448 records; 536 taxonomic labels), summarized in [`data/status/mapveu_species.tsv`](data/status/mapveu_species.tsv). Broader vector groups use [`data/status/vector_types.json`](data/status/vector_types.json). Source membership does not establish vector competence; categories absent from that export are not represented.

The downloadable, editable [`data/status/pathogens.tsv`](data/status/pathogens.tsv) records each selected species, organism group, disease association, source URL, explicit aliases and curation notes. The initial catalogue was reviewed on 11 October 2026 using [CDC DPDx](https://www.cdc.gov/dpdx/az.html) disease pages and selected species from the [WHO fungal priority pathogen list](https://www.who.int/publications/i/item/9789240060241). It focuses on human and zoonotic disease; it is not an exhaustive catalogue of veterinary, plant or fungal pathogens. Non-pathogenic diagnostic comparison organisms are excluded.

To extend the catalogue, add a species-level scientific name with a disease-specific source and one of the existing organism groups. List a verified alternative binomial in `aliases`, separated by `|` when multiple aliases are needed. Do not add an entire genus merely because some members cause disease. The next publication rebuilds the view automatically.

[`scripts/build_pathogens.py`](scripts/build_pathogens.py) combines the sources and rebuilds the tab on every publication and scheduled refresh, using [`scripts/build_vectors.py`](scripts/build_vectors.py) for the retained vector inventory. Current GenBank Chromosome and Complete Genome assemblies qualify. Pathogen strains and subspecies roll up to their curated species; aliases are matched only when explicitly listed. Each accession is counted once, including when multiple sources refer to it. A zero means no qualifying assembly matched, rather than no genome exists. Coverage denominators describe the selected catalogue, not every pathogen. Pace retains the trailing 30-calendar-day window.

## Acknowledgements

The visual concept was inspired by Kate Morley's [National Grid: Live](https://grid.iamkate.com/), which demonstrates how a continuously changing technical system can be made immediately legible through a compact public dashboard.

Genome Observatory Live depends on the work of the teams maintaining NCBI, INSDC, ENA, DDBJ, IUCN, ROR, Tree of Sex, Wikimedia, and—most importantly—the researchers and sequencing initiatives depositing genome assemblies and their metadata in public databases.

## Citation and reuse

This is an evolving public dashboard rather than a static curated database release. If using a result analytically, record the **dashboard generation date** and verify critical accession-level information against the underlying primary database.

Code in this repository can be cited by linking to the relevant GitHub commit or release. For scientific claims derived from NCBI, IUCN, Tree of Sex, or other upstream datasets, please cite the underlying resource as well.

---

**Genome Observatory Live** · [Live dashboard](https://hanliconius.github.io/genome-observatory-live/app/) · [Source code](https://github.com/Hanliconius/genome-observatory-live) · [Joe Hanly](https://github.com/Hanliconius)

## Agriculture

The **Agriculture** tab has three separate subtabs: **Organisms**, **Pests** and **Pathogens**. Each has its own all-time summaries, newest genome, catalogue coverage, deposition history, recent assemblies, species inventory and BioSample sample-origin map. The broad-group selector filters every panel. Maps sit beside the yearly and cumulative charts.

The editable, downloadable [`data/status/agriculture.tsv`](data/status/agriculture.tsv) supplies explicit scientific names, roles, broad groups, source links, aliases and curation notes. The initial selection uses the botanical crop entries in the [FAO agricultural census crop classification](https://www.fao.org/4/a0135e/A0135E10.htm), selected [FAO livestock](https://www.fao.org/livestock-systems/global-distributions/en/) and [aquaculture](https://www.fao.org/4/W2333E/W2333E00.htm) taxa, individual [EPPO](https://gd.eppo.int/) records for additional crops, animal pests, weeds and plant pathogens, and [WOAH](https://www.woah.org/en/disease/theileriosis/) livestock pathogen records. Names were reviewed against NCBI Taxonomy on 11 October 2026; older names are retained as explicit aliases and duplicate synonyms are consolidated. Source misspellings of major crops, including potato and sweet potato, are corrected. Each taxon has one primary display group, although several crops have multiple uses. It is a selected catalogue, not a complete global list of cultivated organisms, agricultural pests or diseases.

The 13 October 2026 expansion combines the [Ag100Pest target table](https://i5k.github.io/ag100pest) with qualifying assemblies under [PRJNA555319](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA555319), [USDA CAPS 2026](https://approvedmethods.ceris.purdue.edu/2026), the public [EPPO datasheet index](https://gd.eppo.int/datasheets/), the [USDA APHIS veterinary list](https://www.aphis.usda.gov/animal-product-import/organisms-vectors/livestock-poultry-pathogens), and [PHI-base 5.6](https://zenodo.org/records/21196331). PHI-base is restricted to interactions involving the listed agricultural hosts; gene records are collapsed to species/host memberships. Plant health includes forestry, ornamentals, stored products and invasive weeds. The catalogue is a union of these selected sources, not a complete global census.

Every included taxon retains all source memberships in [`agriculture_memberships.tsv`](data/status/agriculture_memberships.tsv), including original names, hosts/commodities and publication links. [`agriculture_sources.tsv`](data/status/agriculture_sources.tsv) records source versions, retrieval dates, scope, licences and available snapshot hashes. The page shows source badges, selected publication links and an inventory source filter. All publication links remain in the downloadable memberships file. [`agriculture_exclusions.tsv`](data/status/agriculture_exclusions.tsv) records rejected source labels. Unresolved, ambiguous, genus-only and non-eukaryotic labels are excluded rather than matched to an entire genus. NCBI Taxonomy provides name resolution and lineage checks, not evidence of agricultural relevance.

Canonical taxa have one primary display role, so overlapping sources do not duplicate genomes across subtabs. Documented biological-control species appear under Organisms → Biological control, with evidence in [`agriculture_role_overrides.tsv`](data/status/agriculture_role_overrides.tsv). Source interactions can describe multiple biological roles; the display classification does not imply every interaction is pathogenic. Agricultural-host associations alone are not sufficient to label a beneficial organism as a pest. The explicit importer is run when reviewing source updates (`python scripts/import_agriculture_sources.py --cache-dir /path/to/cache --reports-jsonl /path/to/current.jsonl`); daily builds use the reviewed TSV snapshots without silently changing category definitions. Importing requires `requests` and `beautifulsoup4` in addition to the normal build dependencies.

[`scripts/build_agriculture.py`](scripts/build_agriculture.py) refreshes the data on every publication and daily update. Eligibility remains current GenBank Chromosome/Complete eukaryotic assemblies. Only explicit species names and aliases match; named cultivated hybrids can be listed individually. Varieties, strains and breeds roll up to their listed taxon. Unspecified hybrids and unlisted wild relatives are excluded; wild individuals of a listed species can still qualify. Therefore these counts describe genomes of agriculturally relevant taxa, not exclusively farmed samples. Pest/pathogen membership does not prove that each sample caused damage or disease. Bacteria and viruses are outside the dashboard's eukaryotic scope.

Geography uses reported BioSample collection countries and named marine localities, with unassigned assemblies shown explicitly. These maps describe sequenced sample origins, rather than agricultural production or pest/disease prevalence. Catalogue coverage uses the selected source taxa as its denominator. Pace retains the 30-calendar-day window.


The country-source expansion adds nine reviewed snapshots covering Brazil (MAPA present/absent quarantine lists), China (MARA national agricultural quarantine list and import quarantine catalogue), Australia (DAFF national priorities and Bioplatforms IPM projects), Canada (CFIA regulated pests), Japan (MAFF current quarantine table updated 18 June 2026), and Ghana (NPPO crop quarantine tables). The registry distinguishes source countries from genome collection origins. Original restrictions such as exotic strains, races and non-national species remain in membership evidence. These lists define regional plant-health relevance; membership does not imply a species is present in that country or that every strain is harmful. Existing primary roles are preserved, with explicit reviews separating crop pollinators and biological-control agents from pests.

[`agriculture_country_sources.tsv`](data/status/agriculture_country_sources.tsv) records source versions, scope and hashes; [`agriculture_country_candidates.tsv`](data/status/agriculture_country_candidates.tsv) retains reviewed source labels and explicit matching identities before taxonomy resolution. [`scripts/extract_country_agriculture.py`](scripts/extract_country_agriculture.py) rebuilds these tables from downloaded snapshots and reviewed text extraction; the main importer incorporates them into the union. A changed Australian IPM table requires renewed role review. Australia's priority list is a reviewed transcription of the scientific-name column (hash of that transcription), not a claim that every source item is eligible. Ghana's source has October 2017 content, a December 2020 attachment and a July 2026 republication: it is labelled as historical evidence rather than current legal status. Japan's future December 2026 table is not included.

New Zealand's public threat-page retrieval did not provide an extractable species list; wider genebank catalogues were identified but not wholesale imported because they include wild relatives and conserved material without explicit cultivation roles. The country expansion is a reviewed selection, not complete global coverage. Source snapshots are refreshed explicitly, while genome counts and coverage donuts continue to rebuild daily against the reviewed catalogue.


### Assembly discovery and duplicate prevention

Every data refresh prepares one shared current GenBank eukaryote Chromosome/Complete inventory with `scripts/assembly_sources.py`. It combines the full NCBI Datasets inventory with current Entrez Assembly discoveries from the last 30 days (sequence release, GenBank publication or assembly update). Pending Assembly records are rechecked by UID even after leaving that discovery window. Withdrawn/superseded records and non-qualifying assembly levels are excluded. A failed or incomplete discovery response stops publication.

A versioned GenBank accession is the shared record identity; its unversioned accession stem is the counting identity. The highest current version wins across both sources. Datasets enriches the same version rather than creating another record; older-version sequence statistics are never copied to a new version. RefSeq partner accessions are not separate GenBank deposits. Shared counts, historical days, earliest-species dates and all derived panels are rebuilt from this single temporary JSONL (`GENOME_REPORTS_JSONL`), so source counts are never added together. The full snapshot is temporary; pending records and a compact public audit persist in `cache/assembly_index_pending.json` and `data/audits/assembly_sources.json`.

Datasets remains the preferred bundled metadata source. Pending Assembly records use verified NCBI Taxonomy scientific names/lineages, sequence-release dates, assembly statistics and linked BioSample attributes where available. Other unavailable details remain missing; the site explicitly reports the pending-metadata count. Sequence-release dates retain the dashboard's existing time-series definition; Assembly publication dates are recorded separately, and disagreements with Datasets are recorded in the source audit. Once Datasets indexes an accession, its metadata replaces the pending representation without changing that accession's identity. Current inventory reconciliation also removes obsolete versions and withdrawals outside the old incremental window.
