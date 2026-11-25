"""Validate the static HES adapter-family catalog without loading provider code.

The catalog is an inventory/guardrail, not a dynamic plugin loader. Validation
uses Python AST so provider modules are never imported and no network or
execution side effect can occur.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

SCHEMA = "hes.adapter_family_catalog.v1"
STATUSES = {
    "active",
    "interface_only",
    "candidate_not_wired",
    "fixture_only",
    "legacy_disabled",
    "disabled",
}
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _module_symbols(root: Path, module_path: object) -> tuple[set[str], str | None]:
    if not isinstance(module_path, str) or not module_path.strip():
        return set(), "MODULE_PATH_MISSING"
    rel = PurePosixPath(module_path)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".py":
        return set(), "MODULE_PATH_INVALID"
    path = root.joinpath(*rel.parts)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return set(), "MODULE_PATH_ESCAPES_ROOT"
    if not path.is_file():
        return set(), "MODULE_NOT_FOUND"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set(), "MODULE_PARSE_FAILED"
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return names, None


def validate_catalog(root: Path, payload: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if payload.get("schema") != SCHEMA:
        errors.append("SCHEMA_MISMATCH")
    if type(payload.get("revision")) is not int or payload.get("revision") != 1:
        errors.append("REVISION_UNSUPPORTED")
    baseline = payload.get("baseline_release_sha")
    if not isinstance(baseline, str) or not _SHA40.fullmatch(baseline):
        errors.append("BASELINE_RELEASE_SHA_INVALID")
    if payload.get("catalog_mode") != "inventory_only_no_dynamic_loader":
        errors.append("CATALOG_MUST_NOT_BE_RUNTIME_LOADER")

    market_policy = payload.get("market_data_policy")
    if not isinstance(market_policy, Mapping):
        errors.append("MARKET_DATA_POLICY_MISSING")
        market_policy = {}
    if market_policy.get("auto_discovery") is not False:
        errors.append("MARKET_DATA_AUTO_DISCOVERY_MUST_BE_DISABLED")
    if market_policy.get("automatic_failover") is not False:
        errors.append("MARKET_DATA_AUTO_FAILOVER_MUST_BE_DISABLED")
    if market_policy.get("browser_direct_exchange_access") is not False:
        errors.append("BROWSER_DIRECT_EXCHANGE_ACCESS_MUST_BE_DISABLED")
    if market_policy.get("chart_and_analysis_share_same_persisted_batch") is not True:
        errors.append("CHART_ANALYSIS_BATCH_MUST_BE_SHARED")

    execution_policy = payload.get("execution_policy")
    if not isinstance(execution_policy, Mapping):
        errors.append("EXECUTION_POLICY_MISSING")
        execution_policy = {}
    if execution_policy.get("execution_enabled") is not False:
        errors.append("EXECUTION_MUST_REMAIN_DISABLED")
    if execution_policy.get("orders_placed") is not False:
        errors.append("ORDERS_MUST_REMAIN_DISABLED")
    if execution_policy.get("concrete_adapters_active") != []:
        errors.append("CONCRETE_EXECUTION_ADAPTERS_MUST_REMAIN_EMPTY")
    if not isinstance(execution_policy.get("manual_execution_surface"), str) or not execution_policy.get("manual_execution_surface", "").strip():
        errors.append("MANUAL_EXECUTION_SURFACE_MISSING")

    adapters = payload.get("adapters")
    if not isinstance(adapters, list) or not adapters:
        errors.append("ADAPTER_LIST_INVALID")
        adapters = []

    ids: set[str] = set()
    active_market_data: list[Mapping[str, Any]] = []
    active_execution: list[Mapping[str, Any]] = []
    seen_module_symbols: set[tuple[str, str]] = set()

    for index, adapter in enumerate(adapters):
        prefix = f"ADAPTER_{index}"
        if not isinstance(adapter, Mapping):
            errors.append(f"{prefix}_INVALID")
            continue

        adapter_id = adapter.get("adapter_id")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            errors.append(f"{prefix}_ID_MISSING")
        elif adapter_id in ids:
            errors.append("DUPLICATE_ADAPTER_ID")
        else:
            ids.add(adapter_id)

        domain = adapter.get("domain")
        status = adapter.get("status")
        if not isinstance(domain, str) or not domain.strip():
            errors.append(f"{prefix}_DOMAIN_MISSING")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"{prefix}_STATUS_INVALID")

        runtime_enabled = adapter.get("runtime_enabled")
        if type(runtime_enabled) is not bool:
            errors.append(f"{prefix}_RUNTIME_FLAG_INVALID")
        elif status == "active" and runtime_enabled is not True:
            errors.append(f"{prefix}_ACTIVE_RUNTIME_FLAG_FALSE")
        elif status != "active" and runtime_enabled is not False:
            errors.append(f"{prefix}_NONACTIVE_RUNTIME_FLAG_TRUE")

        for field in ("contract_version", "evidence_ref"):
            value = adapter.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}_{field.upper()}_MISSING")
        evidence_ref = adapter.get("evidence_ref")
        if isinstance(evidence_ref, str):
            evidence = PurePosixPath(evidence_ref)
            if evidence.is_absolute() or ".." in evidence.parts or not root.joinpath(*evidence.parts).is_file():
                errors.append(f"{prefix}_EVIDENCE_REF_INVALID")

        for field in ("capabilities", "side_effects"):
            values = adapter.get(field)
            if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values):
                errors.append(f"{prefix}_{field.upper()}_INVALID")

        module_symbols, module_error = _module_symbols(root, adapter.get("module_path"))
        if module_error:
            errors.append(f"{prefix}_{module_error}")
        symbol = adapter.get("symbol")
        if not isinstance(symbol, str) or symbol not in module_symbols:
            errors.append(f"{prefix}_SYMBOL_NOT_FOUND")
        elif isinstance(adapter.get("module_path"), str):
            key = (adapter["module_path"], symbol)
            if key in seen_module_symbols:
                errors.append("DUPLICATE_MODULE_SYMBOL_REGISTRATION")
            seen_module_symbols.add(key)

        contract = adapter.get("contract")
        if contract is not None:
            if not isinstance(contract, Mapping):
                errors.append(f"{prefix}_CONTRACT_INVALID")
            else:
                contract_symbols, contract_error = _module_symbols(root, contract.get("module_path"))
                if contract_error:
                    errors.append(f"{prefix}_CONTRACT_{contract_error}")
                declared = contract.get("symbols")
                if not isinstance(declared, list) or not declared:
                    errors.append(f"{prefix}_CONTRACT_SYMBOLS_INVALID")
                elif any(not isinstance(name, str) or name not in contract_symbols for name in declared):
                    errors.append(f"{prefix}_CONTRACT_SYMBOL_NOT_FOUND")

        side_effects = adapter.get("side_effects", [])
        if domain == "market_data" and status == "active":
            active_market_data.append(adapter)
            if any(effect in side_effects for effect in ("order_submit", "private_account_read", "capital_mutation")):
                errors.append("ACTIVE_MARKET_DATA_ADAPTER_HAS_FORBIDDEN_SIDE_EFFECT")
        if domain == "execution" and status == "active":
            active_execution.append(adapter)

    if len(active_market_data) != 1:
        errors.append("EXACTLY_ONE_ACTIVE_MARKET_DATA_ADAPTER_REQUIRED")
    canonical_id = market_policy.get("canonical_adapter_id")
    canonical = next((x for x in adapters if isinstance(x, Mapping) and x.get("adapter_id") == canonical_id), None)
    if canonical is None or canonical.get("status") != "active" or canonical.get("domain") != "market_data":
        errors.append("CANONICAL_MARKET_DATA_ADAPTER_NOT_ACTIVE")
    elif len(active_market_data) == 1 and active_market_data[0].get("adapter_id") != canonical_id:
        errors.append("ACTIVE_MARKET_DATA_ADAPTER_DIFFERS_FROM_CANONICAL")
    profile = market_policy.get("canonical_profile")
    if not isinstance(profile, Mapping) or canonical is None or canonical.get("profile") != profile:
        errors.append("CANONICAL_MARKET_DATA_PROFILE_MISMATCH")
    if active_execution:
        errors.append("ACTIVE_EXECUTION_ADAPTER_FORBIDDEN")

    return tuple(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("docs/adapter_family_catalog_v1.json"),
    )
    args = parser.parse_args()
    catalog_path = args.root / args.catalog
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ADAPTER_CATALOG_UNREADABLE: {exc}")
        return 2
    if not isinstance(payload, Mapping):
        print("ADAPTER_CATALOG_ROOT_INVALID")
        return 2
    errors = validate_catalog(args.root, payload)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("ADAPTER_FAMILY_CATALOG_V1: PASS")
    print(f"adapters={len(payload['adapters'])}")
    print(f"active_market_data={payload['market_data_policy']['canonical_adapter_id']}")
    print("execution_enabled=false")
    print("orders_placed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
