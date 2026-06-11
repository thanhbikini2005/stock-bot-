"""
⏰ Scheduler: Tự động chạy quét vào giờ thị trường VN
  - 9:15 (sau mở cửa 15 phút)
  - 14:30 (ATO buổi chiều)
  - 15:05 (sau đóng cửa)
"""

import schedule
import time
from stock_analyzer import run_scan


def job():
    run_scan()


# Chạy 3 lần / ngày vào ngày trong tuần
schedule.every().monday.at("09:15").do(job)
schedule.every().tuesday.at("09:15").do(job)
schedule.every().wednesday.at("09:15").do(job)
schedule.every().thursday.at("09:15").do(job)
schedule.every().friday.at("09:15").do(job)

schedule.every().monday.at("14:30").do(job)
schedule.every().tuesday.at("14:30").do(job)
schedule.every().wednesday.at("14:30").do(job)
schedule.every().thursday.at("14:30").do(job)
schedule.every().friday.at("14:30").do(job)

schedule.every().monday.at("15:05").do(job)
schedule.every().tuesday.at("15:05").do(job)
schedule.every().wednesday.at("15:05").do(job)
schedule.every().thursday.at("15:05").do(job)
schedule.every().friday.at("15:05").do(job)

print("🤖 Scheduler đang chạy... (Ctrl+C để dừng)")
print("Lịch quét: 09:15 | 14:30 | 15:05 các ngày T2–T6")

while True:
    schedule.run_pending()
    time.sleep(30)
