"""Intraday refresh for zhenscapital.com (runs on GitHub Actions every ~10 minutes in market hours).
Reprices the holdings published in data.json with live quotes. Trades, stops and the daily equity curve are written
only by the trading agent after the close; this script touches prices, values and returns only."""
import json, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
now = datetime.now(NY)
force = "--force" in sys.argv
if not force and (now.weekday() > 4 or not ((now.hour, now.minute) >= (9, 30) and (now.hour, now.minute) <= (16, 5))):
    print("market closed, nothing to do"); sys.exit(0)

D = json.load(open("data.json"))
H = D.get("holdings")
if not H:
    print("no holdings block"); sys.exit(0)


def quote(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.replace('.', '-')}?range=1d&interval=1m"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
        m = json.loads(r.read())["chart"]["result"][0]["meta"]
    return float(m["regularMarketPrice"])


px = {}
for s in list(H["shares"]) + ["SPY"]:
    try:
        px[s] = quote(s)
    except Exception as e:
        print("quote failed", s, e); sys.exit(0)  # never publish a partial repricing

E = float(H["cash"]) + sum(q * px[s] for s, q in H["shares"].items())
P = float(H["principal"])
D["capital"].update(account_value=round(E, 2), pnl_usd=round(E - P, 2), principal=round(P, 2))
for p in D.get("positions", []):
    s = p["ticker"]
    if s not in H["shares"]: continue
    v = H["shares"][s] * px[s]
    p["value_usd"] = round(v, 2); p["weight"] = round(v / E, 3)
    if s in H.get("entries", {}): p["ret"] = round(px[s] / H["entries"][s] - 1, 4)
st = D["stats"]
st["total_return"] = round(E / float(H["units"]) / 100 - 1, 4)
st["spy_return"] = round(px["SPY"] / float(H["spy0"]) - 1, 4)
st["invested_pct"] = round((E - float(H["cash"])) / E, 3) if E else 0
D["updated"] = now.isoformat(timespec="seconds")
D["intraday"] = True
json.dump(D, open("data.json", "w"), separators=(",", ":"))
print("repriced", {k: round(v, 2) for k, v in px.items()}, "equity", round(E, 2))
