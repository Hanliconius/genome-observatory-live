#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pycountry
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sequencing_countries.json"
AUDIT_DIR = ROOT / "data" / "audits"
AUDIT_JSON = AUDIT_DIR / "sequencing_country_provenance.json"
AUDIT_TSV = AUDIT_DIR / "sequencing_country_dtol_failures.tsv"
CACHE_DIR = ROOT / "cache"
SRA_CACHE = CACHE_DIR / "sra_biosample_centers.json"
ROR_CACHE = CACHE_DIR / "ror_center_countries.json"

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ROR_URL = "https://api.ror.org/v2/organizations"
UA = "EukaryoteGenomeWatch/0.7 (public research dashboard; contact via repository)"
RATE_WINDOW_DAYS = 30
SRA_BATCH_SIZE = 250

# Provenance audit v1
DTOL_BIOPROJECT = "PRJEB40665"
SANGER_TOL_BIOPROJECT = "PRJEB43745"

# Independent positive controls taken from the assembly submitter field.
# These are deliberately conservative, institution-specific names with
# unambiguous countries; they are used only for audit metrics, not to alter
# production country assignments.
SUBMITTER_CONTROLS = [
    ("Wellcome Sanger Institute", "GBR", ("WELLCOME SANGER INSTITUTE", "WELLCOME TRUST SANGER INSTITUTE")),
    ("Earlham Institute", "GBR", ("EARLHAM INSTITUTE",)),
    ("Broad Institute", "USA", ("BROAD INSTITUTE",)),
    ("Baylor College of Medicine", "USA", ("BAYLOR COLLEGE OF MEDICINE",)),
    ("DOE Joint Genome Institute", "USA", ("JOINT GENOME INSTITUTE",)),
    ("Chinese Academy of Sciences", "CHN", ("CHINESE ACADEMY OF SCIENCES",)),
    ("Max Planck Institute", "DEU", ("MAX PLANCK INSTITUTE",)),
    ("University of Copenhagen", "DNK", ("UNIVERSITY OF COPENHAGEN",)),
    ("Australian National University", "AUS", ("AUSTRALIAN NATIONAL UNIVERSITY",)),
]

S = requests.Session()
S.headers.update({"User-Agent": UA})


def request_with_retries(method, url, *, attempts=5, **kwargs):
    last = None
    for attempt in range(attempts):
        try:
            r = S.request(method, url, **kwargs)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                last = requests.HTTPError(
                    f"{r.status_code} transient response for {url}",
                    response=r,
                )
                time.sleep(min(8.0, 0.75 * (2 ** attempt)))
                continue
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = exc
            time.sleep(min(8.0, 0.75 * (2 ** attempt)))
    if last is not None:
        raise last
    raise RuntimeError(f"request failed without response: {url}")


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


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n")


def stream_assemblies():
    cmd = [
        "datasets", "summary", "genome", "taxon", "Eukaryota",
        "--assembly-source", "GenBank",
        "--assembly-level", "chromosome,complete",
        "--as-json-lines",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line:
            yield json.loads(line)
    stderr = proc.stderr.read() if proc.stderr else ""
    code = proc.wait()
    if code:
        raise RuntimeError(
            f"NCBI datasets failed with exit code {code}: {stderr[-4000:]}"
        )


def bioproject_accessions(report):
    info = first(report, "assembly_info", "assemblyInfo", default={}) or {}
    found = set()

    direct = first(
        info,
        "bioproject_accession",
        "bioprojectAccession",
        default=None,
    )
    if direct:
        found.add(str(direct).strip())

    lineage = info.get("bioproject_lineage") or info.get("bioprojectLineage") or []
    for level in lineage:
        for project in (level.get("bioprojects") or []):
            accession = project.get("accession")
            if accession:
                found.add(str(accession).strip())
            parents = project.get("parent_accessions") or project.get("parentAccessions") or []
            for parent in parents:
                if parent:
                    found.add(str(parent).strip())

    bs = first(info, "biosample", default={}) or {}
    for project in (bs.get("bioprojects") or []):
        accession = project.get("accession")
        if accession:
            found.add(str(accession).strip())
        parents = project.get("parent_accessions") or project.get("parentAccessions") or []
        for parent in parents:
            if parent:
                found.add(str(parent).strip())

    return sorted(x for x in found if x)


def normalize_assembly(report):
    info = first(report, "assembly_info", "assemblyInfo", default={}) or {}
    bs = first(info, "biosample", default={}) or {}
    owner = first(bs, "owner", default={}) or {}
    return {
        "accession": first(
            report, "accession", "assembly.accession",
            "assembly_info.assembly_accession", default=""
        ),
        "organism_name": str(first(
            report, "organism.organism_name", "organism.organismName",
            "organism_name", "organism.name", default="Unknown"
        )).strip(),
        "release_date": str(first(
            report, "assembly_info.release_date", "assemblyInfo.releaseDate",
            "assembly.release_date", "release_date", default=""
        ))[:10],
        "biosample": str(first(bs, "accession", default="") or "").strip(),
        "submitter": str(first(info, "submitter", default="") or "").strip(),
        "biosample_owner": str(first(owner, "name", default="") or "").strip(),
        "bioproject_accessions": bioproject_accessions(report),
    }


def parse_runinfo(text, biosamples):
    reader = csv.DictReader(io.StringIO(text))
    fields = set(reader.fieldnames or [])
    bs_field = next(
        (x for x in ("BioSample", "BioSampleAccn", "biosample") if x in fields),
        None,
    )
    center_field = next(
        (x for x in ("CenterName", "center_name", "Center") if x in fields),
        None,
    )
    if not bs_field or not center_field:
        raise RuntimeError(
            f"Unexpected SRA RunInfo fields: {sorted(fields)}; "
            f"response prefix={text[:500]!r}"
        )

    found = defaultdict(set)
    wanted = set(biosamples)
    for row in reader:
        bs = str(row.get(bs_field, "") or "").strip()
        center = re.sub(r"\\s+", " ", str(row.get(center_field, "") or "")).strip()
        if bs in wanted and center and center.casefold() not in {
            "not provided", "not applicable", "missing", "unknown", "na", "n/a"
        }:
            found[bs].add(center)
    return found


def query_sra_runinfo(biosamples):
    if not biosamples:
        return {}

    term = " OR ".join(f'"{x}"[BioSample]' for x in biosamples)
    time.sleep(0.36)
    search = request_with_retries(
        "POST",
        ESEARCH_URL,
        data={
            "db": "sra",
            "term": term,
            "retmode": "json",
            "retmax": "100000",
            "tool": "EukaryoteGenomeWatch",
        },
        timeout=120,
    )
    ids = ((search.json().get("esearchresult") or {}).get("idlist") or [])
    if not ids:
        return {x: [] for x in biosamples}

    found = defaultdict(set)
    for start in range(0, len(ids), 5000):
        chunk = ids[start:start + 5000]
        time.sleep(0.36)
        fetch = request_with_retries(
            "POST",
            EFETCH_URL,
            data={
                "db": "sra",
                "id": ",".join(chunk),
                "rettype": "runinfo",
                "retmode": "text",
                "tool": "EukaryoteGenomeWatch",
            },
            timeout=180,
        )
        parsed = parse_runinfo(fetch.text, biosamples)
        for bs, centers in parsed.items():
            found[bs].update(centers)

    return {x: sorted(found.get(x, set())) for x in biosamples}


def backfill_sra_cache(biosamples, cache):
    missing = sorted(x for x in biosamples if x and x not in cache)
    if not missing:
        return cache

    print(f"SRA: resolving {len(missing)} uncached BioSamples")
    for start in range(0, len(missing), SRA_BATCH_SIZE):
        batch = missing[start:start + SRA_BATCH_SIZE]
        try:
            result = query_sra_runinfo(batch)
        except requests.HTTPError as exc:
            # If a query is rejected because it is too large, retry this batch
            # as smaller chunks. Persistent transient failures are left
            # uncached so a later scheduled run can retry only those BioSamples.
            if exc.response is not None and exc.response.status_code in {400, 414} and len(batch) > 10:
                result = {}
                step = max(10, len(batch) // 3)
                for j in range(0, len(batch), step):
                    small = batch[j:j + step]
                    try:
                        result.update(query_sra_runinfo(small))
                    except requests.RequestException as subexc:
                        print(f"SRA batch deferred after retries ({len(small)} BioSamples): {subexc}")
                    time.sleep(0.34)
            else:
                print(f"SRA batch deferred after retries ({len(batch)} BioSamples): {exc}")
                result = {}
        except requests.RequestException as exc:
            print(f"SRA batch deferred after retries ({len(batch)} BioSamples): {exc}")
            result = {}
        cache.update(result)
        if start % (SRA_BATCH_SIZE * 10) == 0:
            write_json(SRA_CACHE, cache)
        time.sleep(0.34)

    write_json(SRA_CACHE, cache)
    return cache


def country_from_ror_org(org):
    codes = []
    names = []
    for loc in org.get("locations", []) or []:
        gd = loc.get("geonames_details") or {}
        code = str(gd.get("country_code") or "").strip().upper()
        name = str(gd.get("country_name") or "").strip()
        if code:
            codes.append(code)
        if name:
            names.append(name)
    unique = sorted(set(codes))
    if len(unique) != 1:
        return None
    c = pycountry.countries.get(alpha_2=unique[0])
    if not c:
        return None
    return {
        "iso2": c.alpha_2,
        "iso3": c.alpha_3,
        "iso_n3": str(c.numeric).zfill(3),
        "name": c.name,
        "ror_id": org.get("id"),
        "ror_name": next(
            (
                n.get("value")
                for n in org.get("names", []) or []
                if "ror_display" in (n.get("types") or [])
            ),
            None,
        ),
    }


def resolve_center(center):
    r = S.get(ROR_URL, params={"affiliation": center}, timeout=60)
    r.raise_for_status()
    data = r.json()
    chosen = next((x for x in data.get("items", []) if x.get("chosen") is True), None)
    if not chosen:
        return {"status": "unmatched"}
    org = chosen.get("organization") or {}
    country = country_from_ror_org(org)
    if not country:
        return {
            "status": "ambiguous_location",
            "ror_id": org.get("id"),
        }
    return {
        "status": "matched",
        **country,
        "matching_type": chosen.get("matching_type"),
    }


def backfill_ror_cache(centers, cache):
    missing = sorted(x for x in centers if x and x not in cache)
    if not missing:
        return cache

    print(f"ROR: resolving {len(missing)} uncached SRA center names")
    for i, center in enumerate(missing, 1):
        try:
            cache[center] = resolve_center(center)
        except requests.RequestException as exc:
            # Do not cache transient network failures; they can retry next run.
            print(f"ROR transient failure for {center!r}: {exc}")
            continue
        if i % 20 == 0:
            write_json(ROR_CACHE, cache)
        # Stay comfortably below the public API's maximum request rate.
        time.sleep(0.2)

    write_json(ROR_CACHE, cache)
    return cache


def aggregate(records, sra_cache, ror_cache):
    today = date.today()
    cutoff = (today - timedelta(days=RATE_WINDOW_DAYS - 1)).isoformat()
    countries = {}
    coverage = Counter()
    unresolved_centers = Counter()

    def ensure(country):
        key = country["iso3"]
        if key not in countries:
            countries[key] = {
                "iso2": country["iso2"],
                "iso3": country["iso3"],
                "iso_n3": country["iso_n3"],
                "name": country["name"],
                "assemblies": 0,
                "window_assemblies": 0,
                "species": set(),
                "first_seen": {},
                "yearly_assemblies": defaultdict(int),
                "centers": Counter(),
            }
        return countries[key]

    for x in records:
        coverage["assemblies_scanned"] += 1
        bs = x["biosample"]
        if not bs:
            continue
        coverage["assemblies_with_biosample"] += 1

        centers = sorted(set(sra_cache.get(bs, []) or []))
        if not centers:
            continue
        coverage["assemblies_with_sra_center"] += 1

        country_to_centers = defaultdict(set)
        for center in centers:
            info = ror_cache.get(center) or {}
            if info.get("status") != "matched" or not info.get("iso3"):
                unresolved_centers[center] += 1
                continue
            country_to_centers[info["iso3"]].add(center)

        if not country_to_centers:
            continue
        coverage["assemblies_with_resolved_center_country"] += 1
        if len(country_to_centers) > 1:
            coverage["assemblies_with_multiple_center_countries"] += 1

        for iso3, matched_centers in country_to_centers.items():
            info = next(
                v for v in ror_cache.values()
                if isinstance(v, dict) and v.get("status") == "matched" and v.get("iso3") == iso3
            )
            rec = ensure(info)
            rec["assemblies"] += 1
            rec["species"].add(x["organism_name"])
            rec["yearly_assemblies"][x["release_date"][:4]] += 1
            if x["release_date"] >= cutoff:
                rec["window_assemblies"] += 1
            for center in matched_centers:
                rec["centers"][center] += 1

            org = x["organism_name"]
            old = rec["first_seen"].get(org)
            if old is None or x["release_date"] < old:
                rec["first_seen"][org] = x["release_date"]

    rows = []
    for rec in countries.values():
        first_by_year = Counter(ds[:4] for ds in rec["first_seen"].values())
        years = sorted(set(rec["yearly_assemblies"]) | set(first_by_year))
        rows.append({
            "iso2": rec["iso2"],
            "iso3": rec["iso3"],
            "iso_n3": rec["iso_n3"],
            "name": rec["name"],
            "assemblies": rec["assemblies"],
            "species": len(rec["species"]),
            "first_time_species": len(rec["first_seen"]),
            "window_assemblies": rec["window_assemblies"],
            "genomes_per_day": rec["window_assemblies"] / float(RATE_WINDOW_DAYS),
            "top_centers": [
                {"name": name, "assemblies": n}
                for name, n in rec["centers"].most_common(5)
            ],
            "yearly": [
                {
                    "year": int(year),
                    "assemblies": rec["yearly_assemblies"].get(year, 0),
                    "first_time_species": first_by_year.get(year, 0),
                }
                for year in years
            ],
        })

    rows.sort(key=lambda x: x["name"])
    coverage["country_assignments"] = sum(x["assemblies"] for x in rows)
    total = coverage["assemblies_scanned"]
    resolved = coverage["assemblies_with_resolved_center_country"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rate_window_days": RATE_WINDOW_DAYS,
        "source": {
            "linkage": "NCBI genome assembly BioSample -> SRA RunInfo BioSample",
            "center_field": "SRA CenterName",
            "organization_resolution": "ROR v2 affiliation matcher; chosen:true results only",
            "interpretation": (
                "An assembly is counted once in each country represented by a resolved "
                "SRA sequencing center linked to its BioSample. Country totals can therefore "
                "overlap when an assembly has sequencing data from centers in multiple countries."
            ),
        },
        "coverage": {
            **coverage,
            "fraction_resolved": resolved / total if total else 0,
            "distinct_sra_centers": len({
                c for vals in sra_cache.values() for c in (vals or [])
            }),
            "distinct_centers_resolved_to_country": sum(
                1 for v in ror_cache.values()
                if isinstance(v, dict) and v.get("status") == "matched"
            ),
        },
        "unresolved_centers": [
            {"name": name, "assemblies": n}
            for name, n in unresolved_centers.most_common(25)
        ],
        "countries": rows,
    }




def resolved_center_info(centers, ror_cache):
    resolved = []
    unresolved = []
    for center in sorted(set(centers or [])):
        info = ror_cache.get(center) or {}
        if info.get("status") == "matched" and info.get("iso3"):
            resolved.append({
                "center": center,
                "iso3": info.get("iso3"),
                "ror_name": info.get("ror_name"),
                "ror_id": info.get("ror_id"),
                "matching_type": info.get("matching_type"),
            })
        else:
            unresolved.append({
                "center": center,
                "status": info.get("status", "not_cached"),
                "ror_name": info.get("ror_name"),
                "ror_id": info.get("ror_id"),
            })
    return resolved, unresolved


def exclusive_failure_stage(record, centers, resolved, expected_iso3):
    if not record.get("biosample"):
        return "no_biosample"
    if not centers:
        return "no_sra_center"
    if not resolved:
        return "centers_unresolved"
    countries = {x.get("iso3") for x in resolved if x.get("iso3")}
    if expected_iso3 not in countries:
        return "resolved_wrong_country"
    return "resolved_expected_country"


def control_for_submitter(submitter):
    text = str(submitter or "").upper()
    for label, iso3, patterns in SUBMITTER_CONTROLS:
        if any(pattern in text for pattern in patterns):
            return label, iso3
    return None


def build_provenance_audit(records, sra_cache, ror_cache):
    generated_at = datetime.now(timezone.utc).isoformat()
    global_counts = Counter()
    global_center_counts = Counter()

    dtol_rows = []
    dtol_stages = Counter()
    dtol_center_counts = Counter()
    dtol_submitters = Counter()
    dtol_owners = Counter()

    controls = {}
    for label, iso3, _ in SUBMITTER_CONTROLS:
        controls[label] = {
            "label": label,
            "expected_iso3": iso3,
            "assemblies": 0,
            "with_biosample": 0,
            "with_sra_center": 0,
            "with_resolved_country": 0,
            "resolved_expected_country": 0,
            "resolved_wrong_country": 0,
            "stage_counts": Counter(),
            "center_counts": Counter(),
            "wrong_country_examples": [],
        }

    for record in records:
        global_counts["assemblies"] += 1
        bs = record.get("biosample")
        centers = sorted(set(sra_cache.get(bs, []) or [])) if bs else []
        resolved, unresolved = resolved_center_info(centers, ror_cache)
        countries = sorted({x["iso3"] for x in resolved if x.get("iso3")})

        if bs:
            global_counts["with_biosample"] += 1
        if centers:
            global_counts["with_sra_center"] += 1
        if resolved:
            global_counts["with_resolved_country"] += 1
        for center in centers:
            global_center_counts[center] += 1

        project_set = set(record.get("bioproject_accessions") or [])
        is_dtol = DTOL_BIOPROJECT in project_set
        if is_dtol:
            stage = exclusive_failure_stage(record, centers, resolved, "GBR")
            dtol_stages[stage] += 1
            dtol_submitters[record.get("submitter") or "(missing)"] += 1
            dtol_owners[record.get("biosample_owner") or "(missing)"] += 1
            for center in centers:
                dtol_center_counts[center] += 1

            dtol_rows.append({
                "accession": record.get("accession"),
                "organism_name": record.get("organism_name"),
                "release_date": record.get("release_date"),
                "biosample": bs,
                "submitter": record.get("submitter"),
                "biosample_owner": record.get("biosample_owner"),
                "bioproject_accessions": record.get("bioproject_accessions") or [],
                "centers": centers,
                "resolved_countries": countries,
                "resolved_centers": resolved,
                "unresolved_centers": unresolved,
                "failure_stage": stage,
            })

        control = control_for_submitter(record.get("submitter"))
        if control:
            label, expected_iso3 = control
            c = controls[label]
            c["assemblies"] += 1
            if bs:
                c["with_biosample"] += 1
            if centers:
                c["with_sra_center"] += 1
            if resolved:
                c["with_resolved_country"] += 1
            stage = exclusive_failure_stage(record, centers, resolved, expected_iso3)
            c["stage_counts"][stage] += 1
            if expected_iso3 in countries:
                c["resolved_expected_country"] += 1
            elif resolved:
                c["resolved_wrong_country"] += 1
                if len(c["wrong_country_examples"]) < 20:
                    c["wrong_country_examples"].append({
                        "accession": record.get("accession"),
                        "organism_name": record.get("organism_name"),
                        "submitter": record.get("submitter"),
                        "centers": centers,
                        "resolved_countries": countries,
                        "resolved_centers": resolved,
                    })
            for center in centers:
                c["center_counts"][center] += 1

    def center_rows(counter, limit=50):
        rows = []
        for center, n in counter.most_common(limit):
            info = ror_cache.get(center) or {}
            rows.append({
                "center": center,
                "assemblies": n,
                "status": info.get("status", "not_cached"),
                "iso3": info.get("iso3"),
                "ror_name": info.get("ror_name"),
                "ror_id": info.get("ror_id"),
                "matching_type": info.get("matching_type"),
            })
        return rows

    control_rows = []
    for label, _, _ in SUBMITTER_CONTROLS:
        c = controls[label]
        total = c["assemblies"]
        if total == 0:
            continue
        correct = c["resolved_expected_country"]
        wrong = c["resolved_wrong_country"]
        resolved_total = c["with_resolved_country"]
        c_out = {
            k: v for k, v in c.items()
            if k not in {"stage_counts", "center_counts"}
        }
        c_out["stage_counts"] = dict(c["stage_counts"])
        c_out["recall_expected_country"] = correct / total if total else 0
        c_out["precision_among_resolved"] = (
            correct / (correct + wrong) if (correct + wrong) else None
        )
        c_out["resolution_rate"] = resolved_total / total if total else 0
        c_out["top_centers"] = center_rows(c["center_counts"], 20)
        control_rows.append(c_out)

    dtol_total = len(dtol_rows)
    dtol_gbr = dtol_stages["resolved_expected_country"]
    dtol_wrong = dtol_stages["resolved_wrong_country"]
    dtol_resolved = dtol_gbr + dtol_wrong

    unresolved_global = Counter()
    for center, n in global_center_counts.items():
        info = ror_cache.get(center) or {}
        if info.get("status") != "matched" or not info.get("iso3"):
            unresolved_global[center] = n

    audit = {
        "generated_at": generated_at,
        "scope": "Chromosome/complete GenBank Eukaryota assemblies tracked by Genome Observatory Live",
        "method": {
            "production_path": "Assembly -> BioSample -> SRA RunInfo CenterName -> ROR affiliation match -> country",
            "dtol_positive_control": DTOL_BIOPROJECT,
            "sanger_tree_of_life_parent": SANGER_TOL_BIOPROJECT,
            "note": (
                "DToL membership is read from the NCBI assembly BioProject lineage. "
                "DToL is led by Wellcome Sanger Institute in the UK, so GBR is the "
                "expected country for this positive-control cohort. Submitter controls "
                "are independent conservative checks and do not alter production assignments."
            ),
        },
        "global": {
            **global_counts,
            "sra_center_rate": (
                global_counts["with_sra_center"] / global_counts["assemblies"]
                if global_counts["assemblies"] else 0
            ),
            "resolved_country_rate": (
                global_counts["with_resolved_country"] / global_counts["assemblies"]
                if global_counts["assemblies"] else 0
            ),
            "distinct_center_names": len(global_center_counts),
            "distinct_unresolved_center_names": len(unresolved_global),
            "top_unresolved_centers": center_rows(unresolved_global, 50),
        },
        "dtol": {
            "bioproject": DTOL_BIOPROJECT,
            "tracked_assemblies": dtol_total,
            "stage_counts": dict(dtol_stages),
            "recall_gbr": dtol_gbr / dtol_total if dtol_total else 0,
            "resolution_rate": dtol_resolved / dtol_total if dtol_total else 0,
            "precision_among_resolved": (
                dtol_gbr / dtol_resolved if dtol_resolved else None
            ),
            "assembly_submitter_mentions_sanger": sum(
                n for name, n in dtol_submitters.items()
                if "SANGER" in name.upper()
            ),
            "biosample_owner_mentions_sanger": sum(
                n for name, n in dtol_owners.items()
                if "SANGER" in name.upper()
            ),
            "top_submitters": [
                {"name": name, "assemblies": n}
                for name, n in dtol_submitters.most_common(20)
            ],
            "top_biosample_owners": [
                {"name": name, "assemblies": n}
                for name, n in dtol_owners.most_common(20)
            ],
            "top_centers": center_rows(dtol_center_counts, 50),
            "failure_examples": [
                row for row in dtol_rows
                if row["failure_stage"] != "resolved_expected_country"
            ][:100],
        },
        "submitter_controls": control_rows,
    }

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(AUDIT_JSON, audit)

    with AUDIT_TSV.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow([
            "accession", "organism_name", "release_date", "biosample",
            "submitter", "biosample_owner", "bioproject_accessions",
            "centers", "resolved_countries", "failure_stage",
        ])
        for row in dtol_rows:
            if row["failure_stage"] == "resolved_expected_country":
                continue
            writer.writerow([
                row["accession"],
                row["organism_name"],
                row["release_date"],
                row["biosample"],
                row["submitter"],
                row["biosample_owner"],
                ";".join(row["bioproject_accessions"]),
                ";".join(row["centers"]),
                ";".join(row["resolved_countries"]),
                row["failure_stage"],
            ])

    print(
        f"audit: DToL {dtol_gbr}/{dtol_total} resolved to GBR "
        f"({(dtol_gbr/dtol_total if dtol_total else 0):.1%}); "
        f"global {global_counts['with_resolved_country']}/"
        f"{global_counts['assemblies']} assemblies resolved"
    )
    return audit


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    biosamples = set()

    for report in stream_assemblies():
        x = normalize_assembly(report)
        if not x["accession"] or len(x["release_date"]) != 10:
            continue
        records.append(x)
        if x["biosample"]:
            biosamples.add(x["biosample"])

    print(f"Assemblies: {len(records)}; distinct BioSamples: {len(biosamples)}")

    sra_cache = load_json(SRA_CACHE, {})
    sra_cache = backfill_sra_cache(biosamples, sra_cache)

    centers = {
        center
        for bs in biosamples
        for center in (sra_cache.get(bs, []) or [])
        if center
    }
    print(f"Distinct SRA centers linked to current assemblies: {len(centers)}")

    ror_cache = load_json(ROR_CACHE, {})
    ror_cache = backfill_ror_cache(centers, ror_cache)

    payload = aggregate(records, sra_cache, ror_cache)
    write_json(OUT, payload)
    build_provenance_audit(records, sra_cache, ror_cache)

    cov = payload["coverage"]
    print(
        f"wrote {OUT}: {len(payload['countries'])} countries; "
        f"{cov['assemblies_with_resolved_center_country']}/"
        f"{cov['assemblies_scanned']} assemblies resolved "
        f"({cov['fraction_resolved']:.1%}); "
        f"{cov['assemblies_with_multiple_center_countries']} multi-country assemblies"
    )


if __name__ == "__main__":
    main()
