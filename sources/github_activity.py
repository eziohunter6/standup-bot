"""Pull GitHub commits + PRs the user authored in a given time window."""

import os
from datetime import datetime
from typing import Dict, List

import requests

GRAPHQL_URL = "https://api.github.com/graphql"

CONTRIB_QUERY = """
query($username: String!, $from: DateTime!, $to: DateTime!, $maxRepos: Int!) {
  user(login: $username) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      commitContributionsByRepository(maxRepositories: $maxRepos) {
        repository { nameWithOwner url isPrivate }
        contributions(first: 50) {
          nodes { commitCount occurredAt }
        }
      }
      pullRequestContributions(first: 50) {
        nodes {
          pullRequest {
            title number url state createdAt mergedAt
            repository { nameWithOwner }
            additions deletions
          }
        }
      }
    }
  }
}
"""


def pull_github_activity(start: datetime, end: datetime, max_repos: int = 15) -> List[Dict]:
    token = os.environ["GITHUB_PAT"]
    username = os.environ.get("GITHUB_USERNAME") or _get_username(token)

    resp = requests.post(
        GRAPHQL_URL,
        json={
            "query": CONTRIB_QUERY,
            "variables": {
                "username": username,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "maxRepos": max_repos,
            },
        },
        headers={"Authorization": f"bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GitHub GraphQL: {data['errors']}")

    cc = data["data"]["user"]["contributionsCollection"]
    items: List[Dict] = []

    for rc in cc["commitContributionsByRepository"]:
        repo = rc["repository"]["nameWithOwner"]
        total = sum(n["commitCount"] for n in rc["contributions"]["nodes"])
        if total > 0:
            items.append({
                "type": "commits",
                "repo": repo,
                "count": total,
                "is_private": rc["repository"]["isPrivate"],
                "url": rc["repository"]["url"],
            })

    for pr_node in cc["pullRequestContributions"]["nodes"]:
        p = pr_node["pullRequest"]
        items.append({
            "type": "pr",
            "repo": p["repository"]["nameWithOwner"],
            "number": p["number"],
            "title": p["title"],
            "url": p["url"],
            "state": p["state"],
            "additions": p["additions"],
            "deletions": p["deletions"],
            "merged_at": p.get("mergedAt"),
        })

    return items


def _get_username(token: str) -> str:
    resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["login"]
