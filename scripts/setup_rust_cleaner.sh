#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTERNAL_DIR="$REPO_ROOT/external"
CLEANER_REPO="$EXTERNAL_DIR/mining-design-decisions"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

cd "$REPO_ROOT"

mkdir -p "$EXTERNAL_DIR"

if ! command -v rustc >/dev/null 2>&1; then
  if [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
  fi
fi

if ! command -v rustc >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
  # shellcheck disable=SC1091
  . "$HOME/.cargo/env"
fi

if [ ! -d "$CLEANER_REPO/.git" ]; then
  git clone https://github.com/mining-design-decisions/mining-design-decisions.git "$CLEANER_REPO"
else
  git -C "$CLEANER_REPO" pull --ff-only
fi

if [ ! -d "$REPO_ROOT/.venv" ]; then
  "$PYTHON_BIN" -m venv "$REPO_ROOT/.venv"
fi

# shellcheck disable=SC1091
. "$REPO_ROOT/.venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install nltk setuptools-rust contractions gensim

cd "$CLEANER_REPO/deep_learning"
python setup.py build_ext --inplace

echo "Rust cleaner built successfully."
echo "Use: .venv/bin/python scripts/clean_topic_text_with_rust.py"
