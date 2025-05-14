import asyncio
import ccxt.async_support as ccxt
from fastapi import FastAPI, HTTPException
from model.predictor import SignalPredictor
from core.analysis import analyze_symbol_multi_timeframe
import pandas as pd
from utils.logger import logger
import uvicorn
import os

app = FastAPI()

predictor = SignalPredictor()
binance = None
SYMBOLS = []
TIMEFRAMES = ['15m', '1h', '4h', '1d']
MIN_VOL = 1000000
CONFIDENCE_THRESHOLD = 80.0
COOLDOWN_PERIOD = 4 * 3600

async def initialize_binance():
    global binance
    try:
        binance = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
        })
        await binance.load_markets()
        logger.info("Binance API connection successful")
    except Exception as e:
        logger.error(f"Error initializing Binance: {str(e)}")
        raise

async def fetch_symbols():
    global SYMBOLS
    try:
        markets = await binance.load_markets()
        SYMBOLS = []
        for symbol, market in markets.items():
            quote = market.get('quote', 'N/A')
            active = market.get('active', False)
            quote_volume = float(market.get('info', {}).get('quoteVolume', 0))
            logger.info(f"[{symbol}] Quote: {quote}, Active: {active}, QuoteVolume: {quote_volume}")
            if symbol.endswith('/USDT') and active and quote_volume >= MIN_VOL:
                SYMBOLS.append(symbol)
        logger.info(f"Selected {len(SYMBOLS)} USDT pairs with volume >= ${MIN_VOL}")
    except Exception as e:
        logger.error(f"Error fetching symbols: {str(e)}")
        raise

async def run_bot():
    while True:
        try:
            if not SYMBOLS:
                logger.warning("No symbols selected, skipping bot loop")
                await asyncio.sleep(60)
                continue
            for symbol in SYMBOLS[:150]:
                logger.info(f"[{symbol}] Checking for cooldown")
                result = await analyze_symbol_multi_timeframe(binance, symbol, TIMEFRAMES, predictor)
                if result and result.get('signals'):
                    signal = result['signals'][0]
                    logger.info(f"✅ Signal SENT ✅")
                else:
                    logger.info(f"⚠️ {symbol} - No valid signals")
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in bot loop: {str(e)}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting bot...")
    await initialize_binance()
    await fetch_symbols()
    asyncio.create_task(run_bot())

@app.on_event("shutdown")
async def shutdown_event():
    global binance
    try:
        if binance:
            await binance.close()
            logger.info("Binance connection closed")
    except Exception as e:
        logger.error(f"Error closing Binance: {str(e)}")

@app.get("/health")
async def health_check():
    try:
        if binance is None:
            logger.error("Health check failed: Binance not initialized")
            raise HTTPException(status_code=500, detail="Binance not initialized")
        await binance.fetch_ticker('BTC/USDT')
        logger.info("Health check passed")
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
