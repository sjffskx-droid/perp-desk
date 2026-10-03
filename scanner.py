"""สแกนเนอร์สัญญาณ: เขียนผลลง docs/signals.json ให้เว็บอ่าน + ส่ง Telegram

รันวนต่อเนื่อง:  python scanner.py
รันครั้งเดียว (ใช้กับ GitHub Actions):  python scanner.py --once
"""
import json
import os
import sys
import time
from pathlib import Path

from core import EXCHANGE, fetch_df, find_signal, get_ex, tg, top_symbols

TF = os.getenv("TF", "15m")
TOP = int(os.getenv("TOP", "40"))
OUT = Path(os.getenv("OUT", "docs/signals.json"))
KEEP, EXPIRE_H = 300, 24
HOUR_MS = 3600 * 1000


def load():
    try:
        st = json.loads(OUT.read_text(encoding="utf-8"))
        st.setdefault("signals", [])
        return st
    except Exception:
        return {"signals": []}


def save(st, hour):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    st.update(updated=hour, exchange=EXCHANGE, tf=TF)
    st["signals"] = st["signals"][-KEEP:]
    OUT.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def fmt(x):
    return f"{x:.6g}"


def scan(st):
    ids = {s["id"] for s in st["signals"]}
    for sym in top_symbols(TOP):
        try:
            sg = find_signal(fetch_df(sym, TF))
        except Exception as e:
            print("skip", sym, e)
            continue
        if not sg:
            continue
        sid = f"{sym}|{sg['side']}|{sg['key']}"
        if sid in ids:
            continue
        s = dict(id=sid, symbol=sym, sym=sym.split("/")[0], side=sg["side"], tf=TF,
                 entry=sg["entry"], sl=sg["sl"], tp=sg["tp"], zone=list(sg["zone"]),
                 t=sg["t"], status="open")
        st["signals"].append(s)
        icon = "🟢 LONG" if s["side"] == "long" else "🔴 SHORT"
        tg(f"{icon} <b>{s['sym']}</b> [{TF}]\nEntry {fmt(s['entry'])}\nSL {fmt(s['sl'])}\nTP {fmt(s['tp'])} (RR 2)")


def resolve(st):
    ex = get_ex()
    tf_ms = ex.parse_timeframe(TF) * 1000
    now = time.time() * 1000
    for s in st["signals"]:
        if s["status"] != "open":
            continue
        try:
            candles = ex.fetch_ohlcv(s["symbol"], s["tf"], since=s["t"] + 1, limit=300)
        except Exception as e:
            print("resolve skip", s["sym"], e)
            continue
        for ts, _o, hi, lo, _c, _v in candles:
            if ts <= s["t"]:
                continue
            if ts + tf_ms > now:      # แท่งนี้ยังไม่ปิด
                break
            long_ = s["side"] == "long"
            hit_sl = lo <= s["sl"] if long_ else hi >= s["sl"]
            hit_tp = hi >= s["tp"] if long_ else lo <= s["tp"]
            if hit_sl or hit_tp:      # ถ้าโดนทั้งคู่ในแท่งเดียว นับเป็น SL (เข้มงวดไว้ก่อน)
                s["status"] = "sl" if hit_sl else "tp"
                s["closed"] = int(ts)
                tg(f"{'✅ TP' if s['status'] == 'tp' else '❌ SL'} {s['sym']} [{s['tf']}] {s['side'].upper()}")
                break
        if s["status"] == "open" and now - s["t"] > EXPIRE_H * HOUR_MS:
            s["status"] = "exp"


def run_once():
    st = load()
    before = json.dumps(st["signals"], sort_keys=True)
    try:
        scan(st)
        resolve(st)
    except Exception as e:
        print("error:", e)
    hour = int(time.time() // 3600) * HOUR_MS
    changed = json.dumps(st["signals"], sort_keys=True) != before
    if changed or st.get("updated") != hour or not OUT.exists():
        save(st, hour)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        while True:
            run_once()
            time.sleep(60)
