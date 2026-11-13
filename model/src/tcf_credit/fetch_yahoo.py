"""Pipeline step 5a (free stand-in for CRSP): download daily price history from Yahoo, one request per ticker.

Goes in:  a text file with one ticker per line.
Comes out: one CSV per ticker in OUT_DIR: date, open, high, low, close, adjclose, volume. Tickers already saved are
          skipped, so an interrupted run can simply be started again.
Data:     public Yahoo prices (network needed). Requests are paced (default 1 per second) so Yahoo is not hammered;
          if Yahoo answers "429" (too many requests) the script stops.
Usage: python -m tcf_credit.fetch_yahoo TICKERS_FILE OUT_DIR [--start 2010-01-01] [--pause 1.0] [--limit N]
"""
import csv
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tcf-credit-lecture research script"}


def fetch(ticker: str, start: str) -> list:
    """One ticker's daily rows from Yahoo's chart endpoint, from `start` to today."""
    p1 = int(dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp())
    p2 = int(time.time())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={p1}&period2={p2}"
           f"&interval=1d&events=div%2Csplit&includeAdjustedClose=true")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        res = json.loads(r.read())["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
    return [[dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(), q["open"][i], q["high"][i], q["low"][i],
             q["close"][i], adj[i], q["volume"][i]] for i, t in enumerate(ts)]


def main() -> None:
    """Download each listed ticker that is not saved yet, pausing between requests."""
    args = sys.argv[1:]
    tickers = [t.strip() for t in open(args[0]) if t.strip()]
    out = Path(args[1]); out.mkdir(parents=True, exist_ok=True)
    start = args[args.index("--start") + 1] if "--start" in args else "2010-01-01"
    pause = float(args[args.index("--pause") + 1]) if "--pause" in args else 1.0
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    t0, ok, fail = time.time(), 0, []
    for tk in tickers[:limit]:
        dest = out / f"{tk}.csv"
        if dest.exists():
            continue
        try:
            rows = fetch(tk, start)
            with dest.open("w", newline="") as fh:
                w = csv.writer(fh); w.writerow(["date", "open", "high", "low", "close", "adjclose", "volume"]); w.writerows(rows)
            ok += 1
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, TypeError, IndexError) as e:
            fail.append((tk, getattr(e, "code", type(e).__name__)))
            if getattr(e, "code", None) == 429:
                print("rate limited (429); stopping", flush=True); break
        time.sleep(pause)
    print(f"ok {ok}, failed {len(fail)} {fail[:10]}, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
