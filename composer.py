"""Compose a PM-style standup from collected activity.

Picks an LLM provider based on env:
  ANTHROPIC_API_KEY → Claude    (preferred when set; pay-per-token)
  GEMINI_API_KEY    → Gemini    (free tier, generous limits, no card required)
"""

import os
from typing import Dict

SYSTEM = """You write daily standup updates for a senior product designer.

Output format — Slack mrkdwn (note: *single asterisk* for bold, not **double**):

*Yesterday*
- Bullet per logical chunk of work, grouped by theme not source
- Mention the artifact ("shipped X review screen", "merged auth refactor PR")
- Skip duplicates across sources (don't list a commit AND its PR separately)

*Today*
- Plausible next steps based on yesterday's trajectory
- Tasks that follow naturally from yesterday's work or open PRs

*Blockers*
- Only include if there's real signal. If nothing's stuck, omit this section entirely.

Tone: matter-of-fact, no filler, no hype. Crisp PM voice.
Keep total length under 180 words. If activity is thin, say so honestly — never pad."""


def compose_standup(activity: Dict, cfg: Dict) -> str:
    activity_text = _format_activity(activity)
    user_prompt = (
        f"Yesterday's activity (raw, deduplicated):\n\n{activity_text}\n\n"
        "Write today's standup."
    )

    if os.getenv("ANTHROPIC_API_KEY"):
        return _compose_anthropic(user_prompt, cfg)
    if os.getenv("GEMINI_API_KEY"):
        return _compose_gemini(user_prompt, cfg)
    raise RuntimeError("Set ANTHROPIC_API_KEY or GEMINI_API_KEY")


def _compose_anthropic(user_prompt: str, cfg: Dict) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=cfg.get("anthropic_model", "claude-haiku-4-5-20251001"),
        max_tokens=cfg.get("max_tokens", 600),
        system=SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return resp.content[0].text.strip()


def _compose_gemini(user_prompt: str, cfg: Dict) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=cfg.get("gemini_model", "gemini-2.5-flash"),
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            max_output_tokens=cfg.get("max_tokens", 1500),
            temperature=0.4,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (resp.text or "").strip()


def _format_activity(activity: Dict) -> str:
    sections = []

    gh = activity.get("github", [])
    if gh:
        lines = ["GITHUB:"]
        for item in gh:
            if item["type"] == "commits":
                privacy = " (private)" if item.get("is_private") else ""
                lines.append(f"  - {item['count']} commits to {item['repo']}{privacy}")
            elif item["type"] == "pr":
                state = item["state"].lower()
                size = f" (+{item.get('additions', 0)}/-{item.get('deletions', 0)})"
                lines.append(f"  - PR {state}: {item['repo']}#{item['number']} '{item['title']}'{size}")
        sections.append("\n".join(lines))

    fg = activity.get("figma", [])
    if fg:
        lines = ["FIGMA:"]
        for item in fg:
            lines.append(f"  - Edited '{item['name']}' in {item['project']}")
        sections.append("\n".join(lines))

    cal = activity.get("calendar", [])
    if cal:
        total_meeting_min = sum(c.get("duration_min") or 0 for c in cal)
        lines = [f"MEETINGS ({len(cal)} total, {total_meeting_min}min):"]
        for item in cal:
            dur = f" ({item['duration_min']}min)" if item.get("duration_min") else ""
            org = " [organized]" if item.get("self_organized") else ""
            lines.append(f"  - {item['summary']}{dur}{org}")
        sections.append("\n".join(lines))

    if not sections:
        return "(no recorded activity across any source)"
    return "\n\n".join(sections)
