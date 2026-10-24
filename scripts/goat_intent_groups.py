"""Mutually-exclusive cohort labels for the GoaT intent comparison."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = json.loads((ROOT / "data" / "goat_intent_project_groups.json").read_text())
CONSORTIA = {x.upper() for x in GROUPS["consortia"]}
INSTITUTIONAL = {x.upper() for x in GROUPS["institutional_programmes"]}


def classify_intent_projects(projects):
    """Classify first-observed direct tags; uncertain and mixed records stay unassigned."""
    tags = {str(x).strip().upper() for x in (projects or []) if str(x).strip()}
    if not tags:
        return "unclassified"
    if tags <= CONSORTIA:
        return "consortia"
    if len(tags) == 1 and not (tags & CONSORTIA) and not (tags & INSTITUTIONAL):
        return "small_groups_proxy"
    return "unclassified"
