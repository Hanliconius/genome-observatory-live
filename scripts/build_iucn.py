#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import time
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
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


def meta_char(value, default="\t"):
    if value is None:
        return default
    return (
        value.replace("\\t", "\t")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
    )


def archive_layout(zf):
    root = ET.fromstring(zf.read("meta.xml"))
    components = []
    for node in list(root):
        kind = node.tag.rsplit("}", 1)[-1].casefold()
        if kind not in {"core", "extension"}:
            continue
        files = next((x for x in list(node) if x.tag.rsplit("}", 1)[-1] == "files"), None)
        if files is None:
            continue
        location_node = next((x for x in list(files) if x.tag.rsplit("}", 1)[-1] == "location"), None)
        if location_node is None or not (location_node.text or "").strip():
            continue
        location = (location_node.text or "").strip()
        fields = {}
        id_index = None
        coreid_index = None
        for child in list(node):
            tag = child.tag.rsplit("}", 1)[-1].casefold()
            if tag == "id":
                id_index = int(child.attrib["index"])
            elif tag == "coreid":
                coreid_index = int(child.attrib["index"])
            elif tag == "field":
                fields[int(child.attrib["index"])] = canonical_header(child.attrib.get("term", ""))
        components.append({
            "kind": kind,
            "location": location,
            "fields": fields,
            "id_index": id_index,
            "coreid_index": coreid_index,
            "delimiter": meta_char(node.attrib.get("fieldsTerminatedBy"), "\t"),
            "ignore": int(node.attrib.get("ignoreHeaderLines", "0") or 0),
            "encoding": node.attrib.get("encoding", "UTF-8"),
        })
    return components


def iter_component_rows(zf, component):
    with zf.open(component["location"]) as raw:
        text = io.TextIOWrapper(
            raw,
            encoding=component["encoding"] or "utf-8",
            errors="replace",
            newline="",
        )
        reader = csv.reader(text, delimiter=component["delimiter"])
        for _ in range(component["ignore"]):
            next(reader, None)
        for values in reader:
            row = {}
            for idx, term in component["fields"].items():
                row[term] = values[idx] if idx < len(values) else ""
            if component["id_index"] is not None:
                idx = component["id_index"]
                row["_id"] = values[idx] if idx < len(values) else ""
            if component["coreid_index"] is not None:
                idx = component["coreid_index"]
                row["_coreid"] = values[idx] if idx < len(values) else ""
            yield row


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
        layout = archive_layout(zf)
        core = next((x for x in layout if x["kind"] == "core"), None)
        if core is None:
            raise RuntimeError("IUCN Darwin Core archive has no core table in meta.xml")

        for row in iter_component_rows(zf, core):
            tid = str(row.get("_id") or row.get("taxonid") or "").strip()
            if tid:
                taxa[tid] = row

        status_components = [
            x for x in layout
            if set(x["fields"].values()).intersection(
                {"threatstatus", "iucnredlistcategory", "redlistcategory", "conservationstatus"}
            )
        ]
        if not status_components:
            raise RuntimeError(
                "IUCN archive has no status extension; meta.xml components="
                + json.dumps([
                    {"file": x["location"], "fields": sorted(set(x["fields"].values()))}
                    for x in layout
                ], ensure_ascii=False)[:12000]
            )

        status_rows = 0
        for component in status_components:
            for row in iter_component_rows(zf, component):
                status = category_from_row(row)
                if status not in THREATENED | EXTINCT:
                    continue
                tid = str(row.get("_coreid") or row.get("taxonid") or row.get("_id") or "").strip()
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
            raise RuntimeError(
                "Status extension was found but no VU/EN/CR/EW/EX rows were recognized"
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


def api_json(base, params):
    req = Request(base + "?" + urlencode(params), headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def commons_file_info(title):
    try:
        q = api_json("https://commons.wikimedia.org/w/api.php", {
            "action": "query", "titles": title, "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": 900, "format": "json",
        })
        for page in (q.get("query", {}).get("pages", {}) or {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            thumb = ii.get("thumburl")
            if not thumb:
                continue
            meta = ii.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName") or {}).get("value", "")
            artist = re.sub("<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()
            return {
                "thumb_url": thumb,
                "page_url": ii.get("descriptionurl", ""),
                "credit": " · ".join(x for x in (artist, lic) if x),
                "matched_name": title,
            }
    except Exception:
        pass
    return None


def wikidata_image(name):
    if not name:
        return None
    try:
        hits = api_json("https://www.wikidata.org/w/api.php", {
            "action": "wbsearchentities", "search": name, "language": "en",
            "type": "item", "limit": 5, "format": "json",
        }).get("search", [])
        for hit in hits:
            qid = hit.get("id")
            if not qid:
                continue
            ent = api_json("https://www.wikidata.org/w/api.php", {
                "action": "wbgetentities", "ids": qid, "props": "claims", "format": "json",
            }).get("entities", {}).get(qid, {})
            p18 = (ent.get("claims") or {}).get("P18") or []
            filename = first(p18[0], "mainsnak.datavalue.value") if p18 else None
            if filename:
                info = commons_file_info("File:" + filename)
                if info:
                    info["matched_name"] = name
                    return info
    except Exception:
        pass
    return None


def commons_search(name):
    if not name:
        return None
    try:
        q = api_json("https://commons.wikimedia.org/w/api.php", {
            "action": "query", "generator": "search",
            "gsrsearch": 'intitle:"' + name + '" filetype:bitmap',
            "gsrnamespace": 6, "gsrlimit": 6, "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": 900, "format": "json",
        })
        for page in (q.get("query", {}).get("pages", {}) or {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            thumb = ii.get("thumburl")
            if not thumb:
                continue
            meta = ii.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName") or {}).get("value", "")
            artist = re.sub("<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()
            return {
                "thumb_url": thumb,
                "page_url": ii.get("descriptionurl", ""),
                "credit": " · ".join(x for x in (artist, lic) if x),
                "matched_name": name,
            }
    except Exception:
        pass
    return None


def image_names(row):
    # Prefer the NCBI organism name, then the matched IUCN name. For older
    # fallback rows this avoids depending on the rolling dashboard taxonomy cache.
    names = []
    for raw in (row.get("organism_name"), row.get("iucn_name")):
        n = norm_name(raw)
        if n and n not in names:
            names.append(n)
        parts = n.split()
        if len(parts) >= 2:
            genus = parts[0]
            if genus not in names:
                names.append(genus)
    return names


def find_image(row):
    for name in image_names(row):
        info = wikidata_image(name) or commons_search(name)
        if info:
            return info
        time.sleep(0.1)
    return None

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


def aggregate(rows, dashboard, recent_cutoff, seed_recent_if_empty=False):
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

    # The extinct set is exceptionally sparse. On first population only, keep the
    # recent-content area useful by showing the latest known qualifying genomes
    # when the normal rolling window is empty. This is display content only:
    # recent_daily and all summary/rate calculations retain the real cutoff.
    recent_fallback = False
    if seed_recent_if_empty and not recent and rows:
        latest_species = set()
        for x in reversed(rows):
            org = x["organism_name"]
            if org in latest_species:
                continue
            y = dict(x)
            image = image_cache.get(org)
            if not image:
                image = find_image(y)
                if image:
                    image_cache[org] = image
            y["image"] = image
            recent.append(y)
            latest_species.add(org)
            if len(latest_species) >= min(6, len(first_seen)):
                break
        recent_fallback = bool(recent)

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
        "recent_assemblies_fallback": recent_fallback,
        "annotations": annotations,
    }


def main():
    today = date.today()
    recent_cutoff = (today - timedelta(days=RECENT_DAYS - 1)).isoformat()
    dashboard = json.loads(DASH.read_text()) if DASH.exists() else {}
    iucn, source_counts = load_iucn_names()

    # [refresh] Reuse the dashboard's resolved common names for overlapping assemblies.
    # update.py applies the canonical fallback rule: NCBI assembly common name,
    # then taxonomy curator_common_name, then group_name/BLAST name.
    dashboard_by_accession = {
        x.get("accession"): x
        for x in dashboard.get("recent_assemblies", [])
        if x.get("accession")
    }

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
        dashboard_row = dashboard_by_accession.get(x["accession"], {})
        if not x.get("common_name") and dashboard_row.get("common_name"):
            x["common_name"] = dashboard_row["common_name"]
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
        "extinct": aggregate(
            buckets["extinct"], dashboard, recent_cutoff, seed_recent_if_empty=True
        ),
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
