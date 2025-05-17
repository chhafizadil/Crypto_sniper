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

# Memory-based cooldown tracking
cooldowns = {}

def save_signal_to_csv(signal):
    try:
        os.makedirs('logs', exist_ok=True)
        file_path = 'logs/signals_log_new.csv'
        df = pd.DataFrame([signal])
        df.to_csv(file_path, mode='a', index=False, header=not os.path.exists(file_path))
        logger.info(f"Signal saved to CSV: {signal['symbol']} at {signal['timestamp']}")
    except Exception as e:
        logger.error(f"Error saving signal to CSV for {signal['symbol']}: {str(e)}")

def is_symbol_on_cooldown(symbol):
    try:
        if symbol in cooldowns:
            last_signal_time = cooldowns[symbol]
            if datetime.now() < last_signal_time + timedelta(hours=6):
                logger.info(f"[{symbol}] On cooldown until {last_signal_time + timedelta(hours=6)}")
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking cooldown for {symbol}: {str(e)}")
        return False

def update_cooldown(symbol):
    try:
        cooldowns[symbol] = datetime.now()
        logger.info(f"[{symbol}] Cooldown updated until {datetime.now() + timedelta(hours=6)}")
    except Exception as e:
        logger.error(f"Error updating cooldown for {symbol}: {str(e)}")

async def process_symbol(symbol, exchange, timeframes):
    try:
        if is_symbol_on_cooldown(symbol):
            return
        
        logger.info(f"[{symbol}] Starting multi-timeframe analysis")
        signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes)
        
        for timeframe, signal in signals.items():
            if signal and signal['confidence'] >= 60:
                signal['timestamp'] = datetime.now().isoformat()
                signal['status'] = 'pending'
                signal['hit_timestamp'] = None
                await send_signal(signal)
                save_signal_to_csv(signal)
                update_cooldown(symbol)
                logger.info(f"[{symbol}] Signal generated for {timeframe}: {signal['direction']}")
                break
        else:
            logger.info(f"[{symbol}] No valid signals across any timeframe")
            await send_signal({
                'symbol': symbol,
                'direction': 'No valid signals',
                'confidence': 0,
                'timeframe': '',
                'conditions': [],
                'entry': 0,
                'tp1': 0,
                'tp2': 0,
                'tp3': 0,
                'sl': 0,
                'tp1_possibility': 0,
                'tp2_possibility': 0,
                'tp3_possibility': 0,
                'volume': 0,
                'status': 'none',
                'hit_timestamp': None,
                'trade_type': '',
                'timestamp': datetime.now().isoformat()
            })
    except Exception as e:
        logger.error(f"[{symbol}] Error processing symbol: {str(e)}")

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
        symbols = [symbol for symbol in exchange.symbols if symbol.endswith('/USDT')]
        high_volume_symbols = []
        
        for symbol in symbols:
            try:
                ticker = await exchange.fetch_ticker(symbol)
                quote_volume = ticker.get('quoteVolume')
                if quote_volume is not None and quote_volume >= 50:
                    high_volume_symbols.append(symbol)
                else:
                    logger.warning(f"[{symbol}] Skipped: Insufficient or missing quoteVolume")
            except Exception as e:
                logger.error(f"Error fetching ticker for {symbol}: {str(e)}")
        
        logger.info(f"Selected {len(high_volume_symbols)} USDT pairs with volume >= $1")
        
        while True:
            tasks = [process_symbol(symbol, exchange, timeframes) for symbol in high_volume_symbols[:200]]
            await asyncio.gather(*tasks)
            await asyncio.sleep(60)
    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
    finally:
        await exchange.close()

@app.on_event("startup")
async def startup_event():
    logger.info("Starting bot...")
    asyncio.create_task(start_bot())
    asyncio.create_task(main_loop())

@app.get("/health")
async def health_check():
    logger.info("Health check passed")
    return {"status": "healthy"}
