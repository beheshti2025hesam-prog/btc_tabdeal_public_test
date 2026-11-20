#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BUILD=/usr/local/sbin/hes-dropbox-recovery-capsule-build
PUBLISH=/usr/local/sbin/hes-dropbox-recovery-capsule-publish
OUT=/var/backups/hes-trade-agent/offsite-staging
LOGDIR=/var/log/hes-trade-agent
mkdir -p "$LOGDIR"; chmod 0700 "$LOGDIR"
LOG="$LOGDIR/dropbox-recovery-capsule-cycle.log"
BUILD_LOG=$(mktemp "$OUT/.capsule-build.XXXXXX")
trap 'rm -f "$BUILD_LOG"' EXIT
"$BUILD" 2>&1 | tee -a "$BUILD_LOG" | tee -a "$LOG"
ARCHIVE=$(awk '/^CAPSULE_BUILD_OK /{for(i=1;i<=NF;i++) if($i ~ /^file=/){sub(/^file=/,"",$i);print $i}}' "$BUILD_LOG" | tail -1)
[[ -s "$ARCHIVE" ]] || { echo 'CAPSULE_CYCLE_ARCHIVE_NOT_FOUND' | tee -a "$LOG"; exit 30; }
"$PUBLISH" --rotate "$ARCHIVE" 2>&1 | tee -a "$LOG"
mapfile -t LOCAL_CAPSULES < <(find "$OUT" -maxdepth 1 -type f -name 'hes-recovery-capsule-*.tar.zst.gpg' -printf '%f\n' | sort -r)
for ((i=7;i<${#LOCAL_CAPSULES[@]};i++)); do
  f=${LOCAL_CAPSULES[$i]}
  [[ "$f" =~ ^hes-recovery-capsule-[0-9]{8}T[0-9]{6}Z\.tar\.zst\.gpg$ ]] || exit 31
  rm -f -- "$OUT/$f" "$OUT/$f.sha256" "$OUT/$f.manifest.txt"
  echo "CAPSULE_LOCAL_ROTATED_OLD_VERSION=$f" | tee -a "$LOG"
done
echo 'CAPSULE_CYCLE_OK' | tee -a "$LOG"
