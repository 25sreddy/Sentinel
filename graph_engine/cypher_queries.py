"""
cypher_queries.py
Reference library of all Cypher queries used in the Kalshi Graph Engine.
Can be run directly (prints query strings) or imported by neo4j_ingest.py.
"""

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Market) REQUIRE m.ticker IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Player)  REQUIRE p.name   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Team)    REQUIRE t.name   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event)   REQUIRE e.ticker IS UNIQUE",
]

SCHEMA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (m:Market) ON (m.prop_type)",
    "CREATE INDEX IF NOT EXISTS FOR (m:Market) ON (m.threshold)",
    "CREATE INDEX IF NOT EXISTS FOR (m:Market) ON (m.implied_prob)",
]

# ─────────────────────────────────────────────────────────────────────────────
# LADDER INCONSISTENCY QUERIES
# ─────────────────────────────────────────────────────────────────────────────

# Find all ladder pairs where the probability gap is too narrow
LADDER_INCONSISTENCY = """
MATCH (p:Player)-[:HAS_MARKET]->(lo:Market)-[:LADDER_NEXT]->(hi:Market)
WHERE lo.prop_type = hi.prop_type
  AND lo.implied_prob IS NOT NULL
  AND hi.implied_prob IS NOT NULL
  AND (lo.implied_prob - hi.implied_prob) < 8   // Gap < 8 percentage points
RETURN
  p.name             AS player,
  lo.prop_type       AS prop_type,
  lo.threshold       AS lower_threshold,
  lo.implied_prob    AS lower_prob_pct,
  hi.threshold       AS upper_threshold,
  hi.implied_prob    AS upper_prob_pct,
  (lo.implied_prob - hi.implied_prob) AS gap_pct,
  lo.ticker          AS lower_ticker,
  hi.ticker          AS upper_ticker
ORDER BY gap_pct ASC
LIMIT 50
"""

# Specifically find inversions (upper threshold priced HIGHER than lower — impossible)
LADDER_INVERSIONS = """
MATCH (p:Player)-[:HAS_MARKET]->(lo:Market)-[:LADDER_NEXT]->(hi:Market)
WHERE lo.implied_prob < hi.implied_prob
RETURN
  p.name          AS player,
  lo.prop_type    AS prop_type,
  lo.threshold    AS lower_threshold,
  lo.implied_prob AS lower_prob_pct,
  hi.threshold    AS upper_threshold,
  hi.implied_prob AS upper_prob_pct,
  (hi.implied_prob - lo.implied_prob) AS inversion_size_pct
ORDER BY inversion_size_pct DESC
"""

# ─────────────────────────────────────────────────────────────────────────────
# STALE PRICE / DEPENDENCY QUERIES
# ─────────────────────────────────────────────────────────────────────────────

# Find player prop markets whose implied prob hasn't moved relative to their
# team's series win probability (stored in parent_prob_delta property)
STALE_CHILD_MARKETS = """
MATCH (t:Team)-[:HAS_MARKET]->(parent:Market),
      (t)-[:HAS_MARKET]->(child:Market)
WHERE parent.prop_type IN ['series', 'moneyline']
  AND child.prop_type  IN ['points','rebounds','assists','blocks','steals','threes']
  AND parent.prob_delta IS NOT NULL       // set by anomaly_detector.py
  AND abs(parent.prob_delta) >= 10        // parent moved ≥10 pct pts
  AND child.prob_delta IS NOT NULL
  AND abs(child.prob_delta) < 3           // child moved <3 pct pts
RETURN
  t.name             AS team,
  parent.title       AS parent_market,
  parent.implied_prob AS parent_prob,
  parent.prob_delta  AS parent_delta,
  child.title        AS stale_market,
  child.implied_prob AS child_prob,
  child.prob_delta   AS child_delta
ORDER BY abs(parent.prob_delta) DESC
LIMIT 30
"""

# ─────────────────────────────────────────────────────────────────────────────
# RISK CLUSTER QUERIES
# ─────────────────────────────────────────────────────────────────────────────

# Find the densest risk clusters — players/teams most connected to open markets
RISK_CLUSTER_DENSITY = """
MATCH (p:Player)-[:HAS_MARKET]->(m:Market)
WHERE m.implied_prob IS NOT NULL
RETURN
  p.name                   AS player,
  count(m)                 AS open_market_count,
  avg(m.implied_prob)      AS avg_implied_prob,
  collect(m.prop_type)     AS prop_types
ORDER BY open_market_count DESC
LIMIT 20
"""

# Find markets that share a game event (cross-market risk exposure)
CROSS_MARKET_EXPOSURE = """
MATCH (a:Market)-[:SAME_GAME]->(b:Market)
WHERE a.prop_type = 'series'
  AND b.prop_type IN ['points','rebounds']
  AND a.implied_prob IS NOT NULL
  AND b.implied_prob IS NOT NULL
RETURN
  a.title         AS series_market,
  a.implied_prob  AS series_prob,
  b.title         AS prop_market,
  b.implied_prob  AS prop_prob,
  abs(a.implied_prob - b.implied_prob) AS prob_diff
ORDER BY prob_diff DESC
LIMIT 20
"""

# ─────────────────────────────────────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────────────────────────────────────

# Quick health check — count nodes by label
HEALTH_CHECK = """
CALL apoc.meta.stats()
YIELD labels
RETURN labels
"""

if __name__ == "__main__":
    queries = {
        "Ladder Inconsistencies": LADDER_INCONSISTENCY,
        "Ladder Inversions":      LADDER_INVERSIONS,
        "Stale Child Markets":    STALE_CHILD_MARKETS,
        "Risk Cluster Density":   RISK_CLUSTER_DENSITY,
        "Cross-Market Exposure":  CROSS_MARKET_EXPOSURE,
    }
    for name, q in queries.items():
        print(f"\n{'='*60}")
        print(f"  {name}")
        print('='*60)
        print(q)
