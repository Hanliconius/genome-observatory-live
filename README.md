# Eukaryote Genome Watch

A small static dashboard for chromosome-scale eukaryote genome deposition and NCBI RefSeq annotation activity, aesthetically inspired by Kate Morley's **National Grid: Live**.

## What it counts

* **Deposits:** GenBank (GCA_) eukaryotic assemblies whose assembly level is `chromosome` or `complete`. RefSeq partners are not counted again.
* **Species:** distinct organism names represented in the selected period.
* **First-time species:** first observed chromosome/complete GenBank assembly for that organism in the historical index.
* **Annotations:** NCBI Eukaryotic RefSeq annotation runs currently in progress and those recently completed.

This is best described as public **genome assembly/deposition throughput**, not literal sequencing-machine capacity.

## Storage model

No sequence data are stored. Full per-assembly metadata is retained only for the last 90 days. Older history is collapsed to daily counts; the first-seen species index stores only organism -> date. Wikimedia images are cached as URLs plus credit strings.

## First deployment

1. Install Python 3.12, `pip install -r requirements.txt`, and the NCBI `datasets` CLI.
2. Run `python scripts/bootstrap_history.py` once. This streams all matching historical metadata and discards the individual records after aggregating them.
3. Run `python scripts/update.py`.
4. Serve the repository root as a static site and use `/app/` as the entry point. For GitHub Pages, either publish the whole repo or move/copy `app/` and `data/` into the selected Pages directory.

## Automatic updates

`.github/workflows/update.yml` refreshes the data daily (24-hour cadence) and commits the changed JSON. A static host such as GitHub Pages, Cloudflare Pages, or Netlify can deploy every commit.

## Local preview

From the repository root:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/app/`.

## Data-source notes

The updater deliberately re-queries the last 14 days and replaces that overlap, making missed runs and retrospective NCBI metadata changes much less troublesome. The Wikimedia lookup falls back species -> genus -> family and retains attribution metadata.
