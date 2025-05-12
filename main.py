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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("crypto-signal-bot")

# FastAPI app
app = FastAPI()

# Configuration
EXCHANGE = ccxt.binance()
SYMBOL_LIMIT = 150
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
MIN_VOLUME = 1000000  # Minimum 24h volume in USD
CONFIDENCE_THRESHOLD = 60.0  # For combined signal
COOLDOWN_PERIOD = 4 * 3600  # 4 hours in seconds

# Initialize predictor
predictor = SignalPredictor()
log.info("Signal Predictor initialized successfully")

# Cooldown tracking
cooldowns = {}  # {symbol: timestamp}

async def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 50) -> pd.DataFrame:
    try:
        ohlcv = await EXCHANGE.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        log.error(f"[{symbol}] Error fetching OHLCV for {timeframe}: {str(e)}")
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
    
    # Check if symbol is in cooldown
    if symbol in cooldowns:
        cooldown_end = cooldowns[symbol] + timedelta(seconds=COOLDOWN_PERIOD)
        if datetime.utcnow() < cooldown_end:
            log.info(f"[{symbol}] In cooldown until {cooldown_end}")
            return
    
    log.info(f"[{symbol}] Starting multi-timeframe analysis")
    
    # Fetch data for all timeframes
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
    
    # Analyze across all timeframes
    result = await analyze_symbol_multi_timeframe(EXCHANGE, symbol, TIMEFRAMES, predictor)
    
    if result and 'signals' in result and result['signals']:
        # Select the signal with the highest confidence
        best_signal = max(result['signals'], key=lambda x: x['confidence'], default=None)
        if best_signal and best_signal['confidence'] >= CONFIDENCE_THRESHOLD:
            # Add to cooldown
            cooldowns[symbol] = datetime.utcnow()
            log.info(f"[{symbol}] Added to cooldown for {COOLDOWN_PERIOD/3600} hours")
            
            # Update trade type
            best_signal['trade_type'] = "Normal" if best_signal['confidence'] >= 80 else "Scalping"
            
            # Ensure timestamp is included
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
    log.info(f"Scanning {SYMBOL_LIMIT} symbols across {TIMEFRAMES}")
    symbols = await get_high_volume_symbols()
    
    for symbol in symbols:
        try:
            await process_symbol(symbol)
            await asyncio.sleep(1)  # Increased delay to avoid API rate limits
        except Exception as e:
            log.error(f"Error processing {symbol}: {str(e)}")
    await asyncio.sleep(60)  # Wait before next scan

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
                await asyncio.sleep(60)  # Run every minute
            except Exception as e:
                log.error(f"Error in scan cycle: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    except Exception as e:
        log.error(f"Error in startup: {str(e)}")
        await asyncio.sleep(300)  # Wait 5 minutes before retrying

@app.on_event("shutdown")
async def shutdown_event():
    log.info("Shutting down")
    try:
        await EXCHANGE.close()
        log.info("Binance connection closed successfully")
    except Exception as e:
        log.error(f"Error closing Binance connection: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
