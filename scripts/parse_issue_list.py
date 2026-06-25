#!/usr/bin/env python3
"""Parse assignment issue keys and design-decision flags from Issues.xlsx."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
FLAG_NAMES = ["existence", "property", "executive"]
FLAG_LABELS = ["Existence", "Property", "Executive"]


def column_number(cell_reference: str) -> int:
    letters = "".join(ch for ch in cell_reference if ch.isalpha())
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter.upper()) - 64
    return number


def read_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("main:si", NS):
        strings.append("".join((text.text or "") for text in item.iter(f"{{{NS['main']}}}t")))
    return strings


def get_sheet_path(workbook: ZipFile, sheet_name: str) -> str:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root}

    for sheet in workbook_root.findall("main:sheets/main:sheet", NS):
        if sheet.attrib["name"].strip().lower() == sheet_name.strip().lower():
            rel_id = sheet.attrib[f"{{{NS['rel']}}}id"]
            target = rel_map[rel_id]
            return "xl/" + target.lstrip("/") if not target.startswith("xl/") else target

    available = [
        sheet.attrib["name"]
        for sheet in workbook_root.findall("main:sheets/main:sheet", NS)
    ]
    raise ValueError(f"Sheet {sheet_name!r} not found. Available sheets: {available}")


def read_sheet_rows(workbook: ZipFile, sheet_path: str, shared_strings: list[str]) -> Iterable[list[str]]:
    root = ET.fromstring(workbook.read(sheet_path))
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
        yield values


def parse_bool(value: str, issue_key: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Unexpected flag value for {issue_key}: {value!r}")


def parse_issue_rows(rows: list[list[str]]) -> tuple[list[str], list[dict[str, object]]]:
    if not rows:
        raise ValueError("The selected sheet is empty.")

    header = rows[0]
    issues = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not row[0].strip():
            continue

        issue_key = row[0].strip()
        raw_flags = row[1].split() if len(row) > 1 else []
        if len(raw_flags) != len(FLAG_NAMES):
            raise ValueError(
                f"Expected {len(FLAG_NAMES)} flags for row {row_number} "
                f"({issue_key}), got {raw_flags!r}"
            )

        design_decisions = {
            name: parse_bool(value, issue_key)
            for name, value in zip(FLAG_NAMES, raw_flags)
        }
        issues.append(
            {
                "key": issue_key,
                "design_decisions": design_decisions,
            }
        )
    return header, issues


def write_json(
    output_path: Path,
    input_path: Path,
    project: str,
    header: list[str],
    issues: list[dict[str, object]],
) -> None:
    payload = {
        "project": project,
        "source_file": str(input_path),
        "source_sheet": project,
        "spreadsheet_columns": header,
        "flag_order": FLAG_LABELS,
        "issue_count": len(issues),
        "issues": issues,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_csv(output_path: Path, issues: list[dict[str, object]]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["key", *FLAG_NAMES])
        writer.writeheader()
        for issue in issues:
            row = {"key": issue["key"]}
            row.update(issue["design_decisions"])  # type: ignore[arg-type]
            writer.writerow(row)


def summarize(issues: list[dict[str, object]]) -> dict[str, object]:
    true_counts = {
        name: sum(bool(issue["design_decisions"][name]) for issue in issues)  # type: ignore[index]
        for name in FLAG_NAMES
    }
    combinations: Counter[tuple[bool, ...]] = Counter()
    for issue in issues:
        decisions = issue["design_decisions"]  # type: ignore[assignment]
        combinations[tuple(bool(decisions[name]) for name in FLAG_NAMES)] += 1  # type: ignore[index]

    return {
        "issue_count": len(issues),
        "true_counts": true_counts,
        "combination_counts": {
            " ".join(str(value) for value in combo): count
            for combo, count in combinations.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/input/Issues.xlsx"),
        help="Assignment Excel workbook.",
    )
    parser.add_argument(
        "--project",
        default="Yarn",
        help="Workbook sheet/project to parse, e.g. Yarn.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/normalized"),
        help="Directory for parsed issue-list outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    slug = args.project.strip().lower()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(args.input) as workbook:
        shared_strings = read_shared_strings(workbook)
        sheet_path = get_sheet_path(workbook, args.project)
        rows = list(read_sheet_rows(workbook, sheet_path, shared_strings))

    header, issues = parse_issue_rows(rows)
    json_path = args.output_dir / f"{slug}_issue_list.json"
    csv_path = args.output_dir / f"{slug}_issue_list.csv"

    write_json(json_path, args.input, args.project, header, issues)
    write_csv(csv_path, issues)

    summary = summarize(issues)
    print(f"Parsed {summary['issue_count']} {args.project} issues")
    print(f"Flag order: {', '.join(FLAG_LABELS)}")
    print(f"True counts: {summary['true_counts']}")
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
