import httpx
import asyncio
import pandas as pd
from utils.logger import log
from utils.helpers import round_price

BOT_TOKEN = "7620836100:AAEEe4yAP18Lxxj0HoYfH8aeX4PetAxYsV0"
CHAT_ID = "-4694205383"

async def send_telegram_signal(symbol: str, signal: dict):
    try:
        # Format signal using round_price from utils/helpers.py
        entry = round_price(signal.get("entry", 0))
        tp1 = round_price(signal.get("tp1", 0))
        tp2 = round_price(signal.get("tp2", 0))
        tp3 = round_price(signal.get("tp3", 0))
        sl = round_price(signal.get("sl", 0))
        confidence = signal.get("confidence", 0)
        direction = signal.get("direction", "Unknown")
        timeframe = signal.get("timeframe", "Unknown")
        trade_type = signal.get("trade_type", "Scalping")
        timestamp = signal.get("timestamp", pd.Timestamp.now()).strftime('%Y-%m-%d %H:%M:%S')

        # Check if TP1 and entry are the same
        if entry == tp1:
            log.warning(f"[{symbol}] TP1 ({tp1}) and Entry ({entry}) are the same, check ATR or rounding")

        message = (
            f"🚀 *{symbol} Signal*\n\n"
            f"📊 *Direction*: {direction}\n"
            f"⏰ *Timeframe*: {timeframe}\n"
            f"💰 *Entry Price*: {entry}\n"
            f"🎯 *TP1*: {tp1}\n"
            f"🎯 *TP2*: {tp2}\n"
            f"🎯 *TP3*: {tp3}\n"
            f"🛑 *SL*: {sl}\n"
            f"🔍 *Confidence*: {confidence:.2f}%\n"
            f"⚡ *Trade Type*: {trade_type}\n"
            f"🕒 *Timestamp*: {timestamp}"
        )

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            for attempt in range(3):
                try:
                    payload = {
                        "chat_id": CHAT_ID,
                        "text": message,
                        "parse_mode": "Markdown"
                    }
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        log.info(f"Telegram signal sent for {symbol}")
                        return
                    else:
                        log.error(f"Failed to send Telegram signal: {response.text}")
                except Exception as e:
                    log.error(f"Error sending Telegram signal: {e}")
                await asyncio.sleep(2)
    except Exception as e:
        log.error(f"Error in send_telegram_signal: {e}")
