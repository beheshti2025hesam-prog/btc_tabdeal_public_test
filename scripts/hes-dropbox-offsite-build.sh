#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
cd /

ROOT="/opt/hes-trade-agent"
KEY_FILE="/root/.config/hes-backup/passphrase"
OUTDIR="/var/backups/hes-trade-agent/offsite-staging"
LOCK_FILE="/run/lock/hes-dropbox-offsite-build.lock"
MAX_BYTES=$((1792 * 1024 * 1024))
MIN_FREE_KB=$((3 * 1024 * 1024))

exec 9>"$LOCK_FILE"
flock -n 9 || { echo "another offsite build is running"; exit 10; }
[[ -d "$ROOT" && -s "$KEY_FILE" && -d /srv/hes-evidence ]] || { echo "project, evidence store, or encryption key unavailable"; exit 11; }
[[ -L "$ROOT/current" && -L "$ROOT/current-before-4329a3df" ]] || { echo "active/rollback release pointers missing"; exit 12; }

ACTIVE="$(readlink -f "$ROOT/current")"
ROLLBACK="$(readlink -f "$ROOT/current-before-4329a3df")"
case "$ACTIVE" in "$ROOT"/releases/*) ;; *) echo "active release resolves outside releases"; exit 13 ;; esac
case "$ROLLBACK" in "$ROOT"/releases/*) ;; *) echo "rollback release resolves outside releases"; exit 14 ;; esac
[[ -d "$ACTIVE" && -d "$ROLLBACK" ]] || { echo "active/rollback release target missing"; exit 15; }

# Capture reproducible dependency metadata before building the archive.
SNAPSHOT_DIR="$ROOT/docs/checkpoints/offsite-dependency-snapshot"
VENV_PYTHON="$ROOT/.venv/bin/python"
[[ -x "$VENV_PYTHON" ]] || { echo "runtime virtualenv missing; cannot produce dependency snapshot"; exit 18; }
mkdir -p "$SNAPSHOT_DIR"
"$VENV_PYTHON" -m pip freeze --all | sort > "$SNAPSHOT_DIR/python-venv-freeze.txt.tmp"
mv "$SNAPSHOT_DIR/python-venv-freeze.txt.tmp" "$SNAPSHOT_DIR/python-venv-freeze.txt"
dpkg-query -W -f='${db:Status-Status}\t${binary:Package}\t${Version}\n' | awk -F '\t' '$1 == "installed" {print $2 "\t" $3}' | sort > "$SNAPSHOT_DIR/apt-installed-packages.tsv.tmp"
mv "$SNAPSHOT_DIR/apt-installed-packages.tsv.tmp" "$SNAPSHOT_DIR/apt-installed-packages.tsv"
{
  printf 'Captured UTC: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  . /etc/os-release
  printf 'OS: %s %s\n' "$PRETTY_NAME" "${VERSION_ID:-unknown}"
  printf 'Kernel: %s\n' "$(uname -r)"
  printf 'System Python: %s\n' "$(python3 --version 2>&1)"
  printf 'Venv Python: %s\n' "$("$VENV_PYTHON" --version 2>&1)"
  printf 'Venv pip: %s\n' "$("$VENV_PYTHON" -m pip --version)"
  printf 'Virtualenv path: %s\n' "$ROOT/.venv"
} > "$SNAPSHOT_DIR/runtime-platform.txt.tmp"
mv "$SNAPSHOT_DIR/runtime-platform.txt.tmp" "$SNAPSHOT_DIR/runtime-platform.txt"
chmod 0600 "$SNAPSHOT_DIR"/*

mkdir -p "$OUTDIR"
chmod 0700 "$OUTDIR"
avail_kb="$(df -Pk "$OUTDIR" | awk 'NR==2{print $4}')"
[[ "$avail_kb" =~ ^[0-9]+$ ]] && (( avail_kb >= MIN_FREE_KB )) || { echo "insufficient free disk for safe offsite build"; exit 16; }

WORK="$(mktemp -d "$OUTDIR/.build.XXXXXX")"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT
LIST="$WORK/include.list0"
ACTIVE_REL="$(printf '%s' "$ACTIVE" | sed 's#^/##')"
ROLLBACK_REL="$(printf '%s' "$ROLLBACK" | sed 's#^/##')"

# Preserve candidates, worktrees, evidence, journals, archives, hidden workspaces,
# and unknown data. Exclude only historical releases and reproducible Python caches.
# Build an explicit recursive file list, then archive with --no-recursion so
# parent directories cannot accidentally pull excluded historical releases back in.
find opt/hes-trade-agent -mindepth 0 \
  \( -path 'opt/hes-trade-agent/releases' \
     -o -name '.venv' -o -name '__pycache__' -o -name '.pytest_cache' \
     -o -name '.mypy_cache' -o -name '.ruff_cache' \) -prune \
  -o -print0 > "$LIST"

for p in "$ACTIVE_REL" "$ROLLBACK_REL" "opt/hes-trade-agent/releases/deployment-records"; do
  [[ ! -e "/$p" && ! -L "/$p" ]] || find "$p" -mindepth 0 \
    \( -name '.venv' -o -name '__pycache__' -o -name '.pytest_cache' \
       -o -name '.mypy_cache' -o -name '.ruff_cache' \) -prune \
    -o -print0 >> "$LIST"
done

for p in etc/ssh etc/nftables.conf etc/systemd/system etc/hes-trade-agent etc/xray etc/nginx \
         usr/local/sbin/hes-operational-healthcheck \
         usr/local/sbin/hes-runtime-healthcheck \
         usr/local/sbin/hes-encrypted-local-backup srv/hes-evidence; do
  [[ ! -e "/$p" && ! -L "/$p" ]] || find "$p" -mindepth 0 -print0 >> "$LIST"
done

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
base="hes-offsite-core-$stamp.tar.gz.gpg"
tmp="$WORK/$base.partial"
final="$OUTDIR/$base"
[[ ! -e "$final" ]] || { echo "refusing to overwrite existing local archive"; exit 17; }

echo "BUILD_START utc=$stamp"
echo "ACTIVE_RELEASE=$ACTIVE_REL"
echo "ROLLBACK_RELEASE=$ROLLBACK_REL"
echo "MAX_ARCHIVE_BYTES=$MAX_BYTES"
echo "REMOTE_ACTION=NONE"

tar -C / --no-recursion --one-file-system --numeric-owner --xattrs --acls --null --files-from="$LIST" -cf - \
  | gzip -1 \
  | gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 \
      --s2k-mode 3 --s2k-count 65011712 --passphrase-file "$KEY_FILE" --output "$tmp"

chmod 0600 "$tmp"
size="$(stat -c %s "$tmp")"
if (( size > MAX_BYTES )); then
  echo "BUILD_REJECTED size_bytes=$size cap_bytes=$MAX_BYTES"
  exit 30
fi

gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | gzip -t
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | tar -tzf - > "$WORK/archive.list"

grep -Fxq "$ACTIVE_REL/" "$WORK/archive.list" || grep -Fxq "$ACTIVE_REL" "$WORK/archive.list"
grep -Fxq "$ROLLBACK_REL/" "$WORK/archive.list" || grep -Fxq "$ROLLBACK_REL" "$WORK/archive.list"
expected_evidence_entries=$(find /srv/hes-evidence -xdev \( -type f -o -type l \) -printf '%y\n' | wc -l)
archived_evidence_entries=$(awk 'index($0, "srv/hes-evidence/") == 1 && $0 !~ /\/$/ { n++ } END { print n+0 }' "$WORK/archive.list")
grep -Fxq "srv/hes-evidence/" "$WORK/archive.list" || grep -Fxq "srv/hes-evidence" "$WORK/archive.list" || { echo "BUILD_REJECTED evidence_store_missing"; exit 31; }
[[ "$archived_evidence_entries" == "$expected_evidence_entries" ]] || { echo "BUILD_REJECTED evidence_store_incomplete expected=$expected_evidence_entries actual=$archived_evidence_entries"; exit 32; }

mv "$tmp" "$final"
chmod 0600 "$final"
sha256sum "$final" > "$final.sha256"
chmod 0600 "$final.sha256"

cat > "$final.manifest.txt" <<EOF
HES encrypted offsite core backup
Created UTC: $stamp
Archive: $base
Archive bytes: $size
SHA-256: $(sha256sum "$final" | awk '{print $1}')
Active release: $ACTIVE_REL
Rollback release: $ROLLBACK_REL
Required evidence store: /srv/hes-evidence (coverage verified by archive listing).
Included: complete project checkout and data, plus the independent /srv/hes-evidence store, except historical release collection; active and rollback releases included; system SSH, nftables, systemd, /etc/hes-trade-agent runtime configuration, optional xray/nginx and HES operational scripts included.
Dependency evidence: exact Python virtualenv package freeze, Ubuntu platform/Python metadata, and installed apt package inventory are captured under docs/checkpoints/offsite-dependency-snapshot.
Excluded: historical release directories other than active/rollback; Python virtualenv binaries and Python test/lint caches. Rebuild the virtualenv from the archived dependency freeze; reinstall OS packages from the archived apt inventory.
External recovery secret: /root/.config/hes-backup/passphrase is intentionally NOT included and must remain available through the operator's separate secure escrow.
Candidates, worktrees, evidence, journals, project archives, hidden workspaces, and unknown project paths are retained in this offsite bundle.
Encryption: GPG symmetric AES-256; passphrase/key file is NOT included.
Archive builder remote action: NONE; the separate offsite cycle performs transfer and verifies the remote content hash.
EOF
chmod 0600 "$final.manifest.txt"
sha256sum -c "$final.sha256"
echo "BUILD_OK file=$final size_bytes=$size sha256=$(sha256sum "$final" | awk '{print $1}')"
echo "MANIFEST=$final.manifest.txt"
echo "REMOTE_ACTION=NONE"