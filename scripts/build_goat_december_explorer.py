#!/usr/bin/env python3
"""Build a compact, reproducible discussion snapshot from existing GoaT/NCBI exports.

No network access and no new classification of scientific leadership is implied.
"""
import collections
import datetime as dt
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/goat_december_explorer.json"

# Operational programmes, not EBP/ERGA umbrella membership alone. These labels
# are already attached to assembly records by the provenance workflow.
MAJOR_LABELS = {
    "Darwin Tree of Life", "Vertebrate Genomes Project", "Psyche",
    "Human Pangenome Reference Consortium", "Genome Reference Consortium",
    "ATLASea", "Bat1K", "Bird 10,000 Genomes", "DNA Zoo",
    "Ag100Pest", "Canadian BioGenome Project", "Bee100 / Beenome100",
    "GAGA", "California Conservation Genomics",
}


def main():
    with gzip.open(ROOT / "data/goat_project_stats.json.gz", "rt") as handle:
        ncbi = json.load(handle)
    with (ROOT / "data/goat_intent_history.json").open() as handle:
        history = json.load(handle)

    rows = ncbi["records"]
    declared = history["records"]
    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ncbi_snapshot": ncbi["generated_at"],
        "goat_snapshot": history["updated_at"],
        "scope": "Current GenBank eukaryotic chromosome/complete assemblies in the NCBI provenance snapshot",
        "major_labels": sorted(MAJOR_LABELS),
        "classification_note": "Curated operational programme signal; neither EBP nor ERGA umbrella membership alone implies a major producer. Unflagged is not synonymous with small or independent.",
    }

    def major(row):
        return bool(MAJOR_LABELS.intersection(row.get("programme_labels") or []))

    def classification(row):
        return "major" if major(row) else "other"

    def novelty(row):
        n = row.get("novelty")
        return "additional" if n == "earlier_high_level" else n

    groups = ["Animals", "Plants", "Fungi", "Other eukaryotes"]
    output["group_comparison"] = []
    for group in ["All eukaryotes", *groups]:
        subset = rows if group == "All eukaryotes" else [r for r in rows if r["group"] == group]
        for kind in ("major", "other"):
            selected = [r for r in subset if classification(r) == kind]
            output["group_comparison"].append({
                "group": group, "class": kind,
                "assemblies": len(selected),
                "species": len({r["species_id"] for r in selected}),
                "first_ever": sum(novelty(r) == "first_ever" for r in selected),
                "upgrades": sum(novelty(r) == "upgrade" for r in selected),
                "additional": sum(novelty(r) == "additional" for r in selected),
                "unknown": sum(novelty(r) == "unknown" for r in selected),
                "direct_projects": len({r["bioproject"] for r in selected if r["bioproject"]}),
            })

    producer = collections.defaultdict(lambda: {"assemblies": 0, "species": set(), "first_ever": 0})
    for row in rows:
        labels = MAJOR_LABELS.intersection(row.get("programme_labels") or [])
        for label in labels:
            target = producer[label]
            target["assemblies"] += 1
            target["species"].add(row["species_id"])
            target["first_ever"] += novelty(row) == "first_ever"
    output["programmes"] = sorted([
        {"name": name, "assemblies": d["assemblies"], "species": len(d["species"]), "first_ever": d["first_ever"]}
        for name, d in producer.items()
    ], key=lambda d: -d["assemblies"])

    sizes = [("1", lambda n: n == 1), ("2–5", lambda n: 2 <= n <= 5),
             ("6–20", lambda n: 6 <= n <= 20), ("21–100", lambda n: 21 <= n <= 100),
             (">100", lambda n: n > 100), ("Unknown", lambda n: n is None)]
    output["footprint"] = [
        {"label": name, "major": sum(major(r) and test(r["project_species"]) for r in rows),
         "other": sum(not major(r) and test(r["project_species"]) for r in rows)}
        for name, test in sizes
    ]

    # A project is a direct NCBI BioProject, not necessarily a distinct laboratory.
    projects = {}
    for row in rows:
        key = row.get("bioproject")
        if not key:
            continue
        p = projects.setdefault(key, {"id": key, "title": row.get("project_title") or "",
            "footprint": row.get("project_species"), "assemblies": 0,
            "species": set(), "major": False, "labels": set(), "submitters": set()})
        p["assemblies"] += 1
        p["species"].add(row["species_id"])
        p["major"] = p["major"] or major(row)
        p["labels"].update(MAJOR_LABELS.intersection(row.get("programme_labels") or []))
        if row.get("submitter"):
            p["submitters"].add(row["submitter"])
    output["top_projects"] = sorted([
        {**{k: v for k, v in p.items() if k not in ("species", "labels", "submitters")},
         "species": len(p["species"]), "labels": sorted(p["labels"]),
         "submitters": sorted(p["submitters"])[:4]}
        for p in projects.values()
    ], key=lambda p: (-(p["footprint"] or 0), -p["assemblies"]))[:150]

    # Distinct taxa, not count of status declarations, in each project tag.
    intent_by_tag = collections.defaultdict(set)
    intent_taxa = set()
    release_after = set()
    preexisting = set()
    unreleased = set()
    for taxon, record in declared.items():
        declarations = record.get("declarations") or {}
        if not declarations:
            continue
        intent_taxa.add(str(taxon))
        tags = {str(tag) for values in declarations.values() for tag in values}
        for tag in tags:
            intent_by_tag[tag].add(str(taxon))
        observed = record.get("first_observed")
        release = record.get("first_qualifying_release")
        if not release:
            unreleased.add(str(taxon))
        elif observed and release >= observed:
            release_after.add(str(taxon))
        else:
            preexisting.add(str(taxon))
    output["intent_inventory"] = {
        "taxa": len(intent_taxa), "no_qualifying_release": len(unreleased),
        "release_on_or_after_observation": len(release_after),
        "assembly_predates_observation": len(preexisting),
        "note": "Cross-sectional inventory, not a completion probability. First observed is not necessarily the true declaration date; no release is not cancellation.",
    }
    output["intent_tags"] = [
        {"tag": tag, "taxa": len(taxa), "without_qualifying_release": len(taxa & unreleased),
         "released_on_or_after_observation": len(taxa & release_after)}
        for tag, taxa in sorted(intent_by_tag.items(), key=lambda kv: -len(kv[1]))[:45]
    ]

    ncbi_i5k = {str(r["species_id"]) for r in rows if "i5K" in (r.get("programme_labels") or [])}
    goat_i5k = intent_by_tag.get("i5K", set()) | intent_by_tag.get("I5K", set())
    output["i5k"] = {
        "ncbi_flagged_assemblies": sum("i5K" in (r.get("programme_labels") or []) for r in rows),
        "ncbi_flagged_species": len(ncbi_i5k),
        "goat_intent_taxa": len(goat_i5k),
        "matched_taxa": len(ncbi_i5k & goat_i5k),
        "intent_no_qualifying_release": len(goat_i5k & unreleased),
        "note": "Only explicitly flagged i5K labels in existing snapshots; not complete i5k community output or a historical advance-registration test.",
    }
    ncbi_i5k_by_taxon = collections.defaultdict(list)
    for row in rows:
        if "i5K" in (row.get("programme_labels") or []):
            ncbi_i5k_by_taxon[str(row["species_id"])].append(row)
    output["i5k_crosswalk"] = []
    for taxon in sorted(ncbi_i5k | goat_i5k, key=lambda x: int(x) if x.isdigit() else x):
        r = (ncbi_i5k_by_taxon.get(taxon) or [None])[0]
        h = declared.get(taxon, {})
        output["i5k_crosswalk"].append({
            "taxon_id": taxon,
            "name": (r or {}).get("species") or h.get("name") or taxon,
            "ncbi_flagged": bool(r), "goat_intent": taxon in goat_i5k,
            "ncbi_assemblies": len(ncbi_i5k_by_taxon.get(taxon, [])),
            "bioprojects": sorted({x["bioproject"] for x in ncbi_i5k_by_taxon.get(taxon, []) if x.get("bioproject")}),
            "goat_first_observed": h.get("first_observed"),
            "qualifying_release": h.get("first_qualifying_release"),
        })
    OUTPUT.write_text(json.dumps(output, separators=(",", ":")) + "\n")
    print(f"Wrote {OUTPUT}: {len(rows)} assemblies, {len(intent_taxa)} intent taxa")


if __name__ == "__main__":
    main()
