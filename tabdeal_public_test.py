import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from config import SYMBOL, TIMEOUT


BASE_URL = "https://api1.tabdeal.org"

ENDPOINTS = [
    "/r/fapi/v1/ping",
    "/r/fapi/v1/time",
    "/r/fapi/v1/exchangeInfo",
    "/r/fapi/v1/depth",
    "/r/fapi/v1/aggDepth",
    "/r/fapi/v1/klines",
]


def get_json(url):
    req = Request(
        url,
        headers={
            "User-Agent": "btc-tabdeal-paper-test/1.0",
            "Accept": "application/json",
        },
    )

    with urlopen(req, timeout=TIMEOUT) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)


def test_endpoint(url):
    print("=" * 70)
    print(f"Testing: {url}")

    try:
        status, data = get_json(url)

        print(f"HTTP: {status}")
        print(
            "Response:",
            json.dumps(
                data,
                ensure_ascii=False,
                separators=(",", ":")
            )[:2500]
        )

        return True

    except HTTPError as e:
        print(f"HTTP ERROR: {e.code} {e.reason}")
        return False

    except URLError as e:
        print(f"NETWORK ERROR: {e.reason}")
        return False

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return False


def main():

    print("=== TABDEAL FUTURES API TEST ===")
    print(f"Symbol: {SYMBOL}")
    print("Tabdeal Futures symbol: BTC_USDT")
    print()

    successful = []

    for endpoint in ENDPOINTS:

        url = BASE_URL + endpoint

        if endpoint.endswith("/exchangeInfo"):
            url += "?symbol=BTC_USDT"

        elif endpoint.endswith("/depth"):
            url += "?symbol=BTC_USDT&limit=5"

        elif endpoint.endswith("/aggDepth"):
            url += "?symbol=BTC_USDT&limit=5"

        elif endpoint.endswith("/klines"):
            url += "?symbol=BTC_USDT&interval=15m&limit=5"

        if test_endpoint(url):
            successful.append(url)

    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for url in successful:
        print(f"  + {url}")

    print()
    print("=== TEST COMPLETE ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
