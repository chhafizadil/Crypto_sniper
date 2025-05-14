import schedule
import time
from datetime import datetime
from telebot.report_generator import generate_daily_summary
from utils.logger import logger

def run_scheduler():
    logger.info("📅 Report scheduler started...")
    schedule.every().day.at("23:59").do(lambda: asyncio.run(generate_daily_summary()))
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    run_scheduler()
