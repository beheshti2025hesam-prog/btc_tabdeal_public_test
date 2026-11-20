#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MODE=${1:-}
ARCHIVE=${2:?usage: publish-capsule.sh [--rotate] /path/to/archive.tar.zst.gpg}
KEY=/root/.config/hes-backup/passphrase
REMOTE='hesdropbox:HES Trade Agent Backups/recovery-capsules'
RESERVE=$((128*1024*1024))
[[ -s "$ARCHIVE" && -s "$ARCHIVE.sha256" && -s "$ARCHIVE.manifest.txt" && -s "$KEY" ]] || exit 10
(cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256")
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY" --decrypt "$ARCHIVE" 2>/dev/null | zstd -t -q
bytes=$(stat -c %s "$ARCHIVE"); ((bytes<64*1024*1024)) || exit 11
quota=$(rclone about hesdropbox: --json)
free=$(printf '%s' "$quota" | python3 -c 'import json,sys;print(int(json.load(sys.stdin)["free"]))')
((free>=bytes+RESERVE)) || { echo "CAPSULE_PUBLISH_QUOTA_BLOCK free=$free bytes=$bytes reserve=$RESERVE"; exit 12; }
name=$(basename "$ARCHIVE")
rclone copyto "$ARCHIVE" "$REMOTE/$name" --immutable
rclone copyto "$ARCHIVE.sha256" "$REMOTE/$name.sha256" --immutable
rclone copyto "$ARCHIVE.manifest.txt" "$REMOTE/$name.manifest.txt" --immutable
rclone check "$(dirname "$ARCHIVE")" "$REMOTE" --include "$name" --include "$name.sha256" --include "$name.manifest.txt" --checkers 2

VERIFY=$(mktemp -d /run/hes-capsule-remote-verify.XXXXXX)
trap 'rm -rf -- "$VERIFY"' EXIT
rclone copyto "$REMOTE/$name" "$VERIFY/$name"
rclone copyto "$REMOTE/$name.sha256" "$VERIFY/$name.sha256"
rclone copyto "$REMOTE/$name.manifest.txt" "$VERIFY/$name.manifest.txt"
(cd "$VERIFY" && sha256sum -c "$name.sha256")
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY" --decrypt "$VERIFY/$name" 2>/dev/null | zstd -t -q
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY" --decrypt "$VERIFY/$name" 2>/dev/null | zstd -dc -q | tar -tf - > "$VERIFY/$name.list"
grep -q '^opt/hes-trade-agent/releases/' "$VERIFY/$name.list"
echo "CAPSULE_REMOTE_READBACK_PASS name=$name bytes=$bytes"

if [[ "$MODE" == "--rotate" ]]; then
  mapfile -t CAPSULES < <(rclone lsf --files-only "$REMOTE" | grep -E '^hes-recovery-capsule-[0-9]{8}T[0-9]{6}Z\.tar\.zst\.gpg$' | sort -r)
  KEEP=${#CAPSULES[@]}
  ((KEEP>2)) && KEEP=2
  for ((i=0;i<KEEP;i++)); do
    f=${CAPSULES[$i]}
    [[ -n "$f" ]] || exit 20
    for suffix in "" ".sha256" ".manifest.txt"; do
      rclone copyto "$REMOTE/$f$suffix" "$VERIFY/$f$suffix"
    done
    (cd "$VERIFY" && sha256sum -c "$f.sha256")
    gpg --batch --pinentry-mode loopback --passphrase-file "$KEY" --decrypt "$VERIFY/$f" 2>/dev/null | zstd -t -q
    gpg --batch --pinentry-mode loopback --passphrase-file "$KEY" --decrypt "$VERIFY/$f" 2>/dev/null | zstd -dc -q | tar -tf - > "$VERIFY/$f.list"
    grep -q '^opt/hes-trade-agent/releases/' "$VERIFY/$f.list"
  done
  for ((i=2;i<${#CAPSULES[@]};i++)); do
    f=${CAPSULES[$i]}
    [[ "$f" =~ ^hes-recovery-capsule-[0-9]{8}T[0-9]{6}Z\.tar\.zst\.gpg$ ]] || exit 21
    rclone deletefile "$REMOTE/$f"
    rclone deletefile "$REMOTE/$f.sha256"
    rclone deletefile "$REMOTE/$f.manifest.txt"
    echo "CAPSULE_ROTATED_OLD_VERSION=$f"
  done
fi
echo "CAPSULE_PUBLISH_OK name=$name bytes=$bytes"
echo 'REMOTE_DELETE_SCOPE=VERSIONED_RECOVERY_CAPSULES_ONLY'
