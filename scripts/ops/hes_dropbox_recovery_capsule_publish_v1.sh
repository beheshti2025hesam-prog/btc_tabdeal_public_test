#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ARCHIVE=${1:?usage: publish-capsule.sh /path/to/archive.tar.zst.gpg}
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
echo "CAPSULE_PUBLISH_OK name=$name bytes=$bytes"; echo REMOTE_DELETE=NONE
