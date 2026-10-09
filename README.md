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

The site uses **Past week**, **Past year**, and **All time** views where appropriate. Rate-oriented geographical displays use a trailing **30-day business-day** window to avoid unstable very-short-window estimates.

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

## Acknowledgements

The visual concept was inspired by Kate Morley's [National Grid: Live](https://grid.iamkate.com/), which demonstrates how a continuously changing technical system can be made immediately legible through a compact public dashboard.

Genome Observatory Live depends on the work of the teams maintaining NCBI, INSDC, ENA, DDBJ, IUCN, ROR, Tree of Sex, Wikimedia, and—most importantly—the researchers and sequencing initiatives depositing genome assemblies and their metadata in public databases.

## Citation and reuse

This is an evolving public dashboard rather than a static curated database release. If using a result analytically, record the **dashboard generation date** and verify critical accession-level information against the underlying primary database.

Code in this repository can be cited by linking to the relevant GitHub commit or release. For scientific claims derived from NCBI, IUCN, Tree of Sex, or other upstream datasets, please cite the underlying resource as well.

---

**Genome Observatory Live** · [Live dashboard](https://hanliconius.github.io/genome-observatory-live/app/) · [Source code](https://github.com/Hanliconius/genome-observatory-live) · [Joe Hanly](https://github.com/Hanliconius)
