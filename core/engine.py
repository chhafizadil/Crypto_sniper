# Core engine module for running trading analysis and signal generation
# Updated to implement user-specified signal format, MACD validation, and TP/SL tracking
import asyncio
import ccxt.async_support as ccxt
from core.analysis import analyze_symbol_multi_timeframe
from core.trade_classifier import classify_trade
from utils.logger import logger
import pandas as pd
import psutil
from telegram import Bot
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Function to track TP/SL status
async def track_signal_status(signal, exchange):
    # Added TP/SL status tracking using real-time price data
    try:
        symbol = signal['symbol']
        entry = signal['entry']
        tp1, tp2, tp3 = signal['tp1'], signal['tp2'], signal['tp3']
        sl = signal['sl']
        direction = signal['direction']
        timeout = pd.Timestamp.now() + pd.Timedelta(hours=24)

        while pd.Timestamp.now() < timeout:
            ticker = await exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            if direction == "LONG":
                if current_price >= tp3:
                    return "TP3 Hit", pd.Timestamp.now().isoformat()
                elif current_price >= tp2:
                    return "TP2 Hit", pd.Timestamp.now().isoformat()
                elif current_price >= tp1:
                    return "TP1 Hit", pd.Timestamp.now().isoformat()
                elif current_price <= sl:
                    return "SL Hit", pd.Timestamp.now().isoformat()
            else:
                if current_price <= tp3:
                    return "TP3 Hit", pd.Timestamp.now().isoformat()
                elif current_price <= tp2:
                    return "TP2 Hit", pd.Timestamp.now().isoformat()
                elif current_price <= tp1:
                    return "TP1 Hit", pd.Timestamp.now().isoformat()
                elif current_price >= sl:
                    return "SL Hit", pd.Timestamp.now().isoformat()
            await asyncio.sleep(60)
        return "Pending", None
    except Exception as e:
        logger.error(f"Error tracking signal status for {symbol}: {str(e)}")
        return "Pending", None

# Main function to run the trading engine
async def run_engine():
    logger.info("[Engine] Starting run_engine")

    try:
        # Check environment variables
        required_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "BINANCE_API_KEY", "BINANCE_API_SECRET"]
        for var in required_vars:
            if not os.getenv(var):
                logger.error(f"[Engine] Missing environment variable: {var}")
                return

        # Check model file
        model_path = "models/rf_model.joblib"
        if not os.path.exists(model_path):
            logger.error(f"[Engine] Model file not found at {model_path}")
            return

        # Ensure logs directory
        logs_dir = "logs"
        if not os.path.exists(logs_dir):
            logger.info(f"[Engine] Creating logs directory: {logs_dir}")
            os.makedirs(logs_dir)

        # Initialize Telegram bot
        try:
            bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
            logger.info("[Engine] Telegram bot initialized")
        except Exception as e:
            logger.error(f"[Engine] Error initializing Telegram bot: {str(e)}")
            return

        # Initialize Binance exchange
        try:
            exchange = ccxt.binance({
                "enableRateLimit": True,
                "apiKey": os.getenv("BINANCE_API_KEY"),
                "secret": os.getenv("BINANCE_API_SECRET")
            })
            logger.info("[Engine] Binance exchange initialized")
        except Exception as e:
            logger.error(f"[Engine] Error initializing Binance exchange: {str(e)}")
            return

        # Load markets
        try:
            await exchange.load_markets()
            symbols = [s for s in exchange.markets.keys() if s.endswith("/USDT")]
            logger.info(f"[Engine] Found {len(symbols)} USDT pairs")
        except Exception as e:
            logger.error(f"[Engine] Error loading markets: {str(e)}")
            return

        # Process symbols
        for symbol in symbols[:20]:
            memory_before = psutil.Process().memory_info().rss / 1024 / 1024
            cpu_percent = psutil.cpu_percent(interval=0.1)
            logger.info(f"[Engine] [{symbol}] Before analysis - Memory: {memory_before:.2f} MB, CPU: {cpu_percent:.1f}%")

            try:
                timeframes = ["15m", "1h", "4h", "1d"]
                signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes)
                for timeframe, signal in signals.items():
                    if signal and signal['confidence'] >= 60:
                        # Validate MACD
                        if signal['direction'] == "LONG" and signal.get('macd_status') != "bullish":
                            logger.warning(f"[Engine] [{symbol}] Invalid LONG signal with {signal.get('macd_status')} MACD, skipping")
                            continue
                        if signal['direction'] == "SHORT" and signal.get('macd_status') != "bearish":
                            logger.warning(f"[Engine] [{symbol}] Invalid SHORT signal with {signal.get('macd_status')} MACD, skipping")
                            continue
                        # Validate TP1 range
                        tp1_percent = abs(signal['tp1'] - signal['entry']) / signal['entry'] * 100
                        if not (0.5 <= tp1_percent <= 3.0):
                            logger.warning(f"[Engine] [{symbol}] TP1 out of 0.5-3% range ({tp1_percent:.2f}%), skipping")
                            continue
                        # Format signal message per user-specified format
                        message = (
                            f"📈 Trading Signal\n"
                            f"📊 Direction: {signal['direction']}\n"
                            f"⏰ Timeframe: {signal['timeframe']}\n"
                            f"⏳ Trade Duration: {signal['trade_duration']}\n"
                            f"💰 Entry Price: {signal['entry']:.4f}\n"
                            f"🎯 TP1: {signal['tp1']:.4f} ({signal['tp1_possibility']:.1f}%)\n"
                            f"🎯 TP2: {signal['tp2']:.4f} ({signal['tp2_possibility']:.1f}%)\n"
                            f"🎯 TP3: {signal['tp3']:.4f} ({signal['tp3_possibility']:.1f}%)\n"
                            f"🛑 SL: {signal['sl']:.4f}\n"
                            f"🔍 Confidence: {signal['confidence']:.2f}%\n"
                            f"⚡ Trade Type: {signal['trade_type']}\n"
                            f"📈 1 hour Volume: ${signal['volume']:,.2f}\n"
                            f"📈 24 Hour Volume: ${signal['quote_volume_24h']:,.2f}\n"
                            f"🔎 Conditions: {', '.join(signal['conditions'])}\n"
                            f"🕒 Timestamp: {signal['timestamp']}\n"
                            f"📊 Leverage: {signal['leverage']}x"
                        )
                        logger.info(f"[Engine] [{symbol}] Signal generated, sending to Telegram")
                        try:
                            await bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=message)
                            logger.info(f"[Engine] [{symbol}] Signal sent: {signal['direction']}, Confidence: {signal['confidence']:.2f}%")
                        except Exception as e:
                            logger.error(f"[Engine] [{symbol}] Error sending Telegram message: {str(e)}")
                            continue

                        # Track TP/SL status
                        status, hit_timestamp = await track_signal_status(signal, exchange)
                        signal['status'] = status
                        signal['hit_timestamp'] = hit_timestamp

                        # Save signal to CSV
                        signal_df = pd.DataFrame([signal])
                        signal_df.to_csv(f"{logs_dir}/signals_log_new.csv", mode="a", header=not os.path.exists(f"{logs_dir}/signals_log_new.csv"), index=False)
                        logger.info(f"[Engine] [{symbol}] Signal saved to CSV with status: {status}")
            except Exception as e:
                logger.error(f"[Engine] [{symbol}] Error analyzing symbol: {str(e)}")
                continue

            memory_after = psutil.Process().memory_info().rss / 1024 / 1024
            cpu_percent_after = psutil.cpu_percent(interval=0.1)
            memory_diff = memory_after - memory_before
            logger.info(f"[Engine] [{symbol}] After analysis - Memory: {memory_after:.2f} MB (Change: {memory_diff:.2f} MB), CPU: {cpu_percent_after:.1f}%")

        # Close exchange
        logger.info("[Engine] Closing exchange")
        try:
            await exchange.close()
            logger.info("[Engine] Exchange closed")
        except Exception as e:
            logger.error(f"[Engine] Error closing exchange: {str(e)}")

    except Exception as e:
        logger.error(f"[Engine] Unexpected error in run_engine: {str(e)}")
