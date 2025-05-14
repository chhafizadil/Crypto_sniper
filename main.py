import asyncio
import logging
import pandas as pd
import ccxt.async_support as ccxt
from fastapi import FastAPI
from typing import List, Dict
from core.analysis import analyze_symbol_multi_timeframe
from model.predictor import SignalPredictor
from telebot.sender import send_telegram_signal
from datetime import datetime, timedelta
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("crypto-signal-bot")

app = FastAPI()

EXCHANGE = ccxt.binance()
SYMBOL_LIMIT = 300
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
MIN_VOLUME = 1000000
CONFIDENCE_THRESHOLD = 70.0  # Lowered to allow 70% confidence signals
COOLDOWN_PERIOD = 21600  # 6 hours

predictor = SignalPredictor()
log.info("Signal Predictor initialized successfully")

cooldowns = {}
http_client = None

async def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    for attempt in range(3):  # Retry logic for API limits
        try:
            ohlcv = await EXCHANGE.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except ccxt.RateLimitExceeded:
            log.warning(f"[{symbol}] Rate limit exceeded for {timeframe}, retrying in 10s")
            await asyncio.sleep(10)
        except Exception as e:
            log.error(f"[{symbol}] Error fetching OHLCV for {timeframe}: {str(e)}")
            return pd.DataFrame()
    log.error(f"[{symbol}] Failed to fetch OHLCV for {timeframe} after 3 attempts")
    return pd.DataFrame()

async def get_high_volume_symbols() -> List[str]:
    try:
        await EXCHANGE.load_markets()
        tickers = await EXCHANGE.fetch_tickers()
        symbols = [
            symbol for symbol, ticker in tickers.items()
            if symbol.endswith('/USDT') and ticker.get('quoteVolume', 0) >= MIN_VOLUME
        ]
        log.info(f"Selected {len(symbols)} USDT pairs with volume >= ${MIN_VOLUME}")
        return symbols[:SYMBOL_LIMIT]
    except Exception as e:
        log.error(f"Error fetching symbols: {str(e)}")
        return []

async def save_signal_to_csv(signal: Dict):
    try:
        df = pd.DataFrame([signal])
        df.to_csv('logs/signals_log_new.csv', mode='a', index=False, header=not pd.io.common.file_exists('logs/signals_log_new.csv'))
        log.info("Signal logged to logs/signals_log_new.csv")
    except Exception as e:
        log.error(f"Error saving signal to CSV: {str(e)}")

async def process_symbol(symbol: str):
    log.info(f"[{symbol}] Checking for cooldown")
    
    if symbol in cooldowns:
        cooldown_end = cooldowns[symbol] + timedelta(seconds=COOLDOWN_PERIOD)
        if datetime.utcnow() < cooldown_end:
            log.info(f"[{symbol}] In cooldown until {cooldown_end} across all timeframes")
            return
    
    log.info(f"[{symbol}] Starting multi-timeframe analysis")
    
    timeframe_data = {}
    for timeframe in TIMEFRAMES:
        df = await fetch_ohlcv(symbol, timeframe)
        if not df.empty:
            timeframe_data[timeframe] = df
        else:
            log.warning(f"[{symbol}] No OHLCV data for {timeframe}")
    
    if not timeframe_data:
        log.warning(f"[{symbol}] No data available for any timeframe")
        return
    
    result = await analyze_symbol_multi_timeframe(EXCHANGE, symbol, TIMEFRAMES, predictor)
    
    if result and 'signals' in result and result['signals']:
        best_signal = max(result['signals'], key=lambda x: x['confidence'], default=None)
        if best_signal and best_signal['confidence'] >= CONFIDENCE_THRESHOLD:
            cooldowns[symbol] = datetime.utcnow()
            log.info(f"[{symbol}] Added to cooldown for {COOLDOWN_PERIOD/3600} hours across all timeframes")
            
            best_signal['trade_type'] = "Normal" if best_signal['confidence'] >= 80 else "Scalping"
            best_signal['timestamp'] = pd.Timestamp.now()
            
            await send_telegram_signal(symbol, best_signal)
            log.info(f"[{best_signal['symbol']}] Telegram signal sent successfully")
            await save_signal_to_csv(best_signal)
            log.info(f"✅ Signal SENT ✅")
        else:
            log.info(f"⚠️ {symbol} - No signal with sufficient confidence")
    else:
        log.info(f"⚠️ {symbol} - No valid signals")

async def scan_symbols():
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient()
    log.info(f"Scanning {SYMBOL_LIMIT} symbols across {TIMEFRAMES}")
    symbols = await get_high_volume_symbols()
    
    for symbol in symbols:
        try:
            await process_symbol(symbol)
            await asyncio.sleep(30)  # Increased to 30s to avoid API limits
        except Exception as e:
            log.error(f"Error processing {symbol}: {str(e)}")
    await asyncio.sleep(1800)  # Increased to 30 minutes

@app.on_event("startup")
async def startup_event():
    log.info("Starting bot...")
    try:
        await EXCHANGE.load_markets()
        log.info("Binance API connection successful")
        while True:
            try:
                await scan_symbols()
                log.info("Scan complete, waiting for next cycle...")
                await asyncio.sleep(1800)  # Increased to 30 minutes
            except Exception as e:
                log.error(f"Error in scan cycle: {str(e)}")
                await asyncio.sleep(1800)
    except Exception as e:
        log.error(f"Error in startup: {str(e)}")
        await asyncio.sleep(1800)

@app.on_event("shutdown")
async def shutdown_event():
    log.info("Shutting down")
    try:
        await EXCHANGE.close()
        log.info("Binance connection closed successfully")
        if http_client:
            await http_client.aclose()
            log.info("HTTPX client closed successfully")
    except Exception as e:
        log.error(f"Error closing resources: {str(e)}")

@app.get("/health")
async def health_check():
    try:
        if EXCHANGE is None or not hasattr(EXCHANGE, 'markets'):
            log.error("Health check failed: Exchange not initialized or markets not loaded")
            return {"status": "unhealthy", "error": "Exchange not initialized or markets not loaded"}, 500
        log.info("Health check passed")
        return {"status": "healthy", "timestamp": str(datetime.utcnow())}
    except Exception as e:
        log.error(f"Health check failed: {str(e)}")
        return {"status": "unhealthy", "error": str(e)}, 500

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
