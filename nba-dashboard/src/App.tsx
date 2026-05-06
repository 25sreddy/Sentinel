import { useEffect, useState } from 'react'
import './App.css'

interface Market {
  ticker: string;
  title: string;
  yes_bid_dollars: number;
  no_bid_dollars: number;
  volume_fp: number;
  volume_24h_fp: number;
  category_label?: string; // We'll add this dynamically
}

const KALSHI_API = '/api/trade-api/v2';

function App() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeTab, setActiveTab] = useState("All");

  const categorizeMarket = (title: string, ticker: string): string => {
    const t = title.toLowerCase() + " " + ticker.toLowerCase();
    
    if (t.includes('series') || t.includes('championship') || t.includes('finals') || t.includes('win it all')) {
      return "Series & Futures";
    }
    if (t.includes('points') && (t.includes('over') || t.includes('under')) && !t.match(/(rebound|assist|block|steal|threes)/)) {
      return "Game Lines";
    }
    if (t.includes('spread') || t.includes('moneyline') || t.includes('vs.')) {
      return "Game Lines";
    }
    if (t.includes('pts') || t.includes('rebs') || t.includes('asts') || t.includes('points') || t.includes('rebounds') || t.includes('assists') || t.includes('threes') || t.includes('blocks') || t.includes('steals') || t.includes('+')) {
      return "Player Props";
    }
    if (t.includes('triple-double') || t.includes('coach') || t.includes('sweep') || t.includes('award')) {
      return "Milestones";
    }
    return "Other";
  };

  const fetchNBAMarkets = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${KALSHI_API}/markets?series_ticker=KXNBASERIES&status=open`);
      if (!res.ok) throw new Error("Failed to fetch markets");
      const data = await res.json();
      
      const enrichedMarkets = (data.markets || []).map((m: any) => ({
        ...m,
        category_label: categorizeMarket(m.title, m.ticker)
      }));
      
      setMarkets(enrichedMarkets);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNBAMarkets();
    const interval = setInterval(fetchNBAMarkets, 30000);
    return () => clearInterval(interval);
  }, []);

  const tabs = ["All", "Series & Futures", "Game Lines", "Player Props", "Milestones", "Other"];

  const filteredMarkets = markets.filter(m => {
    const matchesSearch = m.title.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          m.ticker.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesTab = activeTab === "All" || m.category_label === activeTab;
    return matchesSearch && matchesTab;
  });

  return (
    <div className="dashboard">
      <header className="header">
        <div className="header-content">
          <h1>
            <span className="gradient-text">NBA</span> Risk Graph
          </h1>
          <p className="subtitle">Real-time dependency mapping of sports derivatives</p>
        </div>
        <div className="header-actions">
          <input
            type="text"
            placeholder="Search markets..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="search-bar"
          />
          <button className="refresh-btn" onClick={fetchNBAMarkets} disabled={loading}>
            {loading ? <span className="spinner"></span> : "Refresh Live"}
          </button>
        </div>
      </header>

      <div className="tabs-container">
        {tabs.map(tab => (
          <button 
            key={tab} 
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
            {tab !== "All" && (
              <span className="tab-count">
                {markets.filter(m => m.category_label === tab).length}
              </span>
            )}
          </button>
        ))}
      </div>

      <main className="main-content">
        {loading && markets.length === 0 ? (
          <div className="loading-state">
            <div className="radar-spinner"></div>
            <p>Scanning active NBA market events...</p>
          </div>
        ) : error ? (
          <div className="error-state">
            <p>Connection Error: {error}</p>
          </div>
        ) : filteredMarkets.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🏀</div>
            <h2>No {activeTab} markets found</h2>
            <p>There are currently no active markets fitting this risk cluster. Try another tab or clear your search.</p>
          </div>
        ) : (
          <div className="grid">
            {filteredMarkets.map((market) => (
              <div key={market.ticker} className="card glass">
                <div className="card-header">
                  <span className="ticker">{market.ticker}</span>
                  <span className="volume">Vol: {(market.volume_fp / 100000).toFixed(1)}k</span>
                </div>
                <h3 className="card-title">{market.title}</h3>

                <div className="price-container">
                  <div className="price-box yes">
                    <span className="price-label">YES</span>
                    <span className="price-value">
                      ${market.yes_bid_dollars != null ? Number(market.yes_bid_dollars).toFixed(2) : '--'}
                    </span>
                  </div>
                  <div className="price-box no">
                    <span className="price-label">NO</span>
                    <span className="price-value">
                      ${market.no_bid_dollars != null ? Number(market.no_bid_dollars).toFixed(2) : '--'}
                    </span>
                  </div>
                </div>

                <div className="probability-bar">
                  <div
                    className="probability-fill"
                    style={{ width: `${Number(market.yes_bid_dollars || 0) * 100}%` }}
                  ></div>
                </div>
                <div className="probability-labels">
                  <span>{(Number(market.yes_bid_dollars || 0) * 100).toFixed(0)}% Implied</span>
                  <span>{(Number(market.no_bid_dollars || 0) * 100).toFixed(0)}% Implied</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

export default App
