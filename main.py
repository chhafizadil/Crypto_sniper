import asyncio
import uvicorn
from fastapi import FastAPI
from core.analysis import fetch_ohlcv, analyze_symbol
from core.indicators import calculate_indicators
import ccxt.async_support as ccxt
import os
import logging
from dotenv import load_dotenv
import telegram

# لاگنگ سیٹ اپ کرو
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("scanner")

# ماحولیاتی متغیرات لوڈ کرو
load_dotenv()

# FastAPI ایپ
app = FastAPI()

# کنفیڈنس اور TP1 کی حد (تمہارے ڈسپلے کے مطابق)
CONFIDENCE_THRESHOLD = 60  # 60% سے زیادہ کنفیڈنس
TP1_POSSIBILITY_THRESHOLD = 0.8  # 80% سے زیادہ TP1 امکان
SCALPING_CONFIDENCE_THRESHOLD = 85  # 85 سے کم کنفیڈنس اسکیلپنگ کے لیے

# ٹیلیگرام میسیج بھیجنے کا فنکشن
async def send_telegram_message(message):
    try:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not bot_token or not chat_id:
            logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing!")
            return
        bot = telegram.Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message)
        logger.info("Telegram message sent successfully.")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

# ہیلتھ چیک اینڈ پوائنٹ (روٹ)
@app.get("/")
async def root():
    return {"message": "Crypto Signal Bot is running."}

# ہیلتھ چیک اینڈ پوائنٹ (Koyeb کے لیے)
@app.get("/health")
async def health():
    return {"status": "healthy", "message": "Bot is operational."}

# بائننس سے تمام USDT پیئرز لینے کا فنکشن
async def get_valid_symbols(exchange):
    try:
        markets = await exchange.load_markets()
        # صرف USDT پیئرز فلٹر کرو
        usdt_symbols = [s for s in markets.keys() if s.endswith('/USDT')]
        logger.info(f"Found {len(usdt_symbols)} USDT pairs")
        return usdt_symbols
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []
    finally:
        await exchange.close()

# سگنلز سکین کرنے کا فنکشن
async def scan_symbols():
    # بائننس ایکسچینج سیٹ اپ کرو
    exchange = ccxt.binance({
        'apiKey': os.getenv("BINANCE_API_KEY"),
        'secret': os.getenv("BINANCE_API_SECRET"),
        'enableRateLimit': True,  # API ریٹ لمٹ سے بچاؤ
    })

    # API کیز چیک کرو
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        logger.error("API Key or Secret is missing! Check Koyeb Config Vars.")
        return

    try:
        # API کنکشن ٹیسٹ کرو
        try:
            await exchange.fetch_ticker('BTC/USDT')
            logger.info("Binance API connection successful.")
        except Exception as e:
            logger.error(f"Binance API connection failed: {e}")
            return

        # ٹریڈنگ پیئرز لے لو
        symbols = await get_valid_symbols(exchange)
        if not symbols:
            logger.error("No valid USDT symbols found!")
            return

        for symbol in symbols:
            try:
                # ڈیٹا اور تجزیہ کرو
                result = await analyze_symbol(exchange, symbol)
                if not result or not result.get('signal'):
                    logger.info(f"⚠️ {symbol} - No valid signal")
                    continue

                confidence = result.get("confidence", 0)
                tp1_possibility = result.get("tp1_chance", 0)
                direction = result.get("signal", "none")
                trade_type = "Scalping" if confidence < SCALPING_CONFIDENCE_THRESHOLD else "Normal"

                # تمہارے ڈسپلے کے مطابق لاگنگ
                logger.info(
                    f"🔍 {symbol} | Confidence: {confidence:.2f} | "
                    f"Direction: {direction} | TP1 Chance: {tp1_possibility:.2f}"
                )

                # اگر کنفیڈنس اور TP1 امکان حد سے زیادہ ہو، تو میسیج بھیجو
                if confidence >= CONFIDENCE_THRESHOLD and tp1_possibility >= TP1_POSSIBILITY_THRESHOLD:
                    message = (
                        f"🚀 {symbol}\n"
                        f"Trade Type: {trade_type}\n"
                        f"Direction: {direction}\n"
                        f"Confidence: {confidence:.2f}\n"
                        f"TP1 Possibility: {tp1_possibility:.2f}"
                    )
                    await send_telegram_message(message)
                    logger.info("✅ Signal SENT ✅")
                elif confidence < CONFIDENCE_THRESHOLD:
                    logger.info("⚠️ Skipped - Low confidence")
                elif tp1_possibility < TP1_POSSIBILITY_THRESHOLD:
                    logger.info("⚠️ Skipped - Low TP1 possibility")

                logger.info("---")

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")

    except Exception as e:
        logger.error(f"Error in scan_symbols: {e}")
    finally:
        await exchange.close()

# بوٹ کو مسلسل چلانے کا فنکشن
async def run_bot():
    while True:
        try:
            await scan_symbols()
        except Exception as e:
            logger.error(f"Error in run_bot: {e}")
        await asyncio.sleep(60)  # ہر منٹ سکین کرو

# مین ایپلیکیشن
if __name__ == "__main__":
    # API کیز کی دستیابی چیک کرو
    if not os.getenv("BINANCE_API_KEY") or not os.getenv("BINANCE_API_SECRET"):
        logger.error("BINANCE_API_KEY or BINANCE_API_SECRET not set in environment!")
        exit(1)

    loop = asyncio.get_event_loop()
    loop.create_task(run_bot())
    uvicorn.run(app, host="0.0.0.0", port=8000)
