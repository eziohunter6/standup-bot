#!/usr/bin/env python3
"""standup-bot — generate a daily standup from GitHub, Figma, and Calendar.

Usage:
    python standup.py                    # generate + post to Slack
    python standup.py --dry-run          # generate + print, no Slack post
    python standup.py --out latest.json  # also write structured JSON
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from composer import compose_standup
from slack_poster import post_to_slack
from sources.calendar_activity import pull_calendar_activity
from sources.figma_activity import pull_figma_activity
from sources.github_activity import pull_github_activity


def yesterday_window(now: datetime) -> tuple:
    """Return the [start, end) window 'yesterday' should cover.

    Monday extends back over Fri/Sat/Sun so weekend gap doesn't produce
    a thin standup.
    """
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now.weekday() == 0:
        start = today_midnight - timedelta(days=3)
    else:
        start = today_midnight - timedelta(days=1)
    return start, today_midnight


def main() -> int:
    parser = argparse.ArgumentParser(description="standup-bot")
    parser.add_argument("--dry-run", action="store_true", help="don't post to Slack")
    parser.add_argument("--config", default=os.getenv("STANDUP_CONFIG", "config.yaml"))
    parser.add_argument("--out", help="also write the standup + activity JSON to this path")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    now = datetime.now(timezone.utc)
    start, end = yesterday_window(now)
    print(f"standup-bot — window: {start.isoformat()} → {end.isoformat()}")

    activity = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "github": [],
        "figma": [],
        "calendar": [],
    }

    if os.getenv("GITHUB_PAT"):
        try:
            activity["github"] = pull_github_activity(start, end, cfg.get("github_max_repos", 15))
            print(f"  GitHub:   {len(activity['github'])} items")
        except Exception as exc:
            print(f"  GitHub:   ERROR {exc}", file=sys.stderr)

    if os.getenv("FIGMA_TOKEN"):
        try:
            activity["figma"] = pull_figma_activity(start, end)
            print(f"  Figma:    {len(activity['figma'])} items")
        except Exception as exc:
            print(f"  Figma:    ERROR {exc}", file=sys.stderr)

    if os.getenv("GOOGLE_OAUTH_TOKEN_JSON") or Path("token.json").exists():
        try:
            activity["calendar"] = pull_calendar_activity(
                start, end, ignore_patterns=cfg.get("calendar_ignore", [])
            )
            print(f"  Calendar: {len(activity['calendar'])} events")
        except Exception as exc:
            print(f"  Calendar: ERROR {exc}", file=sys.stderr)

    have_llm = os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY")
    if have_llm:
        standup = compose_standup(activity, cfg)
        print("\n--- standup ---")
        print(standup)
        print("---------------\n")
    else:
        standup = None
        print("\n(no LLM key set — set ANTHROPIC_API_KEY or GEMINI_API_KEY)")
        print("Raw activity preview:")
        for src in ("github", "figma", "calendar"):
            items = activity.get(src) or []
            print(f"  {src}: {len(items)} item(s)")
            for it in items[:5]:
                print(f"    · {json.dumps(it, default=str)[:140]}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "generated_at": now.isoformat(),
            "activity": activity,
            "standup": standup,
        }, indent=2))
        print(f"Wrote {args.out}")

    if not args.dry_run and standup is not None:
        webhook = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook:
            print("SLACK_WEBHOOK_URL not set — skipping Slack post", file=sys.stderr)
        else:
            post_to_slack(standup, activity, webhook)
            print("Posted to Slack ✓")

    return 0


if __name__ == "__main__":
    sys.exit(main())
