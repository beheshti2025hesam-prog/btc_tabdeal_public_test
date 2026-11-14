#!/usr/bin/env python3
"""Dependency-aware, fail-closed Smart Cleanup Manager (audit/planner only).

Consumes the existing IDLM v1 inventory. It has no delete, move, truncate,
compression, rotation, or service-mutation path. Unknown means KEEP.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import pwd
from pathlib import Path
import shutil
import shlex
import stat
import subprocess
import tempfile
import re
from typing import Any

PROJECT_ROOT = Path("/opt/hes-trade-agent")
ACTIVE_POINTERS = (PROJECT_ROOT / "current", PROJECT_ROOT / "current-before-4329a3df")
PROTECTED_PREFIXES = ("KEEP_",)
REVIEWABLE_CLASSES = {"REVIEW_STALE_TEMP", "REVIEW_TEMP", "REVIEW_REGENERABLE_CACHE", "REVIEW_SYSTEM_LOG_RETENTION", "REVIEW_LOG_POLICY"}


def _under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((os.path.abspath(path), os.path.abspath(root))) == os.path.abspath(root)
    except (ValueError, OSError):
        return False


def _proc_references() -> tuple[list[dict[str, Any]], int]:
    """Collect live process cwd/root/fd paths without following candidate symlinks."""
    refs: list[dict[str, Any]] = []
    errors = 0
    proc = Path("/proc")
    try:
        pids = [p for p in proc.iterdir() if p.name.isdigit()]
    except OSError:
        return refs, 1
    for entry in pids:
        pid = entry.name
        try:
            comm = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()[:120]
        except OSError:
            comm = "unknown"
        for kind in ("cwd", "root"):
            try:
                target = os.readlink(entry / kind)
                if target.startswith("/"):
                    refs.append({"pid": int(pid), "comm": comm, "kind": kind, "path": target.removesuffix(" (deleted)")})
            except FileNotFoundError:
                pass
            except PermissionError:
                errors += 1
            except OSError:
                pass
        fd_dir = entry / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except FileNotFoundError:
            continue
        except PermissionError:
            errors += 1
            continue
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
                if target.startswith("/"):
                    refs.append({"pid": int(pid), "comm": comm, "kind": "fd", "path": target.removesuffix(" (deleted)")})
            except FileNotFoundError:
                pass
            except PermissionError:
                errors += 1
            except OSError:
                pass
    return refs, errors


def _expand_systemd_path_reference(unit: str, key: str, value: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    if value.strip():
        refs.append({"unit": unit, "property": key, "value": value[:2000]})
    bases = {
        "StateDirectory": "/var/lib",
        "CacheDirectory": "/var/cache",
        "LogsDirectory": "/var/log",
        "RuntimeDirectory": "/run",
    }
    base = bases.get(key)
    if base:
        for raw_name in value.split():
            name = raw_name.split(":", 1)[0]
            if not name:
                continue
            resolved = name if name.startswith("/") else str(Path(base) / name)
            refs.append({"unit": unit, "property": key + "_resolved", "value": resolved})
    return refs


def _is_concrete_systemd_unit(unit: str) -> bool:
    return not unit.endswith(("@.service", "@.timer"))


def _systemd_references() -> tuple[list[dict[str, str]], int]:
    """Inspect running units and enabled service/timer declarations for path dependencies."""
    refs: list[dict[str, str]] = []
    errors = 0
    unit_names: set[str] = set()
    listing_commands = (
        ["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--plain"],
        ["systemctl", "list-units", "--type=timer", "--state=active", "--no-legend", "--plain"],
        ["systemctl", "list-unit-files", "--type=service", "--state=enabled", "--no-legend", "--no-pager"],
        ["systemctl", "list-unit-files", "--type=timer", "--state=enabled", "--no-legend", "--no-pager"],
    )
    for command in listing_commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            errors += 1
            continue
        if result.returncode != 0:
            errors += 1
            continue
        for line in result.stdout.splitlines():
            fields = line.split()
            if fields and fields[0].endswith((".service", ".timer")) and _is_concrete_systemd_unit(fields[0]):
                unit_names.add(fields[0])
    properties = "ExecStart,ExecStartPre,ExecStartPost,WorkingDirectory,EnvironmentFiles,ReadWritePaths,ReadOnlyPaths,RequiresMountsFor,BindPaths,BindReadOnlyPaths,RootDirectory,RootImage,InaccessiblePaths,TemporaryFileSystem,ConditionPathExists,ConditionPathIsDirectory,StateDirectory,CacheDirectory,LogsDirectory,RuntimeDirectory"
    for unit in sorted(unit_names):
        try:
            result = subprocess.run(
                ["systemctl", "show", unit, f"--property={properties}"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            errors += 1
            continue
        if result.returncode != 0:
            errors += 1
            continue
        for prop in result.stdout.splitlines():
            key, _, value = prop.partition("=")
            refs.extend(_expand_systemd_path_reference(unit, key, value))
    return refs, errors


def _register_scheduled_file(
    path: Path, kind: str, home: str | None, username: str | None,
    files: dict[Path, tuple[str, str | None, str | None]], refs: list[dict[str, str]],
) -> int:
    """Register regular jobs and safely inspect symlinked cron/config entries."""
    try:
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_file():
                refs.append({"unit": str(path), "property": kind + "_unresolved_symlink", "value": str(path)})
                return 1
            files[target] = (kind, home, username)
            refs.append({"unit": str(path), "property": kind + "_symlink_path", "value": str(path)})
            refs.append({"unit": str(path), "property": kind + "_symlink_target", "value": str(target)})
            return 0
        if path.is_file():
            files[path] = (kind, home, username)
        return 0
    except (OSError, RuntimeError):
        refs.append({"unit": str(path), "property": kind + "_unresolved_path", "value": str(path)})
        return 1


def _user_systemd_runtime_references(
    *, linger_dir: Path = Path("/var/lib/systemd/linger"),
) -> tuple[list[dict[str, str]], int]:
    """Inspect active and lingering user managers from logind and systemd state."""
    refs: list[dict[str, str]] = []
    errors = 0
    users: dict[str, str] = {}
    active_manager_uids: set[str] = set()

    try:
        listed = subprocess.run(
            ["loginctl", "list-users", "--no-legend", "--no-pager"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        listed = None
        errors += 1
    if listed is not None:
        if listed.returncode != 0:
            errors += 1
        else:
            for line in listed.stdout.splitlines():
                fields = line.split()
                if len(fields) < 2 or not fields[0].isdigit():
                    errors += 1
                    continue
                users[fields[0]] = fields[1]

    # loginctl list-users may omit a lingered account without an interactive
    # session. The linger registry is an independent source of user managers.
    try:
        linger_stat = linger_dir.lstat()
    except FileNotFoundError:
        linger_stat = None
    except OSError:
        linger_stat = None
        errors += 1
    if linger_stat is not None:
        if not stat.S_ISDIR(linger_stat.st_mode):
            errors += 1
        else:
            try:
                linger_entries = list(linger_dir.iterdir())
            except OSError:
                linger_entries = []
                errors += 1
            for entry in linger_entries:
                try:
                    entry_stat = entry.lstat()
                except OSError:
                    errors += 1
                    continue
                if not stat.S_ISREG(entry_stat.st_mode):
                    refs.append({"unit": entry.name, "property": "linger_entry_unexpected_type", "value": str(entry)})
                    errors += 1
                    continue
                username = entry.name
                try:
                    account = pwd.getpwnam(username)
                except KeyError:
                    refs.append({"unit": username, "property": "linger_user_unresolved", "value": str(entry)})
                    errors += 1
                    continue
                users[str(account.pw_uid)] = account.pw_name

    # Also inspect system user@UID.service units so a running manager is not
    # missed if logind's user list is temporarily incomplete.
    try:
        managers = subprocess.run(
            ["systemctl", "list-units", "--all", "--type=service", "--no-legend", "--plain", "--no-pager", "user@*.service"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        managers = None
        errors += 1
    if managers is not None:
        if managers.returncode != 0:
            errors += 1
        else:
            for line in managers.stdout.splitlines():
                fields = line.split()
                if len(fields) < 4 or not fields[0].startswith("user@") or not fields[0].endswith(".service"):
                    continue
                if fields[2] not in ("active", "activating", "reloading"):
                    continue
                uid = fields[0][5:-8]
                if not uid.isdigit():
                    errors += 1
                    continue
                active_manager_uids.add(uid)
                try:
                    account = pwd.getpwuid(int(uid))
                except KeyError:
                    refs.append({"unit": fields[0], "property": "system_user_manager_unresolved", "value": fields[0]})
                    errors += 1
                    continue
                users[uid] = account.pw_name

    properties = "ExecStart,ExecStartPre,ExecStartPost,WorkingDirectory,EnvironmentFiles,ReadWritePaths,ReadOnlyPaths,RequiresMountsFor,BindPaths,BindReadOnlyPaths,RootDirectory,RootImage,InaccessiblePaths,TemporaryFileSystem,ConditionPathExists,ConditionPathIsDirectory,StateDirectory,CacheDirectory,LogsDirectory,RuntimeDirectory"
    for uid, username in sorted(users.items(), key=lambda item: (item[1], item[0])):
        try:
            state_result = subprocess.run(
                ["loginctl", "show-user", username, "--property=State,Linger,RuntimePath", "--no-pager"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            errors += 1
            continue
        if state_result.returncode != 0:
            errors += 1
            continue
        state = {}
        for item in state_result.stdout.splitlines():
            key, _, value = item.partition("=")
            state[key] = value
        linger_file = (linger_dir / username).is_file()
        manager_active = uid in active_manager_uids
        if state.get("State") != "active" and state.get("Linger") != "yes" and not linger_file and not manager_active:
            continue
        if linger_file and state.get("Linger") != "yes":
            refs.append({"unit": username, "property": "linger_registry_logind_mismatch", "value": str(linger_dir / username)})
            errors += 1
            continue
        runtime = state.get("RuntimePath") or f"/run/user/{uid}"
        bus = Path(runtime) / "bus"
        if not bus.exists():
            errors += 1
            continue
        prefix = [
            "runuser", "-u", username, "--", "env",
            f"XDG_RUNTIME_DIR={runtime}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}",
            "systemctl", "--user",
        ]
        unit_names: set[str] = set()
        commands = (
            ["list-units", "--type=service", "--state=running", "--no-legend", "--plain", "--no-pager"],
            ["list-units", "--type=timer", "--state=active", "--no-legend", "--plain", "--no-pager"],
            ["list-unit-files", "--type=service", "--state=enabled", "--no-legend", "--no-pager"],
            ["list-unit-files", "--type=timer", "--state=enabled", "--no-legend", "--no-pager"],
        )
        for args in commands:
            try:
                result = subprocess.run(prefix + args, capture_output=True, text=True, timeout=20, check=False)
            except (OSError, subprocess.TimeoutExpired):
                errors += 1
                continue
            if result.returncode != 0:
                errors += 1
                continue
            for row in result.stdout.splitlines():
                unit_fields = row.split()
                if unit_fields and unit_fields[0].endswith((".service", ".timer")) and _is_concrete_systemd_unit(unit_fields[0]):
                    unit_names.add(unit_fields[0])
        for unit in sorted(unit_names):
            try:
                result = subprocess.run(
                    prefix + ["show", unit, f"--property={properties}"],
                    capture_output=True, text=True, timeout=10, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                errors += 1
                continue
            if result.returncode != 0:
                errors += 1
                continue
            for prop in result.stdout.splitlines():
                key, _, value = prop.partition("=")
                refs.extend(_expand_systemd_path_reference(f"{username}:{unit}", key, value))
    return refs, errors


def _scheduled_job_references() -> tuple[list[dict[str, str]], int]:
    """Read cron, enabled user units, tmpfiles, logrotate and apt path declarations."""
    refs: list[dict[str, str]] = []
    errors = 0
    files: dict[Path, tuple[str, str | None, str | None]] = {}

    def add_file(path: Path, kind: str, home: str | None = None, username: str | None = None) -> None:
        nonlocal errors
        errors += _register_scheduled_file(path, kind, home, username, files, refs)

    add_file(Path("/etc/crontab"), "cron", None, None)
    for root in (Path("/etc/cron.d"), Path("/etc/cron.hourly"), Path("/etc/cron.daily"),
                 Path("/etc/cron.weekly"), Path("/etc/cron.monthly"),
                 Path("/var/spool/cron"), Path("/var/spool/cron/crontabs")):
        try:
            root_exists = root.is_dir()
        except OSError:
            errors += 1
            continue
        if not root_exists:
            continue
        try:
            for path in root.iterdir():
                add_file(path, "cron", None, None)
        except OSError:
            errors += 1

    for root in (Path("/etc/tmpfiles.d"), Path("/usr/lib/tmpfiles.d"), Path("/lib/tmpfiles.d"),
                 Path("/etc/logrotate.d"), Path("/etc/apt/apt.conf.d")):
        try:
            root_exists = root.is_dir()
        except OSError:
            errors += 1
            continue
        if not root_exists:
            continue
        try:
            for path in root.iterdir():
                add_file(path, "system_maintenance_config", None, None)
        except OSError:
            errors += 1
    add_file(Path("/etc/logrotate.conf"), "system_maintenance_config", None, None)

    user_roots: list[tuple[Path, str | None, str | None]] = [
        (Path("/etc/systemd/user"), None, None),
        (Path("/usr/lib/systemd/user"), None, None),
        (Path("/lib/systemd/user"), None, None),
        (Path("/root/.config/systemd/user"), "/root", "root"),
    ]
    home_root = Path("/home")
    try:
        home_root_exists = home_root.is_dir()
    except OSError:
        errors += 1
        home_root_exists = False
    if home_root_exists:
        try:
            for home in home_root.iterdir():
                if home.is_dir():
                    user_roots.append((home / ".config/systemd/user", str(home), home.name))
        except OSError:
            errors += 1
    for root, home, username in user_roots:
        try:
            root_exists = root.is_dir()
        except OSError:
            errors += 1
            continue
        if not root_exists:
            continue
        try:
            wants_dirs = [p for p in root.rglob("*.wants") if p.is_dir()]
            wants_dirs.extend(p for p in root.rglob("*.requires") if p.is_dir())
            for wants in wants_dirs:
                for link in wants.iterdir():
                    if not link.is_symlink():
                        continue
                    try:
                        target = link.resolve(strict=True)
                        add_file(link, "enabled_user_systemd_unit", home, username)
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1

    runtime_refs, runtime_errors = _user_systemd_runtime_references()
    refs.extend(runtime_refs)
    errors += runtime_errors

    for path, (kind, home, username) in files.items():
        try:
            if path.stat().st_size > 1024 * 1024:
                errors += 1
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            errors += 1
            continue
        for line_number, raw in enumerate(content.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith(("#", "//")) or "/" not in line:
                continue
            if kind == "enabled_user_systemd_unit":
                if "%h" in line:
                    if home is None:
                        errors += 1
                        continue
                    line = line.replace("%h", home)
                if "%u" in line and username:
                    line = line.replace("%u", username)
                line = line.replace("%t", "/run/user")
                if "/opt/sentinelx-cloud-core" in line or "${HOME}" in line or "~/" in line:
                    if home is None:
                        errors += 1
                        continue
                    line = line.replace("/opt/sentinelx-cloud-core", home).replace("${HOME}", home).replace("~/", home + "/")
            elif "/opt/sentinelx-cloud-core" in line or "${HOME}" in line or "~/" in line:
                errors += 1
                continue
            refs.append({"unit": str(path), "property": kind, "value": line[:2000],
                         "line": str(line_number)})
    return refs, errors


def _active_targets() -> tuple[list[str], list[str]]:
    targets: list[str] = []
    errors: list[str] = []
    for pointer in ACTIVE_POINTERS:
        try:
            if pointer.is_symlink():
                targets.append(str(pointer.resolve(strict=True)))
            else:
                errors.append(f"pointer_missing_or_not_symlink:{pointer}")
        except OSError as exc:
            errors.append(f"pointer_unresolved:{pointer}:{type(exc).__name__}")
    return targets, errors


def _matches_process(path: str, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for ref in refs:
        target = ref.get("path", "")
        if target and (_under(target, path) or os.path.abspath(target) == os.path.abspath(path)):
            matches.append(ref)
    return matches[:50]


_SYSTEMD_HEX_ESCAPE = re.compile(r"\\x([0-9a-fA-F]{2})")
_GENERIC_PATH_ROOTS = {"/", "/tmp", "/var/tmp", "/var", "/usr", "/etc", "/home", "/opt", "/run", "/root"}
_BROAD_DIRECTORY_PROPERTIES = {
    "WorkingDirectory", "ReadWritePaths", "ReadOnlyPaths", "BindPaths", "BindReadOnlyPaths",
    "InaccessiblePaths", "TemporaryFileSystem", "StateDirectory_resolved", "CacheDirectory_resolved",
    "LogsDirectory_resolved", "RuntimeDirectory_resolved", "system_maintenance_config", "cron",
}


def _declared_paths(value: str) -> list[str] | None:
    """Parse declared paths; unresolved variables without a stable prefix fail closed."""
    protected = _SYSTEMD_HEX_ESCAPE.sub(lambda match: "__HES_HEX_" + match.group(1).upper() + "__", value)
    try:
        tokens = shlex.split(protected, posix=True)
    except ValueError:
        # Cron scripts contain shell continuations and control syntax. Recover
        # absolute path tokens rather than treating every shell line as a hit.
        tokens = re.findall(r"(?<![A-Za-z0-9_])/(?:[^\s\"'`|;&<>]+)", protected)
        if not tokens:
            if re.search(r"(?:\$[A-Za-z_{]|~/|%[A-Za-z])[^\s]*[/\\]", protected):
                return None
            return []
    tokens = [re.sub(r"__HES_HEX_([0-9A-F]{2})__", lambda match: chr(int(match.group(1), 16)), token) for token in tokens]
    paths: list[str] = []
    for token in tokens:
        token = token.strip("{};, ")
        if not token or token.startswith((".*", "./", "../", "/[", "/.*")):
            continue
        if token.startswith("PATH="):
            # PATH is an executable search list, not a declaration that every
            # file below those directories is a dependency.
            continue
        if "=" in token:
            key, candidate = token.split("=", 1)
            if key in {"path", "argv[]", "WorkingDirectory", "RootDirectory", "RootImage"}:
                token = candidate
        token = token.lstrip("-+!@").strip()
        if not token or token == "/":
            continue
        if token.startswith("/"):
            if "$" in token or "%" in token:
                prefix = re.split(r"[$%]", token, maxsplit=1)[0].rstrip("/")
                if prefix in ("", "/"):
                    return None
                if prefix not in paths:
                    paths.append(prefix if token[len(prefix):].startswith("/") else prefix + "*")
            else:
                normalized = os.path.normpath(token)
                if normalized not in paths:
                    paths.append(normalized)
        elif token.startswith(("~/", "${")):
            return None
        elif "/" in token and ("$" in token or "%" in token or any(char.isspace() for char in token)):
            extracted = re.findall(r"(?<![A-Za-z0-9_])/(?:[^\s\"'`|;&<>]+)", token)
            if not extracted:
                return None
            for item in extracted:
                if item not in paths and item != "/":
                    paths.append(os.path.normpath(item))
    return paths


def _paths_related(candidate: str, declared: str, property_name: str) -> bool:
    candidate_abs = os.path.normpath(os.path.abspath(candidate))
    if "*" in declared:
        return candidate_abs.startswith(declared.split("*", 1)[0])
    declared_abs = os.path.normpath(os.path.abspath(declared))
    # A referenced file beneath a candidate directory, or an exact path, is
    # always a dependency. Parent directories are contextual only for explicit
    # directory-access properties; generic roots are never blanket matches.
    if candidate_abs == declared_abs or _under(declared_abs, candidate_abs):
        return True
    if property_name in _BROAD_DIRECTORY_PROPERTIES and declared_abs not in _GENERIC_PATH_ROOTS:
        return _under(candidate_abs, declared_abs)
    return False


def _matches_unit(path: str, refs: list[dict[str, str]]) -> list[dict[str, str]]:
    matches = []
    for ref in refs:
        value = ref.get("value", "")
        declared = _declared_paths(value)
        if declared is None:
            matches.append({**ref, "match_reason": "UNPARSED_PATH_DECLARATION_FAIL_CLOSED"})
            continue
        property_name = ref.get("property", "")
        if any(_paths_related(path, target, property_name) for target in declared):
            matches.append({**ref, "match_reason": "NORMALIZED_PATH_TOKEN_MATCH"})
    return matches[:30]


def _backup_status() -> dict[str, Any]:
    local_dir = Path("/var/backups/hes-trade-agent/encrypted-local")
    offsite_dir = Path("/var/backups/hes-trade-agent/offsite-staging")
    result: dict[str, Any] = {
        "local_latest": None,
        "local_latest_sidecar_verified": False,
        "local_evidence_store_covered": False,
        "offsite_latest": None,
        "offsite_latest_sidecar_verified": False,
        "offsite_evidence_store_covered": False,
        "dropbox_quota": None,
        "dropbox_remote_latest": None,
        "remote_hash_check": "NOT_RUN",
        "full_restore_status": "NOT_PROVEN",
        "selective_restore_status": "PREVIOUSLY_REPORTED_PASS_NOT_REPEATED_BY_THIS_RUN",
    }
    local = sorted(local_dir.glob("hes-full-*.tar.gz.gpg"), key=lambda p: p.name, reverse=True)
    if local:
        archive = local[0]
        sidecar = Path(str(archive) + ".sha256")
        result["local_latest"] = {"path": str(archive), "size_bytes": archive.stat().st_size, "sidecar_present": sidecar.is_file()}
        if sidecar.is_file():
            check = subprocess.run(["sha256sum", "-c", str(sidecar)], cwd=archive.parent, capture_output=True, text=True, timeout=180, check=False)
            result["local_latest_sidecar_verified"] = check.returncode == 0
            result["local_latest_sha256_check"] = check.stdout.strip()[-300:] if check.returncode == 0 else check.stderr.strip()[-300:]
        coverage_manifest = Path(str(archive) + ".manifest.txt")
        if coverage_manifest.is_file():
            try:
                result["local_evidence_store_covered"] = any(
                    line.strip() == "Required evidence store: /srv/hes-evidence (coverage verified by archive listing)."
                    for line in coverage_manifest.read_text(encoding="utf-8").splitlines()
                )
            except OSError:
                result["local_evidence_store_covered"] = False
    offsite = sorted(offsite_dir.glob("hes-offsite-core-*.tar.gz.gpg"), key=lambda p: p.name, reverse=True)
    if offsite:
        archive = offsite[0]
        sidecar = Path(str(archive) + ".sha256")
        result["offsite_latest"] = {"path": str(archive), "size_bytes": archive.stat().st_size, "sidecar_present": sidecar.is_file()}
        if sidecar.is_file():
            check = subprocess.run(["sha256sum", "-c", str(sidecar)], cwd=archive.parent, capture_output=True, text=True, timeout=60, check=False)
            result["offsite_latest_sidecar_verified"] = check.returncode == 0
        coverage_manifest = Path(str(archive) + ".manifest.txt")
        if coverage_manifest.is_file():
            try:
                result["offsite_evidence_store_covered"] = any(
                    line.strip() == "Required evidence store: /srv/hes-evidence (coverage verified by archive listing)."
                    for line in coverage_manifest.read_text(encoding="utf-8").splitlines()
                )
            except OSError:
                result["offsite_evidence_store_covered"] = False
    try:
        quota = subprocess.run(["rclone", "about", "hesdropbox:", "--json"], capture_output=True, text=True, timeout=45, check=False)
        if quota.returncode == 0:
            q = json.loads(quota.stdout)
            total, used, free = (int(q.get(k, 0)) for k in ("total", "used", "free"))
            result["dropbox_quota"] = {"total_bytes": total, "used_bytes": used, "free_bytes": free,
                                        "used_percent": round(100 * used / total, 2) if total else None}
        remote = subprocess.run(["rclone", "lsjson", "hesdropbox:HES Trade Agent Backups/hes-offsite-latest.tar.gz.gpg", "--stat"],
                                capture_output=True, text=True, timeout=45, check=False)
        if remote.returncode == 0:
            data = json.loads(remote.stdout)
            result["dropbox_remote_latest"] = {"size_bytes": int(data.get("Size", 0)), "modified": data.get("ModTime")}
            if offsite:
                with tempfile.TemporaryDirectory(prefix="hes-smart-cleanup-verify-", dir=str(offsite_dir)) as temp_dir:
                    local_link = Path(temp_dir) / "hes-offsite-latest.tar.gz.gpg"
                    os.link(offsite[0], local_link)
                    check = subprocess.run(
                        ["rclone", "check", temp_dir, "hesdropbox:HES Trade Agent Backups", "--one-way", "--checkers", "1"],
                        capture_output=True, text=True, timeout=240, check=False,
                    )
                    result["remote_hash_check"] = "PASS" if check.returncode == 0 else "FAIL"
                    result["remote_hash_check_detail"] = (check.stdout + check.stderr).strip()[-500:]
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        result["dropbox_status"] = "UNAVAILABLE_OR_UNPARSEABLE"
    return result


def _source_audit_gate(audit: dict[str, Any], now: datetime) -> tuple[list[str], float | None]:
    errors: list[str] = []
    if audit.get("schema") != "hes_data_lifecycle_audit_v1":
        errors.append("unexpected_source_audit_schema")
    if audit.get("mode") != "READ_ONLY_DRY_RUN":
        errors.append("source_audit_mode_not_read_only")
    registry = audit.get("worktree_registry")
    if not isinstance(registry, dict):
        errors.append("worktree_registry_missing")
    else:
        if registry.get("error"):
            errors.append("worktree_registry_unverified")
        paths = registry.get("paths")
        if not isinstance(paths, list) or not all(isinstance(path, str) and Path(path).is_absolute() for path in paths):
            errors.append("worktree_registry_paths_invalid")
    age_seconds: float | None = None
    try:
        generated = datetime.fromisoformat(str(audit.get("generated_at", "")).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age_seconds = (now - generated).total_seconds()
        if age_seconds < -60 or age_seconds > 900:
            errors.append("source_audit_stale_or_future_dated")
    except (TypeError, ValueError):
        errors.append("source_audit_timestamp_invalid")
    return errors, age_seconds


def build_manager_report(audit: dict[str, Any], *, now: datetime | None = None,
                         proc_refs: list[dict[str, Any]] | None = None,
                         proc_errors: int | None = None,
                         unit_refs: list[dict[str, str]] | None = None,
                         unit_errors: int | None = None,
                         backup_status: dict[str, Any] | None = None,
                         active_targets: list[str] | None = None,
                         pointer_errors: list[str] | None = None,
                         scheduled_refs: list[dict[str, str]] | None = None,
                         scheduled_errors: int | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if proc_refs is None or proc_errors is None:
        proc_refs, proc_errors = _proc_references()
    if unit_refs is None or unit_errors is None:
        unit_refs, unit_errors = _systemd_references()
    source_audit_errors, source_audit_age = _source_audit_gate(audit, now)
    if scheduled_refs is None or scheduled_errors is None:
        discovered_scheduled_refs, discovered_scheduled_errors = _scheduled_job_references()
        if scheduled_refs is None:
            scheduled_refs = discovered_scheduled_refs
        if scheduled_errors is None:
            scheduled_errors = discovered_scheduled_errors
    if active_targets is None or pointer_errors is None:
        discovered_targets, discovered_errors = _active_targets()
        if active_targets is None:
            active_targets = discovered_targets
        if pointer_errors is None:
            pointer_errors = discovered_errors
    items = []
    for row in audit.get("items", []):
        path = str(row.get("path", ""))
        classification = str(row.get("classification", "KEEP_UNKNOWN"))
        process_matches = _matches_process(path, proc_refs)
        unit_matches = _matches_unit(path, unit_refs)
        scheduled_matches = _matches_unit(path, scheduled_refs)
        active_match = any(_under(target, path) or _under(path, target) for target in active_targets)
        registry = audit.get("worktree_registry", {})
        worktrees = registry.get("paths", []) if isinstance(registry, dict) else []
        worktree_match = any(_under(path, root) or _under(root, path) for root in worktrees)
        dependency_errors = int(proc_errors or 0) + int(unit_errors or 0) + int(scheduled_errors or 0) + len(pointer_errors) + len(source_audit_errors)
        if process_matches or unit_matches or scheduled_matches or active_match or worktree_match:
            dependency_status = "BLOCKED_REFERENCED"
        elif dependency_errors:
            dependency_status = "UNKNOWN_FAIL_CLOSED"
        else:
            dependency_status = "NO_LIVE_REFERENCE_OBSERVED"
        protected = classification.startswith(PROTECTED_PREFIXES) or classification not in REVIEWABLE_CLASSES
        if protected or dependency_status != "NO_LIVE_REFERENCE_OBSERVED":
            decision = "KEEP"
        else:
            decision = "REVIEW_ONLY"
        items.append({
            "path": path,
            "classification": classification,
            "allocated_bytes": int(row.get("allocated_bytes", 0)),
            "age_days": row.get("age_days"),
            "dependency_status": dependency_status,
            "process_references": process_matches,
            "systemd_references": unit_matches,
            "scheduled_job_references": scheduled_matches,
            "active_or_rollback_release_related": active_match,
            "registered_worktree_related": worktree_match,
            "decision": decision,
            "automatic_action": "NONE",
            "reason": "No destructive action exists in this manager; a clean dependency scan is not deletion authorization.",
        })
    disk = audit.get("disk", {})
    free_pct = disk.get("free_percent")
    if free_pct is None:
        pressure = "UNKNOWN"
    elif free_pct < 10:
        pressure = "CRITICAL"
    elif free_pct < 15:
        pressure = "WARN"
    else:
        pressure = "OK"
    backups = backup_status if backup_status is not None else _backup_status()
    remote_size_matches = bool(backups.get("offsite_latest") and backups.get("dropbox_remote_latest")
                               and int(backups["offsite_latest"].get("size_bytes", -1)) == int(backups["dropbox_remote_latest"].get("size_bytes", -2)))
    quota = backups.get("dropbox_quota") or {}
    try:
        quota_total = int(quota.get("total_bytes", -1))
        quota_used = int(quota.get("used_bytes", -1))
        quota_free = int(quota.get("free_bytes", -1))
        remote_size = int((backups.get("dropbox_remote_latest") or {}).get("size_bytes", -1))
        replacement_size = int((backups.get("offsite_latest") or {}).get("size_bytes", -1))
        quota_guard = (
            quota_total > 0 and 0 <= quota_used <= quota_total and 0 <= quota_free <= quota_total
            and remote_size >= 0 and replacement_size >= 0
            and quota_free + remote_size >= replacement_size + 128 * 1024 * 1024
        )
    except (TypeError, ValueError, AttributeError):
        quota_guard = False
    backup_gate = bool(backups.get("local_latest_sidecar_verified") and backups.get("local_evidence_store_covered")
                       and backups.get("offsite_latest_sidecar_verified") and backups.get("offsite_evidence_store_covered")
                       and backups.get("remote_hash_check") == "PASS" and remote_size_matches and quota_guard)
    return {
        "schema": "hes_smart_cleanup_manager_v1",
        "generated_at": now.isoformat(),
        "mode": "READ_ONLY_DEPENDENCY_AWARE_DRY_RUN",
        "source_audit_schema": audit.get("schema"),
        "source_audit_generated_at": audit.get("generated_at"),
        "inventory_items": len(items),
        "source_audit_gate": {
            "status": "PASS" if not source_audit_errors else "FAIL_CLOSED",
            "age_seconds": round(source_audit_age, 2) if source_audit_age is not None else None,
            "errors": source_audit_errors,
            "maximum_age_seconds": 900,
        },
        "dependency_scan": {
            "process_reference_count": len(proc_refs), "process_scan_errors": proc_errors,
            "running_unit_reference_count": len(unit_refs), "unit_scan_errors": unit_errors,
            "scheduled_job_reference_count": len(scheduled_refs), "scheduled_job_scan_errors": scheduled_errors,
            "active_release_targets": active_targets, "active_pointer_errors": pointer_errors,
        },
        "disk_capacity": {**disk, "pressure": pressure},
        "backup_manager": {**backups, "dropbox_quota_guard": "PASS" if quota_guard else "INCOMPLETE"},
        "recovery_gate": {
            "backup_integrity_gate": "PASS" if backup_gate else "INCOMPLETE",
            "full_restore_gate": "BLOCKED_NOT_PROVEN",
            "cleanup_authorization": False,
            "reason": "A selective restore is not a full-system recovery drill; no deletion can be authorized from this report.",
        },
        "summary": {
            "keep": sum(x["decision"] == "KEEP" for x in items),
            "review_only": sum(x["decision"] == "REVIEW_ONLY" for x in items),
            "live_referenced": sum(x["dependency_status"] == "BLOCKED_REFERENCED" for x in items),
            "dependency_unknown": sum(x["dependency_status"] == "UNKNOWN_FAIL_CLOSED" for x in items),
            "delete_authorized": 0,
        },
        "items": items,
        "invariants": [
            "No delete, move, truncate, compress, rotate, prune, or service mutation is implemented.",
            "Unknown ownership/dependency/recovery state means KEEP.",
            "Active and rollback release trees, registered worktrees, canonical market data, journals, evidence, backups, and unknown files remain protected.",
            "Gate.io remains the sole canonical market-data/chart/candle/indicator source; cleanup has no market-data or execution authority.",
            "Dropbox quota is monitored through the existing hesdropbox rclone remote; no credentials or passphrase are read into the report.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    audit = json.loads(args.audit_manifest.read_text(encoding="utf-8"))
    report = build_manager_report(audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SMART_CLEANUP_AUDIT_OK items={} keep={} review={} delete_authorized=0".format(report["inventory_items"], report["summary"]["keep"], report["summary"]["review_only"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())