#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from build_countries import country_from_geo, geo_loc_name, marine_from_geo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "taxa"
TAXDUMP_URL = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"
USER_AGENT = "EukaryoteGenomeWatch/0.4 (public research dashboard; contact via repository)"
RECENT_DAYS = 365


def first(d, *paths, default=None):
    for path in paths:
        x = d
        try:
            for key in path.split("."):
                x = x[int(key)] if isinstance(x, list) else x[key]
            if x not in (None, ""):
                return x
        except (KeyError, IndexError, TypeError, ValueError):
            pass
    return default


def download_taxdump(workdir: Path) -> Path:
    archive = workdir / "taxdump.tar.gz"
    req = Request(TAXDUMP_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=120) as src, archive.open("wb") as dst:
        shutil.copyfileobj(src, dst)

    extract = workdir / "taxdump"
    extract.mkdir()
    with tarfile.open(archive, "r:gz") as tf:
        wanted = {"nodes.dmp", "names.dmp"}
        members = [m for m in tf.getmembers() if Path(m.name).name in wanted]
        tf.extractall(extract, members=members)
    return extract


def load_taxonomy(taxdir: Path):
    parent = {}
    rank = {}
    wanted_name_ids = set()

    with (taxdir / "nodes.dmp").open(errors="replace") as fh:
        for line in fh:
            parts = line.split("|")
            if len(parts) < 3:
                continue
            tid = int(parts[0].strip())
            par = int(parts[1].strip())
            rk = parts[2].strip()
            parent[tid] = par
            rank[tid] = rk
            if rk in {"phylum", "class", "order"}:
                wanted_name_ids.add(tid)

    names = {}
    with (taxdir / "names.dmp").open(errors="replace") as fh:
        for line in fh:
            parts = line.split("|")
            if len(parts) < 4:
                continue
            tid = int(parts[0].strip())
            if tid not in wanted_name_ids:
                continue
            if parts[3].strip() == "scientific name":
                names[tid] = parts[1].strip()

    return parent, rank, names


def stream_assemblies():
    cmd = [
        "datasets", "summary", "genome", "taxon", "Eukaryota",
        "--assembly-source", "GenBank",
        "--assembly-level", "chromosome,complete",
        "--as-json-lines",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)

    stderr = proc.stderr.read() if proc.stderr else ""
    code = proc.wait()
    if code:
        raise RuntimeError(f"NCBI datasets failed with exit code {code}: {stderr[-4000:]}")


def main():
    today = date.today()
    recent_cutoff = (today - timedelta(days=RECENT_DAYS - 1)).isoformat()

    with tempfile.TemporaryDirectory(prefix="egw_taxa_") as td:
        taxdir = download_taxdump(Path(td))
        parent, ranks, names = load_taxonomy(taxdir)

        lineage_cache = {}

        def lineage(taxid):
            if taxid in lineage_cache:
                return lineage_cache[taxid]

            out = {"phylum": None, "class": None, "order": None, "species": None}
            cur = taxid
            seen = set()
            while cur and cur not in seen:
                seen.add(cur)
                rk = ranks.get(cur)
                if rk in out and out[rk] is None:
                    out[rk] = cur
                par = parent.get(cur)
                if par is None or par == cur:
                    break
                cur = par

            lineage_cache[taxid] = out
            return out

        agg = {}
        species_members = defaultdict(set)
        # Latest size-bearing assembly per species/taxon, held only in memory.
        size_by_taxon_species = {}
        recent_species = defaultdict(set)
        species_first = {}
        species_taxa = {}
        country_meta = {}
        marine_meta = {}
        all_order_assemblies = Counter()
        all_order_species = defaultdict(set)
        origin_order_assemblies = Counter()
        origin_order_species = defaultdict(set)
        country_order_assemblies = defaultdict(Counter)
        country_order_species = defaultdict(lambda: defaultdict(set))

        def ensure_taxon(tid, rk, lin):
            if tid not in agg:
                phylum_id = lin.get("phylum")
                class_id = lin.get("class")
                agg[tid] = {
                    "taxid": tid,
                    "name": names.get(tid, str(tid)),
                    "rank": rk,
                    "phylum": (
                        {"taxid": phylum_id, "name": names.get(phylum_id, str(phylum_id))}
                        if phylum_id else None
                    ),
                    "class": (
                        {"taxid": class_id, "name": names.get(class_id, str(class_id))}
                        if class_id else None
                    ),
                    "assemblies": 0,
                    "first_deposit": None,
                    "last_deposit": None,
                    "yearly": defaultdict(int),
                    "recent_daily": defaultdict(int),
                    "countries": defaultdict(int),
                    "marine_localities": defaultdict(int),
                    "origin_assigned": 0,
                    "origin_marine": 0,
                }
            return agg[tid]

        n_reports = 0
        n_classified = 0

        for report in stream_assemblies():
            n_reports += 1
            taxid = first(report, "organism.tax_id", "organism.taxId", "tax_id", "organism.taxid")
            release = str(first(
                report,
                "assembly_info.release_date",
                "assemblyInfo.releaseDate",
                "assembly.release_date",
                "release_date",
                default="",
            ))[:10]
            size_bp = first(report, "assembly_stats.total_sequence_length",
                            "assemblyStats.totalSequenceLength", "total_sequence_length")
            try:
                size_mb = round(int(size_bp) / 1_000_000, 3)
                if size_mb <= 0:
                    size_mb = None
            except (ValueError, TypeError):
                size_mb = None
            organism = first(
                report,
                "organism.organism_name",
                "organism.organismName",
                "organism_name",
                "organism.name",
                default="Unknown",
            )

            if not taxid or len(release) != 10:
                continue

            try:
                taxid = int(taxid)
                datetime.strptime(release, "%Y-%m-%d")
            except (TypeError, ValueError):
                continue

            lin = lineage(taxid)
            raw_geo = geo_loc_name(report)
            country = country_from_geo(raw_geo)
            marine = None if country else marine_from_geo(raw_geo)
            if country:
                country_meta[country["iso3"]] = {
                    "iso2": country["iso2"],
                    "iso3": country["iso3"],
                    "iso_n3": country["iso_n3"],
                    "name": country["name"],
                }
            if marine:
                marine_meta[marine["name"]] = {
                    "name": marine["name"],
                    "lat": marine["lat"],
                    "lon": marine["lon"],
                }

            taxon_ids = []
            if lin.get("phylum"):
                taxon_ids.append((lin["phylum"], "phylum"))
            if lin.get("order"):
                taxon_ids.append((lin["order"], "order"))
            if not taxon_ids:
                continue

            n_classified += 1
            species_key = (
                f"taxid:{lin['species']}"
                if lin.get("species")
                else f"name:{organism}"
            )

            order_tid = lin.get("order")
            if order_tid:
                all_order_assemblies[order_tid] += 1
                all_order_species[order_tid].add(species_key)
                if country:
                    iso3 = country["iso3"]
                    origin_order_assemblies[order_tid] += 1
                    origin_order_species[order_tid].add(species_key)
                    country_order_assemblies[iso3][order_tid] += 1
                    country_order_species[iso3][order_tid].add(species_key)

            for tid, rk in taxon_ids:
                rec = ensure_taxon(tid, rk, lin)
                rec["assemblies"] += 1
                rec["first_deposit"] = (
                    release if rec["first_deposit"] is None
                    else min(rec["first_deposit"], release)
                )
                rec["last_deposit"] = (
                    release if rec["last_deposit"] is None
                    else max(rec["last_deposit"], release)
                )
                rec["yearly"][release[:4]] += 1
                species_members[tid].add(species_key)
                if size_mb is not None:
                    key_size = (tid, species_key)
                    previous = size_by_taxon_species.get(key_size)
                    if previous is None or (release, str(first(report, "accession", default=""))) > (previous[0], previous[1]):
                        size_by_taxon_species[key_size] = (release, str(first(report, "accession", default="")), size_mb)

                if release >= recent_cutoff:
                    rec["recent_daily"][release] += 1
                    recent_species[tid].add(species_key)

                if country:
                    rec["origin_assigned"] += 1
                    rec["countries"][country["iso3"]] += 1
                elif marine:
                    rec["origin_marine"] += 1
                    rec["marine_localities"][marine["name"]] += 1

                key = (tid, species_key)
                if key not in species_first or release < species_first[key]:
                    species_first[key] = release
                    species_taxa[key] = tid

        first_species_year = defaultdict(lambda: defaultdict(int))
        for (tid, _species), release in species_first.items():
            first_species_year[tid][release[:4]] += 1

        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True, exist_ok=True)

        index_rows = []
        # Convert latest per-species sizes into per-taxon lists once; avoid
        # rescanning every organism for every taxon during JSON generation.
        taxon_sizes = defaultdict(list)
        for (taxon_id, _), (_, _, size_mb) in size_by_taxon_species.items():
            taxon_sizes[taxon_id].append(size_mb)
        for values in taxon_sizes.values():
            values.sort()

        for tid, rec in agg.items():
            years = sorted(rec["yearly"])
            yearly = [
                {
                    "year": year,
                    "assemblies": rec["yearly"][year],
                    "first_time_species": first_species_year[tid].get(year, 0),
                }
                for year in years
            ]
            recent_daily = [
                {"date": ds, "assemblies": count}
                for ds, count in sorted(rec["recent_daily"].items())
            ]

            sizes = taxon_sizes.get(tid, [])
            middle = len(sizes) // 2
            median_mb = (
                round((sizes[middle - 1] + sizes[middle]) / 2, 3)
                if sizes and len(sizes) % 2 == 0
                else (sizes[middle] if sizes else None)
            )
            payload = {
                "taxid": tid,
                "name": rec["name"],
                "rank": rec["rank"],
                "phylum": rec["phylum"],
                "class": rec["class"],
                "stats": {
                    "assemblies": rec["assemblies"],
                    "species": len(species_members[tid]),
                    "first_deposit": rec["first_deposit"],
                    "last_deposit": rec["last_deposit"],
                    "past_year_assemblies": sum(rec["recent_daily"].values()),
                    "past_year_species": len(recent_species[tid]),
                    "origin_assigned_assemblies": rec["origin_assigned"],
                    "origin_country_assemblies": rec["origin_assigned"],
                    "origin_marine_assemblies": rec["origin_marine"],
                    "origin_resolved_assemblies": rec["origin_assigned"] + rec["origin_marine"],
                },
                "genome_sizes": {
                    "species": len(sizes),
                    "median_mb": median_mb,
                    "sizes_mb": sizes,
                },
                "yearly": yearly,
                "recent_daily": recent_daily,
                "countries": [
                    {
                        **country_meta[iso3],
                        "assemblies": count,
                    }
                    for iso3, count in sorted(
                        rec["countries"].items(),
                        key=lambda kv: (-kv[1], country_meta[kv[0]]["name"]),
                    )
                ],
                "marine_localities": [
                    {
                        **marine_meta[name],
                        "assemblies": count,
                    }
                    for name, count in sorted(
                        rec["marine_localities"].items(),
                        key=lambda kv: (-kv[1], kv[0]),
                    )
                ],
            }
            (OUT / f"{tid}.json").write_text(
                json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
            )

            index_rows.append({
                "taxid": tid,
                "name": rec["name"],
                "rank": rec["rank"],
                "phylum": rec["phylum"]["name"] if rec["phylum"] else None,
                "class": rec["class"]["name"] if rec["class"] else None,
                "assemblies": rec["assemblies"],
                "species": len(species_members[tid]),
                "first_deposit": rec["first_deposit"],
            })

        def order_rows(assembly_counts, species_sets, limit=10):
            tids = sorted(
                assembly_counts,
                key=lambda tid: (
                    -len(species_sets.get(tid, set())),
                    -assembly_counts[tid],
                    names.get(tid, str(tid)).casefold(),
                ),
            )[:limit]
            return [
                {
                    "taxid": tid,
                    "name": names.get(tid, str(tid)),
                    "assemblies": assembly_counts[tid],
                    "species": len(species_sets.get(tid, set())),
                }
                for tid in tids
            ]

        country_orders = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "definition": (
                "Top taxonomic orders ranked by distinct species represented. "
                "Country-specific and origin-wide values use assemblies with a "
                "resolved BioSample country; all_orders uses all tracked assemblies."
            ),
            "all_orders": order_rows(all_order_assemblies, all_order_species),
            "origin_orders": order_rows(origin_order_assemblies, origin_order_species),
            "countries": {
                iso3: order_rows(
                    country_order_assemblies[iso3],
                    country_order_species[iso3],
                )
                for iso3 in sorted(country_order_assemblies)
            },
        }
        (OUT / "country_orders.json").write_text(
            json.dumps(country_orders, separators=(",", ":"), ensure_ascii=False) + "\n"
        )

        index_rows.sort(key=lambda x: (x["name"].casefold(), x["rank"], x["taxid"]))
        index = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "GenBank Eukaryota assemblies at chromosome or complete level",
            "ranks": ["phylum", "order"],
            "taxa": index_rows,
        }
        (OUT / "index.json").write_text(
            json.dumps(index, separators=(",", ":"), ensure_ascii=False) + "\n"
        )

        print(
            f"built {len(index_rows)} phylum/order records from "
            f"{n_reports} assemblies ({n_classified} classified)"
        )


if __name__ == "__main__":
    main()
