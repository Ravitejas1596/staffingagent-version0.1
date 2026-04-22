"""
Deliver the weekly advisory report as a GitHub Issue.

GitHub automatically sends email notifications to all repository watchers
for new issues — zero external service required.

Requires environment variables:
  GITHUB_TOKEN  — automatically provided by GitHub Actions
  GITHUB_REPOSITORY — automatically provided by GitHub Actions (format: owner/repo)
"""
from __future__ import annotations

import os

import requests

GITHUB_API_BASE = "https://api.github.com"
ISSUE_LABEL = "advisory-board"  # Label applied to all weekly reports for easy filtering


def _get_or_create_label(
    session: requests.Session,
    owner: str,
    repo: str,
) -> None:
    """Ensure the advisory-board label exists in the repo (creates it if missing)."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/labels/{ISSUE_LABEL}"
    response = session.get(url)
    if response.status_code == 404:
        session.post(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/labels",
            json={
                "name": ISSUE_LABEL,
                "color": "0d9488",  # Teal — matches StaffingAgent brand
                "description": "Weekly AI advisory board reports",
            },
        )


def create_github_issue(title: str, body: str) -> str:
    """
    Create a GitHub Issue with the advisory report.

    Returns the URL of the created issue.
    Raises RuntimeError on failure.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")

    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN environment variable not set. "
            "This is automatically available in GitHub Actions."
        )
    if not repository:
        raise RuntimeError(
            "GITHUB_REPOSITORY environment variable not set (expected format: owner/repo). "
            "This is automatically available in GitHub Actions."
        )

    try:
        owner, repo = repository.split("/", 1)
    except ValueError:
        raise RuntimeError(
            f"GITHUB_REPOSITORY format invalid: '{repository}'. Expected 'owner/repo'."
        )

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )

    # Ensure label exists
    try:
        _get_or_create_label(session, owner, repo)
    except Exception:
        pass  # Label creation failure is non-fatal

    # Truncate body if it exceeds GitHub's issue body limit (65,536 chars)
    MAX_BODY = 65000
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY] + "\n\n*[Report truncated — see full output in GitHub Actions run log]*"

    # Create the issue
    response = session.post(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
        json={
            "title": title,
            "body": body,
            "labels": [ISSUE_LABEL],
        },
    )

    if response.status_code == 201:
        return response.json()["html_url"]
    else:
        raise RuntimeError(
            f"GitHub API returned {response.status_code}: {response.text}"
        )
