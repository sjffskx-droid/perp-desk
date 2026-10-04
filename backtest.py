import os
import pandas as pd
from core import find_signal, get_ex, top_symbols

TFS = os.getenv("TFS", "15m,1h").split(",")
TOP = int(os.getenv("TOP", "10"))
CANDLES = int(os.getenv("CANDLES", "4000"))
FEE = float(os.getenv("FEE", "0.0005"))
WARM = 150
MIN_RISKS = [0.0, 0.004, 0.008]


def history(sym, tf):
    ex = get_ex()
    step = ex.parse_timeframe(tf) * 1000
    since = ex.milliseconds() - CANDLES * step
    rows = []
    while len(rows) < CANDLES:
        part = ex.fetch_ohlcv(sym, tf, since=since, limit=300)
        part = [r for r in part if not rows or r[0] > rows[-1][0]]
        if not part:
            break
        rows += part
        since = rows[-1][0] + step
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol"])


def raw_trades(df):
    hi, lo, cl = df.high.values, df.low.values, df.close.values
    ema = df.close.ewm(span=100, adjust=False).mean().values
    out, seen = [], set()
    for t in range(WARM, len(df) - 1):
        sg = find_signal(df.iloc[max(0, t - 249):t + 1])
        if not sg or (sg["side"], sg["key"]) in seen:
            continue
        seen.add((sg["side"], sg["key"]))
        long_ = sg["side"] == "long"
        r = None
        for k in range(t, len(df)):
            hit_sl = lo[k] <= sg["sl"] if long_ else hi[k] >= sg["sl"]
            hit_tp = hi[k] >= sg["tp"] if long_ else lo[k] <= sg["tp"]
            if hit_sl or hit_tp:
                r = -1.0 if hit_sl else 2.0
                break
        if r is None:
            continue
        trend = cl[t - 1] > ema[t - 1] if long_ else cl[t - 1] < ema[t - 1]
        out.append(dict(r=r, risk=abs(sg["entry"] - sg["sl"]) / sg["entry"], trend=bool(trend)))
    return out


def summarize(tag, trades, min_risk, trend_on):
    rs = [t["r"] - 2 * FEE / t["risk"] for t in trades
          if t["risk"] >= min_risk and (t["trend"] or not trend_on)]
    label = f"{tag:4s} minrisk {min_risk*100:.1f}% trend {'on ' if trend_on else 'off'}"
    if not rs:
        print(f"{label} | no trades")
        return
    wins = [r for r in rs if r > 0]
    gp, gl = sum(wins), -sum(r for r in rs if r <= 0)
    print(f"{label} | trades {len(rs):4d} | win {len(wins)/len(rs)*100:5.1f}% | "
          f"avg {sum(rs)/len(rs):+.2f}R | total {sum(rs):+.1f}R | PF {gp/gl if gl else float('inf'):.2f}")


if __name__ == "__main__":
    syms = top_symbols(TOP)
    for tf in TFS:
        allt = []
        for sym in syms:
            try:
                allt += raw_trades(history(sym, tf))
            except Exception as e:
                print("skip", sym, e)
        for mr in MIN_RISKS:
            for tr in (False, True):
                summarize(tf, allt, mr, tr)
        print("-" * 78)

