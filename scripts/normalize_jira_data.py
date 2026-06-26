#!/usr/bin/env python3
"""Normalize downloaded Jira issue JSON into the assignment data structure."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_issue_list(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = load_json(path)
    project = payload.get("project") or "Yarn"
    issues = payload.get("issues") or []
    if not issues:
        raise ValueError(f"No issues found in {path}")
    return project, issues


def load_bot_names(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"Could not find bot-name list in {path}")

    names = json.loads(text[start : end + 1])
    return {normalize_name(name) for name in names if normalize_name(name)}


def normalize_name(value: Any) -> str:
    return str(value or "").strip().lower()


def jira_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("name")
    return None


def jira_list_names(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    names = []
    for value in values:
        if isinstance(value, dict):
            name = value.get("name")
            if name:
                names.append(name)
        elif value:
            names.append(str(value))
    return names


def normalize_parent(parent: Any) -> dict[str, Any] | None:
    if not isinstance(parent, dict):
        return None
    parent_fields = parent.get("fields") or {}
    return {
        "id": parent.get("id"),
        "key": parent.get("key"),
        "summary": parent_fields.get("summary"),
    }


def comment_developer(author: dict[str, Any]) -> str | None:
    return author.get("displayName") or author.get("name") or author.get("key")


def is_bot_author(author: dict[str, Any], bot_names: set[str]) -> bool:
    candidates = [
        author.get("displayName"),
        author.get("name"),
        author.get("key"),
        author.get("emailAddress"),
    ]
    return any(normalize_name(candidate) in bot_names for candidate in candidates)


def normalize_comments(comments: list[dict[str, Any]], bot_names: set[str]) -> list[dict[str, Any]]:
    normalized = []
    for comment in comments:
        author = comment.get("author") or {}
        normalized.append(
            {
                "date": comment.get("created"),
                "developer": comment_developer(author),
                "is_bot": is_bot_author(author, bot_names),
            }
        )
    return normalized


def normalize_attachments(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "date": attachment.get("created"),
            "file": attachment.get("filename"),
        }
        for attachment in attachments
    ]


def normalize_issue(
    issue_entry: dict[str, Any],
    raw_dir: Path,
    bot_names: set[str],
) -> dict[str, Any]:
    issue_key = issue_entry["key"]
    raw_path = raw_dir / f"{issue_key}.json"
    raw = load_json(raw_path)
    jira_issue = raw["issue_response"]
    fields = jira_issue.get("fields") or {}
    comments = normalize_comments(
        raw.get("comments_response", {}).get("comments") or [],
        bot_names,
    )
    attachments = normalize_attachments(fields.get("attachment") or [])
    bot_comment_count = sum(comment["is_bot"] for comment in comments)

    return {
        "id": jira_issue.get("id"),
        "key": jira_issue.get("key") or issue_key,
        "votes": (fields.get("votes") or {}).get("votes", 0),
        "parent": normalize_parent(fields.get("parent")),
        "summary": fields.get("summary") or "",
        "description": fields.get("description") or "",
        "fields": {
            "issue_type": jira_name(fields.get("issuetype")),
            "status": jira_name(fields.get("status")),
            "priority": jira_name(fields.get("priority")),
            "resolution": jira_name(fields.get("resolution")),
            "labels": fields.get("labels") or [],
            "components": jira_list_names(fields.get("components")),
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "number_of_comments": len(comments),
            "number_of_bot_comments": bot_comment_count,
            "number_of_non_bot_comments": len(comments) - bot_comment_count,
            "number_of_attachments": len(attachments),
        },
        "comments": comments,
        "attachments": attachments,
        "design_decisions": issue_entry["design_decisions"],
    }


def summarize(issues: list[dict[str, Any]]) -> dict[str, Any]:
    issue_types = Counter(issue["fields"]["issue_type"] for issue in issues)
    statuses = Counter(issue["fields"]["status"] for issue in issues)
    return {
        "issue_count": len(issues),
        "issues_with_parent": sum(issue["parent"] is not None for issue in issues),
        "total_comments": sum(issue["fields"]["number_of_comments"] for issue in issues),
        "total_bot_comments": sum(issue["fields"]["number_of_bot_comments"] for issue in issues),
        "total_non_bot_comments": sum(issue["fields"]["number_of_non_bot_comments"] for issue in issues),
        "total_attachments": sum(issue["fields"]["number_of_attachments"] for issue in issues),
        "missing_descriptions": sum(not issue["description"] for issue in issues),
        "issue_types": issue_types.most_common(),
        "statuses": statuses.most_common(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-list",
        type=Path,
        default=Path("data/normalized/yarn_issue_list.json"),
        help="Parsed issue-list JSON created by parse_issue_list.py.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw/jira"),
        help="Directory containing downloaded raw Jira JSON files.",
    )
    parser.add_argument(
        "--bot-comments",
        type=Path,
        default=Path("data/input/Bot Comments.rtf"),
        help="RTF file containing bot account names.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/normalized/yarn_issues_normalized.json"),
        help="Normalized project JSON output path.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("reports/week1/yarn_normalization_summary.json"),
        help="Small summary report output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project, issue_entries = load_issue_list(args.issue_list)
    bot_names = load_bot_names(args.bot_comments)

    missing_raw_files = [
        issue["key"]
        for issue in issue_entries
        if not (args.raw_dir / f"{issue['key']}.json").exists()
    ]
    if missing_raw_files:
        preview = ", ".join(missing_raw_files[:10])
        raise FileNotFoundError(
            f"Missing {len(missing_raw_files)} raw Jira files in {args.raw_dir}: {preview}"
        )

    normalized_issues = [
        normalize_issue(issue_entry, args.raw_dir, bot_names)
        for issue_entry in issue_entries
    ]
    payload = {
        "project": project,
        "generated_at": now_iso(),
        "source_issue_list": str(args.issue_list),
        "source_raw_dir": str(args.raw_dir),
        "source_bot_comments": str(args.bot_comments),
        "bot_name_count": len(bot_names),
        "issue_count": len(normalized_issues),
        "issues": normalized_issues,
    }
    summary = summarize(normalized_issues)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Normalized {len(normalized_issues)} {project} issues")
    print(f"Marked bot comments using {len(bot_names)} bot account names")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.summary_output}")
    print(f"Summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
