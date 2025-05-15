import asyncio
import logging
import pandas as pd
import ccxt.async_support as ccxt
from fastapi import FastAPI
from typing import List, Dict
from core.analysis import analyze_symbol_multi_timeframe
from model.predictor import SignalPredictor
from telebot.sender import send_telegram_signal
from telebot.report_generator import generate_daily_summary
from datetime import datetime, timedelta
import schedule
import time
import psutil
from dotenv import load_dotenv
import os

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MIN_VOLUME = int(os.getenv("MIN_VOLUME", 10000000))
SYMBOL_LIMIT = int(os.getenv("SYMBOL_LIMIT", 150))  # Reduced to 10
CONFIDENCE_THRESHOLD = float(os.getenv("MIN_CONFIDENCE", 60.0))

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.FileHandler('logs/bot.log'), logging.StreamHandler()]
)
log = logging.getLogger("crypto-signal-bot")

app = FastAPI()
EXCHANGE = ccxt.binance()
TIMEFRAMES = ["15m", "1h"]
COOLDOWN_PERIOD = 21600
predictor = SignalPredictor()
cooldowns: Dict[str, datetime] = {}

async def fetch_symbols() -> List[str]:
    try:
        await EXCHANGE.load_markets()
        symbols = [s for s in EXCHANGE.symbols if s.endswith("/USDT")]
        valid_symbols = []
        for symbol in symbols[:SYMBOL_LIMIT]:
            ticker = await EXCHANGE.fetch_ticker(symbol)
            if ticker['quoteVolume'] >= MIN_VOLUME:
                valid_symbols.append(symbol)
        log.info(f"Selected {len(valid_symbols)} symbols")
        return valid_symbols
    except Exception as e:
        log.error(f"Error fetching symbols: {e}")
        return []

async def process_symbol(symbol: str):
    try:
        if symbol in cooldowns and cooldowns[symbol] > datetime.now():
            return
        result = await analyze_symbol_multi_timeframe(EXCHANGE, symbol, TIMEFRAMES, predictor)
        if result and result.get("signals"):
            signal = result["signals"][0]
            if signal["confidence"] >= CONFIDENCE_THRESHOLD:
                signal["timestamp"] = datetime.now()
                signal["trade_type"] = "Scalping"
                cooldowns[symbol] = datetime.now() + timedelta(seconds=COOLDOWN_PERIOD)
                await send_telegram_signal(symbol, signal, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    except Exception as e:
        log.error(f"[{symbol}] Error: {e}")

async def run_scanner():
    try:
        await EXCHANGE.load_markets()
        async def daily_report():
            try:
                await generate_daily_summary()
            except Exception as e:
                log.error(f"Daily report error: {e}")
        schedule.every().day.at("23:59").do(lambda: asyncio.create_task(daily_report()))
        while True:
            symbols = await fetch_symbols()
            for symbol in symbols:
                await process_symbol(symbol)
                await asyncio.sleep(600)  # Increased delay
            await asyncio.sleep(1800)  # Increased loop delay
    except Exception as e:
        log.error(f"Scanner error: {e}")
        await asyncio.sleep(1800)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_scanner())

@app.get("/health")
async def health_check():
    memory = psutil.virtual_memory()
    if memory.percent > 85:
        return {"status": "unhealthy", "memory_usage": memory.percent}
    return {"status": "healthy"}
