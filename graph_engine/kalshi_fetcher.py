"""
kalshi_fetcher.py
Fetches all active NBA markets from Kalshi and extracts structured
Player / Team / Market nodes ready for ingestion into Neo4j.
"""

import re
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"

NBA_SERIES = [
    "KXNBASERIES",   # Series winner futures
    "KXNBAGAME",     # Moneyline
    "KXNBASPREAD",   # Spread
    "KXNBATOTAL",    # Over/Under
    "KXNBAPTS",      # Player points
    "KXNBAREB",      # Player rebounds
    "KXNBAAST",      # Player assists
    "KXNBA3PT",      # Player 3-pointers
    "KXNBABLK",      # Player blocks
    "KXNBASTL",      # Player steals
]

# Known NBA teams (city name → full name)
TEAM_MAP = {
    "oklahoma city": "Oklahoma City Thunder",
    "oklahoma":      "Oklahoma City Thunder",
    "okc":           "Oklahoma City Thunder",
    "los angeles l": "Los Angeles Lakers",
    "lakers":        "Los Angeles Lakers",
    "lal":           "Los Angeles Lakers",
    "minnesota":     "Minnesota Timberwolves",
    "timberwolves":  "Minnesota Timberwolves",
    "min":           "Minnesota Timberwolves",
    "san antonio":   "San Antonio Spurs",
    "spurs":         "San Antonio Spurs",
    "sas":           "San Antonio Spurs",
    "cleveland":     "Cleveland Cavaliers",
    "cavaliers":     "Cleveland Cavaliers",
    "cle":           "Cleveland Cavaliers",
    "new york":      "New York Knicks",
    "knicks":        "New York Knicks",
    "nyk":           "New York Knicks",
    "philadelphia":  "Philadelphia 76ers",
    "76ers":         "Philadelphia 76ers",
    "phi":           "Philadelphia 76ers",
    "detroit":       "Detroit Pistons",
    "pistons":       "Detroit Pistons",
    "det":           "Detroit Pistons",
    "indiana":       "Indiana Pacers",
    "pacers":        "Indiana Pacers",
    "ind":           "Indiana Pacers",
    "boston":        "Boston Celtics",
    "celtics":       "Boston Celtics",
    "bos":           "Boston Celtics",
    "miami":         "Miami Heat",
    "heat":          "Miami Heat",
    "mia":           "Miami Heat",
    "denver":        "Denver Nuggets",
    "nuggets":       "Denver Nuggets",
    "den":           "Denver Nuggets",
    "golden state":  "Golden State Warriors",
    "warriors":      "Golden State Warriors",
    "gsw":           "Golden State Warriors",
    "houston":       "Houston Rockets",
    "rockets":       "Houston Rockets",
    "hou":           "Houston Rockets",
    "memphis":       "Memphis Grizzlies",
    "grizzlies":     "Memphis Grizzlies",
    "mem":           "Memphis Grizzlies",
    "dallas":        "Dallas Mavericks",
    "mavericks":     "Dallas Mavericks",
    "dal":           "Dallas Mavericks",
}

# Regex to detect point thresholds like "25+ Points" or "Over 30 Points"
THRESHOLD_RE = re.compile(r'(\d+\.?\d*)\+?\s*(?:or\s*more\s*)?points?', re.IGNORECASE)
OVER_RE      = re.compile(r'over\s+(\d+\.?\d*)', re.IGNORECASE)


@dataclass
class MarketNode:
    ticker:          str
    title:           str
    series_ticker:   str
    yes_bid:         Optional[float]
    no_bid:          Optional[float]
    volume:          Optional[float]
    implied_prob:    Optional[float]      # yes_bid * 100 if cents-based
    prop_type:       Optional[str]        # points / rebounds / assists / blocks / steals / 3pt / series / spread / total / moneyline
    threshold:       Optional[float]      # numeric threshold (e.g. 25.5)
    player_name:     Optional[str]
    team_name:       Optional[str]
    event_ticker:    Optional[str]


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_team(title: str) -> Optional[str]:
    low = title.lower()
    for keyword, full_name in TEAM_MAP.items():
        if keyword in low:
            return full_name
    return None


def _extract_threshold(title: str) -> Optional[float]:
    m = THRESHOLD_RE.search(title) or OVER_RE.search(title)
    return float(m.group(1)) if m else None


def _infer_prop_type(series_ticker: str, title: str) -> str:
    s = series_ticker.upper()
    t = title.lower()
    if "KXNBAPTS"    in s or "point"   in t: return "points"
    if "KXNBAREB"    in s or "rebound" in t: return "rebounds"
    if "KXNBAAST"    in s or "assist"  in t: return "assists"
    if "KXNBABLK"    in s or "block"   in t: return "blocks"
    if "KXNBASTL"    in s or "steal"   in t: return "steals"
    if "KXNBA3PT"    in s or "three"   in t or "3pt" in t: return "threes"
    if "KXNBASERIES" in s or "series"  in t: return "series"
    if "KXNBASPREAD" in s or "spread"  in t: return "spread"
    if "KXNBATOTAL"  in s or "total"   in t: return "total"
    if "KXNBAGAME"   in s:                   return "moneyline"
    return "other"


def _extract_player(title: str) -> Optional[str]:
    """
    Heuristic: player name usually appears before a colon or before digit-based prop.
    e.g. "Tyrese Maxey: 25+ Points" → "Tyrese Maxey"
    """
    colon = title.split(":")
    if len(colon) > 1:
        candidate = colon[0].strip()
        # Rough sanity check — player names are 2–4 words with no digits
        words = candidate.split()
        if 2 <= len(words) <= 4 and not any(c.isdigit() for c in candidate):
            return candidate

    # Fallback: extract text before first number occurrence
    m = re.match(r'^([A-Za-z\s\.\-\']+?)(?=\s+\d|\s+over|\s+under)', title, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if len(candidate.split()) >= 2:
            return candidate
    return None


def fetch_series_markets(series_ticker: str) -> list[dict]:
    """Fetch all open markets for a given Kalshi series ticker."""
    url = f"{KALSHI_BASE}/markets"
    params = {"series_ticker": series_ticker, "status": "open", "limit": 200}
    markets = []
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        markets = resp.json().get("markets", [])
    except Exception as exc:
        print(f"[WARN] Failed to fetch {series_ticker}: {exc}")
    return markets


def build_market_nodes() -> list[MarketNode]:
    """
    Main entry point.
    Fetches all NBA series, extracts structured nodes.
    """
    nodes: list[MarketNode] = []

    for series in NBA_SERIES:
        print(f"  Fetching {series}...")
        raw_markets = fetch_series_markets(series)

        for m in raw_markets:
            title         = m.get("title", "")
            yes_bid       = _to_float(m.get("yes_bid_dollars"))
            prop_type     = _infer_prop_type(series, title)
            is_player_prop = prop_type in ("points","rebounds","assists","blocks","steals","threes")

            node = MarketNode(
                ticker        = m.get("ticker", ""),
                title         = title,
                series_ticker = series,
                yes_bid       = yes_bid,
                no_bid        = _to_float(m.get("no_bid_dollars")),
                volume        = _to_float(m.get("volume_fp")),
                implied_prob  = round(yes_bid * 100, 1) if yes_bid is not None else None,
                prop_type     = prop_type,
                threshold     = _extract_threshold(title),
                player_name   = _extract_player(title) if is_player_prop else None,
                team_name     = _extract_team(title),
                event_ticker  = m.get("event_ticker"),
            )
            nodes.append(node)

    print(f"\n✅ Extracted {len(nodes)} market nodes across {len(NBA_SERIES)} series.")
    return nodes


if __name__ == "__main__":
    import json
    nodes = build_market_nodes()
    # Pretty-print a sample
    sample = [asdict(n) for n in nodes[:5]]
    print(json.dumps(sample, indent=2))
