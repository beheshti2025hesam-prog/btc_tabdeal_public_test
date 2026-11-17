#!/usr/bin/env bash
set -euo pipefail

STATE_DIR=/var/lib/hes-news-monitor
KEY_FILE="$STATE_DIR/hoshyar-llm-api-keys"

if [[ ! -d "$STATE_DIR" ]]; then
  install -d -o sentinelx -g sentinelx -m 0750 "$STATE_DIR"
fi

if [[ -L "$STATE_DIR" ]]; then
  echo "ERROR: state directory must not be a symlink" >&2
  exit 1
fi

if [[ -e "$KEY_FILE" || -L "$KEY_FILE" ]]; then
  [[ ! -L "$KEY_FILE" ]] || { echo "ERROR: API key path must not be a symlink" >&2; exit 1; }
  [[ -f "$KEY_FILE" ]] || { echo "ERROR: API key path must be a regular file" >&2; exit 1; }
  [[ -s "$KEY_FILE" ]] || { echo "ERROR: existing HOSHYAR API key file is empty; refusing to overwrite" >&2; exit 1; }
  [[ "$(stat -c '%a' "$KEY_FILE")" == "600" ]] || { echo "ERROR: existing HOSHYAR API key file must be mode 0600; review manually" >&2; exit 1; }
  [[ "$(stat -c '%U:%G' "$KEY_FILE")" == "sentinelx:sentinelx" ]] || { echo "ERROR: existing HOSHYAR API key file owner must be sentinelx:sentinelx" >&2; exit 1; }
else
  umask 077
  python3 - <<'PY' > "$KEY_FILE"
import secrets
print(secrets.token_urlsafe(48))
PY
  chown sentinelx:sentinelx "$KEY_FILE"
  chmod 0600 "$KEY_FILE"
fi

printf 'HOSHYAR_LOCAL_API_KEY_READY\n'
