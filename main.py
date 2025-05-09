import asyncio
import uvicorn
from fastapi import FastAPI
from core.analysis import analyze_symbol
import ccxt.async_support as ccxt
import os
import logging
from dotenv import load_dotenv
import telegram

# لاگنگ سیٹ اپ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("scanner")

# .env فائل سے ماحولیاتی ویری ایبل لوڈ کرو
load_dotenv()

# FastAPI ایپ
app = FastAPI()

# سگنل کی حدیں
CONFIDENCE_THRESHOLD = 40  # نارمل سگنل کے لیے کم از کم 40%
TP1_POSSIBILITY_THRESHOLD = 0.6  # TP1 امکان کم از کم 60%
SCALPING_CONFIDENCE_THRESHOLD = 65  # اس سے کم ہو تو Scalping Trade

# ٹیلیگرام پر میسج بھیجنے والا فنکشن
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

# روٹ ہیلتھ چیک
@app.get("/")
async def root():
    return {"message": "Crypto Signal Bot is running."}

# Koyeb کے لیے ہیلتھ چیک
@app.get("/health")
async def health():
    return {"status": "healthy", "message": "Bot is operational."}

# تمام USDT پیئرز حاصل کرو
async def get_valid_symbols(exchange):
    try:
        markets = await exchange.load_markets()
        usdt_symbols = [s for s in markets.keys() if s.endswith('/USDT')]
        logger.info(f"Found {len(usdt_symbols)} USDT pairs")
        return usdt_symbols
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []
    finally:
        await exchange.close()

# سگنل سکین فنکشن
async def scan_symbols():
    exchange = ccxt.binance({
        'apiKey': os.getenv("BINANCE_API_KEY"),
        'secret': os.getenv("BINANCE_API_SECRET"),
        'enableRateLimit': True,
    })

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        logger.error("API Key or Secret is missing! Check Koyeb Config Vars.")
        return

    try:
        # کنکشن ٹیسٹ
        try:
            await exchange.fetch_ticker('BTC/USDT')
            logger.info("Binance API connection successful.")
        except Exception as e:
            logger.error(f"Binance API connection failed: {e}")
            return

        # تمام USDT symbols حاصل کرو
        symbols = await get_valid_symbols(exchange)
        if not symbols:
            logger.error("No valid USDT symbols found!")
            return

        for symbol in symbols:
            try:
                result = await analyze_symbol(exchange, symbol)
                if not result:
                    logger.info(f"⚠️ {symbol} - No valid signal")
                    continue

                confidence = result.get("confidence", 0)
                tp1_possibility = result.get("tp1_possibility", 0)
                direction = result.get("direction", "none")
                trade_type = "Scalping" if confidence < SCALPING_CONFIDENCE_THRESHOLD else "Normal"

                logger.info(
                    f"🔍 {symbol} | Confidence: {confidence:.2f} | "
                    f"Direction: {direction} | TP1 Chance: {tp1_possibility:.2f}"
                )

                if confidence >= CONFIDENCE_THRESHOLD and tp1_possibility >= TP1_POSSIBILITY_THRESHOLD:
                    message = (
                        f"🚀 {symbol}\n"
                        f"Trade Type: {trade_type}\n"
                        f"Direction: {direction}\n"
                        f"Entry: {result['entry']:.2f}\n"
                        f"TP1: {result['tp1']:.2f}\n"
                        f"TP2: {result['tp2']:.2f}\n"
                        f"TP3: {result['tp3']:.2f}\n"
                        f"SL: {result['sl']:.2f}\n"
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

# مسلسل سکینر چلانے والا فنکشن
async def run_bot():
    while True:
        try:
            await scan_symbols()
        except Exception as e:
            logger.error(f"Error in run_bot: {e}")
        await asyncio.sleep(60)  # ہر 60 سیکنڈ بعد دوبارہ سکین کرو

# جب ایپ اسٹارٹ ہو تو سکینر چلاؤ
@app.on_event("startup")
async def start_bot():
    asyncio.create_task(run_bot())

# ایپ رن کرو
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
