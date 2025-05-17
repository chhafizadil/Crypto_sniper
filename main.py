import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
from fastapi import FastAPI
from datetime import datetime, timedelta
from core.analysis import analyze_symbol_multi_timeframe
from telebot.sender import send_signal, start_bot
from utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ==================== ⚙️ CONFIGURATION ==================== 
MIN_QUOTE_VOLUME = 1000000  # 3 million USD minimum volume
MIN_CONFIDENCE = 70         # 80% minimum confidence
COOLDOWN_HOURS = 6          # 6 hours cooldown between signals

# Memory-based cooldown tracking
cooldowns = {}

# ==================== 📊 DATA HANDLING ==================== 
def save_signal_to_csv(signal):
    try:
        os.makedirs('logs', exist_ok=True)
        file_path = 'logs/signals_log_new.csv'
        df = pd.DataFrame([signal])
        df.to_csv(file_path, mode='a', index=False, 
                 header=not os.path.exists(file_path))
        logger.info(f"Signal saved to CSV: {signal['symbol']} at {signal['timestamp']}")
    except Exception as e:
        logger.error(f"Error saving signal to CSV for {signal['symbol']}: {str(e)}")

# ==================== ⏳ COOLDOWN MANAGEMENT ==================== 
def is_symbol_on_cooldown(symbol):
    try:
        if symbol in cooldowns:
            last_signal_time = cooldowns[symbol]
            if datetime.now() < last_signal_time + timedelta(hours=COOLDOWN_HOURS):
                logger.info(f"[{symbol}] On cooldown until {last_signal_time + timedelta(hours=COOLDOWN_HOURS)}")
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking cooldown for {symbol}: {str(e)}")
        return False

def update_cooldown(symbol):
    try:
        cooldowns[symbol] = datetime.now()
        logger.info(f"[{symbol}] Cooldown updated until {datetime.now() + timedelta(hours=COOLDOWN_HOURS)}")
    except Exception as e:
        logger.error(f"Error updating cooldown for {symbol}: {str(e)}")

# ==================== 🔍 SYMBOL PROCESSING ==================== 
async def process_symbol(symbol, exchange, timeframes):
    try:
        if is_symbol_on_cooldown(symbol):
            return
        
        logger.info(f"[{symbol}] Starting multi-timeframe analysis")
        signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes)
        
        for timeframe, signal in signals.items():
            if signal and signal['confidence'] >= MIN_CONFIDENCE:  # 80% confidence check
                signal['timestamp'] = datetime.now().isoformat()
                signal['status'] = 'pending'
                signal['hit_timestamp'] = None
                await send_signal(signal)
                save_signal_to_csv(signal)
                update_cooldown(symbol)
                logger.info(f"[{symbol}] Signal generated for {timeframe}: {signal['direction']} (Confidence: {signal['confidence']}%)")
                break
        else:
            logger.info(f"[{symbol}] No valid signals across any timeframe (Confidence < {MIN_CONFIDENCE}%)")
            
    except Exception as e:
        logger.error(f"[{symbol}] Error processing symbol: {str(e)}")

# ==================== 📈 VOLUME FILTERING ==================== 
async def get_high_volume_symbols(exchange, min_volume):
    symbols = [s for s in exchange.symbols if s.endswith('/USDT')]
    high_volume_symbols = []
    
    for symbol in symbols:
        try:
            ticker = await exchange.fetch_ticker(symbol)
            quote_volume = ticker.get('quoteVolume', 0)
            
            if quote_volume >= min_volume:
                high_volume_symbols.append(symbol)
            else:
                logger.warning(f"[{symbol}] Skipped: Low volume (${quote_volume:,.2f} < ${min_volume:,.0f})")
                
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {str(e)}")
    
    return high_volume_symbols

# ==================== 🔄 MAIN LOOP ==================== 
async def main_loop():
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True
        })
        await exchange.load_markets()
        logger.info("Binance API connection successful")

        timeframes = ['15m', '1h', '4h', '1d']
        high_volume_symbols = await get_high_volume_symbols(exchange, MIN_QUOTE_VOLUME)
        
        logger.info(f"Selected {len(high_volume_symbols)} USDT pairs with volume >= ${MIN_QUOTE_VOLUME:,.0f}")
        
        while True:
            tasks = [process_symbol(symbol, exchange, timeframes) 
                   for symbol in high_volume_symbols[:200]]  # Process first 200 symbols
            await asyncio.gather(*tasks)
            await asyncio.sleep(60)
            
    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
    finally:
        await exchange.close()

# ==================== 🚀 FASTAPI ENDPOINTS ==================== 
@app.on_event("startup")
async def startup_event():
    logger.info("Starting bot...")
    asyncio.create_task(start_bot())
    asyncio.create_task(main_loop())

@app.get("/health")
async def health_check():
    logger.info("Health check passed")
    return {"status": "healthy"}
