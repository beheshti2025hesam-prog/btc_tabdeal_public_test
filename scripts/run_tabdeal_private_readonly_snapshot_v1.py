"""One-shot private Tabdeal FAPI evidence capture; signed GET only."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core.execution.tabdeal_fapi_readonly import (
    FapiReadError, TabdealFapiReadOnlyClient, load_systemd_credentials,
)
from core.paper.tabdeal_fapi_fee_reconciliation_v1 import (
    FeeObservationError, build_historical_fee_observation,
)

STATE_DIR = Path("/var/lib/hes-tabdeal-readonly")
SYMBOL_ALIASES = ("BTC_USDT", "BTCUSDT")
MAX_ROWS = 100


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def safe_call(method, *args, **kwargs):
    try:
        value = method(*args, **kwargs)
        if isinstance(value, dict) and type(value.get("code")) is int and value["code"] < 0:
            return {"status": "API_REJECTED", "error_code": value["code"],
                    "response_sha256": digest(value)}, value
        return {"status": "OK", "response_sha256": digest(value)}, value
    except (FapiReadError, ValueError) as exc:
        return {"status": "FAILED", "error": str(exc), "response_sha256": None}, None


def row_count(value):
    return len(value) if isinstance(value, list) else None


def main():
    key, secret = load_systemd_credentials()
    client = TabdealFapiReadOnlyClient(key, secret, timeout=12.0)
    del key, secret

    captured = datetime.now(timezone.utc)
    end_ms = int(time.time() * 1000)
    window = {
        "start_time_ms": None,
        "end_time_ms": end_ms,
        "start_utc": None,
        "end_utc": datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat(),
        "lower_bound": "NOT_SPECIFIED_BY_WORKING_ENDPOINT_QUERY",
        "duration_days": None,
    }

    results = {
        "account": safe_call(client.get_account)[0],
        "position_risk_all_symbols": safe_call(client.get_position_risk)[0],
        "leverage_symbol_underscore": safe_call(client.get_leverage, "BTC_USDT")[0],
        "leverage_symbol_compact": safe_call(client.get_leverage, "BTCUSDT")[0],
    }

    # Current balance is summarized without persisting amounts.
    balance_meta, balance_rows = safe_call(client.get_balance)
    results["balance"] = dict(balance_meta)
    if isinstance(balance_rows, list):
        results["balance"].update({
            "asset_count": len(balance_rows),
            "assets": sorted({str(row.get("asset")) for row in balance_rows
                              if isinstance(row, dict) and row.get("asset")}),
            "raw_amounts_persisted": False,
        })
    else:
        results["balance"]["asset_count"] = None
        results["balance"]["raw_amounts_persisted"] = False

    # Force-order history is capped at 100; Tabdeal documents time filters as unused.
    results["force_orders"] = {}
    for alias in SYMBOL_ALIASES:
        meta, rows = safe_call(client.get_force_orders, symbol=alias)
        results["force_orders"][alias] = {
            **meta,
            "row_count": row_count(rows),
            "maximum_documented_rows": MAX_ROWS,
            "time_filter_supported": False,
            "coverage": "LATEST_CAPPED_SNAPSHOT_ONLY",
        }

    # userTrades and Income are probed per exact alias. No alias rewrite or merging.
    results["historical_fee_observations"] = {}
    for alias in SYMBOL_ALIASES:
        trade_meta, trade_rows = safe_call(
            client.get_user_trades, alias,
            endTime=end_ms, limit=MAX_ROWS,
        )
        trade_query_mode = "END_TIME_ONLY_CAPPED"
        trade_fallback = None
        if trade_meta["status"] != "OK":
            trade_fallback, fallback_rows = safe_call(
                client.get_user_trades, alias, limit=MAX_ROWS,
            )
            if trade_fallback["status"] == "OK":
                trade_meta, trade_rows = trade_fallback, fallback_rows
                trade_query_mode = "SYMBOL_ONLY_LATEST_CAPPED"

        income_meta, income_rows = safe_call(
            client.get_income, symbol=alias,
            endTime=end_ms, limit=MAX_ROWS,
        )
        income_query_mode = "END_TIME_ONLY_CAPPED"
        income_fallback = None
        if income_meta["status"] != "OK":
            income_fallback, fallback_rows = safe_call(
                client.get_income, symbol=alias, limit=MAX_ROWS,
            )
            if income_fallback["status"] == "OK":
                income_meta, income_rows = income_fallback, fallback_rows
                income_query_mode = "SYMBOL_ONLY_LATEST_CAPPED"

        entry = {
            "query_symbol": alias,
            "requested_query_window": window,
            "user_trades": {
                **trade_meta,
                "row_count": row_count(trade_rows),
                "limit": MAX_ROWS,
                "query_mode": trade_query_mode,
                "fallback_without_time_filter": trade_fallback,
                "fromId_used": False,
                "fromId_documented_server_behavior": "CURRENTLY_UNUSED",
            },
            "income": {
                **income_meta,
                "row_count": row_count(income_rows),
                "limit": MAX_ROWS,
                "query_mode": income_query_mode,
                "fallback_without_time_filter": income_fallback,
            },
            "fee_observation": None,
        }
        if trade_query_mode != income_query_mode:
            entry["fee_observation"] = {
                "status": "NOT_RUN_QUERY_WINDOW_MISMATCH",
                "fee_schedule_verified": False,
                "future_fee_tier_verified": False,
                "execution_enabled": False,
                "orders_placed": False,
            }
        elif isinstance(trade_rows, list) and isinstance(income_rows, list):
            try:
                report = build_historical_fee_observation(
                    trade_rows, income_rows,
                    expected_symbol=alias, base_asset="BTC", quote_asset="USDT",
                )
                summary = asdict(report)
                summary.pop("trades", None)
                summary.pop("income_rows", None)
                summary["query_mode"] = trade_query_mode
                summary["query_window"] = window
                if trade_query_mode == "END_TIME_ONLY_CAPPED":
                    summary["coverage"] = "END_TIME_ONLY_CAPPED_NO_LOWER_BOUND_COMPLETENESS_UNKNOWN"
                elif trade_query_mode == "SYMBOL_ONLY_LATEST_CAPPED":
                    summary["coverage"] = "LATEST_CAPPED_NO_TIME_FILTER_COMPLETENESS_UNKNOWN"
                elif len(trade_rows) == MAX_ROWS or len(income_rows) == MAX_ROWS:
                    summary["coverage"] = "POSSIBLY_TRUNCATED_AT_100"
                else:
                    summary["coverage"] = "WINDOW_COMPLETENESS_NOT_PROVEN_BY_DOCUMENTATION"
                summary["fromId_pagination_available"] = False
                entry["fee_observation"] = summary
            except FeeObservationError as exc:
                entry["fee_observation"] = {
                    "status": "REJECTED_INVALID_OR_MISMATCHED_EVIDENCE",
                    "error": str(exc),
                    "fee_schedule_verified": False,
                    "future_fee_tier_verified": False,
                    "execution_enabled": False,
                    "orders_placed": False,
                }
        else:
            entry["fee_observation"] = {
                "status": "NOT_RUN_INPUT_UNAVAILABLE",
                "fee_schedule_verified": False,
                "future_fee_tier_verified": False,
                "execution_enabled": False,
                "orders_placed": False,
            }
        results["historical_fee_observations"][alias] = entry

    successful_aliases = [
        name for name in ("leverage_symbol_underscore", "leverage_symbol_compact")
        if results[name]["status"] == "OK"
    ]
    if len(successful_aliases) == 1:
        alias_status = "ONE_ALIAS_ACCEPTED_FOR_LEVERAGE_ONLY"
    elif len(successful_aliases) == 2:
        alias_status = "AMBIGUOUS_BOTH_ALIASES_ACCEPTED_FOR_LEVERAGE"
    else:
        alias_status = "UNRESOLVED_NO_LEVERAGE_ALIAS_ACCEPTED"

    payload = {
        "schema": "hes_tabdeal_private_readonly_snapshot_v2",
        "captured_at_utc": captured.isoformat(),
        "venue": "tabdeal",
        "api_family": "FAPI",
        "access_mode": "SIGNED_GET_ONLY_CLIENT",
        "market_data_source": "gateio_public_spot_remains_canonical",
        "results": results,
        "symbol_alias_assessment": {
            "status": alias_status,
            "accepted_leverage_probes": successful_aliases,
            "automatic_symbol_rewrite_enabled": False,
            "endpoint_aliases_are_independent": True,
        },
        "safety": {
            "execution_enabled": False,
            "orders_placed": False,
            "write_endpoints_called": False,
            "raw_user_trades_persisted": False,
            "raw_income_persisted": False,
            "raw_balance_amounts_persisted": False,
            "historical_fees_authorize_future_fee_tier": False,
        },
    }
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    fd, tmp = tempfile.mkstemp(prefix=".snapshot-", suffix=".tmp", dir=STATE_DIR)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        final = STATE_DIR / "tabdeal_private_readonly_snapshot.json"
        os.replace(tmp, final)
        os.chmod(final, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    print("SNAPSHOT_WRITTEN=YES")
    for name in ("account", "position_risk_all_symbols", "balance"):
        print(f"{name.upper()}_STATUS={results[name]['status']}")
    for alias in SYMBOL_ALIASES:
        item = results["historical_fee_observations"][alias]
        print(f"USER_TRADES_{alias}_STATUS={item['user_trades']['status']}")
        print(f"USER_TRADES_{alias}_QUERY_MODE={item['user_trades'].get('query_mode')}")
        print(f"INCOME_{alias}_STATUS={item['income']['status']}")
        print(f"INCOME_{alias}_QUERY_MODE={item['income'].get('query_mode')}")
        print(f"FEE_OBSERVATION_{alias}_STATUS={None if not item['fee_observation'] else item['fee_observation'].get('status')}")
        print(f"FEE_OBSERVATION_{alias}_TRADE_COUNT={None if not item['fee_observation'] else item['fee_observation'].get('trade_count')}")
    print(f"FORCE_ORDERS_STATUS={','.join(alias+':'+results['force_orders'][alias]['status'] for alias in SYMBOL_ALIASES)}")
    print(f"SYMBOL_ALIAS_STATUS={alias_status}")
    print("EXECUTION_ENABLED=NO")
    print("ORDERS_PLACED=NO")
    if results["account"]["status"] != "OK" or results["position_risk_all_symbols"]["status"] != "OK":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
