#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/hes-trade-agent
CODE_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOAK_UNIT=hes-mother-supervisor-soak-20261121-v2.service
SOAK_SUMMARY=/var/lib/hes-mother-supervisor-soak-20261121-v2/mother-supervisor-soak-summary.json

if [[ "$#" -ne 1 ]]; then
  echo "BLOCKED: pass the verified immutable release id" >&2
  exit 2
fi
RELEASE_ID="$1"
if [[ -z "$RELEASE_ID" || ! "$RELEASE_ID" =~ ^[0-9a-f]{40}$ ]]; then
  echo "BLOCKED: pass the verified immutable release id" >&2
  exit 2
fi
if systemctl is-active --quiet "$SOAK_UNIT"; then
  echo "BLOCKED: Mother 24h read-only acceptance soak is still active; canonical journal must remain unchanged" >&2
  exit 3
fi
if [[ ! -s "$SOAK_SUMMARY" ]]; then
  echo "BLOCKED: Mother soak summary is missing" >&2
  exit 4
fi
python3 - "$SOAK_SUMMARY" <<'PY'
import json,sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text())
required=(d.get("status")=="PASS" and d.get("complete") is True
          and d.get("soak_journal_snapshot_unchanged") is True
          and d.get("production_journal_used_for_soak") is False)
if not required:
    raise SystemExit("BLOCKED: Mother soak did not PASS with an unchanged journal")
PY
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
