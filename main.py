# Main module to run the trading bot and handle symbol processing
# Updated to fix zero price/volume issues, ensure new pairs are loaded, improve error handling, add BTC trend check, and prevent bot stopping
import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import psutil  # Added for memory/CPU monitoring
from fastapi import FastAPI
from datetime import datetime, timedelta
from core.analysis import analyze_symbol_multi_timeframe
from telebot.sender import send_signal, start_bot
from utils.logger import logger

# Initialize FastAPI app
app = FastAPI()

# Configuration constants
# Set MIN_QUOTE_VOLUME to filter symbols with sufficient trading activity
MIN_QUOTE_VOLUME = 500000  # Minimum quote volume for filtering symbols
# Set MIN_CONFIDENCE to ensure only high-confidence signals are processed
MIN_CONFIDENCE = 65  # Confidence threshold set to 65% for robust signals
# Set COOLDOWN_HOURS to prevent over-trading on the same symbol
COOLDOWN_HOURS = 6  # Cooldown period for symbols

# Cooldown tracking for symbols
cooldowns = {}

# Function to save signal to CSV
def save_signal_to_csv(signal):
    # Ensure logs directory exists and save signal with all required fields
    # Added robust error handling and logging for CSV operations
    try:
        os.makedirs('logs', exist_ok=True)
        file_path = 'logs/signals_log_new.csv'
        df = pd.DataFrame([signal])
        df.to_csv(file_path, mode='a', index=False, 
                  header=not os.path.exists(file_path))
        logger.info(f"Signal saved to CSV: {signal.get('symbol', 'Unknown')} at {signal['timestamp']}")
    except Exception as e:
        logger.error(f"Error saving signal to CSV for {signal.get('symbol', 'Unknown')}: {str(e)}")

# Function to check if symbol is on cooldown
def is_symbol_on_cooldown(symbol):
    # Check if symbol is within cooldown period to avoid over-trading
    # Added error handling for datetime operations
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

# Function to update cooldown for a symbol
def update_cooldown(symbol):
    # Update cooldown timestamp after a signal is generated
    # Added error handling for cooldown updates
    try:
        cooldowns[symbol] = datetime.now()
        logger.info(f"[{symbol}] Cooldown updated until {datetime.now() + timedelta(hours=COOLDOWN_HOURS)}")
    except Exception as e:
        logger.error(f"Error updating cooldown for {symbol}: {str(e)}")

# Function to fetch BTC market trend
async def get_btc_trend(exchange):
    # Fetch BTC/USDT 24h price change to determine market trend
    # Added to prevent LONG signals in bearish markets and SHORT in bullish markets
    try:
        ticker = await exchange.fetch_ticker('BTC/USDT')
        price_change_24h = ticker.get('percentage', 0)  # 24h price change in percentage
        logger.info(f"[Main] BTC/USDT 24h price change: {price_change_24h:.2f}%")
        return price_change_24h
    except Exception as e:
        logger.error(f"[Main] Error fetching BTC trend: {str(e)}")
        return 0

# Function to process a symbol
async def process_symbol(symbol, exchange, timeframes, btc_trend):
    # Analyze and process signals for a symbol with BTC trend context
    # Added btc_trend parameter to pass market trend to predictor
    try:
        if is_symbol_on_cooldown(symbol):
            return
        logger.info(f"[{symbol}] Starting multi-timeframe analysis")
        signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes, btc_trend=btc_trend)
        for timeframe, signal in signals.items():
            if signal and signal['confidence'] >= MIN_CONFIDENCE:
                signal['timestamp'] = datetime.now().isoformat()
                signal['status'] = 'pending'
                signal['hit_timestamp'] = None
                await send_signal(signal)
                save_signal_to_csv(signal)
                update_cooldown(symbol)
                logger.info(f"✅ Signal generated for {symbol} ({timeframe}): {signal['direction']} (Confidence: {signal['confidence']:.1f}%, Entry: {signal['entry']:.4f}, TP1: {signal['tp1']:.4f}, TP2: {signal['tp2']:.4f}, TP3: {signal['tp3']:.4f}, SL: {signal['sl']:.4f}, Conditions: {', '.join(signal['conditions'])})")
                break
    except Exception as e:
        logger.error(f"[{symbol}] Error processing symbol: {str(e)}")

# Function to fetch high-volume symbols
async def get_high_volume_symbols(exchange, min_volume):
    # Load fresh markets and filter high-volume USDT pairs
    # Fixed volume filtering bug by ensuring quote_volume is correctly validated
    try:
        await exchange.load_markets(reload=True)
        symbols = [s for s in exchange.markets.keys() if s.endswith('/USDT')]
        logger.info(f"[Main] Loaded {len(symbols)} USDT pairs from exchange")
    except Exception as e:
        logger.error(f"[Main] Error loading markets: {str(e)}")
        return []

    high_volume_symbols = []
    async def fetch_ticker(symbol):
        # Fetch ticker data with strict validation
        # Added delay to prevent API rate limit issues
        try:
            ticker = await exchange.fetch_ticker(symbol)
            quote_volume = ticker.get('quoteVolume', 0)
            close_price = ticker.get('close', 0)
            if (quote_volume is not None and quote_volume >= min_volume and 
                close_price is not None and 0.01 < close_price < 100000):
                return symbol, quote_volume
            else:
                logger.warning(f"[{symbol}] Skipped: Low volume (${quote_volume:,.2f} < ${min_volume:,.0f}) or invalid price ({close_price})")
                return None
        except Exception as e:
            logger.error(f"[{symbol}] Error fetching ticker: {str(e)}")
            return None

    # Process symbols in batches with delay to prevent rate limits
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
        await asyncio.sleep(5)  # Increased delay to prevent API rate limit
    return high_volume_symbols

# Main loop for the bot
async def main_loop():
    # Initialize Binance exchange and run main loop
    # Enhanced error handling and resource monitoring to prevent bot stopping
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True
        })
        logger.info("Binance API connection successful")
        timeframes = ['15m', '1h', '4h', '1d']
        while True:
            try:
                # Monitor system resources to detect potential crashes
                memory = psutil.Process().memory_info().rss / 1024 / 1024
                cpu = psutil.cpu_percent(interval=0.1)
                logger.info(f"[Main] System stats - Memory: {memory:.2f} MB, CPU: {cpu:.1f}%")
                if memory > 1000:  # Alert if memory usage exceeds 1GB
                    logger.warning("[Main] High memory usage detected, consider restarting")

                # Fetch BTC trend for market context
                btc_trend = await get_btc_trend(exchange)
                
                high_volume_symbols = await get_high_volume_symbols(exchange, MIN_QUOTE_VOLUME)
                logger.info(f"Selected {len(high_volume_symbols)} USDT pairs with volume >= ${MIN_QUOTE_VOLUME:,.0f}")
                if not high_volume_symbols:
                    logger.warning("No symbols passed volume filter. Retrying in 180 seconds...")
                    await asyncio.sleep(180)
                    continue
                batch_size = 1
                selected_symbols = high_volume_symbols[:20]
                for i in range(0, len(selected_symbols), batch_size):
                    batch = selected_symbols[i:i + batch_size]
                    tasks = [process_symbol(symbol, exchange, timeframes, btc_trend) for symbol in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.info(f"Completed analysis batch {i//batch_size + 1}/{len(selected_symbols)//batch_size + 1}")
                    await asyncio.sleep(20)  # Increased delay to prevent rate limits
                logger.info("Completed analysis cycle. Waiting 180 seconds for next cycle...")
                await asyncio.sleep(180)
            except Exception as e:
                logger.error(f"Error in analysis cycle: {str(e)}")
                await asyncio.sleep(60)  # Wait before retrying to avoid spamming
    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        await asyncio.sleep(300)  # Long wait before restarting loop
    finally:
        try:
            await exchange.close()
            logger.info("Exchange connection closed")
        except Exception as e:
            logger.error(f"Error closing exchange: {str(e)}")

# FastAPI startup event
@app.on_event("startup")
async def startup_event():
    # Start bot and main loop
    logger.info("Starting bot...")
    asyncio.create_task(start_bot())
    asyncio.create_task(main_loop())

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Test analysis function
async def test_analysis():
    # Test analysis for a specific symbol
    # Updated to include BTC trend for testing
    symbol = "ADA/USDT"
    exchange = ccxt.binance({"enableRateLimit": True})
    timeframes = ["15m"]
    btc_trend = await get_btc_trend(exchange)
    logger.info(f"Testing analysis for {symbol} with BTC trend: {btc_trend:.2f}%")
    signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes, btc_trend=btc_trend)
    logger.info(f"Test analysis results for {symbol}: {signals}")
    await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_analysis())
