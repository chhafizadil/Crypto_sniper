import pandas as pd
from datetime import datetime
from utils.logger import logger
from telebot.sender import send_telegram_message

def generate_daily_summary() -> None:
    try:
        log_file = "logs/signals_log_new.csv"
        df = pd.read_csv(log_file)
        if df.empty:
            logger.info("No signals found for daily summary")
            return

        today = datetime.now().date()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        daily_signals = df[df['timestamp'].dt.date == today]

        if daily_signals.empty:
            logger.info("No signals for today")
            return

        summary = (
            f"📊 Daily Signal Summary ({today})\n"
            f"Total Signals: {len(daily_signals)}\n"
            f"Symbols: {', '.join(daily_signals['symbol'].unique())}\n"
            f"Successful Signals: {len(daily_signals[daily_signals['status'].isin(['tp1', 'tp2', 'tp3'])])}"
        )

        send_telegram_message(summary)
        logger.info("Daily summary sent to Telegram")
    except Exception as e:
        logger.error(f"Error generating daily summary: {str(e)}")
