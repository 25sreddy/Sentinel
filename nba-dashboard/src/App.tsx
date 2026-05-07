import { useEffect, useState } from 'react'
import './App.css'

interface KalshiEvent {
  id: string;
  title: string;
  start_date: string;
  teamA: string;
  teamB: string;
}

interface Market {
  ticker: string;
  title: string;
  yes_sub_title: string | null;
  series_ticker: string;
  yes_bid_dollars: number | null;
  no_bid_dollars: number | null;
  volume_fp: number | null;
}

const KALSHI_API = '/api/trade-api/v2';

// Infer prop type from the series ticker — no Odds API needed
const SERIES_PROP_MAP: Record<string, string> = {
  KXNBAGAME:   'moneyline',
  KXNBASPREAD: 'spread',
  KXNBATOTAL:  'total',
  KXNBAPTS:    'points',
  KXNBAREB:    'rebounds',
  KXNBAAST:    'assists',
  KXNBA3PT:    'threes',
  KXNBABLK:    'blocks',
  KXNBASTL:    'steals',
  KXNBASERIES: 'series',
};

const PLAYER_PROP_TYPES = new Set(['points','rebounds','assists','threes','blocks','steals']);
const GAME_LINE_TYPES   = new Set(['moneyline','spread','total','series']);

// Parse "Team A vs Team B" titles from Kalshi event titles
function parseTeams(title: string): [string, string] {
  const vsMatch = title.match(/^(.+?)\s+vs\.?\s+(.+?)(?:\s+\d{4}|\s+Game|\s+Series|$)/i);
  if (vsMatch) return [vsMatch[1].trim(), vsMatch[2].trim()];
  return [title, ''];
}

function App() {
  const [events, setEvents]               = useState<KalshiEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [eventsError, setEventsError]     = useState<string | null>(null);

  const [selectedEvent, setSelectedEvent] = useState<KalshiEvent | null>(null);
  const [gameMarkets, setGameMarkets]     = useState<Market[]>([]);
  const [loadingGame, setLoadingGame]     = useState(false);
  const [gameError, setGameError]         = useState<string | null>(null);

  // ── Step 1: Fetch Kalshi game events (lightweight) ──────────────────────
  useEffect(() => {
    const fetchEvents = async () => {
      try {
        setLoadingEvents(true);
        const res = await fetch(`${KALSHI_API}/events?series_ticker=KXNBAGAME&status=open`);
        if (!res.ok) throw new Error(`Kalshi API ${res.status}`);
        const data = await res.json();
        const parsed: KalshiEvent[] = (data.events || []).map((e: any) => {
          const [teamA, teamB] = parseTeams(e.title);
          return {
            id: e.event_ticker,
            title: e.title,
            start_date: e.start_date || new Date().toISOString(),
            teamA,
            teamB,
          };
        });
        setEvents(parsed);
      } catch (err: any) {
        setEventsError(err.message);
      } finally {
        setLoadingEvents(false);
      }
    };
    fetchEvents();
  }, []);

  // ── Step 2: Lazy-load markets only when a game is clicked ─────────────
  const handleGameClick = async (event: KalshiEvent) => {
    setSelectedEvent(event);
    setGameMarkets([]);
    setGameError(null);
    setLoadingGame(true);

    const targetSeries = Object.keys(SERIES_PROP_MAP);
    let all: Market[] = [];

    try {
      for (const series of targetSeries) {
        try {
          const res = await fetch(`${KALSHI_API}/markets?series_ticker=${series}&status=open`);
          if (res.status === 429) { await new Promise(r => setTimeout(r, 800)); continue; }
          if (!res.ok) continue;
          const data = await res.json();
          if (!data.markets) continue;

          // Filter to markets relevant to this game's event ticker or team names
          const relevant = (data.markets as any[]).filter(m => {
            // Skip zero-volume markets
            if (!m.volume_fp || Number(m.volume_fp) === 0) return false;

            const t = m.title.toLowerCase();
            const matchesEvent = m.event_ticker === event.id;
            const matchesTeam  =
              (event.teamA && t.includes(event.teamA.split(' ').slice(-1)[0].toLowerCase())) ||
              (event.teamB && t.includes(event.teamB.split(' ').slice(-1)[0].toLowerCase()));
            return matchesEvent || matchesTeam;
          });

          all = [...all, ...relevant.map((m: any) => ({ ...m, series_ticker: series }))];
        } catch {
          // skip failed series silently
        }
      }
      setGameMarkets(all);
    } catch (err: any) {
      setGameError(err.message);
    } finally {
      setLoadingGame(false);
    }
  };

  const getPropType = (m: Market) => SERIES_PROP_MAP[m.series_ticker] || 'other';

  // ── Render table ─────────────────────────────────────────────────────────
  const renderTable = (markets: Market[], propLabel: string) => (
    <div className="market-section glass">
      <h3 className="section-title">{propLabel}</h3>
      <table className="props-table">
        <thead>
          <tr>
            <th>Market</th>
            <th>Detail</th>
            <th>YES Bid</th>
            <th>NO Bid</th>
            <th>Implied Prob</th>
            <th>Volume</th>
          </tr>
        </thead>
        <tbody>
          {markets.map(km => {
            const yes = km.yes_bid_dollars != null ? Number(km.yes_bid_dollars) : null;
            const impliedProb = yes != null ? (yes * 100).toFixed(0) + '%' : '--';
            const vol = km.volume_fp != null ? Number(km.volume_fp).toLocaleString() : '--';
            return (
              <tr key={km.ticker}>
                <td>{km.title}</td>
                <td className="sub-title-cell">{km.yes_sub_title || '--'}</td>
                <td className="kalshi-price yes">{yes != null ? `$${yes.toFixed(2)}` : '--'}</td>
                <td className="kalshi-price no">
                  {km.no_bid_dollars != null ? `$${Number(km.no_bid_dollars).toFixed(2)}` : '--'}
                </td>
                <td className="implied-prob">{impliedProb}</td>
                <td className="volume-cell">{vol}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  // ── Render game detail page ───────────────────────────────────────────────
  const renderGameDetails = () => {
    if (!selectedEvent) return null;

    const gameLines   = gameMarkets.filter(m => GAME_LINE_TYPES.has(getPropType(m)));
    const playerProps = gameMarkets.filter(m => PLAYER_PROP_TYPES.has(getPropType(m)));

    // Group player props by type
    const propGroups: Record<string, Market[]> = {};
    for (const m of playerProps) {
      const pt = getPropType(m);
      propGroups[pt] = propGroups[pt] || [];
      propGroups[pt].push(m);
    }

    const propEmoji: Record<string, string> = {
      points: '🏀 Points', rebounds: '🔄 Rebounds', assists: '🎯 Assists',
      threes: '3️⃣ Threes', blocks: '🛡️ Blocks', steals: '💰 Steals',
    };

    return (
      <div className="game-details">
        <button className="back-btn" onClick={() => { setSelectedEvent(null); setGameMarkets([]); }}>
          ← Back to Games
        </button>

        <div className="detail-header glass">
          <div>
            <h2>{selectedEvent.teamA} <span className="vs-text">vs</span> {selectedEvent.teamB}</h2>
            <span className="commence-time">
              {new Date(selectedEvent.start_date).toLocaleString(undefined, {
                weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
              })}
            </span>
          </div>
          <div className="market-count-badge">
            {gameMarkets.length} contracts
          </div>
        </div>

        {loadingGame ? (
          <div className="loading-state">
            <div className="radar-spinner"></div>
            <p>Fetching Kalshi markets for this game...</p>
          </div>
        ) : gameError ? (
          <div className="error-state"><p>{gameError}</p></div>
        ) : gameMarkets.length === 0 ? (
          <div className="no-kalshi-markets glass">
            <p>No active Kalshi contracts found for this matchup.</p>
          </div>
        ) : (
          <div className="markets-container">
            {gameLines.length > 0 && renderTable(gameLines, '🏟️ Game Lines')}

            {Object.entries(propGroups).map(([pt, markets]) =>
              renderTable(markets, propEmoji[pt] || pt)
            )}
          </div>
        )}
      </div>
    );
  };

  // ── Render game lobby ─────────────────────────────────────────────────────
  const renderGameList = () => (
    <div className="game-grid">
      {events.map(game => (
        <div
          key={game.id}
          className="game-card glass interactive"
          onClick={() => handleGameClick(game)}
        >
          <div className="game-card-content">
            <h3>{game.teamA}</h3>
            <div className="vs-badge">VS</div>
            <h3>{game.teamB}</h3>
          </div>
          <div className="game-card-footer">
            <span>{new Date(game.start_date).toLocaleString(undefined, {
              month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            })}</span>
            <span className="view-btn">View Markets →</span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="dashboard">
      <header className="header">
        <div className="header-content">
          <h1><span className="gradient-text">NBA</span> Risk Graph</h1>
          <p className="subtitle">Kalshi-only · Click a game to explore its markets</p>
        </div>
      </header>

      <main className="main-content">
        {selectedEvent ? renderGameDetails() : (
          loadingEvents ? (
            <div className="loading-state">
              <div className="radar-spinner"></div>
              <p>Fetching upcoming NBA games from Kalshi...</p>
            </div>
          ) : eventsError ? (
            <div className="error-state"><p>Error: {eventsError}</p></div>
          ) : events.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🏀</div>
              <h2>No NBA Games Found</h2>
              <p>No upcoming games at the moment. Check back soon.</p>
            </div>
          ) : renderGameList()
        )}
      </main>
    </div>
  );
}

export default App
