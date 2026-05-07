"""
anomaly_detector.py

Two analysis passes:

1. LADDER INCONSISTENCY DETECTOR
   Flags player prop contracts where the price of a higher threshold
   is dangerously close to (or exceeds) a lower threshold — impossible
   in a logically consistent market.

   Example anomaly:
     Player X: 25+ Points @ $0.52
     Player X: 30+ Points @ $0.49   ← only 3¢ gap? Should be much wider.

2. STALE PRICE DETECTOR
   Flags markets whose implied probability hasn't moved despite a
   'parent' event (team win probability) having spiked significantly.

   Example anomaly:
     LAL Win Series  @ $0.72  (just spiked +15¢)
     LeBron 25+ Pts  @ $0.48  (hasn't moved — stale, likely mispriced UP)
"""

import time
from dataclasses import dataclass
from typing import Optional
from kalshi_fetcher import build_market_nodes, MarketNode

# --- Config ---------------------------------------------------------------
LADDER_MIN_GAP      = 0.08   # Minimum expected probability gap between rungs (8¢)
STALE_PARENT_SPIKE  = 0.10   # Parent must have moved ≥10¢ to trigger check
STALE_CHILD_MOVED   = 0.03   # Child is "stale" if it moved <3¢ when parent moved ≥10¢
# --------------------------------------------------------------------------


@dataclass
class LadderAnomaly:
    player:       str
    prop_type:    str
    lower_ticker: str
    lower_title:  str
    lower_thresh: float
    lower_prob:   float
    upper_ticker: str
    upper_title:  str
    upper_thresh: float
    upper_prob:   float
    gap:          float          # lower_prob - upper_prob (should be > LADDER_MIN_GAP)
    severity:     str            # "critical" / "warning"


@dataclass
class StaleAnomaly:
    parent_ticker:  str
    parent_title:   str
    parent_prob:    float
    parent_delta:   float        # simulated/stored delta
    child_ticker:   str
    child_title:    str
    child_prob:     float
    expected_dir:   str          # "UP" or "DOWN"
    reason:         str


def detect_ladder_inconsistencies(nodes: list[MarketNode]) -> list[LadderAnomaly]:
    """
    Groups player prop markets by (player_name, prop_type) and checks
    that probability decreases monotonically as threshold increases.
    Flags pairs where the gap is below LADDER_MIN_GAP.
    """
    anomalies: list[LadderAnomaly] = []

    # Build index: (player_name, prop_type) → sorted list of markets
    groups: dict[tuple, list[MarketNode]] = {}
    for n in nodes:
        if (
            n.player_name
            and n.prop_type in ("points", "rebounds", "assists", "blocks", "steals", "threes")
            and n.threshold is not None
            and n.implied_prob is not None
        ):
            key = (n.player_name, n.prop_type)
            groups.setdefault(key, []).append(n)

    for (player, prop_type), ladder in groups.items():
        # Sort ascending by threshold
        ladder.sort(key=lambda m: m.threshold)

        for i in range(len(ladder) - 1):
            lo = ladder[i]
            hi = ladder[i + 1]

            lo_prob = lo.implied_prob / 100   # convert to 0–1
            hi_prob = hi.implied_prob / 100

            gap = lo_prob - hi_prob           # should be positive + wide enough

            if gap < LADDER_MIN_GAP:
                severity = "critical" if gap < 0 else "warning"
                anomalies.append(LadderAnomaly(
                    player       = player,
                    prop_type    = prop_type,
                    lower_ticker = lo.ticker,
                    lower_title  = lo.title,
                    lower_thresh = lo.threshold,
                    lower_prob   = lo_prob,
                    upper_ticker = hi.ticker,
                    upper_title  = hi.title,
                    upper_thresh = hi.threshold,
                    upper_prob   = hi_prob,
                    gap          = gap,
                    severity     = severity,
                ))

    return anomalies


def detect_stale_prices(
    nodes: list[MarketNode],
    prev_snapshot: dict[str, float]   # ticker → previous implied_prob (0–1)
) -> list[StaleAnomaly]:
    """
    Compares current implied probs against a previous snapshot.

    For each 'parent' market (team series win / moneyline) that spiked ≥ STALE_PARENT_SPIKE,
    check whether associated child markets (same team's player props) have responded.
    """
    anomalies: list[StaleAnomaly] = []

    current: dict[str, MarketNode] = {n.ticker: n for n in nodes}

    # Identify parent markets (series / moneyline)
    parents = [n for n in nodes if n.prop_type in ("series", "moneyline") and n.implied_prob is not None]

    for parent in parents:
        prev_prob = prev_snapshot.get(parent.ticker)
        if prev_prob is None:
            continue

        curr_prob = parent.implied_prob / 100
        delta     = curr_prob - prev_prob

        if abs(delta) < STALE_PARENT_SPIKE:
            continue  # Not a significant move

        # Determine expected child direction
        # If parent WIN prob goes UP → player props for that team should also go UP
        expected_dir = "UP" if delta > 0 else "DOWN"

        # Find child markets on the same team
        if not parent.team_name:
            continue

        children = [
            n for n in nodes
            if n.team_name == parent.team_name
            and n.prop_type not in ("series", "moneyline", "spread", "total")
            and n.implied_prob is not None
        ]

        for child in children:
            prev_child = prev_snapshot.get(child.ticker)
            if prev_child is None:
                continue

            child_delta = (child.implied_prob / 100) - prev_child

            moved_right_dir = (
                (expected_dir == "UP"   and child_delta >= STALE_CHILD_MOVED) or
                (expected_dir == "DOWN" and child_delta <= -STALE_CHILD_MOVED)
            )

            if not moved_right_dir:
                anomalies.append(StaleAnomaly(
                    parent_ticker = parent.ticker,
                    parent_title  = parent.title,
                    parent_prob   = curr_prob,
                    parent_delta  = delta,
                    child_ticker  = child.ticker,
                    child_title   = child.title,
                    child_prob    = child.implied_prob / 100,
                    expected_dir  = expected_dir,
                    reason        = (
                        f"Parent '{parent.title}' moved {delta:+.0%}. "
                        f"Expected child to move {expected_dir} by ≥{STALE_CHILD_MOVED:.0%} "
                        f"but child only moved {child_delta:+.0%}."
                    ),
                ))

    return anomalies


def run_anomaly_loop(poll_interval_seconds: int = 60):
    """
    Continuous monitoring loop.
    Takes a snapshot, waits, fetches fresh data, runs both detectors.
    """
    print("🔍 Kalshi Graph Anomaly Detector — Starting\n")

    # First snapshot
    print("Taking initial snapshot...")
    initial_nodes = build_market_nodes()
    prev_snapshot = {
        n.ticker: (n.implied_prob / 100) if n.implied_prob is not None else 0.0
        for n in initial_nodes
    }
    print(f"Snapshot: {len(prev_snapshot)} markets tracked.\n")

    iteration = 0
    while True:
        iteration += 1
        print(f"⏳ Waiting {poll_interval_seconds}s before next scan...\n")
        time.sleep(poll_interval_seconds)

        print(f"--- Scan #{iteration} ---")
        fresh_nodes = build_market_nodes()

        # 1. Ladder inconsistencies
        ladder_anomalies = detect_ladder_inconsistencies(fresh_nodes)
        if ladder_anomalies:
            print(f"\n🚨 LADDER INCONSISTENCIES ({len(ladder_anomalies)} found):")
            for a in ladder_anomalies:
                print(f"  [{a.severity.upper()}] {a.player} — {a.prop_type}")
                print(f"    {a.lower_thresh}+ @ {a.lower_prob:.0%}  vs  {a.upper_thresh}+ @ {a.upper_prob:.0%}")
                print(f"    Gap: {a.gap:.0%}  (min expected: {LADDER_MIN_GAP:.0%})")
                print(f"    Tickers: {a.lower_ticker}  /  {a.upper_ticker}\n")
        else:
            print("✅ No ladder inconsistencies detected.")

        # 2. Stale prices
        stale_anomalies = detect_stale_prices(fresh_nodes, prev_snapshot)
        if stale_anomalies:
            print(f"\n⚠️  STALE PRICE ALERTS ({len(stale_anomalies)} found):")
            for a in stale_anomalies:
                print(f"  Parent : {a.parent_title} ({a.parent_prob:.0%}, Δ{a.parent_delta:+.0%})")
                print(f"  Child  : {a.child_title} ({a.child_prob:.0%})")
                print(f"  Reason : {a.reason}\n")
        else:
            print("✅ No stale price alerts.")

        # Roll forward snapshot
        prev_snapshot = {
            n.ticker: (n.implied_prob / 100) if n.implied_prob is not None else 0.0
            for n in fresh_nodes
        }
        print()


if __name__ == "__main__":
    # Quick single-pass test (no loop)
    nodes = build_market_nodes()

    print("\n=== LADDER INCONSISTENCIES ===")
    ladder = detect_ladder_inconsistencies(nodes)
    if ladder:
        for a in ladder:
            print(f"  [{a.severity}] {a.player} {a.prop_type}: "
                  f"{a.lower_thresh}+ ({a.lower_prob:.0%}) → {a.upper_thresh}+ ({a.upper_prob:.0%}) | gap={a.gap:.0%}")
    else:
        print("  None found.")

    print("\n=== STALE PRICES (demo — no prev snapshot) ===")
    print("  Run run_anomaly_loop() for live monitoring.")
