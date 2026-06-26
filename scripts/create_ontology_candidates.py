#!/usr/bin/env python3
"""Create ontology replacement/removal candidates from token frequencies."""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ONTOLOGY_URL = (
    "https://raw.githubusercontent.com/IcecubeCreations/LDA-on-blogs/"
    "main/preprocessing/ontology_sheet.xlsx"
)
NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
RUST_MARKER_TOKENS = {
    "attachment",
    "classname",
    "cloudinstance",
    "date",
    "filepath",
    "formattedloggingoutput",
    "formattedtraceback",
    "githublink",
    "imageattachment",
    "inlinecodesample",
    "issuelink",
    "lllog",
    "methodorvariablename",
    "noformatblock",
    "package",
    "simpleclassname",
    "simplemethodorvariablename",
    "storagesize",
    "structuredcodeblock",
    "technologynames",
    "tttraceback",
    "unformattedloggingoutput",
    "unformattedtraceback",
    "userprofilelink",
    "versionnumber",
    "weblink",
}
PROJECT_OR_GENERIC_REVIEW = {
    "yarn": "project name; often too broad for topic modeling",
    "jira": "issue-tracker term; often too broad for topic modeling",
}


def column_number(cell_reference: str) -> int:
    letters = "".join(ch for ch in cell_reference if ch.isalpha())
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter.upper()) - 64
    return number


def download_if_needed(url: str, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "DSSE-Assignment-3/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())


def read_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    shared = []
    for item in root.findall("main:si", NS):
        shared.append("".join((text.text or "") for text in item.iter(f"{{{NS['main']}}}t")))
    return shared


def read_sheet_rows(workbook: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(workbook.read(sheet_path))
    rows = []
    for row in root.findall(".//main:sheetData/main:row", NS):
        values: list[str] = []
        for cell in row.findall("main:c", NS):
            index = column_number(cell.attrib.get("r", "A"))
            while len(values) < index - 1:
                values.append("")

            value = cell.find("main:v", NS)
            text = "" if value is None else (value.text or "")
            if cell.attrib.get("t") == "s" and text:
                text = shared_strings[int(text)]
            elif cell.attrib.get("t") == "inlineStr":
                text = "".join((part.text or "") for part in cell.iter(f"{{{NS['main']}}}t"))
            values.append(text)
        rows.append(values)
    return rows


def workbook_sheet_paths(workbook: ZipFile) -> list[tuple[str, str]]:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root}
    paths = []
    for sheet in workbook_root.findall("main:sheets/main:sheet", NS):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{NS['rel']}}}id"]
        target = rel_map[rel_id]
        sheet_path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
        paths.append((name, sheet_path))
    return paths


def normalize_class_name(value: str) -> str:
    value = value.strip().strip("_")
    value = re.sub(r"\s+", "_", value)
    return value


def normalize_term(value: str) -> str:
    value = value.strip().lower()
    value = value.strip("'\"`.,;:!?()[]{}<>")
    value = re.sub(r"\s+", " ", value)
    return value


def split_terms(value: str) -> list[str]:
    terms = []
    for part in re.split(r"[\n\r]+", value):
        term = normalize_term(part)
        if term:
            terms.append(term)
    return terms


def load_ontology_terms(path: Path) -> dict[str, set[str]]:
    term_to_classes: dict[str, set[str]] = {}
    with ZipFile(path) as workbook:
        shared_strings = read_shared_strings(workbook)
        for _sheet_name, sheet_path in workbook_sheet_paths(workbook):
            rows = read_sheet_rows(workbook, sheet_path, shared_strings)
            if not rows:
                continue
            header = rows[0]
            for column_index in range(max(len(row) for row in rows)):
                class_name = normalize_class_name(header[column_index]) if column_index < len(header) else ""

                # The linked ontology workbook has an empty first header cell, but
                # that first column contains additional Component terms.
                if not class_name and column_index == 0 and len(header) > 1:
                    class_name = normalize_class_name(header[1])
                if not class_name:
                    continue

                for row in rows[1:]:
                    if column_index >= len(row):
                        continue
                    for term in split_terms(row[column_index]):
                        term_to_classes.setdefault(term, set()).add(class_name)
    return term_to_classes


def read_token_records(path: Path) -> list[dict[str, Any]]:
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


def token_statistics(records: list[dict[str, Any]]) -> tuple[Counter[str], Counter[str]]:
    total_counts: Counter[str] = Counter()
    document_frequency: Counter[str] = Counter()
    for record in records:
        tokens = record.get("tokens") or []
        total_counts.update(tokens)
        document_frequency.update(set(tokens))
    return total_counts, document_frequency


def classify_token(token: str, ontology_terms: dict[str, set[str]]) -> tuple[str, str, str, str]:
    if token in RUST_MARKER_TOKENS:
        return "Marker", "remove", "rust_marker", "Rust cleaner marker token; review for removal before LDA"
    if token in PROJECT_OR_GENERIC_REVIEW:
        return "Project_or_generic", "review", "manual_rule", PROJECT_OR_GENERIC_REVIEW[token]
    if token in ontology_terms:
        classes = sorted(ontology_terms[token])
        return "|".join(classes), "review", "ontology_exact_match", "Exact match in ontology sheet"
    return "", "review", "high_frequency", "High-frequency token without exact ontology match"


def build_candidates(
    records: list[dict[str, Any]],
    ontology_terms: dict[str, set[str]],
    top_n: int,
    min_count: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total_counts, document_frequency = token_statistics(records)
    issue_count = len(records)
    ranked_tokens = {token for token, _count in total_counts.most_common(top_n)}
    ontology_matches = {
        token
        for token, count in total_counts.items()
        if count >= min_count and token in ontology_terms
    }
    marker_or_manual = {
        token
        for token, count in total_counts.items()
        if count >= min_count and (token in RUST_MARKER_TOKENS or token in PROJECT_OR_GENERIC_REVIEW)
    }
    selected_tokens = ranked_tokens | ontology_matches | marker_or_manual

    candidates = []
    for rank, (token, total_count) in enumerate(total_counts.most_common(), start=1):
        if token not in selected_tokens:
            continue
        candidate_class, decision, source, reason = classify_token(token, ontology_terms)
        df = document_frequency[token]
        candidates.append(
            {
                "rank": rank,
                "token": token,
                "total_count": total_count,
                "document_frequency": df,
                "percent_documents": round((df / issue_count) * 100, 2) if issue_count else 0,
                "candidate_class": candidate_class,
                "decision": decision,
                "source": source,
                "reason": reason,
            }
        )

    by_source = Counter(candidate["source"] for candidate in candidates)
    by_decision = Counter(candidate["decision"] for candidate in candidates)
    by_class = Counter(candidate["candidate_class"] or "Unmatched" for candidate in candidates)
    summary = {
        "issue_count": issue_count,
        "total_unique_tokens": len(total_counts),
        "ontology_unique_terms": len(ontology_terms),
        "candidate_count": len(candidates),
        "top_n_included": top_n,
        "min_count_for_extra_matches": min_count,
        "candidate_count_by_source": by_source.most_common(),
        "candidate_count_by_decision": by_decision.most_common(),
        "candidate_count_by_class": by_class.most_common(),
        "top_candidates": candidates[:50],
    }
    return candidates, summary


def write_candidates(path: Path, candidates: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "token",
        "total_count",
        "document_frequency",
        "percent_documents",
        "candidate_class",
        "decision",
        "source",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tokens",
        type=Path,
        default=Path("data/processed/yarn_tokens.jsonl"),
        help="Tokenized issue JSONL.",
    )
    parser.add_argument(
        "--ontology-file",
        type=Path,
        default=Path("data/input/ontology_sheet.xlsx"),
        help="Local ontology workbook path. Downloaded if missing.",
    )
    parser.add_argument(
        "--ontology-url",
        default=ONTOLOGY_URL,
        help="Raw GitHub URL for ontology_sheet.xlsx.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/week1/ontology_replacement_candidates.csv"),
        help="Candidate CSV output.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("reports/week1/ontology_replacement_candidates_summary.json"),
        help="Candidate summary JSON output.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=300,
        help="Always include the N most frequent tokens.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=10,
        help="Include extra ontology/marker/manual matches with at least this count.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    download_if_needed(args.ontology_url, args.ontology_file)

    records = read_token_records(args.tokens)
    ontology_terms = load_ontology_terms(args.ontology_file)
    candidates, summary = build_candidates(
        records,
        ontology_terms,
        top_n=args.top_n,
        min_count=args.min_count,
    )

    write_candidates(args.output, candidates)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Read {len(records)} tokenized issues")
    print(f"Loaded {len(ontology_terms)} ontology terms from {args.ontology_file}")
    print(f"Wrote {len(candidates)} candidates to {args.output}")
    print(f"Wrote summary to {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
