import requests
import json
import sys

def verify_sportsbook_odds():
    api_key = "91918d81dcb172e2336a97b7ae601ad1"
    sport = "basketball_nba"
    
    print("=== Sportsbook Odds Verification ===")
    
    # 1. Verify API Connectivity & Get Events
    print("\n1. Checking connectivity and fetching active NBA events...")
    events_url = f"https://api.the-odds-api.com/v4/sports/{sport}/events?apiKey={api_key}"
    res = requests.get(events_url)
    
    if res.status_code != 200:
        print(f"❌ FAILED: API Error {res.status_code}")
        print(res.text)
        sys.exit(1)
        
    events = res.json()
    if not isinstance(events, list) or len(events) == 0:
        print("⚠️ WARNING: No active NBA events found at the moment.")
        sys.exit(0)
        
    print(f"✅ SUCCESS: Found {len(events)} active events.")
    
    # Select first event to verify markets
    event = events[0]
    event_id = event['id']
    print(f"\nTarget Event for Verification: {event['home_team']} vs {event['away_team']}")
    
    # 2. Get player props and verify markets
    markets_to_test = "player_points,player_rebounds,player_assists"
    print(f"\n2. Fetching markets ({markets_to_test}) for the event...")
    odds_url = f"https://api.the-odds-api.com/v4/sports/{sport}/events/{event_id}/odds?apiKey={api_key}&regions=us&markets={markets_to_test}&oddsFormat=american"
    
    odds_res = requests.get(odds_url)
    
    if odds_res.status_code != 200:
        print(f"❌ FAILED: Odds API Error {odds_res.status_code}")
        print(odds_res.text)
        sys.exit(1)
        
    data = odds_res.json()
    
    if not isinstance(data, dict) or 'bookmakers' not in data:
        print("❌ FAILED: Invalid data structure returned from Odds API")
        sys.exit(1)
        
    bookmakers = data.get('bookmakers', [])
    if len(bookmakers) == 0:
        print("⚠️ WARNING: No bookmakers currently offering odds for these markets on this event.")
        sys.exit(0)
        
    print(f"✅ SUCCESS: Found odds from {len(bookmakers)} bookmakers.")
    
    # 3. Verify Market Details
    print("\n3. Validating Market Data Structure...")
    validation_passed = True
    
    # Just show the first bookmaker as an example
    sample_bm = bookmakers[0]
    print(f"\n--- Sample Data from Bookmaker: {sample_bm['title']} ---")
    
    for market in sample_bm.get('markets', []):
        market_name = market['key']
        outcomes = market.get('outcomes', [])
        
        print(f"Market Name: {market_name}")
        print(f"  - Total Players/Outcomes Found: {len(outcomes)}")
        
        # Verify outcomes have expected fields
        for out in outcomes:
            if 'description' not in out or 'price' not in out:
                validation_passed = False
                print(f"    ❌ ERROR: Missing required fields in outcome: {out}")
                break
                
        # Show a sample outcome
        if outcomes:
            sample_out = outcomes[0]
            point_str = f" {sample_out.get('point', '')}" if 'point' in sample_out else ""
            print(f"  - Sample Valid Outcome: {sample_out['description']} ({sample_out['name']}{point_str}) @ {sample_out['price']}")

    print("\n==============================================")
    if validation_passed:
        print("✅ VERIFICATION PASSED: The sportsbook odds API is running smoothly!")
        print("   -> Authentication works.")
        print("   -> Event data is flowing.")
        print("   -> Market details (props) are correctly structured.")
    else:
        print("❌ VERIFICATION FAILED: Data structure anomalies detected.")
        sys.exit(1)

if __name__ == "__main__":
    verify_sportsbook_odds()
