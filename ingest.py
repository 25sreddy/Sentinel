import requests
import duckdb
import json
import os
from datetime import datetime

# Kalshi API Base URL
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

# DuckDB setup
DB_FILE = "kalshi_data.duckdb"

def init_db():
    """Initializes DuckDB and creates tables for raw data."""
    conn = duckdb.connect(DB_FILE)
    
    # Create table to store raw events
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_kalshi_events (
            ingestion_timestamp TIMESTAMP,
            event_ticker VARCHAR,
            series_ticker VARCHAR,
            raw_event_data JSON
        )
    """)
    
    # Create table to store raw markets and capture last_price
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_kalshi_markets (
            ingestion_timestamp TIMESTAMP,
            event_ticker VARCHAR,
            market_ticker VARCHAR,
            last_price BIGINT,
            raw_market_data JSON
        )
    """)
    return conn

def fetch_events(series_ticker):
    """Fetches active events for a given series from Kalshi."""
    url = f"{BASE_URL}/events"
    params = {
        "series_ticker": series_ticker
    }
    
    print(f"Fetching events for {series_ticker}...")
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print(f"Error fetching events for {series_ticker}: {response.text}")
        return []
    
    return response.json().get("events", [])

def fetch_markets_for_event(event_ticker):
    """Fetches the associated markets for a specific event."""
    url = f"{BASE_URL}/markets"
    params = {
        "event_ticker": event_ticker
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Error fetching markets for event {event_ticker}: {response.text}")
        return []
        
    data = response.json()
    return data.get("markets", [])

def main():
    conn = init_db()
    
    # Target series from the Kalshi taxonomy structure
    series_tickers = [
        "KXNBASERIES", "KXNBAGAME", "KXNBASPREAD", "KXNBATOTAL", 
        "KXNBAPTS", "KXNBAREB", "KXNBAAST", "KXNBA3PT", "KXNBABLK", "KXNBASTL"
    ]
    timestamp = datetime.now()
    
    for series in series_tickers:
        events = fetch_events(series)
        print(f"Found {len(events)} active events for {series}")
        
        for event in events:
            event_ticker = event.get("event_ticker")
            
            # Store the raw event in DuckDB
            conn.execute(
                "INSERT INTO raw_kalshi_events VALUES (?, ?, ?, ?)",
                [timestamp, event_ticker, series, json.dumps(event)]
            )
            
            # Fetch markets to get the last_price
            markets = fetch_markets_for_event(event_ticker)
            print(f"  - Event {event_ticker}: found {len(markets)} markets")
            
            for market in markets:
                market_ticker = market.get("ticker")
                last_price = market.get("last_price")
                
                # Store the raw market in DuckDB
                conn.execute(
                    "INSERT INTO raw_kalshi_markets VALUES (?, ?, ?, ?, ?)",
                    [timestamp, event_ticker, market_ticker, last_price, json.dumps(market)]
                )
                
    print(f"Data ingestion complete. Raw data stored in {DB_FILE}")
    conn.close()

if __name__ == "__main__":
    main()
