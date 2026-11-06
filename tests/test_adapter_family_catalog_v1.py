from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_adapter_family_catalog_v1 import validate_catalog


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "docs" / "adapter_family_catalog_v1.json"


def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_current_adapter_family_catalog_is_consistent_with_repository():
    payload = load_catalog()
    assert validate_catalog(ROOT, payload) == ()


def test_catalog_rejects_a_second_active_market_data_provider():
    payload = load_catalog()
    duplicate = copy.deepcopy(payload["adapters"][0])
    duplicate["adapter_id"] = "market-data.unapproved.second-provider"
    payload["adapters"].append(duplicate)
    errors = validate_catalog(ROOT, payload)
    assert "EXACTLY_ONE_ACTIVE_MARKET_DATA_ADAPTER_REQUIRED" in errors


def test_catalog_rejects_active_execution_adapter_even_when_policy_is_off():
    payload = load_catalog()
    execution = next(x for x in payload["adapters"] if x["domain"] == "execution")
    execution["status"] = "active"
    execution["runtime_enabled"] = True
    errors = validate_catalog(ROOT, payload)
    assert "ACTIVE_EXECUTION_ADAPTER_FORBIDDEN" in errors


def test_catalog_rejects_automatic_market_data_failover():
    payload = load_catalog()
    payload["market_data_policy"]["automatic_failover"] = True
    errors = validate_catalog(ROOT, payload)
    assert "MARKET_DATA_AUTO_FAILOVER_MUST_BE_DISABLED" in errors


def test_catalog_rejects_duplicate_adapter_ids():
    payload = load_catalog()
    payload["adapters"].append(copy.deepcopy(payload["adapters"][0]))
    errors = validate_catalog(ROOT, payload)
    assert "DUPLICATE_ADAPTER_ID" in errors


def test_catalog_rejects_unresolved_module_symbols():
    payload = load_catalog()
    payload["adapters"][0]["symbol"] = "MissingProviderClass"
    errors = validate_catalog(ROOT, payload)
    assert "ADAPTER_0_SYMBOL_NOT_FOUND" in errors


def test_catalog_rejects_path_traversal():
    payload = load_catalog()
    payload["adapters"][0]["module_path"] = "../outside.py"
    errors = validate_catalog(ROOT, payload)
    assert "ADAPTER_0_MODULE_PATH_INVALID" in errors


def test_catalog_rejects_nonactive_adapter_marked_runtime_enabled():
    payload = load_catalog()
    payload["adapters"][-1]["runtime_enabled"] = True
    errors = validate_catalog(ROOT, payload)
    assert "ADAPTER_13_NONACTIVE_RUNTIME_FLAG_TRUE" in errors


def test_catalog_rejects_execution_permission_or_order_placement():
    payload = load_catalog()
    payload["execution_policy"]["execution_enabled"] = True
    payload["execution_policy"]["orders_placed"] = True
    errors = validate_catalog(ROOT, payload)
    assert "EXECUTION_MUST_REMAIN_DISABLED" in errors
    assert "ORDERS_MUST_REMAIN_DISABLED" in errors


def test_catalog_rejects_canonical_profile_drift():
    payload = load_catalog()
    payload["market_data_policy"]["canonical_profile"]["venue_symbol"] = "BTCUSDT"
    errors = validate_catalog(ROOT, payload)
    assert "CANONICAL_MARKET_DATA_PROFILE_MISMATCH" in errors
