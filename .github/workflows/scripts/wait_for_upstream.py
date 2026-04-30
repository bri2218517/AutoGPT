"""Wait for upstream workflow runs (by display name) on the given head SHA.

Used by platform-fullstack-ci's preflight job to gate the expensive
big-boi E2E job: only run E2E if every listed upstream workflow has
completed successfully on the same SHA. Outputs ``proceed=true|false``
to ``$GITHUB_OUTPUT`` for downstream ``if:`` conditions.

A workflow that did not trigger for this SHA at all (e.g. excluded by a
``paths`` filter) is treated as a non-blocker — we only block when an
upstream workflow ran and failed.
"""

import os
import sys
import time
from typing import Dict, List, Optional

import requests

REQUEST_TIMEOUT = 15
# Give upstream workflows a moment to register their runs before we
# decide they didn't trigger.
INITIAL_DELAY = 60
POLL_INTERVAL = 30
MAX_WAIT_SECONDS = 90 * 60


def get_env() -> Optional[Dict[str, object]]:
    raw = os.environ.get("UPSTREAM_WORKFLOWS", "")
    workflows = [w.strip() for w in raw.splitlines() if w.strip()]
    if not workflows:
        return None
    return {
        "api": os.environ["GITHUB_API_URL"],
        "repo": os.environ["GITHUB_REPOSITORY"],
        "sha": os.environ["HEAD_SHA"],
        "token": os.environ["GITHUB_TOKEN"],
        "workflows": workflows,
    }


def fetch_runs(env: Dict[str, object], headers: Dict[str, str]) -> List[Dict]:
    runs: List[Dict] = []
    url = (
        f"{env['api']}/repos/{env['repo']}/actions/runs"
        f"?head_sha={env['sha']}&per_page=100"
    )
    while url:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        runs.extend(response.json().get("workflow_runs", []))
        next_url = None
        for part in response.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
                break
        url = next_url
    return runs


def latest_per_workflow(runs: List[Dict], names: List[str]) -> Dict[str, Dict]:
    by_name: Dict[str, Dict] = {}
    name_set = set(names)
    for run in runs:
        name = run.get("name")
        if name not in name_set:
            continue
        prev = by_name.get(name)
        if prev is None or run["run_number"] > prev["run_number"]:
            by_name[name] = run
    return by_name


def write_output(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"{key}={value}\n")
    print(f"output: {key}={value}")


def main() -> None:
    env = get_env()
    if env is None:
        print("No UPSTREAM_WORKFLOWS configured; proceeding.")
        write_output("proceed", "true")
        return

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {env['token']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    print(f"Gating on upstream workflows for SHA {env['sha']}:")
    for w in env["workflows"]:
        print(f"  - {w}")
    print(f"Initial delay {INITIAL_DELAY}s to let upstream runs register...")
    time.sleep(INITIAL_DELAY)

    deadline = time.monotonic() + MAX_WAIT_SECONDS

    while True:
        runs = fetch_runs(env, headers)
        by_name = latest_per_workflow(runs, env["workflows"])

        missing = [w for w in env["workflows"] if w not in by_name]
        in_progress = [
            w for w, r in by_name.items() if r["status"] != "completed"
        ]
        failed = [
            f"{w}={by_name[w]['conclusion']}"
            for w in by_name
            if by_name[w]["status"] == "completed"
            and by_name[w]["conclusion"] not in ("success", "skipped", "neutral")
        ]

        if failed:
            print(f"Upstream failed: {failed}")
            write_output("proceed", "false")
            return

        if not in_progress:
            if missing:
                print(
                    "Workflow(s) did not trigger for this SHA "
                    f"(treating as skipped): {missing}"
                )
            print(f"Upstream passed: {list(by_name.keys())}")
            write_output("proceed", "true")
            return

        if time.monotonic() > deadline:
            print(
                f"Timeout after {MAX_WAIT_SECONDS}s; still in_progress="
                f"{in_progress}"
            )
            write_output("proceed", "false")
            sys.exit(1)

        print(f"Waiting: in_progress={in_progress}, missing={missing}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
