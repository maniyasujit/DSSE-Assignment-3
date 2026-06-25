"""
src/data_loader.py
==================
Loads Issues.xlsx, standardises column names, maps data into the simplified
Jira structure, filters Yarn/YARN issues only, and saves raw + structured CSVs.

Excel structure discovered (June 2025):
  - 5 sheets: Yarn, Mapreduce, Lucene, Tika, JClouds
  - Each sheet has exactly 2 columns:
        "Issue ID"                  → issue_key
        "Types of design decisions" → design_decision_types
  - All other metadata (summary, description, etc.) is absent from the xlsx;
    it must be retrieved via Jira API enrichment (see config.ENABLE_JIRA_API).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src import config
from src.utils import (
    ensure_dirs,
    extract_rtf_text,
    get_logger,
    parse_attachments,
    parse_comments,
    parse_list_field,
    report_missing,
    require_columns,
    safe_str,
    save_csv,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# COLUMN MAPPING
# ---------------------------------------------------------------------------
# Maps possible raw column names (lower-stripped) → standardised name.
# Extend this dict if the xlsx gains additional columns in future.

_COL_MAP: dict[str, str] = {
    # Issue identity
    "issue id": "issue_key",
    "issue_id": "issue_key",
    "key": "issue_key",
    "issue key": "issue_key",
    "issueid": "issue_key",
    # Design decision label (xlsx-specific)
    "types of design decisions": "design_decision_types",
    "design decision": "design_decision_types",
    "design_decision": "design_decision_types",
    # Metadata (populated if ever present)
    "id": "issue_id",
    "project": "project",
    "project key": "project",
    "project name": "project",
    "summary": "summary",
    "description": "description",
    "issue type": "issue_type",
    "issuetype": "issue_type",
    "type": "issue_type",
    "status": "status",
    "priority": "priority",
    "reporter": "reporter",
    "reporter name": "reporter",
    "assignee": "assignee",
    "assignee name": "assignee",
    "created": "created_date",
    "created date": "created_date",
    "creation date": "created_date",
    "updated": "updated_date",
    "updated date": "updated_date",
    "last updated": "updated_date",
    "resolved": "resolution_date",
    "resolution date": "resolution_date",
    "resolutiondate": "resolution_date",
    "labels": "labels",
    "label": "labels",
    "components": "components",
    "component": "components",
    "fix version": "fix_versions",
    "fix versions": "fix_versions",
    "fixversions": "fix_versions",
    "votes": "votes",
    "vote": "votes",
    "parent": "parent_key",
    "parent key": "parent_key",
    "parent_key": "parent_key",
    "parent issue": "parent_key",
    "parent issue key": "parent_key",
    "parent summary": "parent_summary",
    "comments": "comments",
    "comment": "comments",
    "number of comments": "number_of_comments",
    "comment count": "number_of_comments",
    "attachments": "attachments",
    "attachment": "attachments",
    "number of attachments": "number_of_attachments",
    "attachment count": "number_of_attachments",
}

# All columns the standardised dataset should contain (filled with "" if absent).
_ALL_COLUMNS: list[str] = [
    "issue_id", "issue_key", "project", "votes",
    "parent_key", "parent_summary", "has_parent",
    "summary", "description",
    "raw_text", "cleaned_text", "token_list",
    "issue_type", "status", "priority",
    "reporter", "assignee",
    "created_date", "updated_date", "resolution_date",
    "labels", "components", "fix_versions",
    "comments", "number_of_comments",
    "comment_dates", "comment_developers",
    "bot_comment_count", "human_comment_count", "has_bot_comments",
    "attachments", "number_of_attachments",
    "attachment_dates", "attachment_files", "has_attachments",
    "design_decision_types",
]

# Columns that MUST be present (after standardisation).
_REQUIRED_COLUMNS: list[str] = ["issue_key"]


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def load_yarn_issues(
    xlsx_path: Path | str = config.ISSUES_XLSX,
    sheet_name: Optional[str] = config.SHEET_NAME,
) -> pd.DataFrame:
    """
    Load, filter, and standardise Yarn/YARN issues from Issues.xlsx.

    Steps
    -----
    1. Load all sheets from the Excel file.
    2. Select the relevant sheet (auto-detected or configured).
    3. Standardise column names.
    4. Derive the ``project`` column from the issue key prefix.
    5. Filter to Yarn/YARN issues only.
    6. Ensure all standard columns exist (fill with empty strings if absent).
    7. Parse comment and attachment fields where present.
    8. Log statistics.
    9. Save ``data/raw/yarn_issues_raw.csv`` and
       ``data/processed/yarn_issues_structured.csv``.

    Parameters
    ----------
    xlsx_path:  Path to Issues.xlsx.
    sheet_name: Sheet to use; None = auto-detect.

    Returns
    -------
    pd.DataFrame  The filtered, standardised Yarn DataFrame.
    """
    xlsx_path = Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {xlsx_path}\n"
            "Ensure Issues.xlsx is in the project root."
        )

    # ------------------------------------------------------------------
    # 1. Load Excel
    # ------------------------------------------------------------------
    logger.info("Loading Excel file: %s", xlsx_path)
    xl = pd.ExcelFile(xlsx_path, engine="openpyxl")
    all_sheets = xl.sheet_names
    logger.info("Available sheets: %s", all_sheets)

    # ------------------------------------------------------------------
    # 2. Sheet selection
    # ------------------------------------------------------------------
    chosen = _select_sheet(all_sheets, sheet_name)
    logger.info("Using sheet: '%s'", chosen)
    df_raw = xl.parse(chosen)
    total_rows = len(df_raw)
    logger.info("Loaded %d rows from sheet '%s'", total_rows, chosen)

    # ------------------------------------------------------------------
    # 3. Standardise column names
    # ------------------------------------------------------------------
    df = _standardise_columns(df_raw.copy())

    # ------------------------------------------------------------------
    # 4. Validate required columns
    # ------------------------------------------------------------------
    require_columns(df, _REQUIRED_COLUMNS, context=f"sheet '{chosen}'")

    # ------------------------------------------------------------------
    # 5. Clean issue keys
    # ------------------------------------------------------------------
    df["issue_key"] = df["issue_key"].apply(lambda v: safe_str(v).strip().upper())
    df = df[df["issue_key"].str.len() > 0].copy()

    # ------------------------------------------------------------------
    # 6. Derive project from issue key (e.g. "YARN-10650" → "YARN")
    # ------------------------------------------------------------------
    if "project" not in df.columns or df["project"].eq("").all():
        df["project"] = df["issue_key"].apply(
            lambda k: k.split("-")[0] if "-" in k else ""
        )
        logger.debug("Derived 'project' column from issue key prefixes.")

    # ------------------------------------------------------------------
    # 7. Filter Yarn/YARN issues
    # ------------------------------------------------------------------
    yarn_mask = _build_yarn_mask(df)
    non_yarn_count = (~yarn_mask).sum()
    df_yarn = df[yarn_mask].copy().reset_index(drop=True)

    logger.info("Total rows loaded    : %d", total_rows)
    logger.info("Yarn rows retained   : %d", len(df_yarn))
    logger.info("Non-Yarn rows removed: %d", non_yarn_count)

    if len(df_yarn) == 0:
        logger.warning(
            "No Yarn/YARN issues found in sheet '%s'. "
            "Check that issue keys start with 'YARN-' or the project column "
            "contains 'YARN'.",
            chosen,
        )

    # ------------------------------------------------------------------
    # 8. Ensure all standard columns exist
    # ------------------------------------------------------------------
    df_yarn = _ensure_all_columns(df_yarn)

    # ------------------------------------------------------------------
    # 9. Parse comment and attachment fields (if present)
    # ------------------------------------------------------------------
    df_yarn = _parse_comment_columns(df_yarn)
    df_yarn = _parse_attachment_columns(df_yarn)

    # ------------------------------------------------------------------
    # 10. Log missing values for key columns
    # ------------------------------------------------------------------
    key_cols = [
        "issue_key", "summary", "description", "issue_type",
        "status", "priority", "reporter", "assignee",
        "created_date", "parent_key",
    ]
    _log_missing(df_yarn, key_cols)

    # ------------------------------------------------------------------
    # 11. Save outputs
    # ------------------------------------------------------------------
    ensure_dirs(config.RAW_DIR, config.PROCESSED_DIR)
    save_csv(df_yarn, config.YARN_RAW_CSV, label="yarn_issues_raw")

    # Structured output (same data, explicit column ordering)
    structured_cols = [c for c in _ALL_COLUMNS if c in df_yarn.columns]
    extra_cols = [c for c in df_yarn.columns if c not in structured_cols]
    df_structured = df_yarn[structured_cols + extra_cols].copy()
    save_csv(df_structured, config.YARN_STRUCTURED_CSV, label="yarn_issues_structured")

    return df_yarn


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _select_sheet(available: list[str], preferred: Optional[str]) -> str:
    """
    Choose the sheet to use.

    Priority:
      1. ``preferred`` if supplied and present.
      2. Any sheet whose name (case-insensitive) contains "yarn".
      3. The first sheet.
    """
    if preferred:
        if preferred in available:
            return preferred
        # Try case-insensitive match
        for s in available:
            if s.lower() == preferred.lower():
                return s
        logger.warning(
            "Configured sheet '%s' not found. Auto-detecting.", preferred
        )

    for s in available:
        if "yarn" in s.lower():
            return s

    logger.warning(
        "No sheet with 'yarn' in name found. Defaulting to first sheet: '%s'",
        available[0],
    )
    return available[0]


def _standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename columns according to ``_COL_MAP`` (case/whitespace insensitive).

    Columns not in the map are left unchanged (lowercased + underscored).
    """
    rename: dict[str, str] = {}
    for col in df.columns:
        normalised = col.strip().lower()
        if normalised in _COL_MAP:
            rename[col] = _COL_MAP[normalised]
        else:
            # Generic normalisation: lowercase, spaces → underscores
            rename[col] = re.sub(r"\s+", "_", normalised)

    df.rename(columns=rename, inplace=True)
    logger.debug("Standardised columns: %s", list(df.columns))
    return df


import re as _re  # noqa: E402 (already imported at top via utils; explicit here for clarity)


def _build_yarn_mask(df: pd.DataFrame) -> pd.Series:
    """
    Build a boolean mask selecting only Yarn/YARN issues.

    Criteria (any one is sufficient):
      - issue_key starts with "YARN-"
      - project == "YARN" (case-insensitive)
      - project contains "Yarn" (case-insensitive)
    """
    mask_key = df["issue_key"].str.startswith("YARN-", na=False)

    if "project" in df.columns:
        proj = df["project"].fillna("").str.strip()
        mask_proj = (
            proj.str.upper() == "YARN"
        ) | proj.str.contains("yarn", case=False, na=False)
    else:
        mask_proj = pd.Series(False, index=df.index)

    return mask_key | mask_proj


def _ensure_all_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add any missing standard columns with empty string values.
    Logs a warning for each optional column that is absent.
    """
    missing_optional = []
    for col in _ALL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
            if col not in _REQUIRED_COLUMNS:
                missing_optional.append(col)

    if missing_optional:
        logger.warning(
            "Optional columns not found in source data (created as empty): %s",
            missing_optional,
        )
    return df


def _parse_comment_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse the ``comments`` column (if present and non-empty) into structured
    sub-columns: ``number_of_comments``, ``comment_dates``, ``comment_developers``.
    """
    if "comments" not in df.columns or df["comments"].eq("").all():
        logger.info(
            "No comment data found in source. "
            "comment_dates / comment_developers will be empty."
        )
        return df

    parsed = df["comments"].apply(parse_comments)
    df["number_of_comments"] = parsed.apply(
        lambda p: p["count"] if isinstance(p, dict) else 0
    )
    df["comment_dates"] = parsed.apply(
        lambda p: str(p["dates"]) if isinstance(p, dict) else ""
    )
    df["comment_developers"] = parsed.apply(
        lambda p: str(p["developers"]) if isinstance(p, dict) else ""
    )
    logger.debug("Parsed comment fields.")
    return df


def _parse_attachment_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse the ``attachments`` column (if present and non-empty) into structured
    sub-columns: ``number_of_attachments``, ``attachment_dates``, ``attachment_files``.
    """
    if "attachments" not in df.columns or df["attachments"].eq("").all():
        logger.info(
            "No attachment data found in source. "
            "attachment_dates / attachment_files will be empty."
        )
        return df

    parsed = df["attachments"].apply(parse_attachments)
    df["number_of_attachments"] = parsed.apply(
        lambda p: p["count"] if isinstance(p, dict) else 0
    )
    df["attachment_dates"] = parsed.apply(
        lambda p: str(p["dates"]) if isinstance(p, dict) else ""
    )
    df["attachment_files"] = parsed.apply(
        lambda p: str(p["files"]) if isinstance(p, dict) else ""
    )
    df["has_attachments"] = df["number_of_attachments"].apply(
        lambda n: True if (isinstance(n, int) and n > 0) else False
    )
    logger.debug("Parsed attachment fields.")
    return df


def _log_missing(df: pd.DataFrame, cols: list[str]) -> None:
    """Log missing value counts for the specified columns."""
    total = len(df)
    for col in cols:
        if col in df.columns:
            n = (df[col].isna() | (df[col].astype(str).str.strip() == "")).sum()
            pct = 100 * n / total if total else 0
            if n > 0:
                logger.info(
                    "  Missing %-25s : %5d / %d  (%.1f%%)",
                    f"'{col}'", n, total, pct,
                )
