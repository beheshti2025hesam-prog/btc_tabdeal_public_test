#!/usr/bin/env bash
# Canonical, offline-safe HES regression gate. Does not start collectors or services.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHONPYCACHEPREFIX="$(mktemp -d "${TMPDIR:-/tmp}/hes-regression-pycache.XXXXXX")"
export PYTHONPYCACHEPREFIX
trap 'rm -rf "$PYTHONPYCACHEPREFIX"' EXIT

printf '%s\n' '=== HES REGRESSION GATE: BYTECODE / SYNTAX ==='
"$PYTHON_BIN" -m compileall -q core forward scripts tests

printf '%s\n' '=== HES REGRESSION GATE: WORKFLOW SUPPLY-CHAIN POLICY ==='
"$PYTHON_BIN" scripts/check_workflow_action_pins.py

printf '%s\n' '=== HES REGRESSION GATE: FULL TEST SUITE (WARNINGS ARE ERRORS) ==='
"$PYTHON_BIN" -m pytest -q -W error

printf '%s\n' 'HES_REGRESSION_GATE=PASS'
printf '%s\n' 'LIVE_EXECUTION=OFF (this gate never starts trading services)'
