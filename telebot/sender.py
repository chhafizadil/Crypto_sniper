import asyncio
from python_telegram_bot import Bot
from utils.logger import logger
import os

async def send_telegram_signal(symbol: str, signal: dict, token: str, chat_id: str) -> None:
    try:
        bot = Bot(token=token)
        # Use the 'message' field if provided (e.g., for summaries), else build signal message
        if "message" in signal:
            message = signal["message"]
        else:
            message = (
                f"[{symbol}] {signal['direction']} Signal\n"
                f"Entry: {signal['entry']}\n"
                f"TP1: {signal['tp1']}\n"
                f"TP2: {signal['tp2']}\n"
                f"TP3: {signal['tp3']}\n"
                f"SL: {signal['sl']}\n"
                f"Confidence: {signal['confidence']}%\n"
                f"Timeframe: {signal['timeframe']}"
            )
        await bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Signal sent for {symbol}")
    except Exception as e:
        logger.error(f"Error sending signal for {symbol}: {str(e)}")
