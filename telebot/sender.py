import telegram
import asyncio
from telegram.ext import Application, CommandHandler
from telegram.error import Conflict
from utils.logger import logger
from telebot.report_generator import generate_daily_summary

# Hard-coded Telegram bot token and chat ID
BOT_TOKEN = "7620836100:AAGY7xBjNJMKlzrDDMrQ5hblXzd_k_BvEtU"
CHAT_ID = "-4694205383"

async def start(update, context):
    await update.message.reply_text("Crypto Signal Bot is running! Use /summary to get daily report.")

async def summary(update, context):
    report = await generate_daily_summary()
    if report:
        await update.message.reply_text(report, parse_mode='Markdown')
    else:
        await update.message.reply_text("No signals available for yesterday.")

async def send_signal(signal):
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        
        conditions_str = ", ".join(signal.get('conditions', [])) or "None"
        message = (
            f"📈 *{signal['symbol']} - {signal['direction']} ({signal['timeframe']})*\n"
            f"Confidence: {signal['confidence']:.2f}%\n"
            f"Entry: ${signal['entry']:.2f}\n"
            f"Take Profit 1: ${signal['tp1']:.2f} ({signal['tp1_possibility']:.1f}%)\n"
            f"Take Profit 2: ${signal['tp2']:.2f} ({signal['tp2_possibility']:.1f}%)\n"
            f"Take Profit 3: ${signal['tp3']:.2f} ({signal['tp3_possibility']:.1f}%)\n"
            f"Stop Loss: ${signal['sl']:.2f}\n"
            f"Volume: ${signal['volume']:,.2f}\n"
            f"Trade Type: {signal.get('trade_type', 'Unknown')}\n"
            f"Conditions: {conditions_str}\n"
            f"Timestamp: {signal['timestamp']}"
        )
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
        logger.info(f"Signal sent to Telegram: {signal['symbol']} - {signal['direction']}")
    except Exception as e:
        logger.error(f"Error sending signal to Telegram: {str(e)}")

async def start_bot():
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        
        # Forcefully delete webhook and clear pending updates
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Telegram webhook deleted successfully")
        
        # Verify webhook is deleted
        webhook_info = await bot.get_webhook_info()
        if not webhook_info.url:
            logger.info("Webhook confirmed deleted with no pending updates")
        
        # Clear all pending updates with retries
        for _ in range(5):  # Retry 5 times
            try:
                await bot.get_updates(offset=-1, timeout=5)
                logger.info("Pending updates cleared via getUpdates")
                break
            except Conflict as e:
                logger.warning(f"Conflict while clearing updates: {str(e)}")
                await asyncio.sleep(3)  # 3 seconds for stability
        
        # Start polling with single instance
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("summary", summary))
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            drop_pending_updates=True,
            poll_interval=4.0,  # Stable polling interval
            timeout=15,  # Increased for better handling
            error_callback=lambda e: logger.error(f"Polling error: {str(e)}")
        )
        logger.info("Telegram polling started successfully")
    except Exception as e:
        logger.error(f"Error starting Telegram bot: {str(e)}")
