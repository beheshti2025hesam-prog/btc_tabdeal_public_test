"""Bounded, opt-in Wallex public-market observation runner.

This runner records read-only public frames and injects a prior-session frame
through the same collector callback path after reconnect. It never sends orders
or account mutations and is not launched automatically.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Callable

from forward.wallex_market_data_collector_v1 import (
    WallexMarketDataCollector,
    WallexMarketEvent,
)


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or type(exc).__name__ == "WebSocketTimeoutException"


def _write_hash(path: Path) -> str:
    digest = sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def run_bounded_observation(
    *,
    output_jsonl: str | Path,
    symbol: str = "BTCUSDT",
    channels: tuple[str, ...] = ("buyDepth", "sellDepth"),
    session_seconds: float = 10.0,
    session_count: int = 2,
    inject_stale_frame: bool = True,
    socket_factory: Callable[[str, float], Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    monotonic_ns: Callable[[], int] | None = None,
) -> dict[str, Any]:
    """Run a bounded number of sessions and write raw, hash-pinned evidence."""
    if isinstance(session_seconds, bool) or not isinstance(session_seconds, (int, float)) or not 0 < session_seconds <= 300:
        raise ValueError("session_seconds must be >0 and <=300")
    if isinstance(session_count, bool) or not isinstance(session_count, int) or not 2 <= session_count <= 5:
        raise ValueError("session_count must be between 2 and 5")
    out = Path(output_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {out}")
    events: list[WallexMarketEvent] = []
    collector = WallexMarketDataCollector(
        symbol,
        channels=channels,
        socket_factory=socket_factory,
        on_event=events.append,
        clock=clock,
        monotonic_ns=monotonic_ns,
    )
    sessions: list[Any] = []
    per_session_events: dict[int, int] = {}
    injected: list[dict[str, Any]] = []
    raw_for_injection: dict[int, str] = {}

    for session_number in range(1, session_count + 1):
        session = collector.connect()
        sessions.append(session)
        per_session_events[session.epoch] = 0

        if inject_stale_frame and session_number > 1:
            previous = sessions[-2]
            prior_raw = raw_for_injection.get(previous.epoch)
            source = "captured_prior_session_frame"
            if prior_raw is None:
                source = "synthetic_prior_session_frame_no_live_frame_available"
                prior_raw = json.dumps(
                    [f"{symbol}@{channels[0]}", []], separators=(",", ":")
                )
            accepted = collector.process_frame(previous, prior_raw) is not None
            injected.append({
                "after_current_epoch": session.epoch,
                "prior_epoch": previous.epoch,
                "source": source,
                "raw_sha256": sha256(prior_raw.encode("utf-8")).hexdigest(),
                "accepted": accepted,
            })
            if accepted:
                collector.close(session)
                raise RuntimeError("stale prior-session frame was accepted")

        deadline = time.monotonic() + float(session_seconds)
        try:
            while time.monotonic() < deadline and per_session_events[session.epoch] < 10000:
                remaining = max(0.05, deadline - time.monotonic())
                settimeout = getattr(session.socket, "settimeout", None)
                if callable(settimeout):
                    settimeout(min(1.0, remaining))
                try:
                    raw = session.socket.recv()
                except Exception as exc:
                    if _is_timeout(exc):
                        continue
                    break
                event = collector.process_frame(session, raw)
                if event is not None:
                    per_session_events[session.epoch] += 1
                    raw_for_injection.setdefault(session.epoch, event.raw)
        finally:
            collector.close(session)

    records = []
    for event in events:
        session_number = next(
            (index for index, session in enumerate(sessions, start=1)
             if session.epoch == event.epoch),
            None,
        )
        records.append({
            "session_number": session_number,
            "server_sid": next(
                (session.server_sid for session in sessions if session.epoch == event.epoch),
                None,
            ),
            "epoch": event.epoch,
            "symbol": event.symbol,
            "channel": event.channel,
            "kind": event.kind,
            "received_at_utc": event.received_at_utc.isoformat(),
            "received_monotonic_ns": event.received_monotonic_ns,
            "raw_sha256": event.raw_sha256,
            "raw": event.raw,
        })
    with out.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    raw_digest = _write_hash(out)

    manifest = {
        "schema": "HES_WALLEX_BOUNDED_OBSERVATION_V1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": collector.endpoint,
        "symbol": symbol,
        "channels": list(channels),
        "session_seconds": float(session_seconds),
        "session_count": session_count,
        "sessions": [
            {
                "epoch": session.epoch,
                "server_sid": session.server_sid,
                "accepted_event_count": per_session_events[session.epoch],
            }
            for session in sessions
        ],
        "server_session_ids_distinct": len({session.server_sid for session in sessions}) == len(sessions),
        "total_accepted_events": len(records),
        "stale_frame_injections": injected,
        "all_stale_injections_rejected": all(not item["accepted"] for item in injected),
        "raw_jsonl_path": out.name,
        "raw_jsonl_sha256": raw_digest,
        "credentials_used": False,
        "orders_sent": False,
        "account_mutations": False,
        "runtime_activated": False,
        "interpretation": (
            "Bounded read-only observation only. Prior-epoch frames are injected "
            "through the collector API after a newer epoch is current. This does "
            "not prove the exchange delivered delayed frames or establish trade "
            "completeness, sequence semantics, or volume units."
        ),
    }
    manifest_path = out.with_name(out.stem + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_digest = _write_hash(manifest_path)
    manifest["manifest_sha256"] = manifest_digest
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--session-seconds", type=float, default=10.0)
    parser.add_argument("--session-count", type=int, default=2)
    parser.add_argument("--channels", default="buyDepth,sellDepth")
    parser.add_argument("--no-stale-frame-injection", action="store_true")
    args = parser.parse_args()
    result = run_bounded_observation(
        output_jsonl=args.output_jsonl,
        symbol=args.symbol,
        channels=tuple(part.strip() for part in args.channels.split(",") if part.strip()),
        session_seconds=args.session_seconds,
        session_count=args.session_count,
        inject_stale_frame=not args.no_stale_frame_injection,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
