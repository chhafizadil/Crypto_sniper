import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.analysis import analyze_symbol
from utils.logger import setup_logger
import ccxt.async_support as ccxt
import time
import httpx

app = FastAPI()
logger = setup_logger()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

exchange = ccxt.binance({
    'enableRateLimit': True,
    'rateLimit': 1200,
    'options': {'adjustForTimeDifference': True}
})

symbols = []
active_signals = {}
CONFIDENCE_THRESHOLD = 50
MAX_SYMBOLS = 100
API_DELAY = 0.4

@app.on_event("startup")
async def startup_event():
    await load_symbols()
    asyncio.create_task(scan_symbols_loop())
    asyncio.create_task(keep_instance_alive())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Signal scanning loop cancelled gracefully.")
    await exchange.close()

@app.get("/")
async def root():
    return {"message": "Crypto Signal Bot is running."}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/signals")
async def get_signals():
    return active_signals

async def load_symbols():
    try:
        markets = await exchange.load_markets()
        all_symbols = [s for s in markets if s.endswith("/USDT") and markets[s]['active']]
        all_symbols = [s.replace("/", "") for s in all_symbols]
        all_symbols = [s for s in all_symbols if not any(x in s for x in ["UP", "DOWN", "BULL", "BEAR", "1000"])]
        global symbols
        symbols = all_symbols[:MAX_SYMBOLS]
        logger.info(f"Loaded {len(symbols)} valid USDT symbols.")
    except Exception as e:
        logger.error(f"Failed to load symbols: {e}")
        symbols.clear()

async def scan_symbols_loop():
    while True:
        try:
            tasks = [analyze_and_store(symbol) for symbol in symbols]
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in scanning loop: {e}")
        await asyncio.sleep(30)

async def analyze_and_store(symbol: str):
    try:
        result = await analyze_symbol(exchange, symbol)
        if result:
            direction = result.get("signal")
            confidence = result.get("confidence", 0)
            if confidence >= CONFIDENCE_THRESHOLD:
                key = f"{symbol}_{direction}"
                opposite = f"{symbol}_{'SHORT' if direction == 'LONG' else 'LONG'}"
                if active_signals.get(opposite):
                    logger.info(f"Skipping {direction} for {symbol}, opposite still active.")
                    return
                active_signals[key] = result
                logger.info(f"New Signal: {result}")
    except Exception as e:
        logger.warning(f"Error analyzing {symbol}: {e}")

async def keep_instance_alive():
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await client.get("http://localhost:8000/health")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
        await asyncio.sleep(240)  # ping every 4 minutes
