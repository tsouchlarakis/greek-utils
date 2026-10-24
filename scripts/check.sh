#!/usr/bin/env bash
# Repo gate: tests, plus lint on the code that is held to it (the reader package and
# the CLI entry point; older modules predate the lint setup).
set -euo pipefail
cd "$(dirname "$0")/.."
uv run pytest -q
uv run ruff check greek_utils/reader greek_utils/cli.py tests
