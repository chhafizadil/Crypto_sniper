import pandas as pd
from datetime import datetime
from utils import logger
from telebot.sender import send_telegram_signal
import os

async def generate_daily_summary() -> None:
    try:
        log_file = "logs/signals_log_new.csv"
        df = pd.read_csv(log_file)
        if df.empty:
            logger.info("No signals found")
            return
        today = datetime.now().date()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        daily_signals = df[df['timestamp'].dt.date == today]
        if daily_signals.empty:
            logger.info("No signals today")
            return
        summary = {
            "symbol": "Daily Summary",
            "message": f"📊 Daily Summary ({today})\nSignals: {len(daily_signals)}\nSymbols: {', '.join(daily_signals['symbol'].unique())}",
            "timestamp": datetime.now(),
            "trade_type": "Summary"
        }
        await send_telegram_signal("Summary", summary, os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
        logger.info("Daily summary sent")
    except Exception as e:
        logger.error(f"Daily summary error: {str(e)}")
