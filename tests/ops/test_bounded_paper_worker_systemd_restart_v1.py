from pathlib import Path


PAPER_WORKER_UNITS = (
    "hes-strategy-paper-evaluator.service",
    "hes-strategy-learning-loop.service",
    "hes-precision-entry-journal.service",
)


def _section_directives(text: str, section: str) -> dict[str, list[str]]:
    current = None
    result: dict[str, list[str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            result.setdefault(current, {})
            continue
        if current == section and "=" in line:
            key, value = line.split("=", 1)
            result.setdefault(key, []).append(value)
    return result


def test_paper_worker_restart_is_owned_only_by_bounded_recovery_monitor():
    for unit in PAPER_WORKER_UNITS:
        text = (Path("deploy/systemd") / unit).read_text(encoding="utf-8")
        service = _section_directives(text, "Service")
        unit_section = _section_directives(text, "Unit")

        assert service.get("Restart") == ["no"], unit
        assert unit_section.get("StartLimitIntervalSec") == ["1h"], unit
        assert unit_section.get("StartLimitBurst") == ["2"], unit
        assert not any(
            value in {"always", "on-failure", "on-abnormal", "on-watchdog"}
            for value in service.get("Restart", [])
        ), unit
