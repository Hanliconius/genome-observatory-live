#!/usr/bin/env python3
"""Add archived GoaT release checkpoints and release-lag summaries to tracker data."""
import json
import gzip
import statistics
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "goat_intent_history.json"
TIMELINE_OUT = ROOT / "data" / "goat_intent_timeline.json"
CONNECTORS_OUT = ROOT / "data" / "goat_intent_connectors.json.gz"
CONNECTOR_STATE_OUT = ROOT / "cache" / "goat_intent_connector_state.json.gz"
ARCHIVE_DATES = ["2022.11.16", "2023.02.20", "2023.05.18", "2023.10.16",
                 "2024.03.01", "2024.09.14", "2025.04.21"]
FIELDS = ("sample_collected", "sample_acquired", "in_progress")
MAX_SIZE = 30000


def fetch(date_label, field):
    version = date_label.replace("-", ".")
    api = "/api/v2" if version == "live" else f"/api/{version}"
    params = {"query": field, "result": "taxon", "taxonomy": "ncbi",
              "size": MAX_SIZE, "fields": ",".join(FIELDS)}
    url = "https://goat.genomehubs.org" + api + "/search?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote)
    req = urllib.request.Request(url, headers={"User-Agent": "GenomeObservatoryLive/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.load(response)
    hits = data.get("status", {}).get("hits", 0)
    results = data.get("results", [])
    if not data.get("status", {}).get("success") or hits >= MAX_SIZE or len(results) != hits:
        raise RuntimeError(f"Incomplete GoaT response {version} {field}: {len(results)}/{hits}")
    return version, field, results


def main():
    dashboard = json.loads((ROOT / "data" / "dashboard.json").read_text())
    first_release = dashboard.get("species_first_seen", {})
    versions = [*ARCHIVE_DATES, "live"]
    # Keep concurrency modest; each response contains many taxon records.
    collected = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for version, field, rows in pool.map(lambda pair: fetch(*pair),
                                             [(v, f) for v in versions for f in FIELDS]):
            collected.setdefault(version, {})[field] = rows

    snapshots = []
    first_observed = {}
    previous_declarations = set()
    previous_taxa = set()
    previous_date = None
    for version in versions:
        daily = collected[version]
        label = date.today().isoformat() if version == "live" else version.replace(".", "-")
        declarations = set()
        names = {}
        for field, rows in daily.items():
            for row in rows:
                result = row.get("result", {})
                taxid = str(result.get("taxon_id", ""))
                if not taxid:
                    continue
                names[taxid] = result.get("scientific_name", "")
                value = result.get("fields", {}).get(field)
                if not value or value.get("aggregation_source") != "direct":
                    continue
                vals = value.get("value", [])
                if not isinstance(vals, list):
                    vals = [vals]
                for v in vals:
                    if not v:
                        continue
                    declarations.add((taxid, field, str(v)))
                    # Preserve the first checkpoint where this taxon had any direct intent.
                    first_observed.setdefault(taxid, {
                        "taxon_id": taxid, "name": names[taxid], "intent_date": label,
                        "intent_interval_start": previous_date})
        taxa = {t for t, _, _ in declarations}
        new_declarations = declarations - previous_declarations
        new_taxa = taxa - previous_taxa
        snapshots.append({"date": label, "taxa_with_direct_declarations": len(taxa),
                          "declarations": len(declarations),
                          "new_declarations": len(new_declarations), "new_taxa": len(new_taxa),
                          "kind": "live baseline" if version == "live" else "GoaT archived release"})
        previous_declarations = declarations
        previous_taxa = taxa
        previous_date = label

    # GoAT query results are returned by field; ensure live count matches the existing baseline.
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    live = snapshots[-1]
    if existing.get("snapshots"):
        expected = existing["snapshots"][-1].get("taxa_with_direct_declarations")
        if expected is not None and live["taxa_with_direct_declarations"] != expected:
            raise RuntimeError(f"Live baseline mismatch: API {live['taxa_with_direct_declarations']} != tracker {expected}")
    today = date.today()
    cutoff = today.replace(year=today.year - 4)
    connector_records = []
    lags = []
    status_counts = {"published_after_intent": 0, "published_before_intent": 0,
                     "publication_within_intent_window": 0, "awaiting_release": 0}
    for record in first_observed.values():
        intent = date.fromisoformat(record["intent_date"])
        if intent < cutoff or intent > today:
            continue
        publication = first_release.get(record["name"])
        lag = None
        if publication:
            release_day = date.fromisoformat(publication)
            lag = (release_day - intent).days
        lag_max = ((date.fromisoformat(publication) -
                    date.fromisoformat(record["intent_interval_start"])).days
                   if publication and record.get("intent_interval_start") else None)
        if publication:
            status = ("published_after_intent" if lag >= 0 else
                      "published_before_intent" if lag_max is not None and lag_max < 0 else
                      "publication_within_intent_window")
        else:
            status = "awaiting_release"
        connector_records.append({**record, "intent_interval_end": record["intent_date"],
                                  "publication_date": publication,
                                  "lag_days": lag, "lag_min_days": lag,
                                  "lag_max_days": lag_max, "status": status})
        status_counts[status] += 1
        if status == "published_after_intent":
            lags.append(lag)
    bins = [{"range": label, "count": sum(1 for n in lags if lo <= n < hi)}
            for label, lo, hi in [("0–6 months", 0, 183), ("6–12 months", 183, 365),
                                  ("1–2 years", 365, 730), ("2–5 years", 730, 1825),
                                  ("5+ years", 1825, 10**9)]]
    lag_summary = {"matched_taxa": len(lags),
        "median_days": statistics.median(lags) if lags else None,
        "p25_days": statistics.quantiles(lags, n=4)[0] if len(lags) >= 4 else None,
        "p75_days": statistics.quantiles(lags, n=4)[2] if len(lags) >= 4 else None,
        "bins": bins,
        "definition": "Exact-name match to the Observatory's first qualifying NCBI assembly date. Lags from archived intent use the latest possible observation date, so they are minimum waits; only releases on or after that date are included."}
    timeline = {"archive_start": snapshots[0]["date"],
                "monitoring_started": existing.get("monitoring_started", snapshots[-1]["date"]),
                "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "snapshots": snapshots, "release_lag_summary": lag_summary}
    tmp = TIMELINE_OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(timeline, separators=(",", ":"), sort_keys=True) + "\n")
    tmp.replace(TIMELINE_OUT)
    sorted_records = sorted(connector_records, key=lambda x: (x["intent_date"], x["name"].casefold()))
    connector_state = {"updated_at": timeline["updated_at"],
                       "records": [{k: r[k] for k in ("taxon_id", "name", "intent_date",
                                                          "intent_interval_start")}
                                   for r in sorted_records]}
    CONNECTOR_STATE_OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp_state = CONNECTOR_STATE_OUT.with_suffix(".tmp")
    with gzip.open(tmp_state, "wt", encoding="utf-8") as handle:
        json.dump(connector_state, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    tmp_state.replace(CONNECTOR_STATE_OUT)
    connectors = {"window_start": cutoff.isoformat(), "window_end": today.isoformat(),
                  "updated_at": timeline["updated_at"], "counts": status_counts,
                  "records": [{k: r[k] for k in ("name", "intent_date", "intent_interval_start",
                                                    "intent_interval_end",
                                                    "publication_date", "lag_days",
                                                    "lag_min_days", "lag_max_days")}
                              for r in sorted_records if r["status"] == "published_after_intent"]}
    tmp_connectors = CONNECTORS_OUT.with_suffix(".tmp")
    with gzip.open(tmp_connectors, "wt", encoding="utf-8") as handle:
        json.dump(connectors, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    tmp_connectors.replace(CONNECTORS_OUT)
    print(json.dumps(timeline, indent=2))


if __name__ == "__main__":
    main()
