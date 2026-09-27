#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pycountry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "countries.json"

MISSING = {
    "", "missing", "not provided", "not applicable", "not collected",
    "unknown", "unspecified", "na", "n/a", "none",
}

ALIASES = {
    "usa": "US",
    "u.s.a.": "US",
    "united states": "US",
    "united states of america": "US",
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "russia": "RU",
    "south korea": "KR",
    "republic of korea": "KR",
    "north korea": "KP",
    "democratic people's republic of korea": "KP",
    "iran": "IR",
    "iran, islamic republic of": "IR",
    "viet nam": "VN",
    "vietnam": "VN",
    "laos": "LA",
    "lao people's democratic republic": "LA",
    "bolivia": "BO",
    "bolivia, plurinational state of": "BO",
    "venezuela": "VE",
    "venezuela, bolivarian republic of": "VE",
    "tanzania": "TZ",
    "tanzania, united republic of": "TZ",
    "moldova": "MD",
    "moldova, republic of": "MD",
    "brunei": "BN",
    "brunei darussalam": "BN",
    "czech republic": "CZ",
    "czechia": "CZ",
    "cape verde": "CV",
    "cabo verde": "CV",
    "swaziland": "SZ",
    "eswatini": "SZ",
    "taiwan": "TW",
    "taiwan, province of china": "TW",
    "palestine": "PS",
    "state of palestine": "PS",
    "micronesia": "FM",
    "federated states of micronesia": "FM",
    "macedonia": "MK",
    "north macedonia": "MK",
    "syria": "SY",
    "syrian arab republic": "SY",
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


def biosample(report):
    return first(
        report,
        "assembly_info.biosample",
        "assemblyInfo.biosample",
        default={},
    ) or {}


def geo_loc_name(report):
    bs = biosample(report)
    direct = first(
        bs,
        "geo_loc_name",
        "geoLocName",
        default=None,
    )
    if direct:
        return str(direct).strip()

    for attr in bs.get("attributes", []) or []:
        name = str(attr.get("name", "")).casefold().replace("-", "_").replace(" ", "_")
        if name in {
            "geo_loc_name", "geographic_location", "country",
            "geographic_location_(country_and/or_sea_region)",
        }:
            value = attr.get("value")
            if value:
                return str(value).strip()
    return None


def country_from_geo(raw):
    if not raw:
        return None
    value = re.sub(r"\s+", " ", str(raw)).strip()
    if value.casefold() in MISSING:
        return None

    # INSDC geo_loc_name uses COUNTRY: finer locality.
    candidate = value.split(":", 1)[0].strip()
    if candidate.casefold() in MISSING:
        return None

    alias = ALIASES.get(candidate.casefold())
    try:
        country = pycountry.countries.get(alpha_2=alias) if alias else pycountry.countries.lookup(candidate)
    except LookupError:
        return None
    if not country:
        return None
    return {
        "iso2": country.alpha_2,
        "iso3": country.alpha_3,
        "iso_n3": str(country.numeric).zfill(3),
        "name": country.name,
        "raw": value,
    }


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


def normalize(report):
    accession = first(
        report, "accession", "assembly.accession",
        "assembly_info.assembly_accession", default=""
    )
    organism = first(
        report, "organism.organism_name", "organism.organismName",
        "organism_name", "organism.name", default="Unknown"
    )
    release = str(first(
        report, "assembly_info.release_date", "assemblyInfo.releaseDate",
        "assembly.release_date", "release_date", default=""
    ))[:10]
    return {
        "accession": accession,
        "organism_name": str(organism).strip(),
        "release_date": release,
        "geo_loc_name": geo_loc_name(report),
    }


def main():
    today = date.today()
    week_cutoff = (today - timedelta(days=6)).isoformat()

    countries = {}
    unassigned = 0
    reports = 0
    with_location = 0

    def ensure(c):
        key = c["iso3"]
        if key not in countries:
            countries[key] = {
                "iso2": c["iso2"],
                "iso3": c["iso3"],
                "iso_n3": c["iso_n3"],
                "name": c["name"],
                "assemblies": 0,
                "week_assemblies": 0,
                "species": set(),
                "first_seen": {},
                "yearly_assemblies": defaultdict(int),
            }
        return countries[key]

    for report in stream_assemblies():
        reports += 1
        x = normalize(report)
        if not x["accession"] or len(x["release_date"]) != 10:
            continue
        if x["geo_loc_name"]:
            with_location += 1
        c = country_from_geo(x["geo_loc_name"])
        if not c:
            unassigned += 1
            continue

        rec = ensure(c)
        rec["assemblies"] += 1
        rec["species"].add(x["organism_name"])
        rec["yearly_assemblies"][x["release_date"][:4]] += 1
        if x["release_date"] >= week_cutoff:
            rec["week_assemblies"] += 1

        org = x["organism_name"]
        old = rec["first_seen"].get(org)
        if old is None or x["release_date"] < old:
            rec["first_seen"][org] = x["release_date"]

    out_rows = []
    for rec in countries.values():
        first_by_year = defaultdict(int)
        for ds in rec["first_seen"].values():
            first_by_year[ds[:4]] += 1

        years = sorted(set(rec["yearly_assemblies"]) | set(first_by_year))
        yearly = [
            {
                "year": int(year),
                "assemblies": rec["yearly_assemblies"].get(year, 0),
                "first_time_species": first_by_year.get(year, 0),
            }
            for year in years
        ]

        out_rows.append({
            "iso2": rec["iso2"],
            "iso3": rec["iso3"],
            "iso_n3": rec["iso_n3"],
            "name": rec["name"],
            "assemblies": rec["assemblies"],
            "species": len(rec["species"]),
            "first_time_species": len(rec["first_seen"]),
            "week_assemblies": rec["week_assemblies"],
            "genomes_per_day": rec["week_assemblies"] / 7.0,
            "yearly": yearly,
        })

    out_rows.sort(key=lambda x: x["name"])
    assigned = sum(x["assemblies"] for x in out_rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "field": "NCBI BioSample geoLocName",
            "interpretation": "country prefix before ':'; non-country geographic features and missing values remain unassigned",
        },
        "coverage": {
            "assemblies_scanned": reports,
            "assemblies_with_geo_loc_name": with_location,
            "assemblies_assigned_to_country": assigned,
            "assemblies_unassigned": unassigned,
            "fraction_assigned": assigned / reports if reports else 0,
        },
        "countries": out_rows,
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(
        f"wrote {OUT}: {len(out_rows)} countries, "
        f"{assigned}/{reports} assemblies assigned ({payload['coverage']['fraction_assigned']:.1%})"
    )


if __name__ == "__main__":
    main()
