#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/hes-trade-agent
CODE_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOAK_UNIT=hes-mother-supervisor-soak-20261122-v1.service
SOAK_SUMMARY=/var/lib/hes-mother-supervisor-soak-20261122-v1/mother-supervisor-soak-summary.json
SOAK_SOURCE_ROOT=/opt/hes-trade-agent/.worktrees/mother-supervisor-v1-20261117

if [[ "$#" -ne 1 ]]; then
  echo "BLOCKED: pass the verified immutable release id" >&2
  exit 2
fi
RELEASE_ID="$1"
if [[ -z "$RELEASE_ID" || ! "$RELEASE_ID" =~ ^[0-9a-f]{40}$ ]]; then
  echo "BLOCKED: pass the verified immutable release id" >&2
  exit 2
fi
if systemctl is-active --quiet "$SOAK_UNIT" 2>/dev/null; then
  echo "BLOCKED: Mother 24h read-only acceptance soak is still active" >&2
  exit 3
fi
if [[ ! -s "$SOAK_SUMMARY" ]]; then
  echo "BLOCKED: Mother soak summary is missing" >&2
  exit 4
fi
if systemctl show "$SOAK_UNIT" -p ActiveState --value >/dev/null 2>&1; then
  SOAK_ACTIVE_STATE="$(systemctl show "$SOAK_UNIT" -p ActiveState --value)"
  SOAK_RESULT="$(systemctl show "$SOAK_UNIT" -p Result --value)"
  SOAK_WORKDIR="$(systemctl show "$SOAK_UNIT" -p WorkingDirectory --value)"
  SOAK_ENV="$(systemctl show "$SOAK_UNIT" -p Environment --value)"
  SOAK_EXEC="$(systemctl show "$SOAK_UNIT" -p ExecStart --value)"
  if [[ "$SOAK_ACTIVE_STATE" != "inactive" || "$SOAK_RESULT" != "success" ]]; then
    echo "BLOCKED: retained Mother soak unit did not finish successfully" >&2
    exit 4
  fi
  if [[ "$SOAK_WORKDIR" != "$SOAK_SOURCE_ROOT" || "$SOAK_ENV" != *"PYTHONPATH=$SOAK_SOURCE_ROOT"* ]]; then
    echo "BLOCKED: Mother soak source path does not match the frozen candidate" >&2
    exit 4
  fi
  if [[ "$SOAK_EXEC" != *"scripts/ops/mother_supervisor_soak_v1.py"* ||
        "$SOAK_EXEC" != *"--duration-seconds 86400"* ||
        "$SOAK_EXEC" != *"--interval-seconds 300"* ||
        "$SOAK_EXEC" != *"--journal /opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl"* ]]; then
    echo "BLOCKED: Mother soak command does not match the frozen 24-hour read-only contract" >&2
    exit 4
  fi
else
  echo "NOTICE: completed transient soak unit metadata was collected; validating the durable summary and pinned source tree instead"
fi
# The activation path runs as root while the frozen source worktree belongs to sentinelx.
# Mark only this exact worktree as safe for Git's ownership check.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=safe.directory
export GIT_CONFIG_VALUE_0="$SOAK_SOURCE_ROOT"
python3 "$CODE_ROOT/scripts/ops/mother_soak_acceptance_gate_v1.py" \
  --summary "$SOAK_SUMMARY" --source-root "$SOAK_SOURCE_ROOT"
RELEASE="$ROOT/releases/$RELEASE_ID"
if [[ "$CODE_ROOT" != "$RELEASE" ]]; then
  echo "BLOCKED: activation script must run from the exact immutable release" >&2
  exit 5
fi
test -f "$RELEASE/scripts/ops/mother_decision_journal_writer_v1.py"
test -f "$ROOT/data/forward/trade_journal_v2.jsonl"
LOCK="$ROOT/data/forward/trade_journal_v2.jsonl.lock"
if [[ ! -e "$LOCK" ]]; then
  install -o sentinelx -g sentinelx -m 0600 /dev/null "$LOCK"
fi
chown sentinelx:sentinelx "$LOCK"
sed "s/REPLACE_RELEASE_ID/$RELEASE_ID/g" "$CODE_ROOT/deploy/systemd/hes-mother-decision-journal-writer.service" > /etc/systemd/system/hes-mother-decision-journal-writer.service
install -o root -g root -m 0644 "$CODE_ROOT/deploy/systemd/hes-mother-decision-journal-writer.timer" /etc/systemd/system/hes-mother-decision-journal-writer.timer
systemctl daemon-reload
systemctl enable --now hes-mother-decision-journal-writer.timer
echo "ACTIVATED: release=$RELEASE_ID timer=enabled"
