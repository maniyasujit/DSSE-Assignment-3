"""
src/config.py
=============
Central configuration for the YARN Jira Issue Mining pipeline (Week 1).

All paths, flags, and tuning parameters live here.
Secrets (Jira credentials) are loaded from a .env file ONLY when
ENABLE_JIRA_API is True.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# ROOT PATHS
# ---------------------------------------------------------------------------
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = ROOT_DIR / "data"
SRC_DIR: Path = ROOT_DIR / "src"

# Input files
ISSUES_XLSX: Path = ROOT_DIR / "Issues.xlsx"
BOT_COMMENTS_RTF: Path = ROOT_DIR / "Bot Comments.rtf"

# Raw outputs
RAW_DIR: Path = DATA_DIR / "raw"
YARN_RAW_CSV: Path = RAW_DIR / "yarn_issues_raw.csv"
YARN_ENRICHED_CSV: Path = RAW_DIR / "yarn_issues_enriched.csv"

# Processed outputs
PROCESSED_DIR: Path = DATA_DIR / "processed"
YARN_STRUCTURED_CSV: Path = PROCESSED_DIR / "yarn_issues_structured.csv"
YARN_PARENTS_CSV: Path = PROCESSED_DIR / "yarn_issues_with_parents.csv"
YARN_CLEANED_CSV: Path = PROCESSED_DIR / "yarn_issues_cleaned.csv"

# Final outputs
OUTPUT_DIR: Path = DATA_DIR / "output"
YARN_VOCAB_CSV: Path = OUTPUT_DIR / "yarn_vocabulary.csv"
YARN_TOP20_CSV: Path = OUTPUT_DIR / "yarn_top_20_tokens.csv"
YARN_TOP50_CSV: Path = OUTPUT_DIR / "yarn_top_50_tokens.csv"
YARN_TOP100_CSV: Path = OUTPUT_DIR / "yarn_top_100_tokens.csv"
YARN_TOP20_PNG: Path = OUTPUT_DIR / "yarn_top_20_terms.png"
YARN_TOP50_PNG: Path = OUTPUT_DIR / "yarn_top_50_terms.png"
YARN_VOCAB_FLAGS_CSV: Path = OUTPUT_DIR / "yarn_vocabulary_flags.csv"
YARN_DTM_CSV: Path = OUTPUT_DIR / "yarn_document_term_matrix.csv"
YARN_DTM_SPARSE: Path = OUTPUT_DIR / "yarn_document_term_matrix_sparse.npz"
YARN_DTM_FEATURES_CSV: Path = OUTPUT_DIR / "yarn_dtm_features.csv"

# ---------------------------------------------------------------------------
# PROJECT SETTINGS
# ---------------------------------------------------------------------------
PROJECT_NAME: str = "YARN"

# Sheet name in Issues.xlsx to use for YARN issues.
# Set to None to auto-detect (picks the sheet named "Yarn" or "YARN").
SHEET_NAME: str | None = "Yarn"

# ---------------------------------------------------------------------------
# JIRA API ENRICHMENT
# ---------------------------------------------------------------------------
# Set to True to enable live Jira API enrichment.
# When False, the pipeline runs on xlsx data only (metadata columns empty).
ENABLE_JIRA_API: bool = True

# Whether to overwrite valid xlsx values with API values.
JIRA_API_OVERWRITE: bool = False

# Load Jira secrets from .env only when API is enabled.
if ENABLE_JIRA_API:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT_DIR / ".env")
    except ImportError:
        pass  # python-dotenv not installed; secrets must be set as env vars.

JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", "")
JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")

# ---------------------------------------------------------------------------
# TEXT PREPROCESSING
# ---------------------------------------------------------------------------
# Formatting handling mode: "remove" | "keep" | "markers"
#   remove  — strip all recognised technical/Jira elements (default)
#   keep    — leave them as-is
#   markers — replace with token markers (WEBLINK, DATE, etc.)
FORMATTING_MODE: str = "remove"   # "remove" | "keep" | "markers"

LOWERCASE: bool = True
REMOVE_STOPWORDS: bool = True
LEMMATIZE: bool = True
STEM: bool = False            # stemming is an alternative to lemmatisation
USE_POS: bool = False         # filter tokens by part-of-speech if True
MIN_TOKEN_LENGTH: int = 3     # drop tokens shorter than this
MAX_TOKEN_LENGTH: int = 50    # drop tokens longer than this (junk identifiers)

# Replace dates with DATE marker (only active when FORMATTING_MODE == "markers")
REPLACE_DATES: bool = True
# Replace IP addresses with IPADDRESS marker
REPLACE_IP: bool = True

# spaCy model to use for lemmatisation
SPACY_MODEL: str = "en_core_web_sm"

# ---------------------------------------------------------------------------
# STOPWORDS
# ---------------------------------------------------------------------------
# Extra stopwords appended to NLTK's English stopwords list.
EXTRA_STOPWORDS: list[str] = [
    "also", "would", "could", "should", "may", "might",
    "must", "shall", "use", "used", "using", "need",
    "get", "got", "set", "run", "runs", "running",
    "one", "two", "per", "via", "etc", "e.g", "i.e",
    "like", "make", "makes", "made", "let", "lets",
    "new", "old", "see", "seen", "note", "noted",
]

# Jira-specific noise tokens to remove after tokenisation.
JIRA_NOISE_TERMS: list[str] = [
    "jira", "apache", "hadoop", "ticket", "issue",
    "fix", "fixed", "patch", "patches", "review",
    "reviewed", "commit", "committed", "revert",
    "reverted", "merge", "merged", "branch", "trunk",
    "version", "release", "released", "update",
    "updated", "attach", "attached", "link", "linked",
    "comment", "commented", "created", "closed",
    "resolved", "reopened", "open", "status", "summary",
    "description", "assignee", "reporter", "priority",
    "watcher", "vote", "block", "blocked",
]

# Project-specific noise terms (optional — only removed if enabled).
ENABLE_PROJECT_NOISE_REMOVAL: bool = False
PROJECT_NOISE_TERMS: list[str] = [
    "yarn", "hadoop",
]

# ---------------------------------------------------------------------------
# ONTOLOGY REPLACEMENT
# ---------------------------------------------------------------------------
# Set to True to apply token → ontology-class substitution.
ENABLE_ONTOLOGY_REPLACEMENT: bool = False

# Ontology mapping: token → ontology class label.
# These are additive; edit freely.
ONTOLOGY_MAP: dict[str, str] = {
    # Component
    "class": "COMPONENT", "method": "COMPONENT",
    "service": "COMPONENT", "module": "COMPONENT",
    "component": "COMPONENT", "package": "COMPONENT",
    "application": "COMPONENT", "framework": "COMPONENT",
    "library": "COMPONENT", "interface": "COMPONENT",
    "nodemanager": "COMPONENT", "resourcemanager": "COMPONENT",
    "applicationmaster": "COMPONENT",
    # Connector
    "send": "CONNECTOR", "write": "CONNECTOR",
    "retrieve": "CONNECTOR", "call": "CONNECTOR",
    "connect": "CONNECTOR", "request": "CONNECTOR",
    "response": "CONNECTOR", "communicate": "CONNECTOR",
    "transfer": "CONNECTOR",
    # Data
    "object": "DATA", "message": "DATA",
    "file": "DATA", "data": "DATA",
    "record": "DATA", "block": "DATA",
    "container": "DATA", "log": "DATA",
    "configuration": "DATA",
    # Quality Attribute
    "performance": "QUALITY_ATTR", "latency": "QUALITY_ATTR",
    "security": "QUALITY_ATTR", "authentication": "QUALITY_ATTR",
    "availability": "QUALITY_ATTR", "reliability": "QUALITY_ATTR",
    "scalability": "QUALITY_ATTR", "fault": "QUALITY_ATTR",
    "failure": "QUALITY_ATTR", "recovery": "QUALITY_ATTR",
}

# Yarn/Hadoop-specific terms to FLAG (not remove) in vocabulary analysis.
YARN_SPECIFIC_TERMS: list[str] = [
    "yarn", "hadoop", "container", "nodemanager",
    "resourcemanager", "applicationmaster", "scheduler",
    "queue", "capacityscheduler", "fairscheduler",
    "application", "cluster",
]

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOG_LEVEL: str = "INFO"   # DEBUG | INFO | WARNING | ERROR
LOG_FILE: Path | None = ROOT_DIR / "pipeline.log"  # None = console only
