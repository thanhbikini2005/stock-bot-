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

# ── Lấy dữ liệu Yahoo Finance ──────────────────────────────────────────────────
def fetch_ohlcv(symbol, days=200):
    ticker    = symbol.strip().upper()
    yf_ticker = ticker + ".VN"
    end_ts    = int(datetime.now().timestamp())
    start_ts  = int((datetime.now() - timedelta(days=days)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}"
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

def fetch_vnindex(days=200):
    """Lấy VNINDEX: thử TCBS trước, fallback sang SSI. Cả 2 miễn phí, không cần key."""
    to_ts   = int(datetime.now().timestamp())
    from_ts = int((datetime.now() - timedelta(days=days)).timestamp())

    # ── Nguồn 1: TCBS ──────────────────────────────────────────────────────────
    try:
        url  = (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
                f"?ticker=VNINDEX&type=index&resolution=D&from={from_ts}&to={to_ts}")
        r    = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = r.json().get("data", [])
        if data:
            df = pd.DataFrame(data)
            df = df.rename(columns={"tradingDate": "date"})
            df["date"] = pd.to_datetime(df["date"], unit="s", errors="coerce")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df.get(col, 0), errors="coerce")
            df = df[["date","open","high","low","close","volume"]].dropna().reset_index(drop=True)
            if len(df) >= 30:
                print("(TCBS)", end=" ", flush=True)
                return df
    except Exception as e:
        print(f"(TCBS lỗi: {e})", end=" ", flush=True)

    # ── Nguồn 2: SSI iBoard ────────────────────────────────────────────────────
    try:
        end_d   = datetime.now().strftime("%Y-%m-%d")
        start_d = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        url  = (f"https://iboard-query.ssi.com.vn/v2/stock/indices-historical-price"
                f"?indexId=VNINDEX&fromDate={start_d}&toDate={end_d}&limit=300&offset=0")
        hdrs = {"User-Agent": "Mozilla/5.0",
                "Referer":    "https://iboard.ssi.com.vn/",
                "Origin":     "https://iboard.ssi.com.vn"}
        r    = requests.get(url, headers=hdrs, timeout=15)
        rows = r.json().get("data", {}).get("items", [])
        if rows:
            df = pd.DataFrame(rows)
            df = df.rename(columns={
                "tradingDate": "date", "openIndex": "open",
                "highIndex":   "high", "lowIndex":  "low",
                "closeIndex":  "close","totalQtty": "volume"
            })
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df.get(col, 0), errors="coerce")
            df = (df[["date","open","high","low","close","volume"]]
                  .dropna().sort_values("date").reset_index(drop=True))
            if len(df) >= 30:
                print("(SSI)", end=" ", flush=True)
                return df
    except Exception as e:
        print(f"(SSI lỗi: {e})", end=" ", flush=True)

    return pd.DataFrame()

# ── Chỉ báo kỹ thuật ───────────────────────────────────────────────────────────
def add_indicators(df):
    df["ma20"]     = df["close"].rolling(20).mean()
    df["ma50"]     = df["close"].rolling(50).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    # TB khối lượng tuần (5 phiên) và tháng (20 phiên)
    df["vol_ma5"]  = df["volume"].rolling(5).mean()
    df["vol_ma20_prev"] = df["volume"].rolling(20).mean().shift(1)
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
            "0.382": high - 0.382*d,
            "0.500": high - 0.500*d,
            "0.618": high - 0.618*d}

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
    if s == "BAN": return "Bán"
    return "Trung tính"

def esc(text):
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ── Phân tích khối lượng ───────────────────────────────────────────────────────
def volume_analysis(df):
    """
    Trả về dict với nhận xét KL hôm nay, so tuần, so tháng, và kết luận hành vi.
    """
    last     = df.iloc[-1]
    vol_today = last["volume"]
    vol_ma20  = last["vol_ma20"]   # TB 20 phiên
    vol_ma5   = last["vol_ma5"]    # TB 5 phiên (tuần)
    change    = last["close"] - df.iloc[-2]["close"]

    # TB tuần trước (5 phiên lùi thêm 5) và tháng trước (20 phiên lùi thêm 20)
    if len(df) >= 10:
        vol_prev_week  = df["volume"].iloc[-10:-5].mean()
    else:
        vol_prev_week  = vol_ma20

    if len(df) >= 40:
        vol_prev_month = df["volume"].iloc[-40:-20].mean()
    else:
        vol_prev_month = vol_ma20

    ratio_today = vol_today / vol_ma20 if vol_ma20 > 0 else 1
    ratio_week  = (vol_ma5 / vol_prev_week - 1) * 100 if vol_prev_week > 0 else 0
    ratio_month = (vol_ma20 / vol_prev_month - 1) * 100 if vol_prev_month > 0 else 0

    def fmt_vol(v):
        if v >= 1_000_000: return f"{v/1_000_000:.2f} triệu"
        if v >= 1_000:     return f"{v/1_000:.0f} nghìn"
        return str(int(v))

    # Icon: 📈 nếu tốt/tăng, 🔺 nếu xấu/giảm
    if ratio_today >= 1.5:
        icon_today = "📈"; note_today = f"RẤT CAO ({ratio_today:.1f}x TB)"
    elif ratio_today >= 1.0:
        icon_today = "📈"; note_today = f"CAO HƠN TB ({ratio_today:.1f}x)"
    elif ratio_today >= 0.7:
        icon_today = "🔺"; note_today = f"THẤP HƠN TB ({ratio_today:.1f}x)"
    else:
        icon_today = "🔺"; note_today = f"RẤT THẤP ({ratio_today:.1f}x TB)"

    icon_week  = "📈" if ratio_week  >= 0 else "🔺"
    icon_month = "📈" if ratio_month >= 0 else "🔺"

    week_txt  = f"{'tăng' if ratio_week  >= 0 else 'giảm'} {abs(ratio_week):.0f}%"
    month_txt = f"{'tăng' if ratio_month >= 0 else 'giảm'} {abs(ratio_month):.0f}%"

    lines = [
        f"  Hôm nay:  {fmt_vol(vol_today)}   {icon_today} {note_today}",
        f"  TB tuần:  {fmt_vol(vol_ma5)}   {icon_week} Tuần này KL {week_txt}",
        f"  TB tháng: {fmt_vol(vol_ma20)}   {icon_month} Tháng này KL {month_txt}",
    ]

    # Kết luận hành vi
    if ratio_today >= 1.5 and change > 0:
        behavior = ["✅ Giá tăng + KL đột biến = Dòng tiền đang MUA VÀO mạnh"]
    elif ratio_today >= 1.5 and change < 0:
        behavior = ["🔻 Giá giảm + KL đột biến = Có thể XẢ HÀNG lớn, cẩn thận"]
    elif ratio_today < 0.6 and change > 0:
        behavior = ["⚠ Giá tăng + KL thấp = PHÂN KỲ hoặc GOM HÀNG im lặng",
                    "⚠ Chưa có xác nhận KL — chờ thêm tín hiệu"]
    elif ratio_today < 0.6 and change < 0:
        behavior = ["⚠ Giá giảm + KL thấp = Thị trường đang CHỜ ĐỢI, chưa rõ hướng"]
    elif ratio_today >= 1.0 and change > 0:
        behavior = ["✅ Giá tăng + KL tốt = Xu hướng tăng đang được xác nhận"]
    elif ratio_today >= 1.0 and change < 0:
        behavior = ["🔻 Giá giảm + KL cao = Áp lực bán còn mạnh"]
    else:
        behavior = ["⚠ KL bình thường — chưa có tín hiệu rõ ràng"]

    if ratio_week >= 20:
        behavior.append("✅ KL tuần tăng mạnh — dòng tiền đang tích lũy bền vững")
    elif ratio_week <= -20:
        behavior.append("🔻 KL tuần giảm mạnh — dòng tiền đang rút lui")

    return {
        "lines":    lines,
        "behavior": behavior,
        "ratio_today": ratio_today,
    }

# ── Phân tích VNINDEX ──────────────────────────────────────────────────────────
def analyze_vnindex():
    df = fetch_vnindex()
    if df.empty or len(df) < 30:
        return None
    df   = add_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    price      = last["close"]
    change     = price - prev["close"]
    change_pct = change / prev["close"] * 100
    rsi        = last["rsi"]
    trend      = analyze_trend(df)
    fib        = fibonacci_levels(df)
    vol_info   = volume_analysis(df)

    sig_day   = timeframe_signal(df, 5)
    sig_week  = timeframe_signal(df, 25)
    sig_month = timeframe_signal(df, 60)

    price_icon = "📈" if change >= 0 else "🔺"

    trend_lines = []
    if trend == "uptrend":
        trend_lines.append("✅ Xu hướng TĂNG — MA20 trên MA50")
    elif trend == "downtrend":
        trend_lines.append("🔻 Xu hướng GIẢM — MA20 dưới MA50")
    else:
        trend_lines.append("⚠ Xu hướng TRUNG TÍNH — đang đi ngang")

    ma20 = last["ma20"] if not pd.isna(last["ma20"]) else 0
    ma50 = last["ma50"] if not pd.isna(last["ma50"]) else 0

    # Kết luận tổng thị trường
    if trend == "uptrend" and vol_info["ratio_today"] >= 1.0:
        market_conclusion = "THỊ TRƯỜNG TÍCH CỰC — Dòng tiền vào mạnh, phù hợp mua cổ phiếu tốt."
        market_emoji = "✅"
    elif trend == "uptrend" and vol_info["ratio_today"] < 1.0:
        market_conclusion = "THỊ TRƯỜNG THẬN TRỌNG — Xu hướng tăng nhưng KL yếu, chờ xác nhận."
        market_emoji = "⚠"
    elif trend == "downtrend":
        market_conclusion = "THỊ TRƯỜNG TIÊU CỰC — Hạn chế mua mới, bảo toàn vốn."
        market_emoji = "🔻"
    else:
        market_conclusion = "THỊ TRƯỜNG ĐI NGANG — Chờ tín hiệu rõ hơn trước khi hành động."
        market_emoji = "⚠"

    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 VNINDEX — THỊ TRƯỜNG CHUNG")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"  Giá: <b>{price:,.2f}</b>  {price_icon} {change:+,.2f} ({change_pct:+.2f}%)")
    lines.append(f"  RSI: {rsi:.0f}   |   MA20: {ma20:,.0f}   MA50: {ma50:,.0f}")
    lines.append("")
    lines.append("  <b>Khối lượng:</b>")
    for l in vol_info["lines"]:
        lines.append(l)
    lines.append("")
    lines.append("  <b>Nhận xét:</b>")
    for b in vol_info["behavior"]:
        lines.append(f"  {b}")
    lines.append("")
    lines.append("  <b>Xu hướng:</b>")
    for t in trend_lines:
        lines.append(f"  {t}")
    lines.append(f"  Fib hỗ trợ: {fib['0.382']:,.0f} / {fib['0.500']:,.0f} / {fib['0.618']:,.0f}")
    lines.append("")
    lines.append(f"  Ngày: <b>{tf_label(sig_day)}</b>   Tuần: <b>{tf_label(sig_week)}</b>   Tháng: <b>{tf_label(sig_month)}</b>")
    lines.append("")
    lines.append(f"  <b>{market_emoji} {market_conclusion}</b>")

    return "\n".join(lines)

# ── Phân tích từng mã ──────────────────────────────────────────────────────────
def analyze(symbol):
    df = fetch_ohlcv(symbol)
    if df.empty or len(df) < 30: return {"symbol": symbol, "error": True}
    df   = add_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    price      = last["close"]
    vol_ratio  = last["volume"] / last["vol_ma20"] if last["vol_ma20"] > 0 else 1
    rsi        = last["rsi"]
    macd_bull  = last["macd"] > last["macd_signal"]
    trend      = analyze_trend(df)
    candle     = detect_candle(df)
    fib        = fibonacci_levels(df)
    atr        = last["atr"] if not pd.isna(last["atr"]) else price * 0.02
    change     = price - prev["close"]
    change_pct = change / prev["close"] * 100
    near_fib   = any(abs(price - fib[k]) / price < 0.02 for k in ["0.382","0.500","0.618"])
    vol_info   = volume_analysis(df)

    buy_pts, buy_why = 0, []
    if trend == "uptrend":
        buy_pts += 2; buy_why.append(("Xu hướng tăng (MA20 trên MA50)", True))
    if near_fib:
        buy_pts += 2; buy_why.append(("Gần vùng Fibonacci hỗ trợ", True))
    if "Hammer" in candle or "Bullish" in candle:
        buy_pts += 2; buy_why.append((f"Nến đảo chiều: {candle}", True))
    if macd_bull:
        buy_pts += 1; buy_why.append(("MACD cắt lên (tích cực)", True))
    if 35 < rsi < 65:
        buy_pts += 1; buy_why.append((f"RSI an toàn ({rsi:.0f})", True))
    if vol_ratio > 1.5 and change > 0:
        buy_pts += 1; buy_why.append((f"Volume đột biến ({vol_ratio:.1f}x TB)", True))
    if not pd.isna(last["ma50"]) and last["ma20"] > last["ma50"]:
        buy_pts += 1; buy_why.append(("MA20 trên MA50", True))

    sell_pts, sell_why = 0, []
    if trend == "downtrend":
        sell_pts += 3; sell_why.append(("Xu hướng giảm (MA20 dưới MA50)", False))
    if "Shooting" in candle or "Bearish" in candle:
        sell_pts += 2; sell_why.append((f"Nến đảo chiều: {candle}", False))
    if rsi > 72:
        sell_pts += 2; sell_why.append((f"RSI quá mua ({rsi:.0f})", False))
    if not macd_bull:
        sell_pts += 1; sell_why.append(("MACD cắt xuống (tiêu cực)", False))
    if vol_ratio < 0.5 and change > 0:
        sell_pts += 2; sell_why.append(("Giá tăng nhưng KL cạn (phân kỳ)", False))
    if change_pct < -3:
        sell_pts += 1; sell_why.append((f"Giảm mạnh hôm nay ({change_pct:.1f}%)", False))

    if buy_pts >= 4 and buy_pts > sell_pts:
        verdict, emoji, score, why = "NÊN MUA", "🟢", buy_pts, buy_why
        sl = price - 1.5*atr; tp = price + 3.0*atr
        conclusion = "KL và kỹ thuật xác nhận. Có thể cân nhắc vào hàng."
    elif sell_pts >= 4 and sell_pts > buy_pts:
        verdict, emoji, score, why = "NÊN BÁN", "🔴", sell_pts, sell_why
        sl = price + 1.5*atr; tp = price - 3.0*atr
        conclusion = "Tránh mua. Nếu đang giữ nên xem xét cắt lỗ."
    elif buy_pts >= 2:
        verdict, emoji, score, why = "THEO DÕI", "🟡", buy_pts, buy_why
        sl = price - 1.5*atr; tp = price + 2.0*atr
        conclusion = "Chờ thêm tín hiệu xác nhận trước khi vào hàng."
    else:
        verdict, emoji, score, why = "TRUNG TÍNH", "⚪", max(buy_pts,sell_pts), sell_why or buy_why
        sl = price - atr; tp = price + atr
        conclusion = "Chưa có tín hiệu rõ. Đứng ngoài quan sát."

    return {
        "symbol": symbol, "error": False,
        "price": price, "change": change, "change_pct": change_pct,
        "vol_ratio": vol_ratio, "rsi": rsi,
        "trend": trend, "candle": candle,
        "verdict": verdict, "emoji": emoji, "score": score, "why": why,
        "sl": sl, "tp": tp, "fib": fib,
        "vol_info": vol_info,
        "conclusion": conclusion,
        "sig_day":   timeframe_signal(df, 5),
        "sig_week":  timeframe_signal(df, 25),
        "sig_month": timeframe_signal(df, 60),
    }

# ── Format tin nhắn ────────────────────────────────────────────────────────────
def format_all(results, now, vnindex_block):
    buy_syms   = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "NÊN MUA"]
    sell_syms  = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "NÊN BÁN"]
    watch_syms = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "THEO DÕI"]

    title_icons = ("".join(["🟢"]*len(buy_syms)) +
                   "".join(["🔴"]*len(sell_syms)) +
                   "".join(["🟡"]*len(watch_syms))) or "⚪"

    lines = [
        f"<b>{esc(now)}</b>",
        f"<b>BÁO CÁO CHỨNG KHOÁN</b>  {title_icons}",
        f"Nên mua: {len(buy_syms)}   Nên bán: {len(sell_syms)}   Theo dõi: {len(watch_syms)}",
        "",
    ]

    # VNINDEX trước
    if vnindex_block:
        lines.append(vnindex_block)
    else:
        lines.append("⚠ Không lấy được dữ liệu VNINDEX")

    order    = {"NÊN MUA":0,"NÊN BÁN":1,"THEO DÕI":2,"TRUNG TÍNH":3}
    sorted_r = sorted([r for r in results if not r.get("error")],
                      key=lambda x: order.get(x["verdict"], 4))
    errors   = [r for r in results if r.get("error")]

    for a in sorted_r:
        price_icon = "📈" if a["change"] >= 0 else "🔺"
        fib = a["fib"]

        why_lines = []
        for text, is_positive in a["why"]:
            icon = "✅" if is_positive else "🔻"
            why_lines.append(f"  {icon} {esc(text)}")
        why_txt = "\n".join(why_lines) if why_lines else "  (Không có tín hiệu rõ)"

        vol_lines = "\n".join(a["vol_info"]["lines"])
        beh_lines = "\n".join(f"  {b}" for b in a["vol_info"]["behavior"])

        block = (
            "\n"
            "—————————————————\n"
            "\n"
            f"{a['emoji']} <b>{esc(a['symbol'])}</b>        <b>{esc(a['verdict'])}</b>\n"
            "\n"
            f"  Giá: <b>{a['price']:,.0f}</b>  {price_icon} {a['change']:+,.0f} ({a['change_pct']:+.1f}%)\n"
            f"  RSI: {a['rsi']:.0f}   |   Điểm: {a['score']}/10\n"
            f"  Fib: {fib['0.382']:,.0f} / {fib['0.500']:,.0f} / {fib['0.618']:,.0f}\n"
            "\n"
            "  <b>Phân tích khối lượng:</b>\n"
            f"{vol_lines}\n"
            "\n"
            "  <b>Nhận xét KL:</b>\n"
            f"{beh_lines}\n"
            "\n"
            "  <b>Lý do kỹ thuật:</b>\n"
            f"{why_txt}\n"
            "\n"
            f"  ✅ Chốt lời:  <b>{a['tp']:,.0f}</b>\n"
            f"  🔻 Cắt lỗ:    <b>{a['sl']:,.0f}</b>\n"
            "\n"
            f"  Ngày: <b>{tf_label(a['sig_day'])}</b>   Tuần: <b>{tf_label(a['sig_week'])}</b>   Tháng: <b>{tf_label(a['sig_month'])}</b>\n"
            "\n"
            f"  <b>⟹ {esc(a['conclusion'])}</b>"
        )
        lines.append(block)

    for a in errors:
        lines.append(f"\n—————————————————\n❌ {esc(a['symbol'])} — Không lấy được dữ liệu")

    # 5 dòng trống cuối để phân tách báo cáo hôm nay với hôm qua
    lines.append("\n\n\n\n\n— — — — — — — — — — — —\n\n\n\n\n")

    return "\n".join(lines)

# ── Gửi Telegram ───────────────────────────────────────────────────────────────
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

# ── Chạy quét ──────────────────────────────────────────────────────────────────
def run_scan():
    now = datetime.now().strftime("%d/%m/%Y  %H:%M")
    print(f"\nQuet {len(WATCHLIST)} ma luc {now}\n")

    print("  -> VNINDEX...", end=" ", flush=True)
    vnindex_block = analyze_vnindex()
    print("OK" if vnindex_block else "LOI")

    results = []
    for sym in WATCHLIST:
        sym = sym.strip().upper()
        print(f"  -> {sym}...", end=" ", flush=True)
        a = analyze(sym)
        results.append(a)
        print(a.get("verdict", "LOI"))
        time.sleep(0.8)

    send_telegram(format_all(results, now, vnindex_block))
    print(f"\nDa gui Telegram.")

if __name__ == "__main__":
    run_scan()
