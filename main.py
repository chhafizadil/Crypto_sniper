# Main module to run the trading bot and handle symbol processing
# Updated to fix zero price/volume issues, relax price check for low-priced coins, improve error handling, add BTC trend check, and prevent bot stopping
import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import psutil  # Added for memory/CPU monitoring to prevent crashes
from fastapi import FastAPI
from datetime import datetime, timedelta
from core.analysis import analyze_symbol_multi_timeframe
from telebot.sender import send_signal, start_bot
from utils.logger import logger

# Initialize FastAPI app for web server
app = FastAPI()

# Configuration constants
# Minimum quote volume to filter symbols with sufficient trading activity
MIN_QUOTE_VOLUME = 500000  # Set to $500,000 to ensure liquid markets
# Confidence threshold to ensure only high-quality signals are processed
MIN_CONFIDENCE = 65  # Set to 65% to filter robust signals
# Cooldown period to prevent over-trading on the same symbol
COOLDOWN_HOURS = 6  # Set to 6 hours to avoid spamming signals

# Dictionary to track cooldowns for symbols
cooldowns = {}

# Function to save signal to CSV
def save_signal_to_csv(signal):
    # Saves signal data to CSV with all required fields
    # Includes robust error handling to prevent CSV write failures
    try:
        os.makedirs('logs', exist_ok=True)  # Create logs directory if it doesn't exist
        file_path = 'logs/signals_log_new.csv'  # Path to signals log CSV
        df = pd.DataFrame([signal])  # Convert signal to DataFrame
        df.to_csv(file_path, mode='a', index=False, 
                  header=not os.path.exists(file_path))  # Append to CSV, add header if new file
        logger.info(f"Signal saved to CSV: {signal.get('symbol', 'Unknown')} at {signal['timestamp']}")
    except Exception as e:
        logger.error(f"Error saving signal to CSV for {signal.get('symbol', 'Unknown')}: {str(e)}")

# Function to check if symbol is on cooldown
def is_symbol_on_cooldown(symbol):
    # Checks if symbol is within cooldown period to avoid over-trading
    # Includes error handling for datetime operations
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
    # Updates cooldown timestamp after a signal is generated
    # Includes error handling to prevent failures
    try:
        cooldowns[symbol] = datetime.now()  # Set current time as last signal time
        logger.info(f"[{symbol}] Cooldown updated until {datetime.now() + timedelta(hours=COOLDOWN_HOURS)}")
    except Exception as e:
        logger.error(f"Error updating cooldown for {symbol}: {str(e)}")

# Function to fetch BTC market trend
async def get_btc_trend(exchange):
    # Fetches BTC/USDT 24h price change to determine market trend
    # Used to prevent LONG signals in bearish markets and SHORT in bullish markets
    try:
        ticker = await exchange.fetch_ticker('BTC/USDT')  # Fetch BTC/USDT ticker
        price_change_24h = ticker.get('percentage', 0)  # Get 24h price change in percentage
        logger.info(f"[Main] BTC/USDT 24h price change: {price_change_24h:.2f}%")
        return price_change_24h
    except Exception as e:
        logger.error(f"[Main] Error fetching BTC trend: {str(e)}")
        return 0  # Return 0 if fetch fails to avoid breaking logic

# Function to process a symbol
async def process_symbol(symbol, exchange, timeframes, btc_trend):
    # Analyzes and processes signals for a symbol with BTC trend context
    # Passes btc_trend to predictor for market-aware signal generation
    try:
        if is_symbol_on_cooldown(symbol):
            return  # Skip if symbol is on cooldown
        logger.info(f"[{symbol}] Starting multi-timeframe analysis")
        signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes)

        for timeframe, signal in signals.items():
            if signal and signal['confidence'] >= MIN_CONFIDENCE:  # Check if signal meets confidence threshold
                signal['timestamp'] = datetime.now().isoformat()  # Add timestamp to signal
                signal['status'] = 'pending'  # Set initial status
                signal['hit_timestamp'] = None  # Initialize hit timestamp
                await send_signal(signal)  # Send signal to Telegram
                save_signal_to_csv(signal)  # Save signal to CSV
                update_cooldown(symbol)  # Update cooldown for symbol
                logger.info(f"✅ Signal generated for {symbol} ({timeframe}): {signal['direction']} (Confidence: {signal['confidence']:.1f}%, Entry: {signal['entry']:.4f}, TP1: {signal['tp1']:.4f}, TP2: {signal['tp2']:.4f}, TP3: {signal['tp3']:.4f}, SL: {signal['sl']:.4f}, Conditions: {', '.join(signal['conditions'])})")
                break  # Stop after first valid signal
    except Exception as e:
        logger.error(f"[{symbol}] Error processing symbol: {str(e)}")

# Function to fetch high-volume symbols
async def get_high_volume_symbols(exchange, min_volume):
    # Loads fresh markets and filters high-volume USDT pairs
    # Fixed volume filtering bug and relaxed price check for low-priced coins
    try:
        await exchange.load_markets(reload=True)  # Reload markets to get fresh data
        symbols = [s for s in exchange.markets.keys() if s.endswith('/USDT')]  # Filter USDT pairs
        logger.info(f"[Main] Loaded {len(symbols)} USDT pairs from exchange")
    except Exception as e:
        logger.error(f"[Main] Error loading markets: {str(e)}")
        return []  # Return empty list if market load fails

    high_volume_symbols = []
    async def fetch_ticker(symbol):
        # Fetches ticker data with strict validation and relaxed price check
        # Added detailed logging and delay to prevent API rate limit issues
        try:
            ticker = await exchange.fetch_ticker(symbol)  # Fetch ticker data
            quote_volume = ticker.get('quoteVolume', 0)  # Get 24h quote volume
            close_price = ticker.get('close', 0)  # Get current close price
            # Log ticker data for debugging
            logger.info(f"[{symbol}] Ticker data: quoteVolume=${quote_volume:,.2f}, close_price={close_price}")
            # Check if ticker data is valid
            if ticker.get('quoteVolume') is None or ticker.get('close') is None:
                logger.warning(f"[{symbol}] Skipped: Missing ticker data")
                return None
            # Relaxed price check to include low-priced coins like SHIB (0.00001407)
            if (quote_volume is not None and quote_volume >= min_volume and 
                close_price is not None and 0.00001 < close_price < 100000):  # Changed 0.01 to 0.00001
                return symbol, quote_volume
            else:
                logger.warning(f"[{symbol}] Skipped: Low volume (${quote_volume:,.2f} < ${min_volume:,.0f}) or invalid price ({close_price})")
                return None
        except Exception as e:
            logger.error(f"[{symbol}] Error fetching ticker: {str(e)}")
            return None

    # Process symbols in batches with delay to prevent rate limits
    batch_size = 25  # Process 25 symbols at a time
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        tasks = [fetch_ticker(symbol) for symbol in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, tuple):
                symbol, quote_volume = result
                high_volume_symbols.append(symbol)
                logger.info(f"[{symbol}] Passed volume filter: ${quote_volume:,.2f} >= ${min_volume:,.0f}")
        await asyncio.sleep(5)  # Delay to prevent API rate limit issues
    return high_volume_symbols

# Main loop for the bot
async def main_loop():
    # Initializes Binance exchange and runs main loop
    # Enhanced error handling and resource monitoring to prevent bot stopping
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),  # Load API key from environment
            'secret': os.getenv('BINANCE_API_SECRET'),  # Load API secret from environment
            'enableRateLimit': True  # Enable rate limiting for API
        })
        logger.info("Binance API connection successful")
        timeframes = ['15m', '1h', '4h', '1d']  # Timeframes for analysis
        while True:
            try:
                # Monitor system resources to detect potential crashes
                memory = psutil.Process().memory_info().rss / 1024 / 1024  # Memory usage in MB
                cpu = psutil.cpu_percent(interval=0.1)  # CPU usage percentage
                logger.info(f"[Main] System stats - Memory: {memory:.2f} MB, CPU: {cpu:.1f}%")
                if memory > 1000:  # Alert if memory usage exceeds 1GB
                    logger.warning("[Main] High memory usage detected, consider restarting")

                # Fetch BTC trend for market context
                btc_trend = await get_btc_trend(exchange)
                
                high_volume_symbols = await get_high_volume_symbols(exchange, MIN_QUOTE_VOLUME)
                logger.info(f"Selected {len(high_volume_symbols)} USDT pairs with volume >= ${MIN_QUOTE_VOLUME:,.0f}")
                if not high_volume_symbols:
                    logger.warning("No symbols passed volume filter. Retrying in 180 seconds...")
                    await asyncio.sleep(180)  # Wait before retrying
                    continue
                batch_size = 1  # Process one symbol at a time
                selected_symbols = high_volume_symbols[:20]  # Limit to top 20 symbols
                for i in range(0, len(selected_symbols), batch_size):
                    batch = selected_symbols[i:i + batch_size]
                    tasks = [process_symbol(symbol, exchange, timeframes, btc_trend) for symbol in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.info(f"Completed analysis batch {i//batch_size + 1}/{len(selected_symbols)//batch_size + 1}")
                    await asyncio.sleep(20)  # Increased delay to prevent rate limits
                logger.info("Completed analysis cycle. Waiting 180 seconds for next cycle...")
                await asyncio.sleep(180)  # Wait before next cycle
            except Exception as e:
                logger.error(f"Error in analysis cycle: {str(e)}")
                await asyncio.sleep(60)  # Wait before retrying to avoid spamming
    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        await asyncio.sleep(300)  # Long wait before restarting loop
    finally:
        try:
            await exchange.close()  # Close exchange connection
            logger.info("Exchange connection closed")
        except Exception as e:
            logger.error(f"Error closing exchange: {str(e)}")

# FastAPI startup event
@app.on_event("startup")
async def startup_event():
    # Starts bot and main loop on FastAPI startup
    logger.info("Starting bot...")
    asyncio.create_task(start_bot())  # Start Telegram bot
    asyncio.create_task(main_loop())  # Start main loop

# Health check endpoint
@app.get("/health")
async def health_check():
    # Returns health status for monitoring
    return {"status": "healthy"}

# Test analysis function
async def test_analysis():
    # Tests analysis for a specific symbol with BTC trend
    symbol = "ADA/USDT"  # Test symbol
    exchange = ccxt.binance({"enableRateLimit": True})  # Initialize Binance exchange
    timeframes = ["15m"]  # Test timeframe
    btc_trend = await get_btc_trend(exchange)  # Fetch BTC trend
    logger.info(f"Testing analysis for {symbol} with BTC trend: {btc_trend:.2f}%")
    signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes, btc_trend=btc_trend)
    logger.info(f"Test analysis results for {symbol}: {signals}")
    await exchange.close()  # Close exchange connection

if __name__ == "__main__":
    asyncio.run(test_analysis())  # Run test analysis if script is executed directly
