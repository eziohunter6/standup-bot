"""Pull Figma files edited in a given time window.

Limitation: Figma's API surfaces team/project file activity, not per-user edit
attribution. Returned items are files in your teams that were modified in the
window — high signal but not personally attributed.
"""

import os
from datetime import datetime
from typing import Dict, List

import requests

API = "https://api.figma.com/v1"


def pull_figma_activity(start: datetime, end: datetime) -> List[Dict]:
    token = os.environ["FIGMA_TOKEN"]
    team_ids = [t.strip() for t in os.environ.get("FIGMA_TEAM_IDS", "").split(",") if t.strip()]
    if not team_ids:
        return []

    headers = {"X-Figma-Token": token}
    items: List[Dict] = []
    seen_keys = set()

    for team_id in team_ids:
        projects_resp = requests.get(f"{API}/teams/{team_id}/projects", headers=headers, timeout=15)
        if projects_resp.status_code != 200:
            continue

        for project in projects_resp.json().get("projects", []):
            files_resp = requests.get(
                f"{API}/projects/{project['id']}/files", headers=headers, timeout=15
            )
            if files_resp.status_code != 200:
                continue

            for f in files_resp.json().get("files", []):
                if f["key"] in seen_keys:
                    continue
                try:
                    last_mod = datetime.fromisoformat(f["last_modified"].replace("Z", "+00:00"))
                except (KeyError, ValueError):
                    continue
                if start <= last_mod < end:
                    seen_keys.add(f["key"])
                    items.append({
                        "type": "file_edited",
                        "name": f["name"],
                        "project": project["name"],
                        "key": f["key"],
                        "last_modified": f["last_modified"],
                        "url": f"https://figma.com/file/{f['key']}",
                    })

    return items
