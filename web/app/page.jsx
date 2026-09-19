"use client";

import { useEffect, useMemo, useState } from "react";

// Data lives on the `data` branch (keeps scan refreshes off main so Vercel
// doesn't rebuild); fall back to the bundled copy if the remote fetch fails.
const DATA_URLS = [
  "https://raw.githubusercontent.com/CoolCriSyS/smart-money-flows-tracker/data/web/public/data/latest.json",
  "/data/latest.json",
];
const loadData = () => {
  const attempt = (i) =>
    i >= DATA_URLS.length
      ? Promise.reject(new Error("data unavailable"))
      : fetch(DATA_URLS[i])
          .then((r) => { if (!r.ok) throw new Error("bad response"); return r.json(); })
          .catch(() => attempt(i + 1));
  return attempt(0);
};

// Compact money: 1.2M, 300K. Handles null/undefined.
const compact$ = (n) => {
  if (n == null || Number.isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
  if (a >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return "$" + (n / 1e3).toFixed(0) + "K";
  return "$" + n.toFixed(0);
};
const signed$ = (n) => (n == null ? "—" : (n < 0 ? "−" : "+") + compact$(n).slice(0));
const shortAddr = (a) => (a ? a.slice(0, 6) + "…" + a.slice(-4) : "—");
// Defense in depth: redact slur-bearing labels before render.
const cleanLabel = (s) => {
  if (!s) return "";
  const low = s.toLowerCase();
  if (low.includes("nigger") || low.includes("nigga")) return "";
  return s;
};
const fmtAge = (d) => (d == null ? "—" : d < 30 ? `${Math.round(d)}d` : `${(d / 30).toFixed(1)}mo`);
const fmtSpread = (h) => (h == null ? "—" : h < 24 ? `${h.toFixed(1)}h` : `${(h / 24).toFixed(1)}d`);

function Sparkline({ points }) {
  if (!points || points.length < 2) return null;
  const W = 600, H = 64, P = 6;
  const vals = points.map((p) => p.balance_usd);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const coords = vals.map((v, i) => {
    const x = P + (i * (W - 2 * P)) / (vals.length - 1);
    const y = H - P - ((v - min) / span) * (H - 2 * P);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <div className="spark">
      <div className="cap">Smart-money holdings</div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <polyline points={coords.join(" ")} fill="none" stroke="#ff5c7a" strokeWidth="2.5" />
      </svg>
    </div>
  );
}

function BuyersList({ items, label }) {
  const rows = (items || []).slice(0, 5);
  if (rows.length === 0) return null;
  return (
    <details className="buyers">
      <summary>{label} ({rows.length})</summary>
      <ul>
        {rows.map((b, i) => (
          <li key={i}>
            <span className="who">
              {shortAddr(b.address)}
              {cleanLabel(b.label) && <span className="lbl">{cleanLabel(b.label)}</span>}
            </span>
            <span className="amt">{compact$(b.value_usd)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function ConsensusCard({ c, maxScore }) {
  const width = maxScore > 0 ? (100 * c.score / maxScore).toFixed(1) : 0;
  return (
    <div className="card">
      <div className="top">
        <div className="sym">
          {c.symbol}
          <span className="chain">{c.chain}</span>
        </div>
        <div className="score-num">{c.score.toFixed(1)}</div>
      </div>
      {c.sectors && c.sectors.length > 0 && <div className="sectors">{c.sectors.join(" · ")}</div>}
      <div className="score-line">
        <div className="bar"><div className="fill g" style={{ width: `${width}%` }} /></div>
      </div>
      <div className="kvgrid">
        <div className="kv"><div className="k">Independent buyers</div><div className="v">{c.buyers}</div></div>
        <div className="kv"><div className="k">Label diversity</div><div className="v">{c.distinct_labels}/{c.buyers} cohorts</div></div>
        <div className="kv"><div className="k">Buy time-spread</div><div className="v">{fmtSpread(c.spread_hours)}</div></div>
        <div className="kv"><div className="k">Smart-buy total</div><div className="v pos">{compact$(c.total_buy_usd)}</div></div>
        <div className="kv"><div className="k">7d netflow</div><div className={`v ${c.netflow_7d < 0 ? "neg" : "pos"}`}>{signed$(c.netflow_7d)}</div></div>
        <div className="kv"><div className="k">Mcap / age</div><div className="v">{compact$(c.market_cap)}</div><div className="sub">{fmtAge(c.token_age_days)} old</div></div>
      </div>
      <BuyersList items={c.top_buyers} label="Top buyers" />
    </div>
  );
}

function ExitCard({ e, maxScore }) {
  const width = maxScore > 0 ? (100 * e.score / maxScore).toFixed(1) : 0;
  const accelCls = e.acceleration >= 4 ? "hot" : e.acceleration >= 1.5 ? "warm" : "cool";
  return (
    <div className="card">
      <div className="top">
        <div className="sym">
          {e.symbol}
          <span className="chain">{e.chain}</span>
          <span className={`accel ${accelCls}`}>{e.acceleration.toFixed(1)}x outflow pace</span>
        </div>
        <div className="score-num">{e.score.toFixed(1)}</div>
      </div>
      {e.sectors && e.sectors.length > 0 && <div className="sectors">{e.sectors.join(" · ")}</div>}
      <div className="score-line">
        <div className="bar"><div className="fill r" style={{ width: `${width}%` }} /></div>
      </div>
      <div className="kvgrid">
        <div className="kv"><div className="k">Sellers</div><div className="v">{e.sellers}</div></div>
        <div className="kv"><div className="k">Smart-sell total</div><div className="v neg">{compact$(e.total_sell_usd)}</div></div>
        <div className="kv"><div className="k">24h netflow</div><div className={`v ${e.netflow_24h < 0 ? "neg" : "pos"}`}>{signed$(e.netflow_24h)}</div></div>
        <div className="kv"><div className="k">7d netflow</div><div className={`v ${e.netflow_7d < 0 ? "neg" : "pos"}`}>{signed$(e.netflow_7d)}</div></div>
        <div className="kv"><div className="k">30d netflow</div><div className={`v ${e.netflow_30d < 0 ? "neg" : "pos"}`}>{signed$(e.netflow_30d)}</div></div>
        <div className="kv"><div className="k">Mcap</div><div className="v">{compact$(e.market_cap)}</div></div>
      </div>
      {e.holdings_history && e.holdings_history.length >= 2 && <Sparkline points={e.holdings_history} />}
      <BuyersList items={e.top_sellers} label="Top sellers" />
    </div>
  );
}

function RotationBars({ rows }) {
  const data = (rows || []).slice().sort((a, b) => b.netflow_7d - a.netflow_7d);
  const maxAbs = Math.max(1, ...data.map((r) => Math.abs(r.netflow_7d)));
  if (data.length === 0) return <div className="empty">No rotation data in this scan.</div>;
  return (
    <div className="rot">
      {data.map((r, i) => {
        const v = r.netflow_7d;
        const pct = (50 * Math.abs(v) / maxAbs).toFixed(1);
        return (
          <div className="rot-row" key={i}>
            <div className="name">{r.chain}</div>
            <div className="track">
              <div className="zero" />
              <div className={`fillbar ${v >= 0 ? "pos" : "neg"}`} style={{ width: `${pct}%` }} />
            </div>
            <div className={`amt ${v >= 0 ? "pos" : "neg"}`}>{signed$(v)}</div>
          </div>
        );
      })}
    </div>
  );
}

export default function Page() {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    loadData()
      .then(setData)
      .catch(() => setLoadError(true));
  }, []);

  const consensus = useMemo(
    () => (data ? [...(data.consensus || [])].sort((a, b) => b.score - a.score) : []),
    [data]
  );
  const exits = useMemo(
    () => (data ? [...(data.exits || [])].sort((a, b) => b.score - a.score) : []),
    [data]
  );
  const maxConsScore = useMemo(() => Math.max(1, ...consensus.map((c) => c.score || 0)), [consensus]);
  const maxExitScore = useMemo(() => Math.max(1, ...exits.map((e) => e.score || 0)), [exits]);
  const sectors = useMemo(
    () => (data?.rotation?.sectors || []).slice().sort((a, b) => b.netflow_7d - a.netflow_7d),
    [data]
  );

  if (loadError) return <div className="wrap"><div className="empty">Could not load scan data. Check back after the next scheduled scan.</div></div>;
  if (!data) return <div className="wrap"><div className="empty">Loading scan data…</div></div>;

  const scannedAt = data.scanned_at ? new Date(data.scanned_at).toLocaleString() : "—";

  return (
    <div className="wrap">
      <div className="hero">
        <span className="kicker">Nansen Meridian Buildathon</span>
        <h1>Smart Money <span className="accent">Flows Tracker</span></h1>
        <p>
          Where Nansen-labeled smart money is <strong>converging</strong>, <strong>exiting</strong>,
          and <strong>rotating</strong> right now. The core idea: a signal is strongest when
          <strong> independent</strong> wallets — different Nansen cohorts that never trade
          together — all pile into the same token. One whale aping in is noise; five strangers
          agreeing is a pattern.
        </p>
      </div>

      <div className="stats">
        <div className="stat"><div className="label">Consensus signals</div><div className="value green">{consensus.length}</div></div>
        <div className="stat"><div className="label">Exit alerts</div><div className="value red">{exits.length}</div></div>
        <div className="stat"><div className="label">Nansen API calls</div><div className="value">{data.api_calls ?? "—"}</div></div>
        <div className="stat"><div className="label">Last scan</div><div className="value" style={{ fontSize: 15 }}>{scannedAt}</div></div>
      </div>

      <div className="section-head">
        <h2><span className="accent-g">Consensus Radar</span></h2>
        <p>
          Tokens where multiple independent smart-money wallets are accumulating.
          Score = buyer breadth × label diversity × buy time-dispersion × conviction.
          High scores mean wallets that normally never agree are suddenly agreeing.
        </p>
      </div>
      <div className="cards">
        {consensus.map((c, i) => <ConsensusCard key={i} c={c} maxScore={maxConsScore} />)}
      </div>
      {consensus.length === 0 && <div className="empty">No consensus signals in this scan.</div>}

      <div className="section-head">
        <h2><span className="accent-r">Exit Whisperer</span></h2>
        <p>
          Tokens smart money is quietly distributing. Score = seller breadth × sell
          value × outflow acceleration (24h pace vs 7d pace). When the badge reads
          several-x, the exit is speeding up — the door is getting crowded.
        </p>
      </div>
      <div className="cards">
        {exits.map((e, i) => <ExitCard key={i} e={e} maxScore={maxExitScore} />)}
      </div>
      {exits.length === 0 && <div className="empty">No exit alerts in this scan.</div>}

      <div className="section-head">
        <h2><span className="accent-b">Rotation Map</span></h2>
        <p>
          Where smart capital is migrating over the last 7 days — by chain and by
          sector. Green bars are net inflows, red bars are net outflows.
        </p>
      </div>
      <RotationBars rows={data.rotation?.chains} />
      {sectors.length > 0 && (
        <ul className="sector-list">
          {sectors.map((s, i) => (
            <li key={i}>
              <span>{s.sector}</span>
              <span className={`amt ${s.netflow_7d >= 0 ? "pos" : "neg"}`}>{signed$(s.netflow_7d)}</span>
            </li>
          ))}
        </ul>
      )}
      {sectors.length === 0 && <div className="empty">No sector flow data in this scan.</div>}

      <div className="method">
        <h2>How the signals are computed</h2>
        <ol>
          <li><code>smart_traders_and_funds_netflow</code> — tokens with the largest 7d smart-money inflows and outflows.</li>
          <li><code>smart_traders_and_funds_dex_trades</code> — per-token smart buys and sells; independence is scored from buyer count, distinct Nansen label cohorts, and the time-spread of first buys.</li>
          <li><code>smart_traders_and_funds_historical_token_balances</code> — day-by-day smart-money holdings for top exits, plus outflow acceleration (24h pace vs 7d pace).</li>
          <li>Consensus score = breadth × label-diversity × time-dispersion × conviction. Exit score = seller breadth × sell value × acceleration. Rotation is the same seed data aggregated by chain and sector — zero extra API calls.</li>
        </ol>
      </div>

      <div className="footer">
        Data via <a href="https://docs.nansen.ai" target="_blank" rel="noreferrer">Nansen API</a> ·
        Built for the Nansen Meridian Buildathon ·
        Analytical signals, not financial advice
      </div>
    </div>
  );
}
