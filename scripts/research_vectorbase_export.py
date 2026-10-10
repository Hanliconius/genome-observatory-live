#!/usr/bin/env python3
"""Match an exported VectorBase GenomeDataTypes_Summary.csv to the NCBI audit.

Research-only: catalogue membership is NOT evidence of disease transmission.
Does not access credentials, network, or write public dashboard data.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

def load_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))

def compare(vector_csv, ncbi_csv):
    vectors=load_csv(vector_csv)
    inventory=load_csv(ncbi_csv)
    required={"Species", "Species NCBI taxon ID", "Genome Version/Assembly ID"}
    if not vectors or not required.issubset(vectors[0]):
        raise ValueError("Expected VectorBase GenomeDataTypes organism summary CSV")
    if not inventory or not {"accession","organism_name","tax_id","release_date"}.issubset(inventory[0]):
        raise ValueError("Expected audit ncbi_full_inventory.csv")
    species={}
    for row in vectors:
        taxid=str(row["Species NCBI taxon ID"]).strip()
        name=str(row["Species"]).strip()
        if not taxid.isdigit() or not name:
            raise ValueError("VectorBase species row lacks valid species-level taxid/name")
        entry=species.setdefault(taxid,{"taxid":taxid,"species":name,"vectorbase_assemblies":0,
                                       "vectorbase_accessions":[]})
        if entry["species"]!=name:
            raise ValueError("Conflicting names for VectorBase taxid "+taxid)
        entry["vectorbase_assemblies"]+=1
        entry["vectorbase_accessions"].append(row["Genome Version/Assembly ID"])
    by_taxid=defaultdict(list)
    by_name=defaultdict(list)
    for row in inventory:
        by_taxid[str(row["tax_id"]).strip()].append(row)
        by_name[row["organism_name"]].append(row)
    output=[]
    for taxid,entry in sorted(species.items(),key=lambda kv:kv[1]["species"]):
        found=by_taxid.get(taxid,[])
        n_by_name=by_name.get(entry["species"],[])
        output.append({
            "species":entry["species"],"ncbi_taxid":taxid,
            "vectorbase_assembly_records":entry["vectorbase_assemblies"],
            "qualifying_ncbi_assemblies":len(found),
            "ncbi_organism_names":sorted({r["organism_name"] for r in found}),
            "name_only_matches_needing_review":len(n_by_name) if not found else 0,
            "coverage_status":"taxid_matched" if found else ("name_only_review" if n_by_name else "no_qualifying_assembly"),
            "vector_status":"unverified",
        })
    return {
        "definition":"VectorBase genomic-resource species; NOT an evidence-verified vector list",
        "vectorbase_rows":len(vectors),
        "vectorbase_species":len(species),
        "ncbi_inventory_rows":len(inventory),
        "ncbi_matched_species":sum(r["qualifying_ncbi_assemblies"]>0 for r in output),
        "ncbi_qualifying_assemblies":sum(r["qualifying_ncbi_assemblies"] for r in output),
        "species":output
    }

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectorbase",required=True)
    parser.add_argument("--inventory",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=compare(args.vectorbase,args.inventory)
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("VectorBase records:",report["vectorbase_rows"])
    print("VectorBase species:",report["vectorbase_species"])
    print("Taxid-matched species:",report["ncbi_matched_species"])
    print("Qualifying NCBI assemblies:",report["ncbi_qualifying_assemblies"])
    print("Saved review-only output:",out)

if __name__=="__main__":
    main()
