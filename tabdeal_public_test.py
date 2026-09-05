import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from config import SYMBOL, TIMEOUT


BASE_URLS = [
    "https://api.tabdeal.org",
    "https://api1.tabdeal.org",
]

ENDPOINTS = [
    "/api/v1/ping",
    "/api/v1/exchangeInfo",
    "/api/v1/time",

    # Candidate public market-data endpoints
    "/api/v1/klines",
    "/api/v1/futures/klines",
    "/fapi/v1/klines",
    "/api/v1/fapi/klines",
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
            )[:1200]
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

    print("=== TABDEAL FUTURES API DISCOVERY TEST ===")
    print(f"Target symbol: {SYMBOL}")
    print()

    successful = []

    for base_url in BASE_URLS:

        print()
        print("#" * 70)
        print(f"BASE URL: {base_url}")
        print("#" * 70)

        for endpoint in ENDPOINTS:

            url = base_url + endpoint

            # Add parameters only to endpoints where they may be useful.
            if "klines" in endpoint:
                url += f"?symbol={SYMBOL}&interval=15m&limit=5"

            if endpoint.endswith("exchangeInfo"):
                url += f"?symbol={SYMBOL}"

            if test_endpoint(url):
                successful.append(url)

    print()
    print("=" * 70)
    print("DISCOVERY SUMMARY")
    print("=" * 70)

    if successful:
        print("Successful endpoints:")
        for url in successful:
            print(f"  + {url}")
    else:
        print("No candidate endpoint returned a successful response.")

    print()
    print("=== TEST COMPLETE ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
