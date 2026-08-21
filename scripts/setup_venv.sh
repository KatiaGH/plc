#!/usr/bin/env bash
# Create .venv in the project root and install this package in editable mode.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON="${PYTHON:-python3}"

cd "${ROOT_DIR}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "error: ${PYTHON} not found. Install Python 3.10+ or set PYTHON." >&2
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating virtual environment at ${VENV_DIR}"
  "${PYTHON}" -m venv "${VENV_DIR}"
else
  echo "Using existing virtual environment at ${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

echo
echo "Virtual environment is ready."
echo "Activate it with:"
echo "  source ${VENV_DIR}/bin/activate"
