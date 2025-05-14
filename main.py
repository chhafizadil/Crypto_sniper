import asyncio
import ccxt.async_support as ccxt
from fastapi import FastAPI, HTTPException
from model.predictor import SignalPredictor
from core.analysis import analyze_symbol_multi_timeframe
import pandas as pd
from utils.logger import logger
import uvicorn
import os
from datetime import datetime, timedelta

app = FastAPI()

EXCHANGE = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_API_SECRET'),
    'enableRateLimit': True,
})
SYMBOL_LIMIT = 150
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
MIN_VOLUME = 1000000
CONFIDENCE_THRESHOLD = 80.0
COOLDOWN_PERIOD = 6 * 3600  # 6 hours in seconds
predictor = SignalPredictor()
SYMBOLS = []
last_signal_time = {}

async def initialize_binance():
    try:
        await asyncio.sleep(2)
        await EXCHANGE.load_markets()
        logger.info("Binance API connection successful")
    except Exception as e:
        logger.error(f"Error initializing Binance: {str(e)}")
        raise

async def fetch_symbols():
    global SYMBOLS
    try:
        await asyncio.sleep(2)
        markets = await EXCHANGE.load_markets()
        SYMBOLS = []
        for symbol, market in markets.items():
            quote = market.get('quote', 'N/A')
            active = market.get('active', False)
            info = market.get('info', {})
            logger.info(f"[{symbol}] Quote: {quote}, Active: {active}, Full Info: {info}")
            if symbol.endswith('/USDT') and active:
                SYMBOLS.append(symbol)
        logger.info(f"Selected {len(SYMBOLS)} USDT pairs (volume check disabled temporarily)")
    except Exception as e:
        logger.error(f"Error fetching symbols: {str(e)}")
        raise

async def run_bot():
    while True:
        try:
            if not SYMBOLS:
                logger.warning("No symbols selected, skipping bot loop")
                await asyncio.sleep(600)
                continue
            for symbol in SYMBOLS[:SYMBOL_LIMIT]:
                current_time = datetime.utcnow()
                last_time = last_signal_time.get(symbol)
                if last_time and (current_time - last_time).total_seconds() < COOLDOWN_PERIOD:
                    logger.info(f"[{symbol}] On cooldown, skipping")
                    continue
                logger.info(f"[{symbol}] Checking for signal")
                await asyncio.sleep(1)
                result = await analyze_symbol_multi_timeframe(EXCHANGE, symbol, TIMEFRAMES, predictor)
                if result and result.get('signals'):
                    signal = result['signals'][0]
                    if signal.get('confidence', 0) >= CONFIDENCE_THRESHOLD:
                        last_signal_time[symbol] = current_time
                        logger.info(f"✅ Signal SENT ✅: {symbol}, Direction: {signal.get('direction')}, Confidence: {signal.get('confidence')}%")
                    else:
                        logger.info(f"⚠️ {symbol} - Signal confidence too low: {signal.get('confidence')}%")
                else:
                    logger.info(f"⚠️ {symbol} - No valid signals")
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in bot loop: {str(e)}")
            await asyncio.sleep(300)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting bot...")
    await initialize_binance()
    await fetch_symbols()
    asyncio.create_task(run_bot())

@app.on_event("shutdown")
async def shutdown_event():
    try:
        await EXCHANGE.close()
        logger.info("Binance connection closed")
    except Exception as e:
        logger.error(f"Error closing Binance: {str(e)}")

@app.get("/health")
async def health_check():
    try:
        await asyncio.sleep(2)
        await EXCHANGE.fetch_ticker('BTC/USDT')
        logger.info("Health check passed")
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
