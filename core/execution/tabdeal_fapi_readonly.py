"""Signed GET-only Tabdeal FAPI client with a strict endpoint allowlist.

In Tabdeal's docs, [TRADE] denotes signed API-key authentication (API key plus
secret/HMAC); it is not a documented API-key permission-scope statement.
This client exposes GET only and cannot prove the key is exchange-side read-only.
No order, cancel, leverage mutation, transfer, SL/TP mutation, or close method
exists. Credentials are supplied by systemd's credential directory; this
module never loads secrets from repository files or environment variables.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import time
from pathlib import Path
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api1.tabdeal.org"
_ENDPOINT_PARAMS = {
    "/r/fapi/v1/leverage": ({"symbol"}, {"symbol"}),
    "/r/fapi/v3/account": (set(), set()),
    "/r/fapi/v3/balance": (set(), set()),
    "/r/fapi/v1/income": (
        {"symbol", "incomeType", "startTime", "endTime", "limit"}, set()
    ),
    "/r/fapi/v1/forceOrders": ({"symbol", "startTime", "endTime"}, set()),
    "/r/fapi/v3/positionRisk": ({"symbol"}, set()),
    "/r/fapi/v1/openOrders": ({"symbol", "limit"}, set()),
    "/r/fapi/v1/allOrders": (
        {"symbol", "startTime", "endTime", "isActive", "isDone", "limit"},
        {"symbol"},
    ),
    "/r/fapi/v1/userTrades": (
        {"symbol", "startTime", "endTime", "fromId", "limit"},
        {"symbol"},
    ),
    "/r/fapi/v1/position": (
        {"symbol", "side", "state", "isActive", "startTime", "endTime", "limit"},
        set(),
    ),
}


class FapiReadError(RuntimeError):
    """Sanitized read failure; never includes request URL or credential data."""


def load_systemd_credentials(directory: str | os.PathLike[str] | None = None) -> tuple[str, str]:
    """Read named files with O_NOFOLLOW from a private systemd credential dir."""
    raw_dir = directory if directory is not None else os.environ.get("CREDENTIALS_DIRECTORY")
    if not raw_dir:
        raise FapiReadError("SYSTEMD_CREDENTIALS_DIRECTORY_MISSING")
    root = Path(raw_dir)
    if not root.is_absolute():
        raise FapiReadError("CREDENTIALS_DIRECTORY_PATH_INVALID")
    dir_fd = None
    values: list[str] = []
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = os.open(str(root), flags)
        root_stat = os.fstat(dir_fd)
        # systemd v255 may expose LoadCredential* material as root:root
        # mode 0550/0440 while granting the service UID access through its
        # credential ACL. Permit group read/execute, but never group-write or
        # any world permission; verify actual access through open(O_NOFOLLOW).
        if not stat.S_ISDIR(root_stat.st_mode) or (root_stat.st_mode & 0o027):
            raise FapiReadError("CREDENTIALS_DIRECTORY_PERMISSIONS_INVALID")
        for filename in ("tabdeal_api_key", "tabdeal_api_secret"):
            fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)
            try:
                file_stat = os.fstat(fd)
                if (not stat.S_ISREG(file_stat.st_mode) or (file_stat.st_mode & 0o037)
                        or file_stat.st_size > 4096):
                    raise FapiReadError("CREDENTIAL_FILE_PERMISSIONS_INVALID")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(4097)
                if len(raw) > 4096:
                    raise FapiReadError("CREDENTIAL_FILE_CONTENT_INVALID")
                value = raw.decode("utf-8").strip()
                if not value or "\n" in value or "\r" in value:
                    raise FapiReadError("CREDENTIAL_FILE_CONTENT_INVALID")
                values.append(value)
            except UnicodeDecodeError as exc:
                raise FapiReadError("CREDENTIAL_FILE_CONTENT_INVALID") from exc
            finally:
                os.close(fd)
    except FapiReadError:
        raise
    except OSError as exc:
        raise FapiReadError("CREDENTIAL_FILE_UNAVAILABLE_OR_UNSAFE") from exc
    finally:
        if dir_fd is not None:
            os.close(dir_fd)
    return values[0], values[1]


class TabdealFapiReadOnlyClient:
    """Allowlisted signed-GET client; no mutating HTTP method is exposed.

    Tabdeal's [TRADE] label means signed API-key authentication, not a
    documented key permission scope. This client itself exposes GET only.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        opener: Callable = urlopen,
        clock_ms: Callable[[], int] | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("API credentials must be non-empty")
        self.__api_key = api_key
        self.__api_secret = api_secret.encode("utf-8")
        self._opener = opener
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._timeout = timeout

    def get(self, endpoint: str, params: Mapping[str, object] | None = None):
        """Call one exact documented read endpoint with HMAC-SHA256 signing."""
        if endpoint not in _ENDPOINT_PARAMS:
            raise ValueError("endpoint_not_in_read_only_allowlist")
        supplied = dict(params or {})
        allowed, required = _ENDPOINT_PARAMS[endpoint]
        if set(supplied) - allowed:
            raise ValueError("query_parameter_not_in_endpoint_allowlist")
        if required - set(supplied):
            raise ValueError("required_query_parameter_missing")
        for key, value in supplied.items():
            if value is None or isinstance(value, (dict, list, tuple)):
                raise ValueError("query_parameter_value_invalid")
            if key == "symbol" and (not isinstance(value, str) or not value.strip()):
                raise ValueError("symbol_invalid")
            if key == "limit" and (type(value) is not int or not 1 <= value <= 100):
                raise ValueError("limit_out_of_documented_range")
            if key == "incomeType" and value not in {
                "Transfer", "TakerCommission", "MakerCommission", "TradePNL",
                "AdlPNL", "Liquidation", "InsuranceFund",
            }:
                raise ValueError("income_type_invalid")
            if key in {"startTime", "endTime", "fromId", "state"} and type(value) is not int:
                raise ValueError("integer_query_parameter_required")
            if key == "isActive" and value not in (0, 1):
                raise ValueError("isActive_must_be_0_or_1")
            if key == "side" and value not in ("BUY", "SELL"):
                raise ValueError("side_invalid")

        ordered = list(supplied.items())
        ordered.append(("timestamp", int(self._clock_ms())))
        query = urlencode(ordered)
        signature = hmac.new(
            self.__api_secret, query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        request = Request(
            f"{BASE_URL}{endpoint}?{query}&signature={signature}",
            headers={"X-MBX-APIKEY": self.__api_key},
            method="GET",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            # Preserve only the documented numeric API error code for audit;
            # never persist or expose the response message/body.
            api_code = None
            try:
                error_payload = json.loads(exc.read(8192).decode("utf-8"))
                if isinstance(error_payload, dict) and type(error_payload.get("code")) is int:
                    api_code = error_payload["code"]
            except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                pass
            suffix = f"_API_CODE_{api_code}" if api_code is not None else ""
            raise FapiReadError(f"FAPI_HTTP_ERROR_{exc.code}{suffix}") from None
        except (URLError, TimeoutError, OSError):
            raise FapiReadError("FAPI_READ_TRANSPORT_ERROR") from None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise FapiReadError("FAPI_RESPONSE_NOT_VALID_JSON") from None

    def get_leverage(self, symbol: str):
        return self.get("/r/fapi/v1/leverage", {"symbol": symbol})

    def get_account(self):
        return self.get("/r/fapi/v3/account")

    def get_balance(self):
        """Return the documented per-asset futures wallet balance."""
        return self.get("/r/fapi/v3/balance")

    def get_income(self, **filters):
        """Return documented income history; does not establish future fees."""
        return self.get("/r/fapi/v1/income", filters)

    def get_force_orders(self, **filters):
        """Return up to 100 forced/liquidation orders.

        Tabdeal currently documents startTime/endTime as accepted but unused
        by the server; callers must not assume those filters are applied.
        """
        return self.get("/r/fapi/v1/forceOrders", filters)

    def get_position_risk(self, symbol: str | None = None):
        return self.get("/r/fapi/v3/positionRisk",
                        {} if symbol is None else {"symbol": symbol})

    def get_open_orders(self, symbol: str | None = None, limit: int | None = None):
        params = {}
        if symbol is not None:
            params["symbol"] = symbol
        if limit is not None:
            params["limit"] = limit
        return self.get("/r/fapi/v1/openOrders", params)

    def get_all_orders(self, symbol: str, **filters):
        return self.get("/r/fapi/v1/allOrders", {"symbol": symbol, **filters})

    def get_user_trades(self, symbol: str, **filters):
        """Read fills; Tabdeal docs say fromId is currently unused by the server.

        Do not rely on fromId for pagination. The documented result cap is 100;
        completeness must not be assumed from a short response.
        """
        return self.get("/r/fapi/v1/userTrades", {"symbol": symbol, **filters})

    def get_positions(self, **filters):
        return self.get("/r/fapi/v1/position", filters)
