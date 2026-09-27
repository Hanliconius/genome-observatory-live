#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "status"
DASH = ROOT / "data" / "dashboard.json"
IUCN_URL = "https://hosted-datasets.gbif.org/datasets/iucn/iucn-latest.zip"
USER_AGENT = "EukaryoteGenomeWatch/0.5 (public research dashboard; contact via repository)"
RECENT_DAYS = 370

CATEGORY_LABELS = {
    "VU": "Vulnerable",
    "EN": "Endangered",
    "CR": "Critically endangered",
    "EW": "Extinct in the wild",
    "EX": "Extinct",
    "VULNERABLE": "Vulnerable",
    "ENDANGERED": "Endangered",
    "CRITICALLY ENDANGERED": "Critically endangered",
    "EXTINCT IN THE WILD": "Extinct in the wild",
    "EXTINCT": "Extinct",
}
THREATENED = {"Vulnerable", "Endangered", "Critically endangered"}
EXTINCT = {"Extinct in the wild", "Extinct"}
STATUS_PRIORITY = {
    "Extinct": 5,
    "Extinct in the wild": 4,
    "Critically endangered": 3,
    "Endangered": 2,
    "Vulnerable": 1,
}


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


def norm_name(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = re.sub(r"\s+\([^)]*\)\s*$", "", value).strip()
    return value


def species_key(value):
    parts = norm_name(value).split()
    if len(parts) >= 2:
        return " ".join(parts[:2]).casefold()
    return norm_name(value).casefold()


def broad_group(row):
    lineage = " ".join(str(row.get(k, "")) for k in ("kingdom", "phylum", "class")).casefold()
    if any(x in lineage for x in ("animalia", "metazoa")):
        return "Animals"
    if any(x in lineage for x in ("plantae", "viridiplantae")):
        return "Plants"
    if "fungi" in lineage:
        return "Fungi"
    return "Other"


def canonical_header(value):
    x = str(value or "").strip()
    if "/" in x:
        x = x.rsplit("/", 1)[-1]
    if "#" in x:
        x = x.rsplit("#", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", x.casefold())


def category_from_row(row):
    candidates = (
        "threatstatus", "redlistcategory", "iucnredlistcategory",
        "conservationstatus", "category", "status"
    )
    for key in candidates:
        raw = row.get(key)
        if not raw:
            continue
        val = re.sub(r"\s+", " ", str(raw)).strip().upper()
        if val in CATEGORY_LABELS:
            return CATEGORY_LABELS[val]
        for code, label in CATEGORY_LABELS.items():
            if len(code) > 2 and code in val:
                return label
    return None


def download_iucn():
    req = Request(IUCN_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=180) as r:
        return r.read()


def iter_table_rows(zf, name):
    with zf.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        sample = text.read(4096)
        text.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.DictReader(text, delimiter=delimiter)
        if not reader.fieldnames:
            return
        mapped = {f: canonical_header(f) for f in reader.fieldnames}
        for row in reader:
            yield {mapped[k]: v for k, v in row.items() if k is not None}


def table_headers(zf, name):
    with zf.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        sample = text.read(4096)
        text.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.reader(text, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return set()
        return {canonical_header(x) for x in header}


def load_iucn_names():
    blob = download_iucn()
    by_name = {}
    counts = Counter()
    taxa = {}

    def store(name, payload, allow_binomial=False):
        key = norm_name(name).casefold()
        if not key:
            return
        old = by_name.get(key)
        if old is None or STATUS_PRIORITY.get(payload["status"], 0) > STATUS_PRIORITY.get(old["status"], 0):
            by_name[key] = payload
        if allow_binomial:
            skey = species_key(name)
            if skey:
                old = by_name.get(skey)
                if old is None or STATUS_PRIORITY.get(payload["status"], 0) > STATUS_PRIORITY.get(old["status"], 0):
                    by_name[skey] = payload

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith((".txt", ".tsv", ".csv"))]

        # Pass 1: index the taxon core (or any taxon-like table) by taxonID.
        for name in names:
            headers = table_headers(zf, name)
            if not headers.intersection({"scientificname", "canonicalname", "species"}):
                continue
            if not headers.intersection({"taxonid", "id"}):
                continue
            for row in iter_table_rows(zf, name):
                tid = str(row.get("taxonid") or row.get("id") or "").strip()
                if not tid:
                    continue
                if tid not in taxa:
                    taxa[tid] = row
                else:
                    # Prefer the row with an explicit scientific name/rank/classification.
                    score_new = sum(bool(row.get(k)) for k in ("scientificname", "taxonrank", "kingdom", "phylum", "class"))
                    score_old = sum(bool(taxa[tid].get(k)) for k in ("scientificname", "taxonrank", "kingdom", "phylum", "class"))
                    if score_new > score_old:
                        taxa[tid] = row

        # Pass 2: read IUCN status from distribution/status extensions and join to taxon core.
        status_rows = 0
        for name in names:
            headers = table_headers(zf, name)
            if not headers.intersection(
                {"threatstatus", "iucnredlistcategory", "redlistcategory", "conservationstatus", "category", "status"}
            ):
                continue
            for row in iter_table_rows(zf, name):
                status = category_from_row(row)
                if status not in THREATENED | EXTINCT:
                    continue
                tid = str(
                    row.get("taxonid")
                    or row.get("coreid")
                    or row.get("id")
                    or row.get("taxonkey")
                    or ""
                ).strip()
                taxon = taxa.get(tid, {})
                merged = {**taxon, **row}
                accepted = (
                    taxon.get("acceptednameusage")
                    or taxon.get("scientificname")
                    or taxon.get("canonicalname")
                    or taxon.get("species")
                    or row.get("acceptednameusage")
                    or row.get("scientificname")
                    or row.get("species")
                )
                scientific = taxon.get("scientificname") or taxon.get("canonicalname") or accepted
                species = taxon.get("species") or accepted or scientific
                if not any((accepted, scientific, species)):
                    continue
                payload = {
                    "status": status,
                    "accepted_name": norm_name(accepted),
                    "group": broad_group(merged),
                }
                rank = str(taxon.get("taxonrank") or taxon.get("rank") or "").strip().casefold()
                for nm in (accepted, scientific, species):
                    words = norm_name(nm).split()
                    allow_binomial = rank == "species" or len(words) == 2
                    store(nm, payload, allow_binomial=allow_binomial)
                counts[status] += 1
                status_rows += 1

        if not status_rows:
            archive_summary = {
                Path(n).name: sorted(table_headers(zf, n))
                for n in names[:25]
            }
            raise RuntimeError(
                "No threatened/extinct distribution rows were parsed from the IUCN archive. "
                + json.dumps(archive_summary, ensure_ascii=False)[:12000]
            )

    if not by_name:
        raise RuntimeError("IUCN status rows were found but no scientific names could be joined")
    return by_name, counts


def stream_assemblies():
    cmd = [
        "datasets", "summary", "genome", "taxon", "Eukaryota",
        "--assembly-source", "GenBank",
        "--assembly-level", "chromosome,complete",
        "--as-json-lines",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line:
            yield json.loads(line)
    stderr = proc.stderr.read() if proc.stderr else ""
    code = proc.wait()
    if code:
        raise RuntimeError(f"NCBI datasets failed with exit code {code}: {stderr[-4000:]}")


def normalize_assembly(report):
    accession = first(report, "accession", "assembly.accession", "assembly_info.assembly_accession", default="")
    organism = first(report, "organism.organism_name", "organism.organismName", "organism_name", "organism.name", default="Unknown")
    common = first(report, "organism.common_name", "organism.commonName", "common_name", "commonName")
    release = str(first(
        report, "assembly_info.release_date", "assemblyInfo.releaseDate",
        "assembly.release_date", "release_date", default=""
    ))[:10]
    level = first(report, "assembly_info.assembly_level", "assemblyInfo.assemblyLevel", "assembly_level", default="")
    assembly_name = first(report, "assembly_info.assembly_name", "assemblyInfo.assemblyName", "assembly_name", default="")
    length = first(report, "assembly_stats.total_sequence_length", "assemblyStats.totalSequenceLength", "total_sequence_length", default=0) or 0
    chromosomes = first(report, "assembly_stats.total_number_of_chromosomes", "assemblyStats.totalNumberOfChromosomes", "total_number_of_chromosomes", default=0) or 0
    return {
        "accession": accession,
        "organism_name": norm_name(organism),
        "common_name": common,
        "release_date": release,
        "assembly_level": level,
        "assembly_name": assembly_name,
        "total_sequence_length": int(length or 0),
        "chromosome_count": int(chromosomes or 0),
    }


def make_milestones(daily_rows):
    total = sum(int(r["assemblies"]) for r in daily_rows)
    targets = [x for x in (10, 100, 1000, 10000) if x <= total]
    targets += list(range(20000, (total // 10000) * 10000 + 1, 10000))
    out = []
    cumulative = 0
    i = 0
    for row in daily_rows:
        cumulative += int(row["assemblies"])
        while i < len(targets) and cumulative >= targets[i]:
            out.append({"threshold": targets[i], "date": row["date"]})
            i += 1
    return out


def aggregate(rows, dashboard, recent_cutoff):
    rows.sort(key=lambda x: (x["release_date"], x["accession"]))
    first_seen = {}
    daily = defaultdict(lambda: {"assemblies": 0, "species": set(), "first_time_species": 0})
    yearly = defaultdict(lambda: {"assemblies": 0, "first_time_species": 0})
    groups = Counter()
    statuses = Counter()

    for x in rows:
        ds = x["release_date"]
        org = x["organism_name"]
        first_seen.setdefault(org, ds)
        if ds < first_seen[org]:
            first_seen[org] = ds
        daily[ds]["assemblies"] += 1
        daily[ds]["species"].add(org)
        yearly[ds[:4]]["assemblies"] += 1
        groups[x["group"]] += 1
        statuses[x["iucn_status"]] += 1

    first_by_day = Counter(first_seen.values())
    first_by_year = Counter(ds[:4] for ds in first_seen.values())
    daily_rows = []
    for ds in sorted(daily):
        daily_rows.append({
            "date": ds,
            "assemblies": daily[ds]["assemblies"],
            "species": len(daily[ds]["species"]),
            "first_time_species": first_by_day[ds],
        })
    yearly_rows = [
        {
            "year": year,
            "assemblies": yearly[year]["assemblies"],
            "first_time_species": first_by_year[year],
        }
        for year in sorted(yearly)
    ]

    image_cache = dashboard.get("image_cache", {})
    recent = []
    for x in reversed(rows):
        if x["release_date"] < recent_cutoff:
            break
        y = dict(x)
        y["image"] = image_cache.get(x["organism_name"])
        recent.append(y)

    matched_species = {x["organism_name"].casefold() for x in rows}
    def ann_match(item):
        name = norm_name(item.get("species", ""))
        return name.casefold() in matched_species or species_key(name) in {species_key(n) for n in matched_species}

    anns = dashboard.get("annotations", {})
    annotations = {
        "in_progress": [x for x in anns.get("in_progress", []) if ann_match(x)],
        "recent_completed": [x for x in anns.get("recent_completed", []) if ann_match(x)],
    }

    return {
        "summary": {
            "assemblies": len(rows),
            "species": len(first_seen),
            "first_time_species": len(first_seen),
        },
        "yearly": yearly_rows,
        "recent_daily": [x for x in daily_rows if x["date"] >= recent_cutoff],
        "groups_all": [{"group": g, "count": groups.get(g, 0)} for g in ("Animals", "Plants", "Fungi", "Other")],
        "iucn_breakdown": [{"group": k, "count": v} for k, v in statuses.most_common()],
        "milestones": make_milestones(daily_rows),
        "recent_assemblies": recent[:200],
        "annotations": annotations,
    }


def main():
    today = date.today()
    recent_cutoff = (today - timedelta(days=RECENT_DAYS - 1)).isoformat()
    dashboard = json.loads(DASH.read_text()) if DASH.exists() else {}
    iucn, source_counts = load_iucn_names()

    buckets = {"threatened": [], "extinct": []}
    reports = matched = 0
    for report in stream_assemblies():
        reports += 1
        x = normalize_assembly(report)
        if not x["accession"] or len(x["release_date"]) != 10:
            continue
        info = iucn.get(x["organism_name"].casefold()) or iucn.get(species_key(x["organism_name"]))
        if not info:
            continue
        matched += 1
        x["iucn_status"] = info["status"]
        x["iucn_name"] = info["accepted_name"]
        x["group"] = info["group"]
        target = "threatened" if info["status"] in THREATENED else "extinct"
        buckets[target].append(x)

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "dataset": "The IUCN Red List of Threatened Species",
            "endpoint": IUCN_URL,
            "scope": "IUCN threatened (VU/EN/CR) and extinct (EW/EX) categories",
            "matching": "NCBI organism scientific name matched to IUCN scientific/accepted/species names",
            "license": "CC BY 4.0 via GBIF",
        },
        "threatened": aggregate(buckets["threatened"], dashboard, recent_cutoff),
        "extinct": aggregate(buckets["extinct"], dashboard, recent_cutoff),
        "audit": {
            "ncbi_assemblies_scanned": reports,
            "matched_assemblies": matched,
            "iucn_category_rows": dict(source_counts),
        },
    }
    (OUT / "iucn.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(
        f"wrote {OUT / 'iucn.json'}: "
        f"{len(buckets['threatened'])} threatened assemblies, "
        f"{len(buckets['extinct'])} extinct assemblies, "
        f"{reports} NCBI assemblies scanned"
    )


if __name__ == "__main__":
    main()
