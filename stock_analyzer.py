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

def volume_analysis(df):
    """So sánh khối lượng hiện tại với TB 5, 20, 60 phiên và nhận định dòng tiền."""
    vol_5  = df["volume"].tail(5).mean()
    vol_20 = df["volume"].tail(20).mean()
    vol_60 = df["volume"].tail(60).mean() if len(df) >= 60 else df["volume"].mean()
    last   = df.iloc[-1]
    prev   = df.iloc[-2]
    vol    = last["volume"]
    change = last["close"] - prev["close"]

    r5  = vol / vol_5  if vol_5  > 0 else 1
    r20 = vol / vol_20 if vol_20 > 0 else 1
    r60 = vol / vol_60 if vol_60 > 0 else 1

    # Nhận định dòng tiền
    if r20 > 1.5 and change > 0:
        flow = "GOM HANG"
    elif r20 > 1.5 and change < 0:
        flow = "XA HANG"
    elif r20 < 0.6:
        flow = "CHO DOI"
    elif r20 > 1.0 and change > 0:
        flow = "MUA VAO"
    elif r20 > 1.0 and change < 0:
        flow = "BAN RA"
    else:
        flow = "BINH THUONG"

    return {
        "vol":   vol,
        "vol_5": vol_5, "vol_20": vol_20, "vol_60": vol_60,
        "r5":  r5,  "r20": r20,  "r60":  r60,
        "flow": flow,
    }

def flow_label(flow):
    m = {
        "GOM HANG":    "🟢 Đang gom hàng",
        "XA HANG":     "🔴 Đang xả hàng",
        "MUA VAO":     "🟢 Mua vào",
        "BAN RA":      "🔴 Bán ra",
        "CHO DOI":     "⚪ Chờ đợi (KL thấp)",
        "BINH THUONG": "⚪ Bình thường",
    }
    return m.get(flow, "⚪ Bình thường")

def fmt_vol(v):
    """Định dạng khối lượng: triệu hoặc nghìn cho dễ đọc."""
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}tr"
    elif v >= 1_000:
        return f"{v/1_000:.0f}k"
    return str(int(v))

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

    vol_info = volume_analysis(df)

    return {
        "symbol": symbol, "error": False,
        "price": price, "change": change, "change_pct": change_pct,
        "volume": volume, "vol_ratio": vol_ratio, "rsi": rsi,
        "trend": trend, "candle": candle,
        "verdict": verdict, "emoji": emoji, "score": score, "why": why,
        "buy_pts": buy_pts, "sell_pts": sell_pts,
        "sl": sl, "tp": tp, "fib": fib,
        "vol_info": vol_info,
        "sig_day":   timeframe_signal(df, 5),
        "sig_week":  timeframe_signal(df, 25),
        "sig_month": timeframe_signal(df, 60),
    }

def format_vnindex_block(vn):
    """Tạo block VNIndex đầu tin nhắn."""
    if vn.get("error"):
        return "━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>VNINDEX</b> — Không lấy được dữ liệu\n"

    chg_arrow = "▲" if vn["change"] >= 0 else "▼"
    trend_vn  = {"uptrend": "Tăng ✅", "downtrend": "Giảm 🔻", "sideways": "Đi ngang ⚪"}.get(vn["trend"], "—")
    macd_txt  = "Tích cực ✅" if vn.get("macd_bull") else "Tiêu cực 🔻"
    vi        = vn["vol_info"]

    # Nhận định tổng thị trường
    if vn["verdict"] in ("NEN MUA",):
        market_mood = "🟢 Thị trường TÍCH CỰC — dòng tiền vào tốt"
    elif vn["verdict"] in ("NEN BAN",):
        market_mood = "🔴 Thị trường TIÊU CỰC — cần thận trọng"
    elif vn["verdict"] == "THEO DOI":
        market_mood = "🟡 Thị trường TRUNG TÍNH — theo dõi thêm"
    else:
        market_mood = "⚪ Thị trường SIDEWAY — chờ tín hiệu rõ hơn"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "📊 <b>VNINDEX — THỊ TRƯỜNG TỔNG QUAN</b>",
        "",
        f"  Chỉ số:  <b>{vn['price']:,.2f}</b>   {chg_arrow} {vn['change']:+.2f} ({vn['change_pct']:+.2f}%)",
        f"  Xu hướng: {trend_vn}   |   RSI: {vn['rsi']:.0f}",
        f"  MACD: {macd_txt}   |   Nến: {esc(vn['candle'])}",
        "",
        "  📦 <b>Phân tích khối lượng thị trường:</b>",
        f"  • Hôm nay:          <b>{fmt_vol(vi['vol'])}</b>",
        f"  • TB 5 phiên (tuần): {fmt_vol(vi['vol_5'])}   →  {vi['r5']:.1f}x",
        f"  • TB 20 phiên (tháng): {fmt_vol(vi['vol_20'])}   →  {vi['r20']:.1f}x",
        f"  • TB 60 phiên (quý): {fmt_vol(vi['vol_60'])}   →  {vi['r60']:.1f}x",
        f"  → {flow_label(vi['flow'])}",
        "",
        f"  📅 Tín hiệu đa khung:",
        f"  Ngày: {tf_label(vn['sig_day'])}   Tuần: {tf_label(vn['sig_week'])}   Tháng: {tf_label(vn['sig_month'])}",
        "",
        f"  {market_mood}",
    ]
    return "\n".join(lines)


def format_symbol_block(a):
    """Tạo block phân tích cho từng mã."""
    chg_arrow = "▲" if a["change"] >= 0 else "▼"
    fib = a["fib"]
    vi  = a["vol_info"]

    why_lines = []
    for text, is_positive in a["why"]:
        icon = "✅" if is_positive else "🔻"
        why_lines.append(f"  {icon} {esc(text)}")
    why_txt = "\n".join(why_lines) if why_lines else "  (Không có tín hiệu rõ)"

    # So sánh KL và kết luận
    kl_lines = [
        "  📦 <b>Phân tích khối lượng:</b>",
        f"  • Hôm nay:           <b>{fmt_vol(vi['vol'])}</b>",
        f"  • TB 5 phiên (tuần):  {fmt_vol(vi['vol_5'])}   →  {vi['r5']:.1f}x",
        f"  • TB 20 phiên (tháng): {fmt_vol(vi['vol_20'])}   →  {vi['r20']:.1f}x",
        f"  • TB 60 phiên (quý):  {fmt_vol(vi['vol_60'])}   →  {vi['r60']:.1f}x",
        f"  → {flow_label(vi['flow'])}",
    ]

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"{a['emoji']} <b>{esc(a['symbol'])}</b>        <b>{esc(a['verdict'])}</b>",
        "",
        f"  Giá:  <b>{a['price']:,.0f}</b>   {chg_arrow} {a['change']:+,.0f} ({a['change_pct']:+.1f}%)",
        f"  RSI:  {a['rsi']:.0f}   |   Điểm: {a['score']}/10   |   Nến: {esc(a['candle'])}",
        f"  Fib:  {fib['0.382']:,.0f}  /  {fib['0.500']:,.0f}  /  {fib['0.618']:,.0f}",
        "",
        why_txt,
        "",
    ] + kl_lines + [
        "",
        f"  ✅ Chốt lời:  <b>{a['tp']:,.0f}</b>",
        f"  🔻 Cắt lỗ:    <b>{a['sl']:,.0f}</b>",
        "",
        f"  📅 Ngày: {tf_label(a['sig_day'])}   Tuần: {tf_label(a['sig_week'])}   Tháng: {tf_label(a['sig_month'])}",
    ]
    return "\n".join(lines)


def format_summary_table(sorted_r):
    """Bảng tổng hợp tất cả mã + hành động đề xuất."""
    if not sorted_r:
        return ""

    rows = []
    for a in sorted_r:
        vi      = a["vol_info"]
        action  = {"NEN MUA": "🟢 Mua", "NEN BAN": "🔴 Bán",
                   "THEO DOI": "🟡 Theo dõi", "TRUNG TINH": "⚪ Chờ"}.get(a["verdict"], "⚪")
        flow_s  = {"GOM HANG": "🟢 Gom", "XA HANG": "🔴 Xả",
                   "MUA VAO": "🟢 Mua", "BAN RA": "🔴 Bán",
                   "CHO DOI": "⚪ Chờ", "BINH THUONG": "⚪ BT"}.get(vi["flow"], "⚪")
        rows.append(f"  {esc(a['symbol']):<6}  {action:<14}  {vi['r20']:.1f}x   {flow_s}")

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "📋 <b>BẢNG TỔNG HỢP</b>",
        "",
        "  Mã      Lệnh            KL/TB20  Dòng tiền",
        "  ──────────────────────────────────────────",
    ] + rows
    return "\n".join(lines)


def format_conclusion(vn, sorted_r):
    """Kết luận tổng cuối bài."""
    buy_list   = [r["symbol"] for r in sorted_r if r["verdict"] == "NEN MUA"]
    sell_list  = [r["symbol"] for r in sorted_r if r["verdict"] == "NEN BAN"]
    watch_list = [r["symbol"] for r in sorted_r if r["verdict"] == "THEO DOI"]

    # Nhận định VNIndex
    if not vn.get("error"):
        if vn["verdict"] == "NEN MUA":
            vn_conclude = "VNIndex đang trong xu hướng <b>TĂNG</b>, dòng tiền vào tốt → Ưu tiên MỞ VỊ THẾ MỚI."
        elif vn["verdict"] == "NEN BAN":
            vn_conclude = "VNIndex đang <b>YẾU</b>, nguy cơ điều chỉnh → Giảm tỷ trọng, ưu tiên bảo toàn vốn."
        elif vn["verdict"] == "THEO DOI":
            vn_conclude = "VNIndex đang <b>TRUNG TÍNH</b> → Chờ tín hiệu rõ hơn, không nên đặt cược lớn."
        else:
            vn_conclude = "VNIndex đang <b>SIDEWAY</b> → Giao dịch chọn lọc, ưu tiên cổ phiếu mạnh hơn index."
    else:
        vn_conclude = "Không lấy được dữ liệu VNIndex hôm nay."

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "🔮 <b>KẾT LUẬN TỔNG — NÊN LÀM GÌ?</b>",
        "",
        f"  {vn_conclude}",
        "",
    ]

    if buy_list:
        lines.append(f"  🟢 <b>Nên mua:</b>  {', '.join(buy_list)}")
    if sell_list:
        lines.append(f"  🔴 <b>Nên bán/thoát:</b>  {', '.join(sell_list)}")
    if watch_list:
        lines.append(f"  🟡 <b>Theo dõi thêm:</b>  {', '.join(watch_list)}")
    if not buy_list and not sell_list:
        lines.append("  ⚪ Không có tín hiệu rõ hôm nay → Nghỉ ngơi, chờ phiên sau.")

    return "\n".join(lines)


def format_all(results, now, vnindex_result=None):
    buy_syms   = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "NEN MUA"]
    sell_syms  = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "NEN BAN"]
    watch_syms = [r["symbol"] for r in results if not r.get("error") and r["verdict"] == "THEO DOI"]

    title_icons = ("".join(["🟢"]*len(buy_syms)) +
                   "".join(["🔴"]*len(sell_syms)) +
                   "".join(["🟡"]*len(watch_syms))) or "⚪"

    order    = {"NEN MUA":0,"NEN BAN":1,"THEO DOI":2,"TRUNG TINH":3}
    sorted_r = sorted([r for r in results if not r.get("error")],
                      key=lambda x: order.get(x["verdict"], 4))
    errors   = [r for r in results if r.get("error")]

    lines = [
        f"<b>{esc(now)}</b>",
        f"<b>BÁO CÁO CHỨNG KHOÁN</b>  {title_icons}",
        f"Nên mua: {len(buy_syms)}   Nên bán: {len(sell_syms)}   Theo dõi: {len(watch_syms)}",
    ]

    # --- Block VNIndex đầu tiên ---
    if vnindex_result:
        lines.append(format_vnindex_block(vnindex_result))

    # --- Từng mã ---
    for a in sorted_r:
        lines.append(format_symbol_block(a))

    # --- Lỗi ---
    for a in errors:
        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━━\n❌ {esc(a['symbol'])} — Không lấy được dữ liệu")

    # --- Bảng tổng hợp ---
    lines.append(format_summary_table(sorted_r))

    # --- Kết luận tổng ---
    vn = vnindex_result or {"error": True}
    lines.append(format_conclusion(vn, sorted_r))

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

def fetch_vnindex_tcbs(days=200):
    """Lấy dữ liệu VNINDEX từ TCBS API (miễn phí, không cần key)."""
    to_ts   = int(datetime.now().timestamp())
    from_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    url = (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
           f"?ticker=VNINDEX&type=index&resolution=D&from={from_ts}&to={to_ts}")
    try:
        r    = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = r.json().get("data", [])
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        # TCBS trả về: tradingDate, open, high, low, close, volume
        df = df.rename(columns={"tradingDate": "date"})
        df["date"] = pd.to_datetime(df["date"], unit="s", errors="coerce")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[["date", "open", "high", "low", "close", "volume"]].dropna().reset_index(drop=True)
        return df
    except Exception as e:
        print(f"  TCBS lỗi VNINDEX: {e}")
        return pd.DataFrame()


def fetch_vnindex_ssi(days=200):
    """Lấy dữ liệu VNINDEX từ SSI API (fallback, miễn phí, không cần key)."""
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = (f"https://iboard-query.ssi.com.vn/v2/stock/indices-historical-price"
           f"?indexId=VNINDEX&fromDate={start_date}&toDate={end_date}&limit=300&offset=0")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://iboard.ssi.com.vn/",
            "Origin": "https://iboard.ssi.com.vn",
        }
        r    = requests.get(url, headers=headers, timeout=15)
        rows = r.json().get("data", {}).get("items", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            "tradingDate": "date", "openIndex": "open",
            "highIndex": "high", "lowIndex": "low",
            "closeIndex": "close", "totalQtty": "volume"
        })
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[["date", "open", "high", "low", "close", "volume"]].dropna()
        df = df.sort_values("date").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"  SSI lỗi VNINDEX: {e}")
        return pd.DataFrame()


def analyze_vnindex():
    """Lấy và phân tích VNINDEX — thử TCBS trước, fallback sang SSI."""
    print("    Thử TCBS...", end=" ", flush=True)
    df = fetch_vnindex_tcbs()
    if df.empty:
        print("thất bại. Thử SSI...", end=" ", flush=True)
        df = fetch_vnindex_ssi()
    if df.empty:
        print("thất bại.")
        return {"symbol": "VNINDEX", "error": True}
    print(f"OK ({len(df)} phiên)")

    if len(df) < 30:
        return {"symbol": "VNINDEX", "error": True}

    df = add_indicators(df)
    last     = df.iloc[-1]
    prev     = df.iloc[-2]
    price    = last["close"]
    change   = price - prev["close"]
    change_pct = change / prev["close"] * 100
    rsi      = last["rsi"]
    macd_bull = last["macd"] > last["macd_signal"]
    trend    = analyze_trend(df)
    candle   = detect_candle(df)
    vi       = volume_analysis(df)

    # Chấm điểm đơn giản cho VNIndex
    buy_pts = 0
    if trend == "uptrend":  buy_pts += 2
    if macd_bull:            buy_pts += 1
    if 35 < rsi < 65:        buy_pts += 1
    if vi["flow"] in ("GOM HANG", "MUA VAO"): buy_pts += 1
    sell_pts = 0
    if trend == "downtrend": sell_pts += 2
    if not macd_bull:         sell_pts += 1
    if rsi > 72:              sell_pts += 2
    if vi["flow"] in ("XA HANG", "BAN RA"):   sell_pts += 1

    if buy_pts >= 3 and buy_pts > sell_pts:
        verdict = "NEN MUA"
    elif sell_pts >= 3 and sell_pts > buy_pts:
        verdict = "NEN BAN"
    elif buy_pts >= 2:
        verdict = "THEO DOI"
    else:
        verdict = "TRUNG TINH"

    return {
        "symbol": "VNINDEX", "error": False,
        "price": price, "change": change, "change_pct": change_pct,
        "rsi": rsi, "macd_bull": macd_bull, "trend": trend, "candle": candle,
        "verdict": verdict, "vol_info": vi,
        "sig_day":   timeframe_signal(df, 5),
        "sig_week":  timeframe_signal(df, 25),
        "sig_month": timeframe_signal(df, 60),
    }


def run_scan():
    now = datetime.now().strftime("%d/%m/%Y  %H:%M")
    print(f"\nQuét {len(WATCHLIST)} mã lúc {now}\n")

    print("  -> VNINDEX...", end=" ", flush=True)
    vn = analyze_vnindex()
    print("OK" if not vn.get("error") else "LỖI")
    time.sleep(0.8)

    results = []
    for sym in WATCHLIST:
        sym = sym.strip().upper()
        print(f"  -> {sym}...", end=" ", flush=True)
        a = analyze(sym)
        results.append(a)
        print(a.get("verdict", "LỖI"))
        time.sleep(0.8)

    send_telegram(format_all(results, now, vnindex_result=vn))
    print(f"\nĐã gửi Telegram.")

if __name__ == "__main__":
    run_scan()
