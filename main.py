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
MIN_QUOTE_VOLUME = 500000  # Minimum quote volume for filtering symbols ($500,000)
MIN_CONFIDENCE = 50  # Minimum confidence for valid signals (kept at 50 per user request)
COOLDOWN_HOURS = 6  # Cooldown period for symbols after generating a signal
# Configuration for volume filtering and signal confidence threshold

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
        # Save signal details to CSV for record-keeping
    except Exception as e:
        logger.error(f"Error saving signal to CSV for {signal['symbol']}: {str(e)}")
        # Log any errors during CSV saving

# ==================== ⏳ COOLDOWN MANAGEMENT ==================== 
def is_symbol_on_cooldown(symbol):
    try:
        if symbol in cooldowns:
            last_signal_time = cooldowns[symbol]
            if datetime.now() < last_signal_time + timedelta(hours=COOLDOWN_HOURS):
                logger.info(f"[{symbol}] On cooldown until {last_signal_time + timedelta(hours=COOLDOWN_HOURS)}")
                return True
        return False
        # Check if symbol is on cooldown to prevent repeated signals
    except Exception as e:
        logger.error(f"Error checking cooldown for {symbol}: {str(e)}")
        return False
        # Log any errors during cooldown check

def update_cooldown(symbol):
    try:
        cooldowns[symbol] = datetime.now()
        logger.info(f"[{symbol}] Cooldown updated until {datetime.now() + timedelta(hours=COOLDOWN_HOURS)}")
        # Update cooldown timestamp for symbol after signal generation
    except Exception as e:
        logger.error(f"Error updating cooldown for {symbol}: {str(e)}")
        # Log any errors during cooldown update

# ==================== 🔍 SYMBOL PROCESSING ==================== 
async def process_symbol(symbol, exchange, timeframes):
    try:
        if is_symbol_on_cooldown(symbol):
            return
        # Skip symbol if it's on cooldown

        logger.info(f"[{symbol}] Starting multi-timeframe analysis")
        signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes)
        # Start multi-timeframe analysis for the symbol

        for timeframe, signal in signals.items():
            if signal:
                logger.info(f"[{symbol}] {timeframe} → Confidence: {signal.get('confidence')}% | Direction: {signal.get('direction')}")
                # Log confidence and direction for each timeframe to ensure visibility in Koyeb logs
            else:
                logger.info(f"[{symbol}] No signal generated for {timeframe}")
                # Log when no signal is generated for a timeframe

            if signal and signal['confidence'] >= MIN_CONFIDENCE:
                signal['timestamp'] = datetime.now().isoformat()
                signal['status'] = 'pending'
                signal['hit_timestamp'] = None
                await send_signal(signal)
                save_signal_to_csv(signal)
                update_cooldown(symbol)
                logger.info(f"[{symbol}] Signal generated for {timeframe}: {signal['direction']} (Confidence: {signal['confidence']}%)")
                break
                # Generate and send signal if confidence meets threshold, then break to avoid multiple signals
        else:
            logger.info(f"[{symbol}] No valid signals across any timeframe (Confidence < {MIN_CONFIDENCE}%)")
            # Log when no valid signals are found across all timeframes

    except Exception as e:
        logger.error(f"[{symbol}] Error processing symbol: {str(e)}")
        # Log any errors during symbol processing to debug issues

# ==================== 📈 VOLUME FILTERING ==================== 
async def get_high_volume_symbols(exchange, min_volume):
    symbols = [s for s in exchange.symbols if s.endswith('/USDT')]
    high_volume_symbols = []
    # Filter USDT pairs for volume analysis

    async def fetch_ticker(symbol):
        try:
            ticker = await exchange.fetch_ticker(symbol)
            quote_volume = ticker.get('quoteVolume', 0)
            if quote_volume is not None and quote_volume >= min_volume:
                return symbol, quote_volume
            else:
                logger.warning(f"[{symbol}] Skipped: Low volume (${quote_volume:,.2f} < ${min_volume:,.0f})")
                return None
            # Fetch ticker and check if volume meets minimum threshold
        except Exception as e:
            logger.error(f"[{symbol}] Error fetching ticker: {str(e)}")
            return None
            # Log any errors during ticker fetching

    batch_size = 25
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        tasks = [fetch_ticker(symbol) for symbol in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, tuple):
                symbol, quote_volume = result
                high_volume_symbols.append(symbol)
                logger.info(f"[{symbol}] Passed volume filter: ${quote_volume:,.2f} >= ${min_volume:,.0f}")
        results = None
        await asyncio.sleep(3)
        # Process symbols in batches of 25 with 3-second delay to reduce server load
    return high_volume_symbols
    # Return list of high-volume symbols

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
        # Initialize Binance exchange with API credentials

        timeframes = ['15m', '1h', '4h', '1d']
        # Define timeframes for multi-timeframe analysis

        while True:
            high_volume_symbols = await get_high_volume_symbols(exchange, MIN_QUOTE_VOLUME)
            logger.info(f"Selected {len(high_volume_symbols)} USDT pairs with volume >= ${MIN_QUOTE_VOLUME:,.0f}")
            # Fetch high-volume symbols

            if not high_volume_symbols:
                logger.warning("No symbols passed volume filter. Retrying in 180 seconds...")
                await asyncio.sleep(180)
                continue
            # Retry if no symbols pass volume filter

            batch_size = 5  # Reduced from 10 to minimize memory usage
            selected_symbols = high_volume_symbols[:20]
            for i in range(0, len(selected_symbols), batch_size):
                batch = selected_symbols[i:i + batch_size]
                tasks = [process_symbol(symbol, exchange, timeframes) for symbol in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Completed analysis batch {i//batch_size + 1}/{len(selected_symbols)//batch_size + 1}")
                await asyncio.sleep(8)  # Increased from 5 to 8 seconds for stability
                # Process symbols in batches of 5 with 8-second delay to reduce server load

            logger.info("Completed analysis cycle. Waiting 180 seconds for next cycle...")
            await asyncio.sleep(180)
            # Complete analysis cycle and wait 180 seconds

    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        # Log any errors in main loop
    finally:
        await exchange.close()
        # Close exchange connection on exit

# ==================== 🚀 FASTAPI ENDPOINTS ==================== 
@app.on_event("startup")
async def startup_event():
    logger.info("Starting bot...")
    asyncio.create_task(start_bot())
    asyncio.create_task(main_loop())
    # Start bot and main loop on application startup

@app.get("/health")
async def health_check():
    logger.info("Health check passed")
    return {"status": "healthy"}
    # Health check endpoint for Koyeb
