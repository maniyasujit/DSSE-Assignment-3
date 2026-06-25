#!/usr/bin/env python3
"""Summarize Jira parent-child issue relationships from normalized data."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_parents(payload: dict[str, Any], sample_size: int) -> dict[str, Any]:
    issues = payload.get("issues") or []
    parent_to_children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    issue_type_counts = Counter()

    for issue in issues:
        parent = issue.get("parent")
        if not parent:
            continue
        parent_key = parent.get("key")
        if not parent_key:
            continue
        parent_to_children[parent_key].append(issue)
        issue_type_counts[issue.get("fields", {}).get("issue_type")] += 1

    child_issue_count = sum(len(children) for children in parent_to_children.values())
    total_issues = len(issues)
    top_parents = sorted(
        parent_to_children.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )

    sample_parent_links = []
    for parent_key, children in top_parents[:sample_size]:
        parent = children[0].get("parent") or {}
        sample_parent_links.append(
            {
                "parent_key": parent_key,
                "parent_id": parent.get("id"),
                "parent_summary": parent.get("summary"),
                "number_of_child_issues": len(children),
                "sample_child_keys": [child.get("key") for child in children[:5]],
            }
        )

    child_to_parent_examples = []
    for issue in issues:
        parent = issue.get("parent")
        if parent:
            child_to_parent_examples.append(
                {
                    "child_key": issue.get("key"),
                    "child_summary": issue.get("summary"),
                    "parent_key": parent.get("key"),
                    "parent_summary": parent.get("summary"),
                }
            )
        if len(child_to_parent_examples) >= sample_size:
            break

    return {
        "project": payload.get("project"),
        "total_issues": total_issues,
        "issues_with_parent": child_issue_count,
        "issues_without_parent": total_issues - child_issue_count,
        "unique_parent_issue_count": len(parent_to_children),
        "child_issue_type_counts": issue_type_counts.most_common(),
        "top_parents_by_child_count": sample_parent_links,
        "sample_child_to_parent_links": child_to_parent_examples,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/normalized/yarn_issues_normalized.json"),
        help="Normalized Jira issue JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/week1/yarn_parent_summary.json"),
        help="Parent summary report path.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Number of sample parent links and top parents to include.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_json(args.input)
    summary = summarize_parents(payload, args.sample_size)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Read {summary['total_issues']} issues from {args.input}")
    print(f"Issues with parent: {summary['issues_with_parent']}")
    print(f"Issues without parent: {summary['issues_without_parent']}")
    print(f"Unique parent issues: {summary['unique_parent_issue_count']}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
