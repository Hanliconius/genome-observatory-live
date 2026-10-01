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
    "not determined", "restricted access", "unknown", "unspecified",
    "na", "n/a", "none",
}

# INSDC geo_loc_name controlled vocabulary entries that are oceans or seas.
# Coordinates are display anchors only: they place a marker in the named water
# body and are not interpreted as the sample's precise collection coordinates.
MARINE_LOCALITIES = {
    "arctic ocean": {"name": "Arctic Ocean", "lat": 82.0, "lon": 0.0},
    "atlantic ocean": {"name": "Atlantic Ocean", "lat": 12.0, "lon": -32.0},
    "baltic sea": {"name": "Baltic Sea", "lat": 58.0, "lon": 20.0},
    "indian ocean": {"name": "Indian Ocean", "lat": -20.0, "lon": 80.0},
    "mediterranean sea": {"name": "Mediterranean Sea", "lat": 36.0, "lon": 18.0},
    "north sea": {"name": "North Sea", "lat": 56.0, "lon": 3.0},
    "pacific ocean": {"name": "Pacific Ocean", "lat": 2.0, "lon": -150.0},
    "ross sea": {"name": "Ross Sea", "lat": -75.0, "lon": 175.0},
    "southern ocean": {"name": "Southern Ocean", "lat": -60.0, "lon": 20.0},
    "tasman sea": {"name": "Tasman Sea", "lat": -40.0, "lon": 160.0},
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

    # INSDC / NCBI geo_loc_name vocabulary differs from current ISO spellings
    # for several countries and territories. Keep these explicit so changes in
    # pycountry/iso-codes do not silently drop valid historical/current labels.
    "turkey": "TR",
    "cote d'ivoire": "CI",
    "côte d'ivoire": "CI",
    "curacao": "CW",
    "democratic republic of the congo": "CD",
    "republic of the congo": "CG",
    "falkland islands (islas malvinas)": "FK",
    "cocos islands": "CC",
    "macau": "MO",
    "micronesia, federated states of": "FM",
    "pitcairn islands": "PN",
    "reunion": "RE",
    "saint barthelemy": "BL",
    "saint helena": "SH",
    "saint martin": "MF",
    "sint maarten": "SX",
    "svalbard": "SJ",
    "jan mayen": "SJ",
    "virgin islands": "VI",
    "french southern and antarctic lands": "TF",
    "gaza strip": "PS",
    "west bank": "PS",

    # Unambiguous historical INSDC names.
    "belgian congo": "CD",
    "british guiana": "GY",
    "burma": "MM",
    "east timor": "TL",
    "siam": "TH",
    "the former yugoslav republic of macedonia": "MK",
    "zaire": "CD",
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


def lookup_country(candidate):
    candidate = re.sub(r"\s+", " ", str(candidate or "")).strip().strip('"')
    if not candidate or candidate.casefold() in MISSING:
        return None

    key = (
        candidate
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .casefold()
    )
    alias = ALIASES.get(key)
    try:
        country = (
            pycountry.countries.get(alpha_2=alias)
            if alias
            else pycountry.countries.lookup(candidate)
        )
    except LookupError:
        return None
    return country


def country_from_geo(raw):
    if not raw:
        return None
    value = re.sub(r"\s+", " ", str(raw)).strip()
    if value.casefold() in MISSING:
        return None

    # INSDC geo_loc_name uses COUNTRY: finer locality. First try the controlled
    # vocabulary prefix verbatim. A comma fallback catches older/non-conforming
    # values such as "Turkey, Ankara" without breaking names such as
    # "Micronesia, Federated States of", because the full value is tried first.
    candidate = value.split(":", 1)[0].strip()
    if candidate.casefold() in MISSING:
        return None

    country = lookup_country(candidate)
    if not country and ":" not in value and "," in candidate:
        country = lookup_country(candidate.split(",", 1)[0])

    if not country:
        return None
    return {
        "iso2": country.alpha_2,
        "iso3": country.alpha_3,
        "iso_n3": str(country.numeric).zfill(3),
        "name": country.name,
        "raw": value,
    }


def marine_from_geo(raw):
    if not raw:
        return None
    value = re.sub(r"\s+", " ", str(raw)).strip()
    if value.casefold() in MISSING:
        return None
    prefix = value.split(":", 1)[0].strip().casefold()
    meta = MARINE_LOCALITIES.get(prefix)
    if not meta:
        return None
    return {**meta, "raw": value}


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
    rate_window_days = 30
    window_start = today - timedelta(days=rate_window_days - 1)
    window_cutoff = window_start.isoformat()
    business_days_in_window = sum(
        1 for i in range(rate_window_days)
        if (window_start + timedelta(days=i)).weekday() < 5
    )

    countries = {}
    marine_localities = {}
    unassigned = 0
    reports = 0
    with_location = 0
    missing_location = 0
    unresolved_location = defaultdict(int)

    def ensure(c):
        key = c["iso3"]
        if key not in countries:
            countries[key] = {
                "iso2": c["iso2"],
                "iso3": c["iso3"],
                "iso_n3": c["iso_n3"],
                "name": c["name"],
                "assemblies": 0,
                "window_assemblies": 0,
                "species": set(),
                "first_seen": {},
                "yearly_assemblies": defaultdict(int),
            }
        return countries[key]

    def ensure_marine(m):
        key = m["name"]
        if key not in marine_localities:
            marine_localities[key] = {
                "name": m["name"],
                "lat": m["lat"],
                "lon": m["lon"],
                "assemblies": 0,
                "window_assemblies": 0,
                "species": set(),
            }
        return marine_localities[key]

    for report in stream_assemblies():
        reports += 1
        x = normalize(report)
        if not x["accession"] or len(x["release_date"]) != 10:
            continue
        if x["geo_loc_name"]:
            with_location += 1
        else:
            missing_location += 1
        c = country_from_geo(x["geo_loc_name"])
        m = None if c else marine_from_geo(x["geo_loc_name"])
        if m:
            mrec = ensure_marine(m)
            mrec["assemblies"] += 1
            mrec["species"].add(x["organism_name"])
            if x["release_date"] >= window_cutoff:
                mrec["window_assemblies"] += 1
            continue

        if not c:
            unassigned += 1
            if x["geo_loc_name"]:
                prefix = re.sub(r"\s+", " ", str(x["geo_loc_name"])).strip().split(":", 1)[0].strip()
                unresolved_location[prefix] += 1
            continue

        rec = ensure(c)
        rec["assemblies"] += 1
        rec["species"].add(x["organism_name"])
        rec["yearly_assemblies"][x["release_date"][:4]] += 1
        if x["release_date"] >= window_cutoff:
            rec["window_assemblies"] += 1

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
            "window_assemblies": rec["window_assemblies"],
            "business_days_in_window": business_days_in_window,
            "genomes_per_day": rec["window_assemblies"] / float(rate_window_days),
            "genomes_per_business_day": rec["window_assemblies"] / float(max(1, business_days_in_window)),
            "yearly": yearly,
        })

    out_rows.sort(key=lambda x: x["name"])
    assigned = sum(x["assemblies"] for x in out_rows)
    marine_rows = [
        {
            "name": rec["name"],
            "lat": rec["lat"],
            "lon": rec["lon"],
            "assemblies": rec["assemblies"],
            "species": len(rec["species"]),
            "window_assemblies": rec["window_assemblies"],
            "business_days_in_window": business_days_in_window,
            "genomes_per_day": rec["window_assemblies"] / float(rate_window_days),
            "genomes_per_business_day": rec["window_assemblies"] / float(max(1, business_days_in_window)),
        }
        for rec in sorted(marine_localities.values(), key=lambda x: x["name"])
    ]
    marine_assigned = sum(x["assemblies"] for x in marine_rows)
    geographically_resolved = assigned + marine_assigned
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "field": "NCBI BioSample geoLocName",
            "interpretation": "controlled geo_loc_name prefix before ':'; ISO countries are choropleth regions and INSDC ocean/sea terms are mapped as representative marine markers",
        },
        "coverage": {
            "assemblies_scanned": reports,
            "assemblies_with_geo_loc_name": with_location,
            "assemblies_assigned_to_country": assigned,
            "assemblies_assigned_to_marine_locality": marine_assigned,
            "assemblies_geographically_resolved": geographically_resolved,
            "assemblies_unassigned": unassigned,
            "assemblies_missing_geo_loc_name": missing_location,
            "assemblies_with_unresolved_geo_loc_name": sum(unresolved_location.values()),
            "fraction_assigned": assigned / reports if reports else 0,
            "fraction_resolved_geographically": geographically_resolved / reports if reports else 0,
            "unresolved_geo_loc_prefixes": [
                {"value": value, "count": count}
                for value, count in sorted(
                    unresolved_location.items(),
                    key=lambda item: (-item[1], item[0].casefold()),
                )[:50]
            ],
        },
        "rate_window_days": rate_window_days,
        "countries": out_rows,
        "marine_localities": marine_rows,
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(
        f"wrote {OUT}: {len(out_rows)} countries, "
        f"{assigned}/{reports} assemblies assigned ({payload['coverage']['fraction_assigned']:.1%}); "
        f"{missing_location} missing geo_loc_name; "
        f"{sum(unresolved_location.values())} non-empty locations unresolved"
    )
    if unresolved_location:
        print("top unresolved geo_loc_name prefixes:")
        for value, count in sorted(
            unresolved_location.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )[:20]:
            print(f"  {count:6d}  {value}")


if __name__ == "__main__":
    main()
