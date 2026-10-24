#!/usr/bin/env python3
"""Track first-observed direct GoaT sample/work declarations across daily runs."""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "goat_intent_history.json"
API = "https://goat.genomehubs.org/api/v2/search?"
FIELDS = ("sample_collected", "sample_acquired", "in_progress")
PAGE_SIZE = 30000


def request(query):
    params = {"query": query, "result": "taxon", "taxonomy": "ncbi",
              "size": PAGE_SIZE,
              "fields": ",".join((*FIELDS, "scientific_name"))}
    url = API + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    req = urllib.request.Request(url, headers={"User-Agent": "GenomeObservatoryLive/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.load(response)
    if not data.get("status", {}).get("success"):
        raise RuntimeError(f"GoaT query failed for {query}: {data.get('status')}")
    return data


def fetch_current():
    taxa = {}
    for field in FIELDS:
        data = request(field)
        hits = data.get("status", {}).get("hits", 0)
        results = data.get("results", [])
        if hits >= PAGE_SIZE or len(results) != hits:
            raise RuntimeError(f"Incomplete GoaT response for {field}: {len(results)} of {hits}; refusing partial snapshot")
        for row in results:
            result = row.get("result", {})
            taxid = str(result.get("taxon_id", ""))
            if not taxid:
                continue
            entry = taxa.setdefault(taxid, {"taxon_id": taxid,
                "name": result.get("scientific_name", ""), "declarations": {}})
            for key in FIELDS:
                value = result.get("fields", {}).get(key)
                if value and value.get("aggregation_source") == "direct":
                    values = value.get("value", [])
                    if not isinstance(values, list):
                        values = [values]
                    entry["declarations"][key] = sorted({str(v) for v in values if v})
    return taxa


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    current = fetch_current()
    old = json.loads(OUT.read_text()) if OUT.exists() else None
    if old is None:
        # First run establishes a baseline; it must not mislabel existing records as new.
        records = {}
        for k, v in current.items():
            event_dates = {f"{field}::{project}": today
                           for field, values in v["declarations"].items() for project in values}
            records[k] = {**v, "first_observed": today, "event_first_seen": event_dates}
        history = {"schema_version": 1, "monitoring_started": today,
                   "updated_at": datetime.now(timezone.utc).isoformat(),
                   "baseline_only": True, "snapshots": [{"date": today,
                   "taxa_with_direct_declarations": len(current), "new_declarations": 0}],
                   "records": records}
    else:
        records = old.get("records", {})
        new_count = 0
        for taxid, now in current.items():
            prev = records.get(taxid)
            if prev is None:
                records[taxid] = {**now, "first_observed": today}
                new_count += sum(len(v) for v in now["declarations"].values())
                continue
            prev_decls = prev.setdefault("declarations", {})
            event_dates = prev.setdefault("event_first_seen", {})
            for field, values in now["declarations"].items():
                for project in values:
                    event_key = f"{field}::{project}"
                    if event_key not in event_dates:
                        event_dates[event_key] = today
                        new_count += 1
                prev_decls[field] = sorted(set(prev_decls.get(field, [])) | set(values))
            # Backfill the one-time baseline created before event-level dates were added.
            baseline = old.get("monitoring_started", today)
            for field, values in prev_decls.items():
                for project in values:
                    event_dates.setdefault(f"{field}::{project}", baseline)
            prev["name"] = now["name"] or prev.get("name", "")
        snaps = old.get("snapshots", [])
        if not snaps or snaps[-1].get("date") != today:
            snaps.append({"date": today, "taxa_with_direct_declarations": len(current),
                          "new_declarations": new_count})
        history = {"schema_version": 1, "monitoring_started": old.get("monitoring_started", today),
                   "updated_at": datetime.now(timezone.utc).isoformat(),
                   "baseline_only": False, "snapshots": snaps, "records": records}
    # Join exact scientific names against the observatory's first-release history.
    # This is deliberately conservative: unmatched synonyms remain unmatched.
    dashboard_path = ROOT / "data" / "dashboard.json"
    if dashboard_path.exists():
        first_release = json.loads(dashboard_path.read_text()).get("species_first_seen", {})
        for record in history["records"].values():
            date = first_release.get(record.get("name", ""))
            record["first_qualifying_release"] = date
            delays = {}
            for event_key, observed in record.get("event_first_seen", {}).items():
                delays[event_key] = ((datetime.fromisoformat(date).date() -
                    datetime.fromisoformat(observed).date()).days
                    if date and observed and date >= observed else None)
            record["release_delays"] = delays
    temp = OUT.with_suffix(".tmp")
    temp.write_text(json.dumps(history, separators=(",", ":"), sort_keys=True) + "\n")
    temp.replace(OUT)
    print(f"GoaT direct-intent taxa: {len(current)}; snapshots: {len(history['snapshots'])}")


if __name__ == "__main__":
    main()
