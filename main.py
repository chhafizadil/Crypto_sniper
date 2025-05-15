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
import httpx
import schedule
import time
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

# Access variables with new names
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MIN_VOLUME = int(os.getenv("MIN_VOLUME", 1000000))
SYMBOL_LIMIT = int(os.getenv("SYMBOL_LIMIT", 150))  # As requested
FORCE_UPDATE = os.getenv("FORCE_UPDATE", "23")
CONFIDENCE_THRESHOLD = float(os.getenv("MIN_CONFIDENCE", 60.0))  # As requested

# Log TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID status
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error(f"TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. TELEGRAM_BOT_TOKEN: {TELEGRAM_BOT_TOKEN}, TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
else:
    logging.info(f"TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID loaded successfully: TELEGRAM_BOT_TOKEN={TELEGRAM_BOT_TOKEN[:10]}..., TELEGRAM_CHAT_ID={TELEGRAM_CHAT_ID}")

logging.basicConfig(
    level=logging.WARNING,  # Reduced logging for Koyeb memory optimization
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("crypto-signal-bot")

app = FastAPI()

EXCHANGE = ccxt.binance()
SYMBOL_LIMIT=50
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
MIN_VOLUME = 100000
COOLDOWN_PERIOD = 21600  # 6 hours
predictor = SignalPredictor()

# Cooldown tracking
cooldowns: Dict[str, datetime] = {}

async def fetch_symbols() -> List[str]:
    try:
        await EXCHANGE.load_markets()
        symbols = [s for s in EXCHANGE.symbols if s.endswith("/USDT")]
        valid_symbols = []
        for symbol in symbols[:SYMBOL_LIMIT]:
            try:
                ticker = await EXCHANGE.fetch_ticker(symbol)
                if ticker['quoteVolume'] >= MIN_VOLUME:
                    valid_symbols.append(symbol)
            except Exception as e:
                log.error(f"Error fetching ticker for {symbol}: {e}")
        log.info(f"Selected {len(valid_symbols)} USDT pairs with volume >= ${MIN_VOLUME}")
        return valid_symbols
    except Exception as e:
        log.error(f"Error fetching symbols: {e}")
        return []

async def process_symbol(symbol: str):
    try:
        if symbol in cooldowns and cooldowns[symbol] > datetime.now():
            log.info(f"[{symbol}] On cooldown until {cooldowns[symbol]}")
            return

        log.info(f"[{symbol}] Starting multi-timeframe analysis")
        result = await analyze_symbol_multi_timeframe(EXCHANGE, symbol, TIMEFRAMES, predictor)
        if result and result.get("signals"):
            signal = result["signals"][0]
            if signal["confidence"] >= CONFIDENCE_THRESHOLD:
                signal["timestamp"] = datetime.now()
                signal["trade_type"] = "Scalping"
                log.info(f"[{symbol}] Added to cooldown for {COOLDOWN_PERIOD/3600:.1f} hours across all timeframes")
                cooldowns[symbol] = datetime.now() + timedelta(seconds=COOLDOWN_PERIOD)
                await send_telegram_signal(symbol, signal, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)  # Pass new names
            else:
                log.info(f"⚠️ {symbol} - No signal with sufficient confidence")
        else:
            log.info(f"⚠️ {symbol} - No valid signals")
    except Exception as e:
        log.error(f"[{symbol}] Error in processing: {e}")

async def run_scanner():
    log.info(f"Starting bot...")
    try:
        await EXCHANGE.load_markets()
        log.info("Binance API connection successful")
    except Exception as e:
        log.error(f"Failed to connect to Binance API: {e}")
        return

    async def daily_report():
        try:
            await generate_daily_summary()
            log.info("Daily report generated and sent")
        except Exception as e:
            log.error(f"Error generating daily report: {e}")

    schedule.every().day.at("23:59").do(lambda: asyncio.create_task(daily_report()))
    log.info("📅 Report scheduler started...")

    while True:
        try:
            log.info(f"Scanning {SYMBOL_LIMIT} symbols across {TIMEFRAMES}")
            symbols = await fetch_symbols()
            for symbol in symbols:
                await process_symbol(symbol)
                await asyncio.sleep(200)  # Increased delay for Koyeb memory optimization
            await asyncio.sleep(600)  # Increased loop delay
        except Exception as e:
            log.error(f"Error in scanner loop: {e}")
            await asyncio.sleep(600)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_scanner())

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
