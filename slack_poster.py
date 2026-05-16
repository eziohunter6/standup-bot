"""Post a composed standup to a Slack channel via incoming webhook."""

from datetime import datetime
from typing import Dict

import requests


def post_to_slack(standup: str, activity: Dict, webhook_url: str) -> None:
    stats = _stats_line(activity)
    today = datetime.now().strftime("%A, %b %d")

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Standup", "emoji": False},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"_{today}_  ·  {stats}"}
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": standup},
            },
        ]
    }

    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()


def _stats_line(activity: Dict) -> str:
    bits = []
    gh = activity.get("github", [])
    gh_commits = sum(c["count"] for c in gh if c["type"] == "commits")
    gh_prs = sum(1 for c in gh if c["type"] == "pr")
    if gh_commits:
        bits.append(f"{gh_commits} commit{'s' if gh_commits != 1 else ''}")
    if gh_prs:
        bits.append(f"{gh_prs} PR{'s' if gh_prs != 1 else ''}")
    if activity.get("figma"):
        n = len(activity["figma"])
        bits.append(f"{n} Figma file{'s' if n != 1 else ''}")
    if activity.get("calendar"):
        n = len(activity["calendar"])
        bits.append(f"{n} meeting{'s' if n != 1 else ''}")
    return " · ".join(bits) if bits else "quiet day"
