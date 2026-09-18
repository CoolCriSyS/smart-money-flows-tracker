#!/usr/bin/env python3
"""Smart Money Flows Tracker v0.1 — Nansen Meridian Buildathon.

Three lenses on smart money movement (Nansen-labeled smart traders & funds):

  1. CONSENSUS RADAR — tokens where multiple *independent* smart-money wallets
     are accumulating. Independence is scored from buyer count, label diversity
     (different Nansen cohorts), and time dispersion of first buys: wallets that
     never trade together suddenly buying the same token is the signal.
  2. EXIT WHISPERER — tokens smart money is distributing: net outflow
     acceleration (24h pace vs 7d pace) plus per-wallet sell prints, with a
     day-by-day smart-holdings chart showing the bleed.
  3. ROTATION MAP — where smart capital is migrating: 7d netflows aggregated
     by chain and by sector, from the same seed data (zero extra API calls).

Pipeline (Nansen MCP tools):
  smart_traders_and_funds_netflow (7d desc + 7d asc)
    -> smart_traders_and_funds_dex_trades (per-token buys / sells)
    -> smart_traders_and_funds_historical_token_balances (top exits)

Usage:
  scanner.py [--inflow-tokens N] [--outflow-tokens N] [--out report.json]

~20 API calls per scan.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import urllib.request
from collections import defaultdict

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
try:
    from dynamic_credentials import (  # noqa: E402
        add_surrogate_to_request,
        read_response_body,
    )
    HAS_SURROGATE = True
except ImportError:
    HAS_SURROGATE = False

ENDPOINT = "https://mcp.nansen.ai/ra/mcp"
CREDENTIAL = "custom.nansen"
ALLOWED_HOSTS = ("mcp.nansen.ai",)

CALL_COUNT = 0

WRAPPED_DENY = {"WETH", "WBTC", "WSOL", "WSTETH", "WEETH", "WBETH", "STETH", "WBNB"}


def _post(payload):
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    api_key = os.environ.get("NANSEN" + "_API_KEY")
    if api_key:
        req.add_header("NANSEN-API-KEY", api_key)
    elif HAS_SURROGATE:
        add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
    else:
        raise RuntimeError("No Nansen API key: set NANSEN_API_KEY or run where the credential helper exists.")
    with urllib.request.urlopen(req, timeout=120) as resp:
        if HAS_SURROGATE:
            body = read_response_body(resp).decode("utf-8", errors="replace")
        else:
            body = resp.read().decode("utf-8", errors="replace")
    lines = [l for l in body.splitlines() if l.strip().startswith("data:")]
    if lines:
        body = lines[-1][len("data:"):].strip()
    return json.loads(body)


def rpc(method, params=None):
    global CALL_COUNT
    CALL_COUNT += 1
    payload = {"jsonrpc": "2.0", "id": CALL_COUNT, "method": method}
    if params is not None:
        payload["params"] = params
    data = _post(payload)
    contents = data.get("result", {}).get("content", [])
    texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
    return "\n".join(texts)


def parse_tables(text):
    tables, current = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            current.append(line)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    out = []
    for t in tables:
        if len(t) < 3:
            continue
        headers = [h.strip() for h in t[0].strip().strip("|").split("|")]
        for line in t[2:]:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == len(headers):
                out.append(dict(zip(headers, cells)))
    return out


def parse_money(s):
    if not s:
        return 0.0
    s = s.strip().replace(",", "").replace("$", "")
    if s in ("N/A", "-", "--", ""):
        return 0.0
    m = re.fullmatch(r"(-?[\d.]+)\s*([kmbKMB])?", s)
    if not m:
        try:
            return float(s)
        except ValueError:
            return 0.0
    val = float(m.group(1))
    mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1)
    return val * mult


def parse_time(s):
    try:
        return datetime.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def netflow(direction, limit=25):
    text = rpc("tools/call", {
        "name": "smart_traders_and_funds_netflow",
        "arguments": {"request": {
            "includeStablecoin": False,
            "includeNativeTokens": False,
            "orderBy": "net_flow_7d_usd",
            "orderByDirection": direction,
        }},
    })
    rows = parse_tables(text)[:limit]
    tokens = []
    for r in rows:
        tokens.append({
            "address": r.get("Token Address", ""),
            "symbol": r.get("Symbol", "").replace("🌱 ", ""),
            "chain": r.get("Chain", ""),
            "sectors": [s.strip() for s in r.get("Sectors", "").split(",") if s.strip()],
            "netflow_1h": parse_money(r.get("Netflow 1h")),
            "netflow_24h": parse_money(r.get("Netflow 24h")),
            "netflow_7d": parse_money(r.get("Netflow 7d")),
            "netflow_30d": parse_money(r.get("Netflow 30d")),
            "trader_count": int(re.sub(r"\D", "", r.get("Traders", "") or "0") or 0),
            "token_age_days": int(re.sub(r"\D", "", r.get("Token Age (Days)", "") or "0") or 0),
            "market_cap": parse_money(r.get("Market Cap")),
        })
    return tokens


def clean_label(s):
    """Redact labels containing slurs before they reach public output."""
    if not s:
        return ""
    low = s.lower()
    if "nigger" in low or "nigga" in low:
        return ""
    return s


def dex_trades(symbol, chain, side):
    """side='buy' -> tokenBoughtSymbol, side='sell' -> tokenSoldSymbol."""
    key = "tokenBoughtSymbol" if side == "buy" else "tokenSoldSymbol"
    text = rpc("tools/call", {
        "name": "smart_traders_and_funds_dex_trades",
        "arguments": {"request": {
            "chains": [chain],
            key: symbol,
        }},
    })
    trades = []
    for r in parse_tables(text):
        trades.append({
            "trader": r.get("Trader", ""),
            "label": clean_label(r.get("Trader Label", "")),
            "time": parse_time(r.get("Time", "")),
            "value_usd": parse_money(r.get("Trade Value")),
            "bought": r.get("Bought", ""),
            "sold": r.get("Sold", ""),
        })
    return [t for t in trades if t["trader"]]


def historical_balances(token_address, chain, days=30):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    text = rpc("tools/call", {
        "name": "smart_traders_and_funds_historical_token_balances",
        "arguments": {"request": {
            "tokenAddress": token_address,
            "chains": [chain],
            "dateRange": {"from": start.isoformat(), "to": end.isoformat()},
            "orderByDirection": "ASC",
        }},
    })
    points = []
    for r in parse_tables(text):
        date = r.get("Date", "") or r.get("date", "")
        bal = r.get("Balance USD", "") or r.get("balance_usd", "") or r.get("Balance", "")
        if date:
            points.append({"date": date.strip(), "balance_usd": parse_money(bal)})
    return points


def consensus_signals(inflow_tokens, n_tokens):
    signals = []
    for tok in inflow_tokens[:n_tokens]:
        if not tok["symbol"] or not tok["chain"]:
            continue
        if tok["symbol"].upper() in WRAPPED_DENY:
            continue
        trades = dex_trades(tok["symbol"], tok["chain"], "buy")
        buyers = {}
        for t in trades:
            b = buyers.setdefault(t["trader"], {"label": t["label"], "value": 0.0, "times": []})
            b["value"] += t["value_usd"]
            if t["time"]:
                b["times"].append(t["time"])
        n = len(buyers)
        if n < 3:
            continue  # need a crowd for consensus
        labels = {b["label"] for b in buyers.values() if b["label"]}
        all_times = [tm for b in buyers.values() for tm in b["times"]]
        spread_h = ((max(all_times) - min(all_times)).total_seconds() / 3600) if len(all_times) > 1 else 0
        total_buy = sum(b["value"] for b in buyers.values())
        breadth = math.log1p(n)
        diversity = (len(labels) / n) if n else 0
        dispersion = 0.5 + 0.5 * min(spread_h / 24.0, 1.0)
        conviction = math.log1p(total_buy)
        score = breadth * diversity * dispersion * conviction
        top_buyers = sorted(buyers.items(), key=lambda kv: kv[1]["value"], reverse=True)[:5]
        signals.append({
            "symbol": tok["symbol"],
            "chain": tok["chain"],
            "address": tok["address"],
            "sectors": tok["sectors"],
            "market_cap": tok["market_cap"],
            "token_age_days": tok["token_age_days"],
            "score": round(score, 3),
            "buyers": n,
            "distinct_labels": len(labels),
            "spread_hours": round(spread_h, 1),
            "total_buy_usd": round(total_buy, 2),
            "netflow_7d": tok["netflow_7d"],
            "top_buyers": [
                {"address": a, "label": b["label"], "value_usd": round(b["value"], 2)}
                for a, b in top_buyers
            ],
        })
    signals.sort(key=lambda s: s["score"], reverse=True)
    return signals


def exit_signals(outflow_tokens, n_tokens):
    signals = []
    for tok in outflow_tokens[:n_tokens]:
        if not tok["symbol"] or not tok["chain"]:
            continue
        if tok["symbol"].upper() in WRAPPED_DENY:
            continue
        trades = dex_trades(tok["symbol"], tok["chain"], "sell")
        sellers = {}
        for t in trades:
            s = sellers.setdefault(t["trader"], {"label": t["label"], "value": 0.0, "times": []})
            s["value"] += t["value_usd"]
            if t["time"]:
                s["times"].append(t["time"])
        m = len(sellers)
        if m < 2:
            continue
        total_sell = sum(s["value"] for s in sellers.values())
        f7 = abs(tok["netflow_7d"])
        daily_pace = f7 / 7.0 if f7 else 0
        accel = min(abs(tok["netflow_24h"]) / daily_pace, 8.0) if daily_pace > 0 else 1.0
        score = math.log1p(m) * math.log1p(total_sell) * math.log1p(accel)
        top_sellers = sorted(sellers.items(), key=lambda kv: kv[1]["value"], reverse=True)[:5]
        signals.append({
            "symbol": tok["symbol"],
            "chain": tok["chain"],
            "address": tok["address"],
            "sectors": tok["sectors"],
            "market_cap": tok["market_cap"],
            "score": round(score, 3),
            "sellers": m,
            "total_sell_usd": round(total_sell, 2),
            "netflow_24h": tok["netflow_24h"],
            "netflow_7d": tok["netflow_7d"],
            "netflow_30d": tok["netflow_30d"],
            "acceleration": round(accel, 2),
            "holdings_history": [],
            "top_sellers": [
                {"address": a, "label": s["label"], "value_usd": round(s["value"], 2)}
                for a, s in top_sellers
            ],
        })
    signals.sort(key=lambda s: s["score"], reverse=True)
    # distribution chart for the top 3 exits
    for sig in signals[:3]:
        try:
            sig["holdings_history"] = historical_balances(sig["address"], sig["chain"])
        except Exception:
            sig["holdings_history"] = []
    return signals


def rotation_map(inflow_tokens, outflow_tokens):
    by_key = {}
    for tok in inflow_tokens + outflow_tokens:
        key = (tok["chain"], tok["address"])
        by_key[key] = tok  # dedupe; inflow list first so it wins ties
    chain_flows = defaultdict(float)
    sector_flows = defaultdict(float)
    for (chain, _), tok in by_key.items():
        chain_flows[chain] += tok["netflow_7d"]
        for sec in tok["sectors"]:
            sector_flows[sec] += tok["netflow_7d"]
    chains = sorted(
        ({"chain": c, "netflow_7d": round(v, 2)} for c, v in chain_flows.items()),
        key=lambda x: x["netflow_7d"], reverse=True,
    )
    sectors = sorted(
        ({"sector": s, "netflow_7d": round(v, 2)} for s, v in sector_flows.items()),
        key=lambda x: x["netflow_7d"], reverse=True,
    )
    return {"chains": chains, "sectors": sectors[:15]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inflow-tokens", type=int, default=8)
    ap.add_argument("--outflow-tokens", type=int, default=8)
    ap.add_argument("--out", default="report.json")
    args = ap.parse_args()

    inflow = netflow("desc")
    outflow = netflow("asc")
    consensus = consensus_signals(inflow, args.inflow_tokens)
    exits = exit_signals(outflow, args.outflow_tokens)
    rotation = rotation_map(inflow, outflow)

    report = {
        "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "api_calls": CALL_COUNT,
        "consensus": consensus,
        "exits": exits,
        "rotation": rotation,
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"calls={CALL_COUNT} consensus={len(consensus)} exits={len(exits)} -> {args.out}")


if __name__ == "__main__":
    main()
