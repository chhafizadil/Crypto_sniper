import os
import telegram
from telegram.ext import Application, CommandHandler
from telegram.error import Conflict
from utils.logger import logger
from dotenv import load_dotenv
from telebot.report_generator import generate_daily_summary

load_dotenv()

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
        bot = telegram.Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
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
        await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        logger.info(f"Signal sent to Telegram: {signal['symbol']} - {signal['direction']}")
    except Exception as e:
        logger.error(f"Error sending signal to Telegram: {str(e)}")

async def start_bot():
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        bot = telegram.Bot(token=bot_token)
        
        # Delete webhook to ensure polling mode
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Telegram webhook deleted successfully")
        
        # Confirm webhook is deleted
        webhook_info = await bot.get_webhook_info()
        if not webhook_info.url:
            logger.info("Webhook confirmed deleted with no pending updates")
        
        # Clear any pending updates
        await bot.get_updates(offset=-1)
        logger.info("Pending updates cleared via getUpdates")
        
        # Start polling with Application
        application = Application.builder().token(bot_token).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("summary", summary))
        
        # Start polling with error handling
        try:
            await application.initialize()
            await application.start()
            await application.updater.start_polling(
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=10,
                error_callback=lambda e: logger.error(f"Polling error: {str(e)}")
            )
            logger.info("Telegram polling started successfully")
        except Conflict as e:
            logger.error(f"Conflict in polling: {str(e)}. Ensure only one bot instance is running.")
            # Attempt to recover by clearing updates
            await bot.get_updates(offset=-1)
            await application.updater.start_polling(
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=10
            )
    except Exception as e:
        logger.error(f"Error starting Telegram bot: {str(e)}")
