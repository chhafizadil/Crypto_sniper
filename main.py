import asyncio
import logging
import pandas as pd
import ccxt.async_support as ccxt
from fastapi import FastAPI
from typing import List, Dict
from core.analysis import analyze_symbol_multi_timeframe
from model.predictor import SignalPredictor
from telebot.sender import send_telegram_signal
from telebot.report_generator import generate_daily_summary
from datetime import datetime, timedelta
import httpx
import psutil
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import Conflict

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
SYMBOL_LIMIT = 200  # اپ ڈیٹ: 200 coins
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
MIN_VOLUME = 1000000  # اپ ڈیٹ: 1 million
CONFIDENCE_THRESHOLD = 70.0
COOLDOWN_PERIOD = 21600  # 6 گھنٹے
BOT_TOKEN = "7620836100:AAEEe4yAP18Lxxj0HoYfH8aeX4PetAxYsV0"
CHAT_ID = "-4694205383"

predictor = SignalPredictor()
log.info("Signal Predictor initialized successfully")

cooldowns: Dict[str, datetime] = {}

async def send_telegram_message(chat_id: str, text: str):
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            response = await client.post(url, json=payload)
            if response.status_code == 200 and response.json().get("ok"):
                log.info(f"Telegram message sent to {chat_id}: {text[:50]}...")
            else:
                log.error(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        log.error(f"Error sending Telegram message: {str(e)}")

async def delete_webhook(max_retries: int = 5):
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Webhook ہٹائیں اور پینڈنگ اپ ڈیٹس صاف کریں
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
                response = await client.get(url)
                if response.status_code == 200 and response.json().get("ok"):
                    log.info("Telegram webhook deleted successfully")
                    # Webhook سٹیٹس چیک کریں
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
                    response = await client.get(url)
                    if response.status_code == 200:
                        webhook_info = response.json().get("result", {})
                        if webhook_info.get("url") == "" and webhook_info.get("pending_update_count", 0) == 0:
                            log.info("Webhook confirmed deleted with no pending updates")
                            return True
                        else:
                            log.warning(f"Webhook not fully cleared: url={webhook_info.get('url')}, pending_updates={webhook_info.get('pending_update_count')}")
                    else:
                        log.error(f"Failed to fetch webhook info: {response.text}")
                else:
                    log.error(f"Failed to delete Telegram webhook: {response.text}")
        except Exception as e:
            log.error(f"Error deleting Telegram webhook (attempt {attempt + 1}/{max_retries}): {str(e)}")
        await asyncio.sleep(2 ** attempt)  # Exponential backoff
    log.error("Failed to delete webhook after maximum retries")
    return False

async def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    for attempt in range(3):
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
    
    # ہر ٹائم فریم سے پہلے cooldown چیک کرو
    if symbol in cooldowns:
        cooldown_end = cooldowns[symbol] + timedelta(seconds=COOLDOWN_PERIOD)
        if datetime.utcnow() < cooldown_end:
            log.info(f"[{symbol}] In cooldown until {cooldown_end} for all timeframes")
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
            # دوبارہ cooldown چیک کرو سگنل بھیجنے سے پہلے
            if symbol in cooldowns:
                cooldown_end = cooldowns[symbol] + timedelta(seconds=COOLDOWN_PERIOD)
                if datetime.utcnow() < cooldown_end:
                    log.info(f"[{symbol}] Signal skipped due to cooldown until {cooldown_end}")
                    return
            
            cooldowns[symbol] = datetime.utcnow()
            log.info(f"[{symbol}] Added to cooldown for all timeframes for {COOLDOWN_PERIOD/3600} hours")
            
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

# Telegram Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != CHAT_ID:
        return
    log.info("Received /start command")
    welcome_msg = (
        "Welcome to the Crypto Signal Bot! 🚀\n"
        "Use /help to see available commands."
    )
    await context.bot.send_message(chat_id=chat_id, text=welcome_msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != CHAT_ID:
        return
    log.info("Received /help command")
    help_msg = (
        "Available Commands:\n"
        "/start - Start the bot and get welcome message\n"
        "/help - Show available commands and usage\n"
        "/report - Generate and send the daily signal report\n"
        "/signals - Display latest trading signals\n"
        "/status - Check bot status and health\n"
        "/summary - Show summary of recent signals"
    )
    await context.bot.send_message(chat_id=chat_id, text=help_msg)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != CHAT_ID:
        return
    log.info("Received /report command")
    await generate_daily_summary()

async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != CHAT_ID:
        return
    log.info("Received /signals command")
    if os.path.exists('logs/signals_log_new.csv'):
        df = pd.read_csv('logs/signals_log_new.csv')
        if not df.empty:
            latest_signals = df.tail(5)[['symbol', 'direction', 'entry', 'confidence', 'timeframe', 'timestamp']]
            signals_msg = "Latest Signals:\n"
            for _, row in latest_signals.iterrows():
                signals_msg += (
                    f"{row['symbol']} ({row['timeframe']}): {row['direction']}, "
                    f"Entry: {row['entry']:.8f}, Confidence: {row['confidence']}%, "
                    f"Time: {row['timestamp']}\n"
                )
        else:
            signals_msg = "No signals found."
    else:
        signals_msg = "No signal logs available."
    await context.bot.send_message(chat_id=chat_id, text=signals_msg)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != CHAT_ID:
        return
    log.info("Received /status command")
    memory = psutil.virtual_memory()
    status_msg = (
        f"Bot Status:\n"
        f"Health: {'Healthy' if memory.percent < 85 else 'Unhealthy'}\n"
        f"Memory Usage: {memory.percent}%\n"
        f"Uptime: {datetime.utcnow() - pd.Timestamp.now(tz='UTC')}\n"
        f"Symbols Scanned: {SYMBOL_LIMIT}\n"
        f"Timeframes: {', '.join(TIMEFRAMES)}"
    )
    await context.bot.send_message(chat_id=chat_id, text=status_msg)

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != CHAT_ID:
        return
    log.info("Received /summary command")
    if os.path.exists('logs/signals_log_new.csv'):
        df = pd.read_csv('logs/signals_log_new.csv')
        if not df.empty:
            total_signals = len(df)
            pending = len(df[df['status'] == 'pending'])
            success = len(df[df['status'].isin(['tpDerek', 'tp2', 'tp3'])])
            failed = len(df[df['status'] == 'sl'])
            avg_confidence = df['confidence'].mean()
            summary_msg = (
                f"Signal Summary:\n"
                f"Total Signals: {total_signals}\n"
                f"Pending: {pending}\n"
                f"Successful (TP Hit): {success}\n"
                f"Failed (SL Hit): {failed}\n"
                f"Average Confidence: {avg_confidence:.2f}%"
            )
        else:
            summary_msg = "No signals found."
    else:
        summary_msg = "No signal logs available."
    await context.bot.send_message(chat_id=chat_id, text=summary_msg)

async def scan_symbols():
    log.info(f"Scanning {SYMBOL_LIMIT} symbols across {TIMEFRAMES}")
    symbols = await get_high_volume_symbols()
    
    for symbol in symbols:
        try:
            async with httpx.AsyncClient() as client:
                await process_symbol(symbol)
            await asyncio.sleep(600)
        except Exception as e:
            log.error(f"Error processing {symbol}: {str(e)}")
    await asyncio.sleep(3600)

async def run_scanner():
    try:
        await EXCHANGE.load_markets()
        async def daily_report():
            try:
                await generate_daily_summary()
                log.info("Daily summary generated and sent")
            except Exception as e:
                log.error(f"Daily report error: {str(e)}")
        while True:
            try:
                await scan_symbols()
                log.info("Scan complete, waiting for next cycle...")
                now = datetime.utcnow()
                if now.hour == 23 and now.minute == 59:
                    await daily_report()
                await asyncio.sleep(60)
            except Exception as e:
                log.error(f"Error in scan cycle: {str(e)}")
                await asyncio.sleep(3600)
    except Exception as e:
        log.error(f"Error in scanner: {str(e)}")
        await asyncio.sleep(3600)

async def run_telegram_polling(telegram_app: Application, max_retries: int = 10):
    for attempt in range(max_retries):
        try:
            # Webhook ہٹانے کی کوشش، پینڈنگ اپ ڈیٹس صاف کرو
            if not await delete_webhook():
                log.error("Failed to delete webhook, retrying...")
                await asyncio.sleep(2 ** attempt)
                continue
            # getUpdates کے ذریعے پینڈنگ اپ ڈیٹس صاف کرو
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset=-1"
                response = await client.get(url)
                if response.status_code == 200 and response.json().get("ok"):
                    log.info("Pending updates cleared via getUpdates")
                else:
                    log.warning(f"Failed to clear pending updates: {response.text}")
            
            await asyncio.sleep(2)  # Webhook اور اپ ڈیٹس صاف ہونے کا انتظار
            await telegram_app.initialize()
            await telegram_app.start()
            await telegram_app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30,
                poll_interval=1.0
            )
            log.info("Telegram polling started successfully")
            return
        except Conflict as e:
            log.error(f"Polling conflict (attempt {attempt + 1}/{max_retries}): {str(e)}")
            # Webhook اور اپ ڈیٹس دوبارہ صاف کرو
            await delete_webhook()
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset=-1"
                response = await client.get(url)
                if response.status_code == 200:
                    log.info("Pending updates cleared during conflict retry")
                else:
                    log.warning(f"Failed to clear updates during conflict: {response.text}")
            await telegram_app.stop()
            await telegram_app.shutdown()
            await asyncio.sleep(5 * (attempt + 1))
        except Exception as e:
            log.error(f"Error in Telegram polling (attempt {attempt + 1}/{max_retries}): {str(e)}")
            await telegram_app.stop()
            await telegram_app.shutdown()
            await asyncio.sleep(5 * (attempt + 1))
    log.error("Failed to start Telegram polling after maximum retries")
    raise RuntimeError("Could not start Telegram polling")

@app.on_event("startup")
async def startup_event():
    log.info("Starting bot...")
    try:
        await EXCHANGE.load_markets()
        log.info("Binance API connection successful")
        await delete_webhook()  # Ensure webhook is deleted on startup
        
        # Initialize Telegram bot
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        # Add command handlers
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("report", report))
        telegram_app.add_handler(CommandHandler("signals", signals))
        telegram_app.add_handler(CommandHandler("status", status))
        telegram_app.add_handler(CommandHandler("summary", summary))
        
        # Start polling in a separate task
        asyncio.create_task(run_telegram_polling(telegram_app))
        
        # Start scanner
        asyncio.create_task(run_scanner())
    except Exception as e:
        log.error(f"Error in startup: {str(e)}")
        await EXCHANGE.close()
        raise

@app.on_event("shutdown")
async def shutdown_event():
    log.info("Shutting down")
    try:
        await EXCHANGE.close()
        log.info("Binance connection closed successfully")
    except Exception as e:
        log.error(f"Error closing resources: {str(e)}")

@app.get("/health")
async def health_check():
    try:
        memory = psutil.virtual_memory()
        if memory.percent > 85:
            log.error(f"Health check failed: High memory usage {memory.percent}%")
            return {"status": "unhealthy", "error": f"High memory usage {memory.percent}%"}, 500
        if EXCHANGE is None or not hasattr(EXCHANGE, 'markets'):
            log.error("Health check failed: Exchange not initialized or markets not loaded")
            return {"status": "unhealthy", "error": "Exchange not initialized or markets not loaded"}, 500
        log.info("Health check passed")
        return {"status": "healthy", "timestamp": str(datetime.utcnow())}
    except Exception as e:
        log.error(f"Health check failed: {str(e)}")
        return {"status": "unhealthy", "error": str(e)}, 500
