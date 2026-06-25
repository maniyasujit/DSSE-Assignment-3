#!/usr/bin/env python3
"""Clean raw topic-modeling text with the linked Rust Jira text cleaner."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any


MARKERS = [
    "ATTACHMENT",
    "CLASSNAME",
    "CLOUDINSTANCE",
    "DATE",
    "FILEPATH",
    "FORMATTEDLOGGINGOUTPUT",
    "FORMATTEDTRACEBACK",
    "GITHUBLINK",
    "IMAGEATTACHMENT",
    "INLINECODESAMPLE",
    "ISSUELINK",
    "IP ADDRESS",
    "LLLOG",
    "METHODORVARIABLENAME",
    "NOFORMATBLOCK",
    "PACKAGE",
    "SIMPLECLASSNAME",
    "SIMPLEMETHODORVARIABLENAME",
    "STORAGESIZE",
    "STRUCTUREDCODEBLOCK",
    "TECHNOLOGYNAMES",
    "TTTRACEBACK",
    "UNFORMATTEDLOGGINGOUTPUT",
    "UNFORMATTEDTRACEBACK",
    "USERPROFILELINK",
    "VERSIONNUMBER",
    "WEBLINK",
]


def load_accelerator(cleaner_root: Path):
    library_dir = cleaner_root / "dl_manager"
    candidates = sorted(library_dir.glob("accelerator*.so"))
    if not candidates:
        raise FileNotFoundError(
            f"No compiled accelerator*.so found in {library_dir}. "
            "Build it first with: cd external/mining-design-decisions/deep_learning "
            "&& python setup.py build_ext --inplace"
        )

    # Prefer a library matching the active Python ABI, e.g. cpython-39.
    version_tag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
    library_path = next((path for path in candidates if version_tag in path.name), candidates[0])
    spec = importlib.util.spec_from_file_location("accelerator", library_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load Rust accelerator module from {library_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, library_path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON on {path}:{line_number}") from error
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def clean_documents(accelerator: Any, documents: list[str], mode: str, threads: int) -> list[str]:
    return accelerator.bulk_clean_text_parallel(documents, mode, threads)


def join_text(summary: str, description: str) -> str:
    summary = summary.strip()
    description = description.strip()
    if summary and description:
        return f"{summary}\n{description}"
    return summary or description


def normalize_spaces(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def marker_counts(texts: list[str]) -> dict[str, int]:
    counts = Counter()
    for text in texts:
        for marker in MARKERS:
            counts[marker] += text.count(marker)
    return {marker: count for marker, count in counts.most_common() if count}


def summarize(records: list[dict[str, Any]], mode: str, threads: int, library_path: Path) -> dict[str, Any]:
    raw_lengths = [len(record["text_raw"]) for record in records]
    cleaned_lengths = [len(record["text_cleaned"]) for record in records]
    cleaned_word_lengths = [len(record["text_cleaned"].split()) for record in records]
    cleaned_texts = [record["text_cleaned"] for record in records]

    return {
        "issue_count": len(records),
        "formatting_handling": mode,
        "threads": threads,
        "rust_cleaner_library": str(library_path),
        "empty_cleaned_texts": sum(not record["text_cleaned"].strip() for record in records),
        "raw_text_char_length": {
            "min": min(raw_lengths) if raw_lengths else 0,
            "max": max(raw_lengths) if raw_lengths else 0,
            "mean": mean(raw_lengths) if raw_lengths else 0,
            "median": median(raw_lengths) if raw_lengths else 0,
        },
        "cleaned_text_char_length": {
            "min": min(cleaned_lengths) if cleaned_lengths else 0,
            "max": max(cleaned_lengths) if cleaned_lengths else 0,
            "mean": mean(cleaned_lengths) if cleaned_lengths else 0,
            "median": median(cleaned_lengths) if cleaned_lengths else 0,
        },
        "cleaned_text_word_length": {
            "min": min(cleaned_word_lengths) if cleaned_word_lengths else 0,
            "max": max(cleaned_word_lengths) if cleaned_word_lengths else 0,
            "mean": mean(cleaned_word_lengths) if cleaned_word_lengths else 0,
            "median": median(cleaned_word_lengths) if cleaned_word_lengths else 0,
        },
        "marker_counts": marker_counts(cleaned_texts),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/yarn_text_raw.jsonl"),
        help="JSONL produced by build_topic_text.py.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/yarn_text_cleaned.jsonl"),
        help="Cleaned JSONL output path.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("reports/week1/yarn_text_cleaned_summary.json"),
        help="Summary report path.",
    )
    parser.add_argument(
        "--cleaner-root",
        type=Path,
        default=Path("external/mining-design-decisions/deep_learning"),
        help="Root of the cloned mining-design-decisions/deep_learning folder.",
    )
    parser.add_argument(
        "--formatting-handling",
        choices=["markers", "remove", "keep"],
        default="markers",
        help="Rust cleaner formatting mode.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, min(os.cpu_count() or 1, 8)),
        help="Number of Rust/Rayon worker threads.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    accelerator, library_path = load_accelerator(args.cleaner_root)
    records = read_jsonl(args.input)

    summaries = [record.get("summary") or "" for record in records]
    descriptions = [record.get("description") or "" for record in records]
    cleaned_summaries = clean_documents(
        accelerator,
        summaries,
        args.formatting_handling,
        args.threads,
    )
    cleaned_descriptions = clean_documents(
        accelerator,
        descriptions,
        args.formatting_handling,
        args.threads,
    )

    output_records = []
    for record, summary_cleaned, description_cleaned in zip(
        records,
        cleaned_summaries,
        cleaned_descriptions,
    ):
        summary_cleaned = normalize_spaces(summary_cleaned)
        description_cleaned = normalize_spaces(description_cleaned)
        output_records.append(
            {
                "key": record["key"],
                "summary_cleaned": summary_cleaned,
                "description_cleaned": description_cleaned,
                "text_raw": record.get("text_raw") or "",
                "text_cleaned": join_text(summary_cleaned, description_cleaned),
                "design_decisions": record.get("design_decisions") or {},
            }
        )

    summary = summarize(output_records, args.formatting_handling, args.threads, library_path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output, output_records)

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Cleaned {len(output_records)} issue texts with Rust cleaner")
    print(f"Formatting mode: {args.formatting_handling}")
    print(f"Threads: {args.threads}")
    print(f"Rust library: {library_path}")
    print(f"Empty cleaned texts: {summary['empty_cleaned_texts']}")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
