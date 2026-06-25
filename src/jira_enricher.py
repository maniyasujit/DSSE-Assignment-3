"""
src/jira_enricher.py
====================
Optional Jira REST API enrichment module.

Activated only when ``config.ENABLE_JIRA_API = True``.

For each Yarn issue key found in the raw CSV, this module retrieves full
metadata from the Apache Jira instance and merges it with the existing data,
filling in empty columns without overwriting valid xlsx values (unless
``config.JIRA_API_OVERWRITE = True``).

Setup
-----
Create a ``.env`` file in the project root::

    JIRA_BASE_URL=https://issues.apache.org/jira
    JIRA_EMAIL=your@email.com
    JIRA_API_TOKEN=your_api_token

Then set ``ENABLE_JIRA_API = True`` in ``src/config.py``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry

from src import config
from src.utils import (
    ensure_dirs,
    get_logger,
    parse_list_field,
    safe_str,
    save_csv,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
_JIRA_ISSUE_ENDPOINT = "{base}/rest/api/2/issue/{key}"
_FIELDS = ",".join([
    "summary", "description", "issuetype", "status", "priority",
    "reporter", "assignee", "created", "updated", "resolutiondate",
    "labels", "components", "fixVersions", "parent", "comment",
    "attachment", "votes", "subtasks", "customfield_10014",
])
_RATE_LIMIT_PAUSE = 0.5   # seconds between requests
_RETRY_BACKOFF = 2.0      # seconds for retry backoff base


# ---------------------------------------------------------------------------
# SESSION FACTORY
# ---------------------------------------------------------------------------

def _build_session() -> requests.Session:
    """Build a requests Session with retry logic."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    if config.JIRA_EMAIL and config.JIRA_API_TOKEN:
        session.auth = (config.JIRA_EMAIL, config.JIRA_API_TOKEN)
    elif config.JIRA_API_TOKEN:
        session.headers.update({"Authorization": f"Bearer {config.JIRA_API_TOKEN}"})
    else:
        logger.warning(
            "No Jira credentials configured. "
            "Public endpoints only — private issues may be inaccessible."
        )
    return session


# ---------------------------------------------------------------------------
# FIELD EXTRACTORS
# ---------------------------------------------------------------------------

def _safe_field(fields: dict, *keys: str, default: Any = "") -> Any:
    """Traverse nested dict keys safely, returning *default* on failure."""
    val: Any = fields
    for key in keys:
        if not isinstance(val, dict):
            return default
        val = val.get(key, default)
    if val is None:
        return default
    return val


def _extract_issue_data(issue_json: dict) -> dict[str, Any]:
    """
    Extract standardised fields from a Jira REST API issue response.

    Parameters
    ----------
    issue_json: Raw JSON dict from the Jira API.

    Returns
    -------
    dict  Flattened dict with standardised field names.
    """
    fields: dict = issue_json.get("fields", {})

    # -- Parent --
    parent_key = ""
    parent_summary = ""
    parent_raw = fields.get("parent") or {}
    if parent_raw:
        parent_key = safe_str(parent_raw.get("key", ""))
        parent_summary = safe_str(
            _safe_field(parent_raw, "fields", "summary", default="")
        )
    # Some projects use customfield_10014 for epic link
    if not parent_key:
        parent_key = safe_str(fields.get("customfield_10014", ""))

    # -- Comments --
    comment_block = fields.get("comment", {}) or {}
    comments_list = comment_block.get("comments", []) if isinstance(comment_block, dict) else []
    comment_dates = [safe_str(c.get("created", "")) for c in comments_list]
    comment_devs = [
        safe_str(_safe_field(c, "author", "displayName", default=""))
        for c in comments_list
    ]

    # -- Attachments --
    attachments_list = fields.get("attachment", []) or []
    attachment_dates = [safe_str(a.get("created", "")) for a in attachments_list]
    attachment_files = [safe_str(a.get("filename", "")) for a in attachments_list]

    # -- Components / Labels / Fix versions --
    components = ", ".join(
        safe_str(c.get("name", "")) for c in (fields.get("components") or [])
    )
    labels = ", ".join(fields.get("labels") or [])
    fix_versions = ", ".join(
        safe_str(v.get("name", "")) for v in (fields.get("fixVersions") or [])
    )

    # -- Votes --
    votes_block = fields.get("votes", {}) or {}
    votes = str(votes_block.get("votes", "")) if isinstance(votes_block, dict) else ""

    return {
        "issue_id": safe_str(issue_json.get("id", "")),
        "issue_key": safe_str(issue_json.get("key", "")),
        "project": safe_str(_safe_field(fields, "project", "key", default="")),
        "summary": safe_str(fields.get("summary", "")),
        "description": safe_str(fields.get("description", "")),
        "issue_type": safe_str(_safe_field(fields, "issuetype", "name", default="")),
        "status": safe_str(_safe_field(fields, "status", "name", default="")),
        "priority": safe_str(_safe_field(fields, "priority", "name", default="")),
        "reporter": safe_str(_safe_field(fields, "reporter", "displayName", default="")),
        "assignee": safe_str(_safe_field(fields, "assignee", "displayName", default="")),
        "created_date": safe_str(fields.get("created", "")),
        "updated_date": safe_str(fields.get("updated", "")),
        "resolution_date": safe_str(fields.get("resolutiondate", "")),
        "labels": labels,
        "components": components,
        "fix_versions": fix_versions,
        "votes": votes,
        "parent_key": parent_key,
        "parent_summary": parent_summary,
        "has_parent": bool(parent_key),
        "number_of_comments": len(comments_list),
        "comment_dates": str(comment_dates),
        "comment_developers": str(comment_devs),
        "number_of_attachments": len(attachments_list),
        "attachment_dates": str(attachment_dates),
        "attachment_files": str(attachment_files),
        "has_attachments": len(attachments_list) > 0,
    }


# ---------------------------------------------------------------------------
# ENRICHER
# ---------------------------------------------------------------------------

def enrich_yarn_issues(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich the Yarn DataFrame with metadata from the Jira REST API.

    For each issue key, fetches the JSON payload and merges it into the
    existing row, filling only empty/missing cells (unless
    ``config.JIRA_API_OVERWRITE`` is True).

    Parameters
    ----------
    df: The filtered Yarn DataFrame (output of data_loader.load_yarn_issues).

    Returns
    -------
    pd.DataFrame  Enriched DataFrame saved to ``YARN_ENRICHED_CSV``.
    """
    if not config.ENABLE_JIRA_API:
        logger.info("Jira API enrichment is disabled (ENABLE_JIRA_API=False).")
        return df

    if not config.JIRA_BASE_URL:
        logger.error(
            "JIRA_BASE_URL is not set. "
            "Add it to your .env file and retry."
        )
        return df

    logger.info(
        "Starting Jira API enrichment for %d issues from: %s",
        len(df), config.JIRA_BASE_URL,
    )

    session = _build_session()
    enriched_rows: list[dict] = []
    errors = 0

    for idx, row in df.iterrows():
        key = safe_str(row.get("issue_key", ""))
        if not key:
            enriched_rows.append(row.to_dict())
            continue

        url = _JIRA_ISSUE_ENDPOINT.format(base=config.JIRA_BASE_URL.rstrip("/"), key=key)
        try:
            resp = session.get(url, params={"fields": _FIELDS}, timeout=30)
            if resp.status_code == 404:
                logger.warning("Issue not found via API: %s", key)
                enriched_rows.append(row.to_dict())
                continue
            resp.raise_for_status()
            api_data = _extract_issue_data(resp.json())

            # Merge: fill empty cells, optionally overwrite
            row_dict = row.to_dict()
            for field, api_val in api_data.items():
                existing = safe_str(row_dict.get(field, ""))
                if config.JIRA_API_OVERWRITE or not existing:
                    row_dict[field] = api_val

            enriched_rows.append(row_dict)
            logger.info("Enriched %d / %d: %s", idx + 1, len(df), key)

        except requests.exceptions.RequestException as exc:
            logger.error("API error for %s: %s", key, exc)
            enriched_rows.append(row.to_dict())
            errors += 1

        time.sleep(_RATE_LIMIT_PAUSE)

    logger.info("Enrichment complete. Errors: %d", errors)

    df_enriched = pd.DataFrame(enriched_rows)
    ensure_dirs(config.RAW_DIR)
    save_csv(df_enriched, config.YARN_ENRICHED_CSV, label="yarn_issues_enriched")
    return df_enriched
