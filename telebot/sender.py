import httpx
import asyncio
import pandas as pd
from utils.logger import logger
import os

async def send_telegram_signal(symbol: str, signal: dict, telegram_bot_token: str, telegram_chat_id: str):
    try:
        if not telegram_bot_token or not telegram_chat_id:
            logger.error(f"[{symbol}] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. TELEGRAM_BOT_TOKEN: {telegram_bot_token}, TELEGRAM_CHAT_ID: {telegram_chat_id}")
            return False

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
        tp1_possibility = signal.get("tp1_possibility", 0.80) * 100
        tp2_possibility = signal.get("tp2_possibility", 0.65) * 100
        tp3_possibility = signal.get("tp3_possibility", 0.50) * 100

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

        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            for attempt in range(5):
                try:
                    payload = {
                        "chat_id": telegram_chat_id,
                        "text": message,
                        "parse_mode": "Markdown"
                    }
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        logger.info(f"[{symbol}] Telegram signal sent successfully")
                        # Save to CSV
                        signal_data = {
                            "timestamp": timestamp,
                            "symbol": symbol,
                            "direction": direction,
                            "entry": entry,
                            "tp1": tp1,
                            "tp2": tp2,
                            "tp3": tp3,
                            "sl": sl,
                            "confidence": confidence,
                            "timeframe": timeframe,
                            "trade_type": trade_type
                        }
                        df = pd.DataFrame([signal_data])
                        csv_path = "logs/signals_log_new.csv"
                        try:
                            df.to_csv(csv_path, mode='a', header=not os.path.exists(csv_path), index=False)
                            logger.info(f"[{symbol}] Signal logged to {csv_path}")
                        except Exception as e:
                            logger.error(f"[{symbol}] Error logging signal to CSV: {e}")
                        return True
                    else:
                        logger.error(f"[{symbol}] Failed to send Telegram signal: {response.text}")
                except Exception as e:
                    logger.error(f"[{symbol}] Error sending Telegram signal (attempt {attempt + 1}): {e}")
                await asyncio.sleep(5)
            logger.error(f"[{symbol}] Failed to send Telegram signal after 5 attempts")
            return False
    except Exception as e:
        logger.error(f"[{symbol}] Error in send_telegram_signal: {e}")
        return False
