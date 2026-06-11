import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
WATCHLIST = os.getenv("WATCHLIST", "VNM,HPG,VIC,VHM,FPT,MWG,TCB,VCB,BID,CTG").split(",")

def fetch_ohlcv(symbol, days=200):
    ticker = symbol.strip().upper() + ".VN"
    end_ts   = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?interval=1d&period1={start_ts}&period2={end_ts}")
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res = r.json()["chart"]["result"]
        if not res: return pd.DataFrame()
        q = res[0]["indicators"]["quote"][0]
        df = pd.DataFrame({
            "date":   pd.to_datetime(res[0]["timestamp"], unit="s"),
            "open":   q["open"], "high": q["high"],
            "low":    q["low"],  "close": q["close"], "volume": q["volume"],
        }).dropna().reset_index(drop=True)
        return df
    except Exception as e:
        print(f"  Loi {symbol}: {e}")
        return pd.DataFrame()

def add_indicators(df):
    df["ma20"]     = df["close"].rolling(20).mean()
    df["ma50"]     = df["close"].rolling(50).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"]  - df["close"].shift()).abs()
    df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    return df

def fibonacci_levels(df):
    r = df.tail(60)
    high, low = r["high"].max(), r["low"].min()
    d = high - low
    return {"high": high, "low": low,
            "0.382": high - 0.382*d, "0.500": high - 0.500*d, "0.618": high - 0.618*d}

def analyze_trend(df):
    last = df.iloc[-1]
    if pd.isna(last["ma50"]): return "sideways"
    if last["ma20"] > last["ma50"] and last["close"] > last["ma20"]: return "uptrend"
    if last["ma20"] < last["ma50"] and last["close"] < last["ma20"]: return "downtrend"
    return "sideways"

def detect_candle(df):
    if len(df) < 2: return "—"
    c, c1 = df.iloc[-1], df.iloc[-2]
    body  = abs(c["close"] - c["open"])
    rng   = c["high"] - c["low"]
    if rng == 0: return "—"
    lower = min(c["close"], c["open"]) - c["low"]
    upper = c["high"] - max(c["close"], c["open"])
    if lower >= 2*body and upper <= body*0.5: return "Hammer"
    if (c["close"] > c["open"] and c1["close"] < c1["open"]
            and c["open"] <= c1["close"] and c["close"] >= c1["open"]):
        return "Bullish Engulfing"
    if upper >= 2*body and lower <= body*0.5 and c["close"] < c["open"]:
        return "Shooting Star"
    if (c["close"] < c["open"] and c1["close"] > c1["open"]
            and c["open"] >= c1["close"] and c["close"] <= c1["open"]):
        return "Bearish Engulfing"
    return "—"

def timeframe_signal(df, period):
    sub = df.tail(period).copy().reset_index(drop=True)
    if len(sub) < 10: return "—"
    sub["ms"] = sub["close"].rolling(5).mean()
    sub["ml"] = sub["close"].rolling(10).mean()
    delta = sub["close"].diff()
    gain  = delta.clip(lower=0).rolling(7).mean()
    loss  = (-delta.clip(upper=0)).rolling(7).mean()
    sub["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    last = sub.iloc[-1]
    if pd.isna(last["ml"]) or pd.isna(last["rsi"]): return "—"
    if last["ms"] > last["ml"] and last["rsi"] < 70: return "MUA"
    if last["ms"] < last["ml"] and last["rsi"] < 35: return "MUA"
    if last["ms"] < last["ml"] and last["rsi"] > 30: return "BAN"
    return "TRUNG TINH"

def tf_label(s):
    if s == "MUA": return "Mua"
    if s == "BAN": return "Ban"
    return "Trung tinh"

def esc(text):
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def analyze(symbol):
    df = fetch_ohlcv(symbol)
    if df.empty or len(df) < 30: return {"symbol": symbol, "error": True}
    df   = add_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price     = last["close"]
    volume    = int(last["volume"])
    vol_ma    = last["vol_ma20"]
    vol_ratio = volume / vol_ma if vol_ma and vol_ma > 0 else 1
    rsi       = last["rsi"]
    macd_bull = last["macd"] > last["macd_signal"]
    trend     = analyze_trend(df)
    candle    = detect_candle(df)
    fib       = fibonacci_levels(df)
    atr       = last["atr"] if not pd.isna(last["atr"]) else price * 0.02
    change    = price - prev["close"]
    change_pct= change / prev["close"] * 100
    near_fib  = any(abs(price - fib[k]) / price < 0.02 for k in ["0.382","0.500","0.618"])

    buy_pts, buy_why = 0, []
    if trend == "uptrend":
        buy_pts += 2; buy_why.append(("Xu huong tang (MA20 tren MA50)", True))
    if near_fib:
        buy_pts += 2; buy_why.append(("Gan vung Fibonacci ho tro", True))
    if "Hammer" in candle or "Bullish" in candle:
        buy_pts += 2; buy_why.append((f"Nen dao chieu: {candle}", True))
    if macd_bull:
        buy_pts += 1; buy_why.append(("MACD cat len (tich cuc)", True))
    if 35 < rsi < 65:
        buy_pts += 1; buy_why.append((f"RSI an toan ({rsi:.0f})", True))
    if vol_ratio > 1.5 and change > 0:
        buy_pts += 1; buy_why.append((f"Volume dot bien ({vol_ratio:.1f}x TB)", True))
    if not pd.isna(last["ma50"]) and last["ma20"] > last["ma50"]:
        buy_pts += 1; buy_why.append(("MA20 tren MA50", True))

    sell_pts, sell_why = 0, []
    if trend == "downtrend":
        sell_pts += 3; sell_why.append(("Xu huong giam (MA20 duoi MA50)", False))
    if "Shooting" in candle or "Bearish" in candle:
        sell_pts += 2; sell_why.append((f"Nen dao chieu: {candle}", False))
    if rsi > 72:
        sell_pts += 2; sell_why.append((f"RSI qua mua ({rsi:.0f})", False))
    if not macd_bull:
        sell_pts += 1; sell_why.append(("MACD cat xuong (tieu cuc)", False))
    if vol_ratio < 0.5 and change > 0:
        sell_pts += 2; sell_why.append(("Gia tang nhung volume can (phan ky)", False))
    if change_pct < -3:
        sell_pts += 1; sell_why.append((f"Giam manh hom nay ({change_pct:.1f}%)", False))

    if buy_pts >= 4 and buy_pts > sell_pts:
        verdict, emoji, score, why = "NEN MUA", "🟢", buy_pts, buy_why
        sl = price - 1.5*atr; tp = price + 3.0*atr
    elif sell_pts >= 4 and sell_pts > buy_pts:
        verdict, emoji, score, why = "NEN BAN", "🔴", sell_pts, sell_why
        sl = price + 1.5*atr; tp = price - 3.0*atr
    elif buy_pts >= 2:
        verdict, emoji, score, why = "THEO DOI", "🟡", buy_pts, buy_why
        sl = price - 1.5*atr; tp = price + 2.0*atr
    else:
        verdict, emoji, score, why = "TRUNG TINH", "⚪", max(buy_pts,sell_pts), sell_why or buy_why
        sl = price - atr; tp = price + atr

    return {
        "symbol": symbol, "error": False,
        "price": price, "change": change, "change_pct": change_pct,
        "volume": volume, "vol_ratio": vol_ratio, "rsi": rsi,
        "trend": trend, "candle": candle,
        "verdict": verdict, "emoji": emoji, "score": score, "why": why,
        "buy_pts": buy_pts, "sell_pts": sell_pts,
        "sl": sl, "tp": tp, "fib": fib,
        "sig_day":   timeframe_signal(df, 5),
        "sig_week":  timeframe_signal(df, 25),
        "sig_month": timeframe_signal(df, 60),
    }

def format_all(results, now):
    buy_syms   = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "NEN MUA"]
    sell_syms  = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "NEN BAN"]
    watch_syms = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "THEO DOI"]

    title_icons = ("".join(["🟢"]*len(buy_syms)) +
                   "".join(["🔴"]*len(sell_syms)) +
                   "".join(["🟡"]*len(watch_syms))) or "⚪"

    lines = [
        f"<b>{esc(now)}</b>",
        f"<b>BAO CAO CHUNG KHOAN</b>  {title_icons}",
        f"Nen mua: {len(buy_syms)}   Nen ban: {len(sell_syms)}   Theo doi: {len(watch_syms)}",
    ]

    order    = {"NEN MUA":0,"NEN BAN":1,"THEO DOI":2,"TRUNG TINH":3}
    sorted_r = sorted([r for r in results if not r.get("error")],
                      key=lambda x: order.get(x["verdict"], 4))
    errors   = [r for r in results if r.get("error")]

    for a in sorted_r:
        chg_arrow = "▲" if a["change"] >= 0 else "▼"
        fib = a["fib"]

        why_lines = []
        for text, is_positive in a["why"]:
            icon = "✅" if is_positive else "🔻"
            why_lines.append(f"  {icon} {esc(text)}")
        why_txt = "\n".join(why_lines) if why_lines else "  (Khong co tin hieu ro)"

        lines.append(
            "\n"
            "—————————————————\n"
            "\n"
            f"{a['emoji']} <b>{esc(a['symbol'])}</b>        <b>{esc(a['verdict'])}</b>\n"
            "\n"
            f"  Gia:   <b>{a['price']:,.0f}</b>   {chg_arrow} {a['change']:+,.0f} ({a['change_pct']:+.1f}%)\n"
            f"  KL:    {a['volume']:,}  ({a['vol_ratio']:.1f}x TB)\n"
            f"  RSI:   {a['rsi']:.0f}   |   Diem: {a['score']}/10\n"
            f"  Fib:   {fib['0.382']:,.0f}  /  {fib['0.500']:,.0f}  /  {fib['0.618']:,.0f}\n"
            "\n"
            f"{why_txt}\n"
            "\n"
            f"  ✅ Chot loi:  <b>{a['tp']:,.0f}</b>\n"
            f"  🔻 Cat lo:    <b>{a['sl']:,.0f}</b>\n"
            "\n"
            f"  Ngay: {tf_label(a['sig_day'])}   Tuan: {tf_label(a['sig_week'])}   Thang: {tf_label(a['sig_month'])}"
        )

    for a in errors:
        lines.append(f"\n—————————————————\n❌ {esc(a['symbol'])} — Khong lay duoc du lieu")

    return "\n".join(lines)

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(text); return
    max_len = 4000
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current: chunks.append(current)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in chunks:
        r = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID, "text": chunk,
            "parse_mode": "HTML", "disable_web_page_preview": True
        }, timeout=10)
        if r.status_code != 200:
            print(f"Telegram loi: {r.text}")
        time.sleep(0.3)

def run_scan():
    now = datetime.now().strftime("%d/%m/%Y  %H:%M")
    print(f"\nQuet {len(WATCHLIST)} ma luc {now}\n")
    results = []
    for sym in WATCHLIST:
        sym = sym.strip().upper()
        print(f"  -> {sym}...", end=" ", flush=True)
        a = analyze(sym)
        results.append(a)
        print(a.get("verdict", "LOI"))
        time.sleep(0.8)
    send_telegram(format_all(results, now))
    print(f"\nDa gui Telegram.")

if __name__ == "__main__":
    run_scan()
