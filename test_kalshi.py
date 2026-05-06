import requests

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

# Test KXHIGHNY
url = f"{BASE_URL}/events"
response = requests.get(url, params={"series_ticker": "KXHIGHNY"})
print("Events for KXHIGHNY:", response.json())

url_markets = f"{BASE_URL}/markets"
response_markets = requests.get(url_markets, params={"series_ticker": "KXHIGHNY", "status": "open"})
print("Markets for KXHIGHNY:", len(response_markets.json().get('markets', [])))

# Test NBA
response_nba = requests.get(url_markets, params={"series_ticker": "NBA", "status": "open"})
print("Markets for NBA:", len(response_nba.json().get('markets', [])))
