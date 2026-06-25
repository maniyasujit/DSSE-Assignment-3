"""
src/utils.py
============
Shared utilities: logging, directory helpers, safe I/O, Excel inspection,
comment/attachment parsers, RTF extractor, and error helpers.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    """
    Configure the root logger.

    Parameters
    ----------
    level:    Logging level string ("DEBUG", "INFO", "WARNING", "ERROR").
    log_file: Optional file path for persistent log output.

    Returns
    -------
    logging.Logger
        The configured root logger.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger()


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger (inherits root configuration)."""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# DIRECTORY HELPERS
# ---------------------------------------------------------------------------

def ensure_dirs(*paths: Path | str) -> None:
    """Create directories (and parents) if they do not already exist."""
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SAFE COLUMN ACCESS
# ---------------------------------------------------------------------------

def safe_get(row: pd.Series, column: str, default: Any = "") -> Any:
    """
    Safely retrieve a value from a pandas Series by column name.

    Returns *default* if the column does not exist or the value is NaN/None.
    """
    if column not in row.index:
        return default
    val = row[column]
    if pd.isna(val):
        return default
    return val


def safe_str(value: Any) -> str:
    """Convert *value* to a stripped string; return '' for NaN/None."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


# ---------------------------------------------------------------------------
# CSV SAVING HELPER
# ---------------------------------------------------------------------------

def save_csv(df: pd.DataFrame, path: Path | str, label: str = "") -> None:
    """
    Save a DataFrame to CSV with UTF-8 BOM encoding (Excel-compatible).

    Parameters
    ----------
    df:    DataFrame to save.
    path:  Destination file path.
    label: Human-readable label used in log messages.
    """
    logger = get_logger("utils.save_csv")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    tag = f" [{label}]" if label else ""
    logger.info("Saved%s -> %s  (%d rows x %d cols)", tag, path, len(df), len(df.columns))


# ---------------------------------------------------------------------------
# EXCEL INSPECTION HELPER
# ---------------------------------------------------------------------------

def inspect_excel(xlsx_path: Path | str) -> dict[str, pd.DataFrame]:
    """
    Load all sheets from an Excel file and log their structure.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of sheet name → DataFrame.
    """
    logger = get_logger("utils.inspect_excel")
    xlsx_path = Path(xlsx_path)
    logger.info("Inspecting Excel file: %s", xlsx_path)

    xl = pd.ExcelFile(xlsx_path, engine="openpyxl")
    sheets: dict[str, pd.DataFrame] = {}

    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)
        sheets[sheet_name] = df
        logger.info(
            "  Sheet '%s': %d rows × %d columns — %s",
            sheet_name, len(df), len(df.columns), list(df.columns),
        )

    return sheets


# ---------------------------------------------------------------------------
# MISSING VALUE REPORTER
# ---------------------------------------------------------------------------

def report_missing(df: pd.DataFrame, label: str = "DataFrame") -> None:
    """Log a summary of missing values for each column."""
    logger = get_logger("utils.missing")
    total = len(df)
    logger.info("Missing value report for '%s' (%d rows):", label, total)
    for col in df.columns:
        n_missing = df[col].isna().sum()
        if n_missing > 0:
            pct = 100 * n_missing / total if total else 0
            logger.info("  %-35s  %5d missing  (%.1f%%)", col, n_missing, pct)


# ---------------------------------------------------------------------------
# JSON / LIST PARSING HELPER
# ---------------------------------------------------------------------------

def parse_list_field(value: Any) -> list[Any]:
    """
    Parse a field that may contain a list represented as:
      - an actual Python list
      - a JSON-encoded string
      - a Python literal string (ast.literal_eval)
      - a comma/semicolon-separated string
      - a plain string (returned as a single-element list)
      - NaN / None (returned as empty list)

    Returns
    -------
    list[Any]
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, float) and pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    # Try JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except (json.JSONDecodeError, ValueError):
        pass
    # Try ast.literal_eval
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except (ValueError, SyntaxError):
        pass
    # Comma / semicolon split
    if "," in text or ";" in text:
        sep = "," if "," in text else ";"
        return [item.strip() for item in text.split(sep) if item.strip()]
    return [text]


# ---------------------------------------------------------------------------
# COMMENT PARSING HELPER
# ---------------------------------------------------------------------------

def parse_comments(value: Any) -> dict[str, Any]:
    """
    Parse a comment field into a structured dict:

        {
            "count":      int,
            "dates":      list[str],
            "developers": list[str],
            "raw":        str,
        }

    The function handles:
      - plain integer / numeric string (only count known)
      - JSON/list with comment objects having 'author'/'date' keys
      - plain text (treated as raw, count = 1)
      - NaN / None (count = 0)
    """
    logger = get_logger("utils.parse_comments")
    result: dict[str, Any] = {"count": 0, "dates": [], "developers": [], "raw": ""}

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return result

    text = str(value).strip()
    result["raw"] = text

    # Numeric — only the count is known
    if re.match(r"^\d+$", text):
        result["count"] = int(text)
        return result

    # Try to parse as list of comment objects
    items = parse_list_field(value)
    if items and isinstance(items[0], dict):
        result["count"] = len(items)
        for item in items:
            if "date" in item:
                result["dates"].append(str(item["date"]))
            if "author" in item:
                result["developers"].append(str(item["author"]))
            elif "developer" in item:
                result["developers"].append(str(item["developer"]))
        return result

    # Fallback: treat entire value as raw text
    if items:
        result["count"] = len(items)
    else:
        logger.warning("Could not parse comment field: %s", text[:120])

    return result


# ---------------------------------------------------------------------------
# ATTACHMENT PARSING HELPER
# ---------------------------------------------------------------------------

def parse_attachments(value: Any) -> dict[str, Any]:
    """
    Parse an attachment field into:

        {
            "count": int,
            "dates": list[str],
            "files": list[str],
            "raw":   str,
        }
    """
    logger = get_logger("utils.parse_attachments")
    result: dict[str, Any] = {"count": 0, "dates": [], "files": [], "raw": ""}

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return result

    text = str(value).strip()
    result["raw"] = text

    if re.match(r"^\d+$", text):
        result["count"] = int(text)
        return result

    items = parse_list_field(value)
    if items and isinstance(items[0], dict):
        result["count"] = len(items)
        for item in items:
            if "date" in item:
                result["dates"].append(str(item["date"]))
            for key in ("filename", "file", "name"):
                if key in item:
                    result["files"].append(str(item[key]))
                    break
        return result

    if items:
        result["count"] = len(items)
    else:
        logger.warning("Could not parse attachment field: %s", text[:120])

    return result


# ---------------------------------------------------------------------------
# RTF TEXT EXTRACTION HELPER
# ---------------------------------------------------------------------------

def extract_rtf_text(rtf_path: Path | str) -> str:
    """
    Extract plain text from a .rtf file.

    Strategy:
      1. Try the `striprtf` library (pip install striprtf).
      2. Fall back to a simple regex that removes RTF control words.

    Returns
    -------
    str
        Extracted plain text, or empty string if the file is missing.
    """
    logger = get_logger("utils.rtf")
    rtf_path = Path(rtf_path)
    if not rtf_path.exists():
        logger.warning("RTF file not found: %s", rtf_path)
        return ""

    raw = rtf_path.read_bytes().decode("latin-1", errors="replace")

    try:
        from striprtf.striprtf import rtf_to_text  # type: ignore
        return rtf_to_text(raw)
    except ImportError:
        logger.debug("striprtf not installed; using regex RTF stripper.")

    # Regex fallback
    text = re.sub(r"\\[a-z]+\-?\d*\s?", " ", raw)
    text = re.sub(r"[{}\\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# ERROR HELPERS
# ---------------------------------------------------------------------------

def require_file(path: Path | str, description: str = "file") -> None:
    """Raise FileNotFoundError with a clear message if *path* does not exist."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Required {description} not found: {path}\n"
            f"Please ensure this file exists before running the pipeline."
        )


def require_columns(df: pd.DataFrame, required: list[str], context: str = "") -> None:
    """
    Raise ValueError if any of *required* columns are missing from *df*.

    Parameters
    ----------
    df:       DataFrame to check.
    required: List of required column names.
    context:  Human-readable context label used in the error message.
    """
    missing = [c for c in required if c not in df.columns]
    if missing:
        ctx = f" ({context})" if context else ""
        raise ValueError(
            f"Required columns missing{ctx}: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )
