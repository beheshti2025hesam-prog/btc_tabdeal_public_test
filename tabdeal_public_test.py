import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from config import TEST_ENDPOINTS, TIMEOUT, SYMBOL

def get_json(url):
    req = Request(url, headers={"User-Agent": "btc-tabdeal-test/1.0"})
    with urlopen(req, timeout=TIMEOUT) as response:
        return response.status, json.loads(response.read().decode("utf-8"))

def main():
    print("=== TABDEAL PUBLIC API TEST ===")
    print(f"Symbol target: {SYMBOL}\n")

    for url in TEST_ENDPOINTS:
        print(f"Testing: {url}")
        try:
            status, data = get_json(url)
            print(f"HTTP: {status}")
            print("Response:", json.dumps(data, ensure_ascii=False)[:1500])

            if "exchangeInfo" in url:
                if SYMBOL in json.dumps(data, ensure_ascii=False):
                    print(f"FOUND: {SYMBOL}")
                else:
                    print(f"WARNING: {SYMBOL} was not found in exchangeInfo response.")
            print("OK\n")
        except HTTPError as e:
            print(f"HTTP ERROR: {e.code} {e.reason}")
            sys.exit(1)
        except URLError as e:
            print(f"NETWORK ERROR: {e.reason}")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            sys.exit(1)

    print("=== PUBLIC TABDEAL CONNECTION TEST PASSED ===")

if __name__ == "__main__":
    main()
