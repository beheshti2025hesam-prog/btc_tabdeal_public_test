import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from core.execution.tabdeal_fapi_readonly import (
    BASE_URL,
    FapiReadError,
    TabdealFapiReadOnlyClient,
    load_systemd_credentials,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


def make_client(calls, body=b'{"ok":true}'):
    def opener(request, timeout):
        calls.append((request, timeout))
        return FakeResponse(body)
    return TabdealFapiReadOnlyClient(
        "test-key", "test-secret", opener=opener, clock_ms=lambda: 1700000000123
    )


def test_signed_request_is_get_and_signature_matches_query():
    calls = []
    result = make_client(calls).get_leverage("BTCUSDT")
    request, timeout = calls[0]
    assert result == {"ok": True}
    assert request.get_method() == "GET"
    assert request.full_url.startswith(BASE_URL + "/r/fapi/v1/leverage?")
    assert request.get_header("X-mbx-apikey") == "test-key"
    query = parse_qs(urlsplit(request.full_url).query)
    signature = query.pop("signature")[0]
    unsigned_query = request.full_url.split("?", 1)[1].rsplit("&signature=", 1)[0]
    expected = hmac.new(b"test-secret", unsigned_query.encode(), hashlib.sha256).hexdigest()
    assert signature == expected
    assert query["symbol"] == ["BTCUSDT"]
    assert query["timestamp"] == ["1700000000123"]
    assert timeout == 10.0


@pytest.mark.parametrize("endpoint", [
    "/fapi/v1/order", "/fapi/v1/leverage", "/fapi/v1/transfer",
    "/r/fapi/v1/positionSlTp", "/r/fapi/v1/does-not-exist",
])
def test_mutating_or_unknown_endpoint_is_rejected_without_network(endpoint):
    calls = []
    with pytest.raises(ValueError, match="endpoint_not_in_read_only_allowlist"):
        make_client(calls).get(endpoint)
    assert calls == []


def test_unknown_query_parameter_is_rejected():
    calls = []
    with pytest.raises(ValueError, match="query_parameter_not_in_endpoint_allowlist"):
        make_client(calls).get("/r/fapi/v1/leverage", {"symbol": "BTCUSDT", "leverage": 20})
    assert calls == []


def test_required_symbol_is_enforced():
    calls = []
    with pytest.raises(ValueError, match="required_query_parameter_missing"):
        make_client(calls).get("/r/fapi/v1/userTrades")
    assert calls == []


def test_account_and_position_methods_only_use_read_endpoints():
    calls = []
    client = make_client(calls)
    client.get_account()
    client.get_position_risk("BTCUSDT")
    client.get_open_orders("BTCUSDT", 50)
    client.get_all_orders("BTCUSDT", startTime=100, endTime=200, limit=100)
    client.get_user_trades("BTCUSDT", startTime=100, endTime=200, limit=100)
    client.get_positions(symbol="BTCUSDT", isActive=1)
    assert [urlsplit(c[0].full_url).path for c in calls] == [
        "/r/fapi/v3/account", "/r/fapi/v3/positionRisk",
        "/r/fapi/v1/openOrders", "/r/fapi/v1/allOrders",
        "/r/fapi/v1/userTrades", "/r/fapi/v1/position",
    ]
    assert all(c[0].get_method() == "GET" for c in calls)




def test_http_error_preserves_only_numeric_api_code():
    def opener(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", {},
                        io.BytesIO(b'{"code":1100,"msg":"Access denied."}'))
    client = TabdealFapiReadOnlyClient("test-key", "test-secret", opener=opener)
    with pytest.raises(FapiReadError, match="FAPI_HTTP_ERROR_401_API_CODE_1100") as exc:
        client.get_account()
    assert "Access denied" not in str(exc.value)
    assert "test-key" not in str(exc.value)

def test_invalid_json_is_rejected():
    calls = []
    with pytest.raises(FapiReadError, match="FAPI_RESPONSE_NOT_VALID_JSON"):
        make_client(calls, b"not-json").get_account()


def test_credentials_load_only_from_private_systemd_directory(tmp_path):
    key = tmp_path / "tabdeal_api_key"
    secret = tmp_path / "tabdeal_api_secret"
    key.write_text("safe-key\n")
    secret.write_text("safe-secret\n")
    key.chmod(0o400)
    secret.chmod(0o400)
    tmp_path.chmod(0o700)
    assert load_systemd_credentials(tmp_path) == ("safe-key", "safe-secret")


def test_credentials_reject_world_readable_or_group_writable_file(tmp_path):
    key = tmp_path / "tabdeal_api_key"
    secret = tmp_path / "tabdeal_api_secret"
    key.write_text("safe-key")
    secret.write_text("safe-secret")
    key.chmod(0o644)
    secret.chmod(0o400)
    tmp_path.chmod(0o700)
    with pytest.raises(FapiReadError, match="CREDENTIAL_FILE_PERMISSIONS_INVALID"):
        load_systemd_credentials(tmp_path)
    key.chmod(0o460)  # group-write is never permitted
    with pytest.raises(FapiReadError, match="CREDENTIAL_FILE_PERMISSIONS_INVALID"):
        load_systemd_credentials(tmp_path)


def test_credentials_accept_systemd_read_only_group_modes(tmp_path):
    key = tmp_path / "tabdeal_api_key"
    secret = tmp_path / "tabdeal_api_secret"
    key.write_text("safe-key")
    secret.write_text("safe-secret")
    key.chmod(0o440)
    secret.chmod(0o440)
    tmp_path.chmod(0o550)
    assert load_systemd_credentials(tmp_path) == ("safe-key", "safe-secret")


def test_credentials_reject_symlink(tmp_path):
    key = tmp_path / "tabdeal_api_key"
    secret = tmp_path / "tabdeal_api_secret"
    target = tmp_path / "key-source"
    target.write_text("safe-key")
    key.symlink_to(target)
    secret.write_text("safe-secret")
    secret.chmod(0o400)
    tmp_path.chmod(0o700)
    with pytest.raises(FapiReadError, match="CREDENTIAL_FILE_UNAVAILABLE_OR_UNSAFE"):
        load_systemd_credentials(tmp_path)


def test_limit_is_bounded_by_documented_api_range():
    calls = []
    with pytest.raises(ValueError, match="limit_out_of_documented_range"):
        make_client(calls).get_open_orders("BTCUSDT", 101)
    assert calls == []


def test_client_exposes_no_mutating_http_helpers():
    client = make_client([])
    assert not hasattr(client, "post")
    assert not hasattr(client, "delete")
    assert not hasattr(client, "cancel_order")


def test_balance_income_and_force_order_methods_use_documented_get_allowlist():
    calls = []
    client = make_client(calls)
    client.get_balance()
    client.get_income(
        symbol="BTCUSDT", incomeType="TradePNL",
        startTime=100, endTime=200, limit=100,
    )
    client.get_force_orders(symbol="BTCUSDT", startTime=100, endTime=200)

    assert [urlsplit(c[0].full_url).path for c in calls] == [
        "/r/fapi/v3/balance",
        "/r/fapi/v1/income",
        "/r/fapi/v1/forceOrders",
    ]
    assert all(c[0].get_method() == "GET" for c in calls)
    income_query = parse_qs(urlsplit(calls[1][0].full_url).query)
    assert income_query["incomeType"] == ["TradePNL"]
    assert income_query["limit"] == ["100"]
    force_query = parse_qs(urlsplit(calls[2][0].full_url).query)
    assert force_query["startTime"] == ["100"]
    assert force_query["endTime"] == ["200"]


@pytest.mark.parametrize("income_type", ["UNKNOWN", "tradepnl", ""])
def test_income_type_must_match_documented_enum(income_type):
    calls = []
    with pytest.raises(ValueError, match="income_type_invalid"):
        make_client(calls).get_income(incomeType=income_type)
    assert calls == []


@pytest.mark.parametrize("limit", [0, 101, True, "100"])
def test_income_limit_is_strictly_bounded(limit):
    calls = []
    with pytest.raises(ValueError, match="limit_out_of_documented_range"):
        make_client(calls).get_income(limit=limit)
    assert calls == []


def test_force_order_time_filters_must_be_integer_milliseconds():
    calls = []
    with pytest.raises(ValueError, match="integer_query_parameter_required"):
        make_client(calls).get_force_orders(startTime="yesterday")
    assert calls == []


def test_income_type_rejects_none_before_network():
    calls = []
    with pytest.raises(ValueError, match="query_parameter_value_invalid"):
        make_client(calls).get_income(incomeType=None)
    assert calls == []
