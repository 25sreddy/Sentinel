import requests

url = "https://external-api.kalshi.com/trade-api/v2/events"
res = requests.get(url)
data = res.json()

events = data.get("events", [])
nba_series = set()

for e in events:
    title = e.get("title", "").lower()
    ticker = e.get("event_ticker", "").lower()
    # Check for NBA related keywords
    if any(k in title or k in ticker for k in ["nba", "basketball", "lakers", "celtics", "knicks"]):
        nba_series.add(e["series_ticker"])

print("NBA Series Tickers:", list(nba_series))
