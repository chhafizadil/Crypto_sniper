# Core engine module for running trading analysis and signal generation
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

# Main function to run the trading engine
async def run_engine():
    # Log engine startup
    logger.info("[Engine] Starting run_engine")

    try:
        # Check required environment variables
        required_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "BINANCE_API_KEY", "BINANCE_API_SECRET"]
        for var in required_vars:
            if not os.getenv(var):
                logger.error(f"[Engine] Missing environment variable: {var}")
                return

        # Check model file existence
        model_path = "models/rf_model.joblib"
        if not os.path.exists(model_path):
            logger.error(f"[Engine] Model file not found at {model_path}")
            return

        # Ensure logs directory exists
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

        # Load markets and filter USDT pairs
        try:
            await exchange.load_markets()
            symbols = [s for s in exchange.markets.keys() if s.endswith("/USDT")]
            logger.info(f"[Engine] Found {len(symbols)} USDT pairs")
        except Exception as e:
            logger.error(f"[Engine] Error loading markets: {str(e)}")
            return

        # Process symbols in batches
        for symbol in symbols[:20]:  # Limit to 20 symbols for stability
            memory_before = psutil.Process().memory_info().rss / 1024 / 1024
            cpu_percent = psutil.cpu_percent(interval=0.1)
            logger.info(f"[Engine] [{symbol}] Before analysis - Memory: {memory_before:.2f} MB, CPU: {cpu_percent:.1f}%")

            # Analyze symbol across multiple timeframes
            try:
                timeframes = ["15m", "1h", "4h", "1d"]
                signals = await analyze_symbol_multi_timeframe(symbol, exchange, timeframes)
                for timeframe, signal in signals.items():
                    if signal and signal['confidence'] >= 40:
                        # Validate MACD for LONG signals
                        if signal['direction'] == "LONG" and signal.get('macd_status') == "bearish":
                            logger.warning(f"[Engine] [{symbol}] Invalid LONG signal with bearish MACD, skipping")
                            continue
                        # Assign trade type dynamically
                        signal['trade_type'] = classify_trade(signal['confidence'], timeframe)
                        # Format signal message
                        message = (
                            f"🚨 {symbol} Trading Signal\n"
                            f"📊 Direction: {signal['direction']}\n"
                            f"⏰ Timeframe: {timeframe}\n"
                            f"💰 Entry Price: {signal['entry']:.4f}\n"
                            f"🎯 TP1: {signal['tp1']:.4f}\n"
                            f"🎯 TP2: {signal['tp2']:.4f}\n"
                            f"🎯 TP3: {signal['tp3']:.4f}\n"
                            f"🛑 SL: {signal['sl']:.4f}\n"
                            f"🔍 Confidence: {signal['confidence']:.2f}%\n"
                            f"⚡ Trade Type: {signal['trade_type']}\n"
                            f"🕒 Timestamp: {signal['timestamp']}"
                        )
                        logger.info(f"[Engine] [{symbol}] Signal generated, sending to Telegram")
                        try:
                            await bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=message)
                            logger.info(f"[Engine] [{symbol}] Signal sent: {signal['direction']}, Confidence: {signal['confidence']:.2f}%")
                        except Exception as e:
                            logger.error(f"[Engine] [{symbol}] Error sending Telegram message: {str(e)}")

                        # Save signal to CSV
                        signal_df = pd.DataFrame([signal])
                        signal_df.to_csv(f"{logs_dir}/signals_log.csv", mode="a", header=not os.path.exists(f"{logs_dir}/signals_log.csv"), index=False)
                        logger.info(f"[Engine] [{symbol}] Signal saved to CSV")
            except Exception as e:
                logger.error(f"[Engine] [{symbol}] Error analyzing symbol: {str(e)}")
                continue

            memory_after = psutil.Process().memory_info().rss / 1024 / 1024
            cpu_percent_after = psutil.cpu_percent(interval=0.1)
            memory_diff = memory_after - memory_before
            logger.info(f"[Engine] [{symbol}] After analysis - Memory: {memory_after:.2f} MB (Change: {memory_diff:.2f} MB), CPU: {cpu_percent_after:.1f}%")

        # Close exchange connection
        logger.info("[Engine] Closing exchange")
        try:
            await exchange.close()
            logger.info("[Engine] Exchange closed")
        except Exception as e:
            logger.error(f"[Engine] Error closing exchange: {str(e)}")

    except Exception as e:
        logger.error(f"[Engine] Unexpected error in run_engine: {str(e)}")
