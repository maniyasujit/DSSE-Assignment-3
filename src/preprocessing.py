"""
src/preprocessing.py
====================
Text preprocessing for Yarn Jira issues.

Pipeline (per issue)
--------------------
1.  Concatenate ``summary`` + ``description``  → ``raw_text``
2.  Apply the Jira/HTML/code cleaning suite (inspired by:
    https://github.com/mining-design-decisions/mining-design-decisions/tree/main/
    deep_learning/dl_manager/accelerator/src/text_cleaning)
3.  Tokenise
4.  Remove stopwords
5.  Lemmatise (spaCy ``en_core_web_sm``)
6.  Drop short tokens
7.  Store ``cleaned_text`` and ``token_list``

Setup commands (run ONCE before executing the pipeline)
-------------------------------------------------------
    pip install spacy nltk beautifulsoup4
    python -m spacy download en_core_web_sm
    python -c "import nltk; nltk.download('stopwords'); nltk.download('punkt')"

Notes
-----
- The module does NOT download models at runtime.
- If required models are absent, a clear error is raised with the fix command.
- Formatting handling is controlled by ``config.FORMATTING_MODE``:
    * "remove"  — strip all recognised markup/code elements (default)
    * "keep"    — leave them untouched
    * "markers" — replace with token markers (WEBLINK, DATE, etc.)
"""

from __future__ import annotations

import ast
import logging
import re
from typing import Optional

import pandas as pd

from src import config
from src.utils import get_logger, safe_str, save_csv, ensure_dirs

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# MODEL INITIALISATION (lazy; fail fast with clear message)
# ---------------------------------------------------------------------------
_nlp = None
_stop_words: set[str] | None = None


def _get_nlp():
    """Load spaCy model (once). Raises on missing model."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load(config.SPACY_MODEL, disable=["parser", "ner"])
        except OSError:
            raise RuntimeError(
                f"spaCy model '{config.SPACY_MODEL}' not found.\n"
                f"Run:  python -m spacy download {config.SPACY_MODEL}"
            )
    return _nlp


def _get_stop_words() -> set[str]:
    """Load NLTK English stopwords (once). Raises on missing corpus."""
    global _stop_words
    if _stop_words is None:
        try:
            from nltk.corpus import stopwords
            base = set(stopwords.words("english"))
        except LookupError:
            raise RuntimeError(
                "NLTK 'stopwords' corpus not found.\n"
                "Run:  python -c \"import nltk; nltk.download('stopwords')\""
            )
        extra = set(w.lower() for w in config.EXTRA_STOPWORDS)
        noise = set(w.lower() for w in config.JIRA_NOISE_TERMS)
        if config.ENABLE_PROJECT_NOISE_REMOVAL:
            noise.update(w.lower() for w in config.PROJECT_NOISE_TERMS)
        _stop_words = base | extra | noise
    return _stop_words


# ---------------------------------------------------------------------------
# REGEX PATTERNS
# ---------------------------------------------------------------------------
# Jira markup
_RE_JIRA_HEADING = re.compile(r"^h[1-6]\.\s*", re.MULTILINE)
_RE_JIRA_QUOTE = re.compile(r"\{quote\}", re.IGNORECASE)
_RE_JIRA_COLOR = re.compile(r"\{color[^}]*\}", re.IGNORECASE)
_RE_JIRA_TABLE_SEP = re.compile(r"^\|[-|]+\|?\s*$", re.MULTILINE)
_RE_JIRA_LIST_MARKER = re.compile(r"^[\*\-#]+\s+", re.MULTILINE)
_RE_JIRA_BOLD_ITALIC = re.compile(r"[\*_]{1,2}(.*?)[\*_]{1,2}")
_RE_JIRA_PANEL = re.compile(r"\{panel[^}]*\}|\{panel\}", re.IGNORECASE)
_RE_JIRA_ANCHOR = re.compile(r"\{anchor[^}]*\}", re.IGNORECASE)
_RE_JIRA_SECTION = re.compile(r"\{section[^}]*\}|\{section\}", re.IGNORECASE)
_RE_JIRA_COLUMN = re.compile(r"\{column[^}]*\}|\{column\}", re.IGNORECASE)

# Code / technical blocks
_RE_CODE_BLOCK = re.compile(
    r"\{code(?::[^}]*)?\}.*?\{code\}", re.DOTALL | re.IGNORECASE
)
_RE_NOFORMAT_BLOCK = re.compile(
    r"\{noformat(?::[^}]*)?\}.*?\{noformat\}", re.DOTALL | re.IGNORECASE
)
_RE_INLINE_CODE = re.compile(r"\{\{.*?\}\}")

# Links / user mentions / issue refs
_RE_JIRA_USER = re.compile(r"\[~[^\]]+\]")
_RE_JIRA_ISSUE_LINK = re.compile(r"\b[A-Z]+-\d+\b")
_RE_GITHUB_LINK = re.compile(
    r"https?://(?:www\.)?github\.com/[\w\-./]+", re.IGNORECASE
)
_RE_URL = re.compile(
    r"https?://[^\s\]>\"\']+|www\.[^\s\]>\"\']+",
    re.IGNORECASE,
)
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# HTML
_RE_HTML_TAGS = re.compile(r"<[^>]+>")
_RE_HTML_ENTITY = re.compile(r"&[a-zA-Z]+;|&#\d+;")

# Image / file attachments (Jira markup)
_RE_IMAGE_ATTACH = re.compile(r"!([^|!\n]+)(?:\|[^!]*)!|\[([^\]]+\.(?:png|jpg|gif|jpeg|bmp|svg))\]",
                               re.IGNORECASE)
_RE_FILE_ATTACH = re.compile(r"\^([^\]^\n]+\.[a-z]{2,5})\b", re.IGNORECASE)

# Date / IP patterns
_RE_DATE = re.compile(
    r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)
_RE_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_RE_VERSION = re.compile(r"\bv?\d+(?:\.\d+)+(?:[.\-][a-z0-9]+)?\b", re.IGNORECASE)

# Log / traceback noise
_RE_LOG_LINE = re.compile(
    r"^\s*(?:ERROR|WARN|INFO|DEBUG|TRACE|FATAL|EXCEPTION|Caused by:|at\s+[\w.$]+)\b.*$",
    re.MULTILINE,
)
_RE_STACK_TRACE = re.compile(
    r"^\s+at\s+[\w.$]+\([\w.]+(?::\d+)?\)\s*$",
    re.MULTILINE,
)

# Punctuation / special chars
_RE_PUNCT_ONLY_LINE = re.compile(r"^\s*[^a-zA-Z0-9\s]+\s*$", re.MULTILINE)
_RE_SPECIAL = re.compile(r"[^a-zA-Z0-9\s]")
_RE_NUMBERS = re.compile(r"\b\d+\b")
_RE_WHITESPACE = re.compile(r"\s+")

# Technical identifiers (CamelCase, dotted package names, file paths)
_RE_CAMELCASE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")
_RE_DOTTED = re.compile(r"\b\w+(?:\.\w+){2,}\b")
_RE_FILEPATH = re.compile(r"(?:[/\\][\w/\\.]+){2,}")

# Jira-style bracketed links  [text|url]  or  [text]
_RE_JIRA_LINK = re.compile(r"\[([^\]|]+)(?:\|[^\]]+)?\]")


# ---------------------------------------------------------------------------
# MARKER CONSTANTS
# ---------------------------------------------------------------------------
_MARKERS = {
    "url": "WEBLINK",
    "email": "EMAILADDRESS",
    "github": "GITHUBLINK",
    "issue_link": "ISSUELINK",
    "code_block": "STRUCTUREDCODEBLOCK",
    "noformat": "NOFORMATBLOCK",
    "inline_code": "INLINECODESAMPLE",
    "image": "IMAGEATTACHMENT",
    "file": "ATTACHMENT",
    "date": "DATE",
    "ip": "IPADDRESS",
    "version": "VERSIONNUMBER",
    "camelcase": "CLASSNAME",
    "dotted": "PACKAGE",
    "filepath": "FILEPATH",
}


def _sub(pattern: re.Pattern, text: str, marker_key: str) -> str:
    """
    Substitute pattern occurrences according to FORMATTING_MODE.

    * "remove"  → replace with a space
    * "keep"    → leave as-is
    * "markers" → replace with the corresponding marker token
    """
    mode = config.FORMATTING_MODE
    if mode == "keep":
        return text
    replacement = f" {_MARKERS[marker_key]} " if mode == "markers" else " "
    return pattern.sub(replacement, text)


# ---------------------------------------------------------------------------
# CLEANING FUNCTIONS
# ---------------------------------------------------------------------------

def _clean_jira_text(text: str) -> str:
    """
    Apply the full Jira/HTML/code/log cleaning pipeline to a single string.

    Order matters — remove structured blocks first, then inline markup, then
    URLs, then whitespace.
    """
    if not text:
        return ""

    # 1. Code and noformat blocks (before anything else corrupts delimiters)
    text = _sub(_RE_CODE_BLOCK, text, "code_block")
    text = _sub(_RE_NOFORMAT_BLOCK, text, "noformat")
    text = _sub(_RE_INLINE_CODE, text, "inline_code")

    # 2. HTML
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    except ImportError:
        text = _RE_HTML_TAGS.sub(" ", text)
    text = _RE_HTML_ENTITY.sub(" ", text)

    # 3. Image and file attachments
    text = _sub(_RE_IMAGE_ATTACH, text, "image")
    text = _sub(_RE_FILE_ATTACH, text, "file")

    # 4. Jira user mentions
    text = _RE_JIRA_USER.sub(" ", text)

    # 5. GitHub links (before generic URL)
    text = _sub(_RE_GITHUB_LINK, text, "github")

    # 6. Generic URLs
    text = _sub(_RE_URL, text, "url")

    # 7. Email addresses
    text = _sub(_RE_EMAIL, text, "email")

    # 8. Jira issue links (e.g. YARN-1234) — kept as ISSUELINK marker or removed
    text = _sub(_RE_JIRA_ISSUE_LINK, text, "issue_link")

    # 9. Bracketed Jira links [text|url] → keep text
    text = _RE_JIRA_LINK.sub(r"\1", text)

    # 10. Jira headings / formatting markup
    text = _RE_JIRA_HEADING.sub(" ", text)
    text = _RE_JIRA_QUOTE.sub(" ", text)
    text = _RE_JIRA_COLOR.sub(" ", text)
    text = _RE_JIRA_PANEL.sub(" ", text)
    text = _RE_JIRA_ANCHOR.sub(" ", text)
    text = _RE_JIRA_SECTION.sub(" ", text)
    text = _RE_JIRA_COLUMN.sub(" ", text)
    text = _RE_JIRA_TABLE_SEP.sub(" ", text)
    text = _RE_JIRA_LIST_MARKER.sub(" ", text)
    text = _RE_JIRA_BOLD_ITALIC.sub(r"\1", text)

    # 11. Log / traceback lines
    text = _RE_STACK_TRACE.sub(" ", text)
    text = _RE_LOG_LINE.sub(" ", text)

    # 12. Punctuation-only lines
    text = _RE_PUNCT_ONLY_LINE.sub(" ", text)

    # 13. Dates
    if config.FORMATTING_MODE != "keep":
        if config.REPLACE_DATES:
            text = _sub(_RE_DATE, text, "date")
        else:
            text = _RE_DATE.sub(" ", text)

    # 14. IP addresses
    if config.FORMATTING_MODE != "keep":
        if config.REPLACE_IP:
            text = _sub(_RE_IP, text, "ip")
        else:
            text = _RE_IP.sub(" ", text)

    # 15. Version numbers
    text = _sub(_RE_VERSION, text, "version")

    # 16. File paths
    text = _sub(_RE_FILEPATH, text, "filepath")

    # 17. CamelCase class names (flag as CLASSNAME or remove)
    text = _sub(_RE_CAMELCASE, text, "camelcase")

    # 18. Dotted package names
    text = _sub(_RE_DOTTED, text, "dotted")

    return text


# ---------------------------------------------------------------------------
# TOKENISATION & LEMMATISATION
# ---------------------------------------------------------------------------

def _tokenise_and_lemmatise(text: str, nlp, stop_words: set[str]) -> list[str]:
    """
    Tokenise, remove stopwords, lemmatise, and filter short tokens.

    Parameters
    ----------
    text:       Clean, lowercased text.
    nlp:        spaCy Language model.
    stop_words: Combined stopword set.

    Returns
    -------
    list[str]  Filtered, lemmatised token list.
    """
    if not text.strip():
        return []

    doc = nlp(text)
    tokens: list[str] = []

    for token in doc:
        lemma = token.lemma_.lower().strip()

        # Length filter
        if len(lemma) < config.MIN_TOKEN_LENGTH:
            continue
        if len(lemma) > config.MAX_TOKEN_LENGTH:
            continue
        # Alpha only
        if not lemma.isalpha():
            continue
        # Stopwords
        if lemma in stop_words:
            continue
        # POS filter (optional)
        if config.USE_POS and token.pos_ not in ("NOUN", "VERB", "ADJ", "ADV"):
            continue

        tokens.append(lemma)

    return tokens


# ---------------------------------------------------------------------------
# PER-ISSUE PREPROCESSING
# ---------------------------------------------------------------------------

def preprocess_issue(
    summary: str,
    description: str,
    nlp,
    stop_words: set[str],
) -> dict[str, str | list[str]]:
    """
    Preprocess a single Jira issue.

    Parameters
    ----------
    summary:     Issue summary text.
    description: Issue description text.
    nlp:         Loaded spaCy model.
    stop_words:  Combined stopword set.

    Returns
    -------
    dict with keys: raw_text, cleaned_text, token_list
    """
    # 1. Concatenate
    raw_text = f"{safe_str(summary)} {safe_str(description)}".strip()

    if not raw_text:
        return {"raw_text": "", "cleaned_text": "", "token_list": "[]"}

    # 2. Clean
    cleaned = _clean_jira_text(raw_text)

    # 3. Lowercase
    if config.LOWERCASE:
        cleaned = cleaned.lower()

    # 4. Remove punctuation and numbers
    cleaned = _RE_SPECIAL.sub(" ", cleaned)
    cleaned = _RE_NUMBERS.sub(" ", cleaned)

    # 5. Normalise whitespace
    cleaned = _RE_WHITESPACE.sub(" ", cleaned).strip()

    # 6. Tokenise + lemmatise
    tokens = _tokenise_and_lemmatise(cleaned, nlp, stop_words)

    # 7. Optional ontology replacement
    if config.ENABLE_ONTOLOGY_REPLACEMENT:
        tokens = [config.ONTOLOGY_MAP.get(t, t) for t in tokens]

    cleaned_text = " ".join(tokens)

    return {
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "token_list": str(tokens),
    }


# ---------------------------------------------------------------------------
# DATAFRAME-LEVEL PREPROCESSING
# ---------------------------------------------------------------------------

def preprocess_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply text preprocessing to all Yarn issues in *df*.

    Expects columns: ``summary``, ``description``.
    Produces columns: ``raw_text``, ``cleaned_text``, ``token_list``.

    Parameters
    ----------
    df: Yarn DataFrame (from parent_extractor or data_loader).

    Returns
    -------
    pd.DataFrame  With preprocessing columns added, saved to CSV.
    """
    df = df.copy()

    # ------------------------------------------------------------------
    # Validate / fill text columns
    # ------------------------------------------------------------------
    for col in ("summary", "description"):
        if col not in df.columns:
            df[col] = ""
            logger.warning(
                "Column '%s' is missing. Preprocessing will produce empty tokens. "
                "Enable Jira API enrichment to retrieve text data.",
                col,
            )
        else:
            df[col] = df[col].apply(safe_str)

    # ------------------------------------------------------------------
    # Load models (fail fast with clear message)
    # ------------------------------------------------------------------
    nlp = _get_nlp()
    stop_words = _get_stop_words()
    logger.info(
        "Preprocessing %d issues with spaCy model '%s'.",
        len(df), config.SPACY_MODEL,
    )

    # ------------------------------------------------------------------
    # Apply per-issue preprocessing
    # ------------------------------------------------------------------
    from tqdm import tqdm  # type: ignore

    results = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Preprocessing"):
        result = preprocess_issue(
            summary=safe_str(row.get("summary", "")),
            description=safe_str(row.get("description", "")),
            nlp=nlp,
            stop_words=stop_words,
        )
        results.append(result)

    results_df = pd.DataFrame(results, index=df.index)
    df["raw_text"] = results_df["raw_text"]
    df["cleaned_text"] = results_df["cleaned_text"]
    df["token_list"] = results_df["token_list"]

    # ------------------------------------------------------------------
    # Log statistics
    # ------------------------------------------------------------------
    non_empty = (df["cleaned_text"].str.strip() != "").sum()
    logger.info(
        "Preprocessing complete: %d / %d issues have non-empty cleaned text.",
        non_empty, len(df),
    )

    if non_empty == 0:
        logger.warning(
            "All cleaned_text values are empty. "
            "This is expected when Jira API enrichment is disabled "
            "(summary and description columns are empty). "
            "Enable ENABLE_JIRA_API in config.py to retrieve text data."
        )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    ensure_dirs(config.PROCESSED_DIR)
    save_csv(df, config.YARN_CLEANED_CSV, label="yarn_issues_cleaned")

    return df
