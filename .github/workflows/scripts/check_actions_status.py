"""PR status gate.

Triggered via ``workflow_run`` after each upstream CI workflow completes.
Walks every check-run on the head SHA, and — only when all non-self runs
have finished — posts a "Check PR Status" check-run with the aggregate
conclusion. Branch protection should require that check name.

If any check is still in_progress, the script exits without posting; the
next ``workflow_run`` firing (when the next upstream workflow completes)
will re-evaluate.
"""

import os
import sys
import time
from typing import Dict, List, Tuple

import requests

CHECK_NAME = "Check PR Status"
REQUEST_TIMEOUT = 15
# Brief retry to absorb the gap between a workflow finishing and its
# check-runs flipping to "completed" in the API.
SETTLE_RETRIES = 3
SETTLE_DELAY = 10


def get_env() -> Tuple[str, str, str, str]:
    try:
        return (
            os.environ["GITHUB_API_URL"],
            os.environ["GITHUB_REPOSITORY"],
            os.environ["HEAD_SHA"],
            os.environ["GITHUB_TOKEN"],
        )
    except KeyError as e:
        print(f"Error: missing required environment variable: {e}")
        sys.exit(1)


def fetch_check_runs(
    api_url: str, repo: str, sha: str, headers: Dict[str, str]
) -> List[Dict]:
    """Return all check-runs for the SHA, following pagination."""
    runs: List[Dict] = []
    url = f"{api_url}/repos/{repo}/commits/{sha}/check-runs?per_page=100"
    while url:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        runs.extend(response.json().get("check_runs", []))
        next_url = None
        for part in response.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
                break
        url = next_url
    return runs


def evaluate(check_runs: List[Dict]) -> Tuple[bool, bool, List[str]]:
    """Return (all_done, all_passed, failures)."""
    all_done = True
    all_passed = True
    failures: List[str] = []
    for run in check_runs:
        if run["name"] == CHECK_NAME:
            continue
        if run["status"] != "completed":
            all_done = False
            print(f"  pending: {run['name']} ({run['status']})")
            continue
        if run["conclusion"] not in ("success", "skipped", "neutral"):
            all_passed = False
            failures.append(f"{run['name']} ({run['conclusion']})")
            print(f"  failed:  {run['name']} -> {run['conclusion']}")
    return all_done, all_passed, failures


def post_check_run(
    api_url: str,
    repo: str,
    sha: str,
    headers: Dict[str, str],
    conclusion: str,
    summary: str,
) -> None:
    url = f"{api_url}/repos/{repo}/check-runs"
    body = {
        "name": CHECK_NAME,
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {"title": f"PR Status: {conclusion}", "summary": summary},
    }
    response = requests.post(
        url, headers=headers, json=body, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    print(f"Posted check-run '{CHECK_NAME}' = {conclusion} for {sha}")


def main() -> None:
    api_url, repo, sha, token = get_env()
    triggering = os.environ.get("TRIGGERING_WORKFLOW", "(unknown)")
    print(f"Gate evaluation for {sha} (triggered by: {triggering})")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    all_done = False
    all_passed = False
    failures: List[str] = []
    for attempt in range(SETTLE_RETRIES):
        runs = fetch_check_runs(api_url, repo, sha, headers)
        all_done, all_passed, failures = evaluate(runs)
        if all_done:
            break
        if attempt < SETTLE_RETRIES - 1:
            print(
                f"Some checks still in progress; retrying in {SETTLE_DELAY}s "
                f"(attempt {attempt + 1}/{SETTLE_RETRIES})"
            )
            time.sleep(SETTLE_DELAY)

    if not all_done:
        print(
            "Upstream checks still in progress. Skipping final report; "
            "the next workflow_run firing will re-evaluate."
        )
        return

    if all_passed:
        post_check_run(
            api_url, repo, sha, headers, "success", "All upstream checks passed."
        )
    else:
        summary = "Failed checks:\n" + "\n".join(f"- {f}" for f in failures)
        post_check_run(api_url, repo, sha, headers, "failure", summary)
        sys.exit(1)


if __name__ == "__main__":
    main()
