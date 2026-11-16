from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "hes_dropbox_offsite_build_v2.sh"


def test_offsite_builder_covers_recovery_critical_host_configuration_and_state():
    text = SCRIPT.read_text()
    required = (
        "etc/ufw",
        "etc/netplan",
        "etc/apt",
        "etc/sentinelx",
        "etc/hes-trade-agent",
        "etc/sysctl.d",
        "etc/modules-load.d",
        "etc/fstab",
        "etc/hosts",
        "etc/hostname",
        "var/lib/dpkg/status",
        "var/lib/apt/extended_states",
        "var/lib/hes-operational-health",
        "var/lib/systemd",
        "root/.ssh",
        "root/.config/rclone",
    )
    for path in required:
        assert path in text
    include_block = text.split("for p in etc/ssh", 1)[1].split("; do", 1)[0]
    assert "root/.config/hes-backup" not in include_block


def test_offsite_builder_keeps_remote_transfer_out_of_build_step():
    text = SCRIPT.read_text()
    assert "REMOTE_ACTION=NONE" in text
    assert "rclone copy" not in text
    assert "rclone copyto" not in text


def test_local_and_offsite_v2_recovery_scopes_cover_same_host_state():
    local = (ROOT / "scripts" / "ops" / "hes_encrypted_local_backup_v2.sh").read_text()
    offsite = SCRIPT.read_text()
    required = (
        "etc/sudoers",
        "etc/sudoers.d",
        "etc/cron.d",
        "etc/cron.daily",
        "etc/cron.hourly",
        "etc/cron.weekly",
        "etc/logrotate.d",
        "etc/security",
        "etc/environment",
        "etc/cloud",
        "etc/network",
        "var/spool/cron/crontabs",
        "var/lib/cloud",
        "var/lib/sentinelx/audit.jsonl",
        "var/lib/sentinelx/hes-runtime-snapshots",
        "var/lib/sentinelx/hes-release-manifests",
        "var/lib/sentinelx/hes-release-live-replay-8e31",
    )
    for path in required:
        assert path in local
        assert path in offsite
