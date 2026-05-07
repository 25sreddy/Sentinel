import requests
res = requests.get('https://external-api.kalshi.com/trade-api/v2/series').json()
series = res.get('series', [])
nba_series = [s['ticker'] for s in series if 'nba' in s['ticker'].lower() or 'nba' in s.get('title', '').lower() or 'basketball' in s.get('title', '').lower()]
for ticker in nba_series:
    print(ticker)
