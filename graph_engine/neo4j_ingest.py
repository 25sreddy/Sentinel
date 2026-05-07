"""
neo4j_ingest.py
Ingests Kalshi MarketNode data into Neo4j, creating the full graph schema:

  (:Player)  -[:HAS_MARKET]->  (:Market)
  (:Team)    -[:HAS_MARKET]->  (:Market)
  (:Market)  -[:SAME_PLAYER]-> (:Market)   (ladder edges between thresholds)
  (:Market)  -[:SAME_GAME]->   (:Market)   (all markets in same game event)

Usage:
  pip install neo4j
  python neo4j_ingest.py
"""

import os
from neo4j import GraphDatabase
from kalshi_fetcher import build_market_nodes, MarketNode
from dataclasses import asdict

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Market) REQUIRE m.ticker IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Player)  REQUIRE p.name   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Team)    REQUIRE t.name   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event)   REQUIRE e.ticker IS UNIQUE",
]

UPSERT_MARKET = """
MERGE (m:Market {ticker: $ticker})
SET   m.title        = $title,
      m.series       = $series_ticker,
      m.prop_type    = $prop_type,
      m.threshold    = $threshold,
      m.yes_bid      = $yes_bid,
      m.no_bid       = $no_bid,
      m.volume       = $volume,
      m.implied_prob = $implied_prob
"""

UPSERT_PLAYER_LINK = """
MERGE (p:Player {name: $player_name})
MERGE (m:Market {ticker: $ticker})
MERGE (p)-[:HAS_MARKET]->(m)
"""

UPSERT_TEAM_LINK = """
MERGE (t:Team {name: $team_name})
MERGE (m:Market {ticker: $ticker})
MERGE (t)-[:HAS_MARKET]->(m)
"""

UPSERT_EVENT_LINK = """
MERGE (e:Event {ticker: $event_ticker})
MERGE (m:Market {ticker: $ticker})
MERGE (m)-[:PART_OF]->(e)
"""

# Connect markets for the same player prop ladder (e.g. 20pt → 25pt → 30pt)
BUILD_LADDER_EDGES = """
MATCH (a:Market), (b:Market)
WHERE a.prop_type    = b.prop_type
  AND a.prop_type   IN ['points','rebounds','assists','blocks','steals','threes']
  AND a.threshold   IS NOT NULL
  AND b.threshold   IS NOT NULL
  AND a.threshold    < b.threshold
  AND EXISTS { MATCH (p:Player)-[:HAS_MARKET]->(a), (p)-[:HAS_MARKET]->(b) }
MERGE (a)-[:LADDER_NEXT]->(b)
"""

BUILD_SAME_GAME_EDGES = """
MATCH (a:Market)-[:PART_OF]->(e:Event)<-[:PART_OF]-(b:Market)
WHERE a.ticker <> b.ticker
MERGE (a)-[:SAME_GAME]->(b)
"""


class Neo4jGraphEngine:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def setup_schema(self):
        with self.driver.session() as s:
            for c in CONSTRAINTS:
                s.run(c)
        print("✅ Neo4j constraints created.")

    def ingest_nodes(self, nodes: list[MarketNode]):
        with self.driver.session() as s:
            for n in nodes:
                d = asdict(n)
                # Upsert market node
                s.run(UPSERT_MARKET, **d)

                # Link to Player
                if n.player_name:
                    s.run(UPSERT_PLAYER_LINK, player_name=n.player_name, ticker=n.ticker)

                # Link to Team
                if n.team_name:
                    s.run(UPSERT_TEAM_LINK, team_name=n.team_name, ticker=n.ticker)

                # Link to Event
                if n.event_ticker:
                    s.run(UPSERT_EVENT_LINK, event_ticker=n.event_ticker, ticker=n.ticker)

        print(f"✅ Ingested {len(nodes)} market nodes.")

    def build_relationships(self):
        with self.driver.session() as s:
            s.run(BUILD_LADDER_EDGES)
            s.run(BUILD_SAME_GAME_EDGES)
        print("✅ Ladder and same-game edges built.")


if __name__ == "__main__":
    engine = Neo4jGraphEngine()
    try:
        engine.setup_schema()
        nodes = build_market_nodes()
        engine.ingest_nodes(nodes)
        engine.build_relationships()
        print("\n🎯 Graph fully populated and ready for analysis.")
    finally:
        engine.close()
