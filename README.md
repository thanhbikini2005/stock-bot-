# 📊 Vietnam Stock Signal Bot

Bot tự động quét cổ phiếu Việt Nam và gửi tín hiệu MUA/BÁN về Telegram theo chiến lược:
**Xu hướng + Hỗ trợ/Kháng cự + Fibonacci + Nến đảo chiều + Phân kỳ Volume**

---

## 🧠 Logic phân tích

### 🟢 Tín hiệu MUA (cần ≥4 điểm)
| Điều kiện | Điểm |
|---|---|
| Xu hướng tăng rõ (HH + HL trên chart) | +2 |
| Giá tại vùng hỗ trợ (±2%) | +2 |
| Nến Hammer / Bullish Engulfing / Morning Star | +2 |
| Fibonacci 38.2% / 50% / 61.8% gần giá | +1 |
| Volume đột biến ≥1.5x trung bình | +1 |
| MACD cắt lên (Golden Cross) | +1 |
| RSI 40–65 (vùng an toàn) | +1 |
| MA20 > MA50 | +1 |

### 🔴 Tín hiệu BÁN (cần ≥4 điểm)
| Điều kiện | Điểm |
|---|---|
| Xu hướng giảm (LH + LL) | +3 |
| Chạm vùng kháng cự (±2%) | +2 |
| Nến Shooting Star / Bearish Engulfing | +2 |
| Phân kỳ giá/volume | +2 |
| RSI > 75 (quá mua) | +1 |
| MACD cắt xuống | +1 |
| Volume cạn dần | +1 |

---

## 🚀 Cài đặt & Chạy

### 1. Clone repo
```bash
git clone https://github.com/YOUR_USERNAME/stock-bot.git
cd stock-bot
```

### 2. Tạo Telegram Bot
1. Mở Telegram → tìm **@BotFather** → `/newbot`
2. Đặt tên → lấy **TOKEN**
3. Nhắn `/start` cho bot của bạn
4. Vào `https://api.telegram.org/bot<TOKEN>/getUpdates` → lấy **chat_id**

### 3. Cấu hình biến môi trường
```bash
cp .env.example .env
# Điền TOKEN và CHAT_ID vào file .env
```

### 4. Cài dependencies & chạy thử
```bash
pip install -r requirements.txt
python stock_analyzer.py
```

### 5. Chạy tự động theo lịch (local)
```bash
python scheduler.py
```

---

## ☁️ Chạy tự động trên GitHub Actions (MIỄN PHÍ)

Đây là cách khuyến nghị — không cần máy chủ, chạy hoàn toàn miễn phí.

### Bước 1: Push code lên GitHub
```bash
git init
git add .
git commit -m "Initial stock bot"
git remote add origin https://github.com/YOUR_USERNAME/stock-bot.git
git push -u origin main
```

### Bước 2: Thêm Secrets vào GitHub
Vào **Settings → Secrets and variables → Actions → New repository secret**:

| Secret Name | Giá trị |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token từ BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID của bạn |

### Bước 3: Thêm Variable (tùy chọn)
Vào **Settings → Secrets and variables → Actions → Variables → New variable**:

| Variable | Giá trị ví dụ |
|---|---|
| `WATCHLIST` | `VNM,HPG,VIC,FPT,MWG,TCB,VCB` |

### Bước 4: Kích hoạt Actions
Vào tab **Actions** → chọn workflow → **Enable workflow**

Bot sẽ tự động chạy vào: **09:15 | 14:30 | 15:05** các ngày **T2–T6**

Để chạy thủ công: Actions → "Stock Bot" → **Run workflow** → nhập danh sách mã tùy ý.

---

## 📱 Ví dụ tin nhắn Telegram

```
🟢 [HPG] TÍN HIỆU MUA  (điểm: 7/10)
━━━━━━━━━━━━━━━━━━━━
💰 Giá hiện tại: 26,500 VNĐ
📊 Xu hướng: 📈 Tăng
🕯 Nến: 🔨 Hammer (Bullish)
📉 RSI: 52.3  |  📦 Vol: 2.1x TB

🔢 Fibonacci (60 phiên):
  High: 28,900  |  Low: 22,100
  38.2%: 26,303  |  50%: 25,500  |  61.8%: 24,697

📋 Lý do:
  ✅ Xu hướng tăng rõ ràng (HH+HL)
  ✅ Giá tại vùng hỗ trợ (26,200)
  ✅ Fibonacci hỗ trợ (26,303–24,697)
  ✅ Nến đảo chiều: 🔨 Hammer (Bullish)
  ✅ Volume đột biến 2.1x
  ✅ MA20 > MA50

🎯 Take Profit: 28,100
🛡 Stop Loss:  25,700
⏰ 10/06/2026 09:15
```

---

## 📁 Cấu trúc file

```
stock-bot/
├── stock_analyzer.py          # Logic chính
├── scheduler.py               # Chạy theo lịch (local)
├── requirements.txt
├── .env.example
├── .github/
│   └── workflows/
│       └── stock_bot.yml      # GitHub Actions
└── README.md
```

---

## ⚠️ Lưu ý

- Dữ liệu lấy từ **TCBS** qua thư viện `vnstock3` (miễn phí, không cần API key)
- Bot chỉ là **công cụ hỗ trợ**, không phải lời khuyên đầu tư
- Luôn áp dụng **cắt lỗ kỷ luật** theo Stop Loss được tính toán
- "Giao dịch theo cái thấy, không theo cái nghĩ" 🧘
