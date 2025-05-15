import httpx
import asyncio
import pandas as pd
from utils.logger import logger
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

async def send_telegram_signal(symbol: str, signal: dict):
    try:
        if not BOT_TOKEN or not CHAT_ID:
            logger.error(f"[{symbol}] BOT_TOKEN or CHAT_ID not set. BOT_TOKEN: {BOT_TOKEN}, CHAT_ID: {CHAT_ID}")
            return

        entry = signal.get("entry", "0")
        tp1 = signal.get("tp1", "0")
        tp2 = signal.get("tp2", "0")
        tp3 = signal.get("tp3", "0")
        sl = signal.get("sl", "0")
        confidence = signal.get("confidence", 0)
        direction = signal.get("direction", "Unknown")
        timeframe = signal.get("timeframe", "Unknown")
        trade_type = signal.get("trade_type", "Scalping")
        timestamp = signal.get("timestamp", pd.Timestamp.now()).strftime('%Y-%m-%d %H:%M:%S')
        tp1_possibility = signal.get("tp1_possibility", 0.70) * 100
        tp2_possibility = signal.get("tp2_possibility", 0.50) * 100
        tp3_possibility = signal.get("tp3_possibility", 0.35) * 100

        if entry == tp1:
            logger.warning(f"[{symbol}] TP1 ({tp1}) and Entry ({entry}) are the same, check ATR or rounding")

        message = (
            f"🚀 *{symbol} Signal*\n\n"
            f"📊 *Direction*: {direction}\n"
            f"⏰ *Timeframe*: {timeframe}\n"
            f"💰 *Entry Price*: {entry}\n"
            f"🎯 *TP1*: {tp1} ({tp1_possibility:.0f}%)\n"
            f"🎯 *TP2*: {tp2} ({tp2_possibility:.0f}%)\n"
            f"🎯 *TP3*: {tp3} ({tp3_possibility:.0f}%)\n"
            f"🛑 *SL*: {sl}\n"
            f"🔍 *Confidence*: {confidence:.2f}%\n"
            f"⚡ *Trade Type*: {trade_type}\n"
            f"🕒 *Timestamp*: {timestamp}"
        )

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            for attempt in range(5):
                try:
                    payload = {
                        "chat_id": CHAT_ID,
                        "text": message,
                        "parse_mode": "Markdown"
                    }
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        logger.info(f"[{symbol}] Telegram signal sent successfully")
                        return
                    else:
                        logger.error(f"[{symbol}] Failed to send Telegram signal: {response.text}")
                except Exception as e:
                    logger.error(f"[{symbol}] Error sending Telegram signal: {e}")
                await asyncio.sleep(5)
            logger.error(f"[{symbol}] Failed to send Telegram signal after 5 attempts")
    except Exception as e:
        logger.error(f"[{symbol}] Error in send_telegram_signal: {e}")
