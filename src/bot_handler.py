"""
src/bot_handler.py
==================
Bot comment detection support.

Reads ``Bot Comments.rtf`` to extract a list of known bot account names,
then uses that list to classify comments in the Yarn DataFrame.

Adds columns (only when comment author data is available):
    bot_comment_count   (int)
    human_comment_count (int)
    has_bot_comments    (bool)

If comment author data is absent (as expected when the xlsx has no comment
detail), this module logs a warning and returns the DataFrame unchanged.
"""

from __future__ import annotations

import ast
import logging
import re

import pandas as pd

from src import config
from src.utils import extract_rtf_text, get_logger, parse_list_field, safe_str

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# BOT LIST EXTRACTION
# ---------------------------------------------------------------------------

def load_bot_list(rtf_path=config.BOT_COMMENTS_RTF) -> list[str]:
    """
    Extract bot account names from ``Bot Comments.rtf``.

    The RTF file contains a JSON-like list of bot usernames, e.g.::

        ["Hadoop QA", "ASF GitHub Bot", "cnsgithub", ...]

    Returns
    -------
    list[str]  List of known bot display names (stripped, lowercase for matching).
    """
    text = extract_rtf_text(rtf_path)
    if not text.strip():
        logger.warning("Bot Comments.rtf is empty or unreadable; using empty bot list.")
        return []

    # Find first JSON-array-like structure in the text
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        logger.warning("No list found in Bot Comments.rtf; using empty bot list.")
        return []

    try:
        raw_list = ast.literal_eval(match.group(0))
        if isinstance(raw_list, list):
            bots = [b.strip() for b in raw_list if isinstance(b, str) and b.strip()]
            logger.info("Loaded %d bot account names from Bot Comments.rtf.", len(bots))
            return bots
    except (ValueError, SyntaxError) as exc:
        logger.warning("Could not parse bot list from RTF: %s", exc)

    return []


# ---------------------------------------------------------------------------
# BOT ANNOTATION
# ---------------------------------------------------------------------------

def annotate_bot_comments(df: pd.DataFrame, bot_list: list[str]) -> pd.DataFrame:
    """
    Annotate each Yarn issue with bot vs human comment counts.

    This function checks the ``comment_developers`` column.  If that column
    is absent or entirely empty, it logs a warning and returns *df* unchanged.

    Parameters
    ----------
    df:       Yarn DataFrame with at least a ``comment_developers`` column.
    bot_list: List of known bot display names.

    Returns
    -------
    pd.DataFrame  With ``bot_comment_count``, ``human_comment_count``,
                  ``has_bot_comments`` columns populated where possible.
    """
    df = df.copy()

    # Ensure columns exist
    for col in ("bot_comment_count", "human_comment_count", "has_bot_comments"):
        if col not in df.columns:
            df[col] = 0

    if "comment_developers" not in df.columns or df["comment_developers"].eq("").all():
        logger.warning(
            "Column 'comment_developers' is absent or empty. "
            "Cannot determine bot vs human comments. "
            "Enable Jira API enrichment to retrieve comment author data."
        )
        return df

    if not bot_list:
        logger.warning(
            "Bot list is empty; all comments will be counted as human comments."
        )

    # Normalise bot names for case-insensitive matching
    bot_set = {b.lower() for b in bot_list}

    def _count_bots(raw: str) -> tuple[int, int]:
        """Return (bot_count, human_count) given a stringified list of authors."""
        if not raw or raw in ("[]", ""):
            return 0, 0
        try:
            devs: list[str] = ast.literal_eval(raw)
            if not isinstance(devs, list):
                devs = [str(devs)]
        except (ValueError, SyntaxError):
            devs = parse_list_field(raw)

        bots = sum(1 for d in devs if safe_str(d).lower() in bot_set)
        humans = len(devs) - bots
        return bots, humans

    results = df["comment_developers"].apply(_count_bots)
    df["bot_comment_count"] = results.apply(lambda t: t[0])
    df["human_comment_count"] = results.apply(lambda t: t[1])
    df["has_bot_comments"] = df["bot_comment_count"] > 0

    total = len(df)
    issues_with_bots = df["has_bot_comments"].sum()
    logger.info(
        "Bot comment annotation: %d / %d issues have at least one bot comment.",
        issues_with_bots, total,
    )

    return df
