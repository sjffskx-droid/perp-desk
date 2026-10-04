import os
import pandas as pd
from core import find_signal, get_ex, top_symbols

TF = os.getenv("TF", "15m")
TOP = int(os.getenv("TOP", "10"))
CANDLES = int(os.getenv("CANDLES", "4000"))
FEE = float(os.getenv("FEE", "0.0005"))
WARM = 150


def history(sym):
    ex = get_ex()
    step = ex.parse_timeframe(TF) * 1000
    since = ex.milliseconds() - CANDLES * step
    rows = []
    while len(rows) < CANDLES:
        part = ex.fetch_ohlcv(sym, TF, since=since, limit=300)
        part = [r for r in part if not rows or r[0] > rows[-1][0]]
        if not part:
            break
        rows += part
        since = rows[-1][0] + step
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol"])


def simulate(df):
    out, seen = [], set()
    for t in range(WARM, len(df) - 1):
        sg = find_signal(df.iloc[max(0, t - 249):t + 1])
        if not sg or (sg["side"], sg["key"]) in seen:
            continue
        seen.add((sg["side"], sg["key"]))
        risk_pct = abs(sg["entry"] - sg["sl"]) / sg["entry"]
        r = None
        for k in range(t, len(df)):
            hi, lo = df.high[k], df.low[k]
            long_ = sg["side"] == "long"
            hit_sl = lo <= sg["sl"] if long_ else hi >= sg["sl"]
            hit_tp = hi >= sg["tp"] if long_ else lo <= sg["tp"]
            if hit_sl or hit_tp:
                r = -1.0 if hit_sl else 2.0
                break
        if r is None:
            continue
        out.append((r - 2 * FEE / risk_pct, sg["side"]))
    return out


def report(name, trades):
    if not trades:
        print(f"{name:10s} no trades")
        return
    rs = [r for r, _ in trades]
    wins = [r for r in rs if r > 0]
    gp, gl = sum(wins), -sum(r for r in rs if r <= 0)
    print(f"{name:10s} trades {len(rs):4d} | win {len(wins)/len(rs)*100:5.1f}% | "
          f"avg {sum(rs)/len(rs):+.2f}R | total {sum(rs):+.1f}R | PF {gp/gl if gl else float('inf'):.2f}")


if __name__ == "__main__":
    allt = []
    for sym in top_symbols(TOP):
        try:
            tr = simulate(history(sym))
        except Exception as e:
            print("skip", sym, e)
            continue
        report(sym.split("/")[0], tr)
        allt += tr
    print("-" * 70)
    report("ALL", allt)
