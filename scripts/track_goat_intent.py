#!/usr/bin/env python3
"""Track first-observed direct GoaT sample/work declarations across daily runs."""
import json
import gzip
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from datetime import date as calendar_date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "goat_intent_history.json"
TIMELINE_OUT = ROOT / "data" / "goat_intent_timeline.json"
CONNECTORS_OUT = ROOT / "data" / "goat_intent_connectors.json.gz"
CONNECTOR_STATE_OUT = ROOT / "cache" / "goat_intent_connector_state.json.gz"
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
    saved_timeline = json.loads(TIMELINE_OUT.read_text()) if TIMELINE_OUT.exists() else {}
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
                   "taxa_with_direct_declarations": len(current),
                   "declarations": sum(len(v) for x in current.values() for v in x["declarations"].values()),
                   "new_taxa": 0, "new_declarations": 0}],
                   "records": records}
    else:
        records = old.get("records", {})
        new_count = 0
        new_taxa = 0
        for taxid, now in current.items():
            prev = records.get(taxid)
            if prev is None:
                records[taxid] = {**now, "first_observed": today}
                records[taxid]["event_first_seen"] = {f"{field}::{project}": today
                    for field, values in now["declarations"].items() for project in values}
                new_taxa += 1
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
        snaps = saved_timeline.get("snapshots", old.get("snapshots", []))
        if not snaps or snaps[-1].get("date") != today:
            snaps.append({"date": today, "taxa_with_direct_declarations": len(current),
                          "declarations": sum(len(v) for x in current.values() for v in x["declarations"].values()),
                          "new_taxa": new_taxa, "new_declarations": new_count,
                          "kind": "daily live capture"})
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
    if old is None:
        snapshots = history["snapshots"]
    else:
        snapshots = saved_timeline.get("snapshots", history["snapshots"])
    timeline = {"archive_start": saved_timeline.get("archive_start", snapshots[0]["date"]),
                "monitoring_started": history.get("monitoring_started", today),
                "updated_at": history["updated_at"], "snapshots": snapshots,
                "release_lag_summary": saved_timeline.get("release_lag_summary", {})}
    tmp_timeline = TIMELINE_OUT.with_suffix(".tmp")
    tmp_timeline.write_text(json.dumps(timeline, separators=(",", ":"), sort_keys=True) + "\n")
    tmp_timeline.replace(TIMELINE_OUT)
    # Keep the small, plot-ready cohort separate from the full tracker history.
    # Archived rows retain their earliest checkpoint date; daily-only taxa start today.
    if CONNECTOR_STATE_OUT.exists():
        with gzip.open(CONNECTOR_STATE_OUT, "rt", encoding="utf-8") as handle:
            prior_connectors = json.load(handle)
    else:
        prior_connectors = {}
    connector_records = {str(row["taxon_id"]): row
                        for row in prior_connectors.get("records", [])}
    releases = first_release if dashboard_path.exists() else {}
    for taxid, record in current.items():
        if taxid not in connector_records:
            connector_records[taxid] = {"taxon_id": taxid, "name": record.get("name", ""),
                                        "intent_date": today}
    cutoff = calendar_date.fromisoformat(today).replace(
        year=calendar_date.fromisoformat(today).year - 4)
    end = calendar_date.fromisoformat(today)
    plotted = []
    counts = {"published_after_intent": 0, "published_before_intent": 0,
              "awaiting_release": 0}
    for record in connector_records.values():
        intent = calendar_date.fromisoformat(record["intent_date"])
        if intent < cutoff or intent > end:
            continue
        publication = releases.get(record.get("name", ""))
        lag = ((calendar_date.fromisoformat(publication) - intent).days
               if publication else None)
        status = ("awaiting_release" if publication is None else
                  "published_after_intent" if lag >= 0 else "published_before_intent")
        counts[status] += 1
        plotted.append({**record, "publication_date": publication,
                        "lag_days": lag, "status": status})
    sorted_records = sorted(plotted, key=lambda x: (x["intent_date"], x["name"].casefold()))
    state = {"updated_at": history["updated_at"],
             "records": [{k: r[k] for k in ("taxon_id", "name", "intent_date")}
                         for r in sorted(connector_records.values(),
                                         key=lambda x: (x["intent_date"], x["name"].casefold()))]}
    CONNECTOR_STATE_OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp_state = CONNECTOR_STATE_OUT.with_suffix(".tmp")
    with gzip.open(tmp_state, "wt", encoding="utf-8") as handle:
        json.dump(state, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    tmp_state.replace(CONNECTOR_STATE_OUT)
    connectors = {"window_start": cutoff.isoformat(), "window_end": today,
                  "updated_at": history["updated_at"], "counts": counts,
                  "records": [{k: r[k] for k in ("name", "intent_date", "publication_date", "lag_days")}
                              for r in sorted_records if r["status"] == "published_after_intent"]}
    tmp_connectors = CONNECTORS_OUT.with_suffix(".tmp")
    with gzip.open(tmp_connectors, "wt", encoding="utf-8") as handle:
        json.dump(connectors, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    tmp_connectors.replace(CONNECTORS_OUT)
    print(f"GoaT direct-intent taxa: {len(current)}; snapshots: {len(history['snapshots'])}")


if __name__ == "__main__":
    main()
