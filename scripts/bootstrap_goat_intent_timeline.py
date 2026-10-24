#!/usr/bin/env python3
"""Add archived GoaT release checkpoints and release-lag summaries to tracker data."""
import json
import statistics
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "goat_intent_history.json"
TIMELINE_OUT = ROOT / "data" / "goat_intent_timeline.json"
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
    delays = []
    previous_declarations = set()
    previous_taxa = set()
    for version in versions:
        daily = collected[version]
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
                declarations.update((taxid, field, str(v)) for v in vals if v)
        label = date.today().isoformat() if version == "live" else version.replace(".", "-")
        taxa = {t for t, _, _ in declarations}
        new_declarations = declarations - previous_declarations
        new_taxa = taxa - previous_taxa
        for taxid in new_taxa:
            name = names.get(taxid, "")
            first_observed[taxid] = (name, label)
            release = first_release.get(name)
            if release and release >= label:
                days = (date.fromisoformat(release) - date.fromisoformat(label)).days
                delays.append(days)
        snapshots.append({"date": label, "taxa_with_direct_declarations": len(taxa),
                          "declarations": len(declarations),
                          "new_declarations": len(new_declarations), "new_taxa": len(new_taxa),
                          "kind": "live baseline" if version == "live" else "GoaT archived release"})
        previous_declarations = declarations
        previous_taxa = taxa

    # GoAT query results are returned by field; ensure live count matches the existing baseline.
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    live = snapshots[-1]
    if existing.get("snapshots"):
        expected = existing["snapshots"][-1].get("taxa_with_direct_declarations")
        if expected is not None and live["taxa_with_direct_declarations"] != expected:
            raise RuntimeError(f"Live baseline mismatch: API {live['taxa_with_direct_declarations']} != tracker {expected}")
    bins = [{"range": label, "count": sum(1 for n in delays if lo <= n < hi)}
            for label, lo, hi in [("0–6 months", 0, 183), ("6–12 months", 183, 365),
                                  ("1–2 years", 365, 730), ("2–5 years", 730, 1825),
                                  ("5+ years", 1825, 10**9)]]
    lag_summary = {"matched_taxa": len(delays),
        "median_days": statistics.median(delays) if delays else None,
        "p25_days": statistics.quantiles(delays, n=4)[0] if len(delays) >= 4 else None,
        "p75_days": statistics.quantiles(delays, n=4)[2] if len(delays) >= 4 else None,
        "bins": bins,
        "definition": "Exact-name match to the Observatory's first qualifying NCBI assembly date; only releases on or after first observed archived intent are included."}
    timeline = {"archive_start": snapshots[0]["date"],
                "monitoring_started": existing.get("monitoring_started", snapshots[-1]["date"]),
                "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "snapshots": snapshots, "release_lag_summary": lag_summary}
    tmp = TIMELINE_OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(timeline, separators=(",", ":"), sort_keys=True) + "\n")
    tmp.replace(TIMELINE_OUT)
    print(json.dumps(timeline, indent=2))


if __name__ == "__main__":
    main()
