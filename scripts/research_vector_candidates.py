#!/usr/bin/env python3
"""Read-only feasibility screen for disease-vector genome coverage.

Genus matches are CANDIDATES, never assertions of vector competence.
Optional species registry must contain evidence URLs and explicit evidence levels.
No NCBI requests, no site changes. Compatible with audit ncbi_full_inventory.csv.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Discovery groups, deliberately broad and NOT a curated disease-vector list.
CANDIDATE_GENERA = {
    "Mosquitoes": "Aedes Anopheles Culex Mansonia Coquillettidia Haemagogus Sabethes",
    "Ticks": "Ixodes Amblyomma Rhipicephalus Dermacentor Hyalomma Ornithodoros",
    "Sand flies": "Phlebotomus Lutzomyia Nyssomyia Psychodopygus",
    "Tsetse flies": "Glossina",
    "Triatomine bugs": "Triatoma Rhodnius Panstrongylus",
    "Biting midges": "Culicoides",
    "Fleas": "Xenopsylla Ctenocephalides",
    "Blackflies": "Simulium",
    "Lice": "Pediculus",
}
CANDIDATES = {name: set(names.split()) for name, names in CANDIDATE_GENERA.items()}
VALID_EVIDENCE = {"established", "potential", "associated_only"}


def binomial(name):
    words = str(name or "").strip().split()
    if len(words) < 2 or not words[0][:1].isupper() or not words[1][:1].islower():
        return ""
    return " ".join(words[:2])


def load_registry(path):
    if not path:
        return {}
    out = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"scientific_name", "ncbi_taxid", "evidence_level", "source_url"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Registry requires: " + ", ".join(sorted(required)))
        for row in reader:
            name = str(row["scientific_name"]).strip()
            level = str(row["evidence_level"]).strip()
            url = str(row["source_url"]).strip()
            taxid = str(row["ncbi_taxid"]).strip()
            if not binomial(name) or level not in VALID_EVIDENCE or not url.startswith("https://"):
                raise ValueError("Invalid registry entry (requires binomial, evidence level, HTTPS source): " + name)
            if not taxid.isdigit():
                raise ValueError("Registry entry missing numeric NCBI taxid: " + name)
            if name in out:
                raise ValueError("Duplicate registry species: " + name)
            out[name] = {**row, "scientific_name": name, "ncbi_taxid": taxid}
    return out


def screen(inventory, registry=None):
    records = list(csv.DictReader(Path(inventory).open(newline="", encoding="utf-8")))
    if not records or not {"accession", "organism_name", "tax_id", "release_date"}.issubset(records[0]):
        raise ValueError("Expected full NCBI audit CSV with accession, organism_name, tax_id, release_date")
    if len(records) != len({r["accession"] for r in records}):
        raise ValueError("Inventory contains duplicate accession rows")
    registry = registry or {}
    groups = {}
    for group, genera in CANDIDATES.items():
        selected = [r for r in records if str(r["organism_name"]).split(" ", 1)[0] in genera]
        species = sorted({binomial(r["organism_name"]) for r in selected if binomial(r["organism_name"])})
        groups[group] = {
            "candidate_assemblies": len(selected),
            "candidate_binomials": len(species),
            "candidate_organism_names": len({r["organism_name"] for r in selected}),
            "species_examples": species[:12],
            "reviewed_registry_binomials_present": sum(s in registry for s in species),
        }
    matched = []
    for name, row in registry.items():
        # Prefer numeric NCBI taxonomy over string matching; retain variants
        # of identical species taxids, but do not assume a subspecies taxid matches.
        hits = [r for r in records if str(r["tax_id"]).strip() == row["ncbi_taxid"]]
        if not hits:
            # Name match is a REVIEW FLAG only, never an accepted taxon-ID match.
            possible = [r for r in records if binomial(r["organism_name"]) == name]
        else:
            possible = []
        matched.append({
            "scientific_name": name, "ncbi_taxid": row["ncbi_taxid"],
            "evidence_level": row["evidence_level"], "source_url": row["source_url"],
            "taxid_matched_assemblies": len(hits),
            "name_only_review_candidates": len(possible),
            "status": "taxid_match" if hits else ("needs_taxonomy_review" if possible else "no_qualifying_assembly"),
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NCBI full-history audit inventory (current qualifying GenBank chromosome/complete assemblies)",
        "inventory_assemblies": len(records),
        "interpretation": "Genus screens are candidate organisms only; not confirmed disease vectors. Registry taxid matches are not transmission evidence.",
        "candidate_groups": groups,
        "registry_review": matched,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inventory", required=True, help="ncbi_full_inventory.csv from full-history audit")
    p.add_argument("--registry", help="Optional manually evidenced vector species CSV")
    p.add_argument("--output", required=True, help="Output JSON (not the production dashboard)")
    args = p.parse_args()
    result = screen(args.inventory, load_registry(args.registry))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("NCBI qualifying assemblies screened:", result["inventory_assemblies"])
    for name, g in result["candidate_groups"].items():
        print(f"  {name}: {g['candidate_assemblies']} assemblies / {g['candidate_binomials']} candidate binomials")
    print("Wrote", target)


if __name__ == "__main__":
    main()
