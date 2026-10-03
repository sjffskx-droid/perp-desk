"""ตรรกะสัญญาณ SMC (BOS -> Order Block -> รอรีเทสต์) และตัวช่วยเชื่อมกระดานเทรด"""
import os
import pandas as pd
import requests

EXCHANGE = os.getenv("EXCHANGE", "binanceusdm")  # binanceusdm | bybit | okx
_ex = None


def get_ex():
    global _ex
    if _ex is None:
        import ccxt
        cfg = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
        if os.getenv("BN_KEY"):
            cfg.update(apiKey=os.getenv("BN_KEY"), secret=os.getenv("BN_SECRET"))
        _ex = getattr(ccxt, EXCHANGE)(cfg)
    return _ex


def tg(msg):
    token, chat = os.getenv("TG_TOKEN"), os.getenv("TG_CHAT")
    print(msg)
    if token and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            print("telegram error:", e)


def top_symbols(n=40):
    ex = get_ex()
    params = {"instType": "SWAP"} if EXCHANGE == "okx" else {}
    tickers = ex.fetch_tickers(params=params) if params else ex.fetch_tickers()
    rows = []
    for k, v in tickers.items():
        if not k.endswith(":USDT"):
            continue
        vol = v.get("quoteVolume") or (v.get("baseVolume") or 0) * (v.get("last") or 0)
        rows.append((k, vol or 0))
    return [k for k, _ in sorted(rows, key=lambda x: -x[1])[:n]]


def fetch_df(sym, tf="15m", limit=200):
    o = get_ex().fetch_ohlcv(sym, tf, limit=limit)
    return pd.DataFrame(o, columns=["ts", "open", "high", "low", "close", "vol"])


def atr(d, p=14):
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(),
                    (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(p).mean()


def find_signal(df, n=3, look=60, rr=2.0):
    """df = แท่งเทียนทั้งหมด แท่งสุดท้ายคือแท่งที่ยังไม่ปิด (ถูกตัดทิ้ง)"""
    d = df.iloc[:-1].reset_index(drop=True)
    if len(d) < look + n + 20:
        return None
    h, l = d.high, d.low
    sh = (h == h.rolling(2 * n + 1, center=True).max())
    sl = (l == l.rolling(2 * n + 1, center=True).min())
    sh.iloc[-n:] = False
    sl.iloc[-n:] = False
    a, last, N, start = atr(d).iloc[-1], d.iloc[-1], len(d), len(d) - look
    if pd.isna(a):
        return None
    for side in ("long", "short"):
        swings = [i for i in d.index[sh if side == "long" else sl] if i >= start - 20]
        for i in reversed(swings):
            lvl = d.high[i] if side == "long" else d.low[i]
            seg = d.iloc[i + 1:]
            m = (seg.close > lvl) if side == "long" else (seg.close < lvl)
            brk = seg.index[m.values]
            if len(brk) == 0:
                continue
            k = brk[0]
            if k < start or k > N - 2:
                continue
            ob = None
            for j in range(k - 1, i - 1, -1):
                bearish = d.close[j] < d.open[j]
                if (side == "long" and bearish) or (side == "short" and not bearish):
                    ob = (d.low[j], d.high[j])
                    break
            if not ob:
                continue
            lo, hi = ob
            later = d.iloc[k + 1:N - 1]
            if side == "long":
                if len(later) and (later.low <= hi).any():
                    continue
                if not (last.low <= hi and last.close >= lo):
                    continue
                sl_p = lo - 0.1 * a
                e = last.close
                tp = e + rr * (e - sl_p)
            else:
                if len(later) and (later.high >= lo).any():
                    continue
                if not (last.high >= lo and last.close <= hi):
                    continue
                sl_p = hi + 0.1 * a
                e = last.close
                tp = e - rr * (sl_p - e)
            return dict(side=side, entry=float(e), sl=float(sl_p), tp=float(tp),
                        zone=(float(lo), float(hi)), key=int(d.ts[k]), t=int(last.ts))
    return None
