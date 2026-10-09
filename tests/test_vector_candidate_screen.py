#!/usr/bin/env python3
"""Offline tests; no NCBI access or dashboard mutation."""
import csv
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_vector_candidates import binomial, load_registry, screen


class ScreenTests(unittest.TestCase):
    def test_binomial_subspecies(self):
        self.assertEqual(binomial("Aedes aegypti aegypti"), "Aedes aegypti")
        self.assertEqual(binomial(""), "")

    def test_taxid_join_does_not_infer_from_genus(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / "inventory.csv"
            registry = Path(tmp) / "registry.csv"
            with inventory.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["accession", "organism_name", "tax_id", "release_date"])
                w.writeheader()
                w.writerows([
                    dict(accession="GCA_1.1", organism_name="Aedes aegypti", tax_id="7159", release_date="2020-01-01"),
                    dict(accession="GCA_2.1", organism_name="Aedes albopictus", tax_id="7160", release_date="2021-01-01"),
                    dict(accession="GCA_3.1", organism_name="Ixodes scapularis", tax_id="6945", release_date="2022-01-01"),
                ])
            registry.write_text("scientific_name,ncbi_taxid,evidence_level,source_url\n"
                                "Aedes aegypti,7159,established,https://example.org/evidence\n"
                                "Aedes albopictus,999,associated_only,https://example.org/context\n")
            report = screen(inventory, load_registry(registry))
            self.assertEqual(report["inventory_assemblies"], 3)
            self.assertEqual(report["candidate_groups"]["Mosquitoes"]["candidate_assemblies"], 2)
            byname = {row["scientific_name"]: row for row in report["registry_review"]}
            self.assertEqual(byname["Aedes aegypti"]["status"], "taxid_match")
            self.assertEqual(byname["Aedes albopictus"]["status"], "needs_taxonomy_review")
            self.assertEqual(byname["Aedes albopictus"]["taxid_matched_assemblies"], 0)

    def test_incomplete_registry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registry.csv"
            p.write_text("scientific_name,ncbi_taxid,evidence_level,source_url\n"
                         "Aedes aegypti,7159,established,\n")
            with self.assertRaises(ValueError):
                load_registry(p)


if __name__ == "__main__":
    unittest.main()
