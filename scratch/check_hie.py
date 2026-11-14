import requests
import json

endpoints = [
    "/api/v1/hie/status",
    "/api/v1/hie/candles/EURUSD/H1",
    "/api/v1/hie/setups?limit=2",
    "/api/v1/hie/pattern-stats?limit=2",
    "/api/v1/hie/failure-patterns",
    "/api/v1/hie/calibration"
]

for ep in endpoints:
    url = f"http://127.0.0.1:8001{ep}"
    print(f"\n=========================================\nGET {ep}\n=========================================")
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            print(json.dumps(res.json(), indent=2))
        else:
            print(f"Error {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Failed to query {url}: {e}")
