#!/usr/bin/env python3
"""Download raw Jira issue data for the assignment issue list."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JIRA_BASE_URL = "https://issues.apache.org/jira/rest/api/2"
ISSUE_FIELDS = [
    "id",
    "key",
    "summary",
    "description",
    "parent",
    "votes",
    "comment",
    "attachment",
    "issuetype",
    "status",
    "priority",
    "resolution",
    "labels",
    "components",
    "created",
    "updated",
    "issuelinks",
    "subtasks",
]
USER_AGENT = "DSSE-Assignment-3-Downloader/1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_issue_keys(issue_list_path: Path) -> list[str]:
    payload = json.loads(issue_list_path.read_text(encoding="utf-8"))
    issues = payload.get("issues", [])
    keys = [issue["key"] for issue in issues if issue.get("key")]
    if not keys:
        raise ValueError(f"No issue keys found in {issue_list_path}")
    return keys


def build_url(path: str, params: dict[str, Any]) -> str:
    query = urllib.parse.urlencode(params)
    return f"{JIRA_BASE_URL}{path}?{query}"


def request_json(url: str, retries: int, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset))
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in {429, 500, 502, 503, 504} and attempt < retries:
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(30, 2 ** attempt)
                time.sleep(delay)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(min(30, 2 ** attempt))
                continue
            raise
    raise RuntimeError(f"Request failed after retries: {url}") from last_error


def fetch_comments(issue_key: str, retries: int, timeout: int) -> dict[str, Any]:
    all_comments: list[dict[str, Any]] = []
    start_at = 0
    max_results = 100
    total: int | None = None
    pages: list[dict[str, Any]] = []

    while total is None or start_at < total:
        url = build_url(
            f"/issue/{urllib.parse.quote(issue_key)}/comment",
            {"startAt": start_at, "maxResults": max_results},
        )
        page = request_json(url, retries=retries, timeout=timeout)
        comments = page.get("comments", [])
        all_comments.extend(comments)
        pages.append(
            {
                "url": url,
                "startAt": page.get("startAt"),
                "maxResults": page.get("maxResults"),
                "total": page.get("total"),
                "returned": len(comments),
            }
        )
        total = page.get("total", len(all_comments))
        if not comments:
            break
        start_at += len(comments)

    return {
        "total": total if total is not None else len(all_comments),
        "comments": all_comments,
        "pages": pages,
    }


def output_is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return "issue_response" in payload and "comments_response" in payload


def fetch_issue(issue_key: str, retries: int, timeout: int) -> tuple[str, dict[str, Any]]:
    url = build_url(
        f"/issue/{urllib.parse.quote(issue_key)}",
        {"fields": ",".join(ISSUE_FIELDS)},
    )
    return url, request_json(url, retries=retries, timeout=timeout)


def download_issue(
    issue_key: str,
    output_dir: Path,
    retries: int,
    timeout: int,
    force: bool,
) -> str:
    output_path = output_dir / f"{issue_key}.json"
    if not force and output_is_complete(output_path):
        return "skipped"

    issue_url, issue_response = fetch_issue(issue_key, retries=retries, timeout=timeout)
    comments_response = fetch_comments(issue_key, retries=retries, timeout=timeout)

    payload = {
        "downloaded_at": now_iso(),
        "source": "Apache Jira REST API v2",
        "issue_key": issue_key,
        "issue_url": issue_url,
        "requested_fields": ISSUE_FIELDS,
        "issue_response": issue_response,
        "comments_response": comments_response,
    }
    tmp_path = output_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(output_path)
    return "downloaded"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-list",
        type=Path,
        default=Path("data/normalized/yarn_issue_list.json"),
        help="Parsed issue-list JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/jira"),
        help="Directory for one raw JSON file per Jira issue.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only download N issues.")
    parser.add_argument("--sleep", type=float, default=0.05, help="Pause between issues.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=4, help="Retries per HTTP request.")
    parser.add_argument("--force", action="store_true", help="Re-download existing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issue_keys = load_issue_keys(args.issue_list)
    if args.limit is not None:
        issue_keys = issue_keys[: args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = args.output_dir / "_download_manifest.jsonl"
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}

    print(f"Downloading {len(issue_keys)} Jira issues into {args.output_dir}", flush=True)
    for index, issue_key in enumerate(issue_keys, start=1):
        try:
            status = download_issue(
                issue_key=issue_key,
                output_dir=args.output_dir,
                retries=args.retries,
                timeout=args.timeout,
                force=args.force,
            )
            counts[status] += 1
            print(f"[{index}/{len(issue_keys)}] {issue_key}: {status}", flush=True)
            manifest_record = {
                "timestamp": now_iso(),
                "issue_key": issue_key,
                "status": status,
            }
        except Exception as error:  # keep going so one bad issue does not stop the batch
            counts["failed"] += 1
            print(f"[{index}/{len(issue_keys)}] {issue_key}: failed: {error}", file=sys.stderr, flush=True)
            manifest_record = {
                "timestamp": now_iso(),
                "issue_key": issue_key,
                "status": "failed",
                "error": repr(error),
            }

        with manifest_path.open("a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(manifest_record) + "\n")
        if args.sleep:
            time.sleep(args.sleep)

    print(f"Done: {counts}", flush=True)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
