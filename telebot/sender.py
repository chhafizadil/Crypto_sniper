# Telegram bot sender module to handle signal notifications and commands
# Updated to fix /report, /summary, /signal, /status commands, handle empty CSV, and add Top Symbol
import telegram
import asyncio
import pandas as pd
import psutil
import os  # Added for file existence checks
from telegram.ext import Application, CommandHandler
from telegram.error import Conflict
from utils.logger import logger
from datetime import datetime, timedelta

# Hard-coded Telegram bot token and chat ID
BOT_TOKEN = "7620836100:AAGY7xBjNJMKlzrDDMrQ5hblXzd_k_BvEtU"
CHAT_ID = "-4694205383"

async def start(update, context):
    # Start command to initialize bot
    await update.message.reply_text("Crypto Signal Bot is running! Use /summary or /report for daily report, /status for bot health, /signal for latest signal, or /help for commands.")

async def status(update, context):
    # Status command to check bot health
    # Reports memory, CPU, and last signal time with robust error handling
    try:
        memory = psutil.Process().memory_info().rss / 1024 / 1024  # Memory usage in MB
        cpu = psutil.cpu_percent(interval=0.1)  # CPU usage percentage
        file_path = 'logs/signals_log_new.csv'
        last_signal = "No signals yet"
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                if not df.empty:
                    last_signal = df['timestamp'].iloc[-1]
            except Exception as e:
                logger.warning(f"Error reading CSV for status: {str(e)}")
                last_signal = "Error reading signals log"
        message = (
            f"🩺 Bot Status\n"
            f"📊 Memory Usage: {memory:.2f} MB\n"
            f"⚡ CPU Usage: {cpu:.1f}%\n"
            f"🕒 Last Signal: {last_signal}"
        )
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error generating status: {str(e)}")
        await update.message.reply_text("Error checking status. Please check logs.")

async def signal(update, context):
    # Signal command to fetch latest signal
    # Updated to handle missing conditions column and empty CSV
    try:
        file_path = 'logs/signals_log_new.csv'
        if not os.path.exists(file_path):
            await update.message.reply_text("No signals available.")
            return
        df = pd.read_csv(file_path)
        if df.empty:
            await update.message.reply_text("No signals available.")
            return
        latest_signal = df.iloc[-1]
        # Handle missing conditions column
        conditions_str = latest_signal.get('conditions', 'None') if 'conditions' in latest_signal else 'None'
        message = (
            f"📈 Trading Signal\n"
            f"📊 Direction: {latest_signal['direction']}\n"
            f"⏰ Timeframe: {latest_signal['timeframe']}\n"
            f"⏳ Trade Duration: {latest_signal['trade_duration']}\n"
            f"💰 Entry Price: {latest_signal['entry']:.4f}\n"
            f"🎯 TP1: {latest_signal['tp1']:.4f} ({latest_signal['tp1_possibility']:.1f}%)\n"
            f"🎯 TP2: {latest_signal['tp2']:.4f} ({latest_signal['tp2_possibility']:.1f}%)\n"
            f"🎯 TP3: {latest_signal['tp3']:.4f} ({latest_signal['tp3_possibility']:.1f}%)\n"
            f"🛑 SL: {latest_signal['sl']:.4f}\n"
            f"🔍 Confidence: {latest_signal['confidence']:.2f}%\n"
            f"⚡ Trade Type: {latest_signal['trade_type']}\n"
            f"📈 1 hour Volume: ${latest_signal['volume']:,.2f}\n"
            f"📈 24 Hour Volume: ${latest_signal['quote_volume_24h']:,.2f}\n"
            f"🔎 Conditions: {conditions_str}\n"
            f"🕒 Timestamp: {latest_signal['timestamp']}\n"
            f"📊 Leverage: {latest_signal['leverage']}x\n"
            f"📈 BTC Trend: {latest_signal['btc_trend']:.2f}%\n"
            f"📊 MA200: {latest_signal['ma200_status']}"
        )
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error fetching latest signal: {str(e)}")
        await update.message.reply_text("Error fetching latest signal. Please check logs.")

async def help(update, context):
    # Help command to list available commands
    message = (
        "📚 Available Commands:\n"
        "/start - Initialize the bot\n"
        "/summary - Get daily trading summary\n"
        "/report - Get daily trading summary (same as /summary)\n"
        "/status - Check bot health\n"
        "/signal - Get latest signal\n"
        "/help - List all commands"
    )
    await update.message.reply_text(message)

async def generate_daily_summary():
    # Generate daily trading summary in user-specified format
    # Updated to handle empty CSV, add Top Symbol, and fix error handling
    try:
        file_path = 'logs/signals_log_new.csv'
        if not os.path.exists(file_path):
            logger.warning("Signals log file not found")
            return (
                f"📊 Daily Trading Summary ({datetime.utcnow().date()})\n"
                f"📈 Total Signals: 0\n"
                f"📅 Yesterday's Signals: 0\n"
                f"🚀 Long Signals: 0\n"
                f"📉 Short Signals: 0\n"
                f"🎯 Successful Signals: 0 (0.00%)\n"
                f"🔍 Average Confidence: 0.00%\n"
                f"🏆 Top Symbol: None\n"
                f"📊 Most Active Timeframe: None\n"
                f"⚡ Total Volume Analyzed: 0 (USDT)\n"
                f"🔎 Signal Status Breakdown:\n"
                f"   - TP1 Hit: 0\n"
                f"   - TP2 Hit: 0\n"
                f"   - TP3 Hit: 0\n"
                f"   - SL Hit: 0\n"
                f"   - Pending: 0\n"
                f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

        df = pd.read_csv(file_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        today = datetime.utcnow().date()
        df_today = df[df['timestamp'].dt.date == today]

        if df_today.empty:
            logger.info("No signals found for today")
            return (
                f"📊 Daily Trading Summary ({today})\n"
                f"📈 Total Signals: 0\n"
                f"📅 Yesterday's Signals: 0\n"
                f"🚀 Long Signals: 0\n"
                f"📉 Short Signals: 0\n"
                f"🎯 Successful Signals: 0 (0.00%)\n"
                f"🔍 Average Confidence: 0.00%\n"
                f"🏆 Top Symbol: None\n"
                f"📊 Most Active Timeframe: None\n"
                f"⚡ Total Volume Analyzed: 0 (USDT)\n"
                f"🔎 Signal Status Breakdown:\n"
                f"   - TP1 Hit: 0\n"
                f"   - TP2 Hit: 0\n"
                f"   - TP3 Hit: 0\n"
                f"   - SL Hit: 0\n"
                f"   - Pending: 0\n"
                f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

        yesterday = (datetime.utcnow() - timedelta(days=1)).date()
        df_yesterday = df[df['timestamp'].dt.date == yesterday]

        total_signals = len(df_today)
        long_signals = len(df_today[df_today['direction'] == 'LONG'])
        short_signals = len(df_today[df_today['direction'] == 'SHORT'])
        successful_signals = len(df_today[df_today['status'].isin(['tp1_hit', 'tp2_hit', 'tp3_hit'])])
        tp1_hits = len(df_today[df_today['status'] == 'tp1_hit'])
        tp2_hits = len(df_today[df_today['status'] == 'tp2_hit'])
        tp3_hits = len(df_today[df_today['status'] == 'tp3_hit'])
        sl_hits = len(df_today[df_today['status'] == 'sl_hit'])
        pending_signals = len(df_today[df_today['status'] == 'pending'])
        avg_confidence = df_today['confidence'].mean() if total_signals > 0 else 0
        most_active_timeframe = df_today['timeframe'].mode()[0] if total_signals > 0 else "None"
        total_volume = df_today['quote_volume_24h'].sum() if 'quote_volume_24h' in df_today else 0
        # Added Top Symbol calculation based on most frequent symbol
        top_symbol = df_today['symbol'].mode()[0] if total_signals > 0 else "None"

        successful_percentage = (successful_signals / total_signals * 100) if total_signals > 0 else 0

        report = (
            f"📊 Daily Trading Summary ({today})\n"
            f"📈 Total Signals: {total_signals}\n"
            f"📅 Yesterday's Signals: {len(df_yesterday)}\n"
            f"🚀 Long Signals: {long_signals}\n"
            f"📉 Short Signals: {short_signals}\n"
            f"🎯 Successful Signals: {successful_signals} ({successful_percentage:.2f}%)\n"
            f"🔍 Average Confidence: {avg_confidence:.2f}%\n"
            f"🏆 Top Symbol: {top_symbol}\n"
            f"📊 Most Active Timeframe: {most_active_timeframe}\n"
            f"⚡ Total Volume Analyzed: {total_volume:,.0f} (USDT)\n"
            f"🔎 Signal Status Breakdown:\n"
            f"   - TP1 Hit: {tp1_hits}\n"
            f"   - TP2 Hit: {tp2_hits}\n"
            f"   - TP3 Hit: {tp3_hits}\n"
            f"   - SL Hit: {sl_hits}\n"
            f"   - Pending: {pending_signals}\n"
            f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        logger.info("Daily report generated successfully")
        return report
    except Exception as e:
        logger.error(f"Error generating daily report: {str(e)}")
        return (
            f"📊 Daily Trading Summary ({datetime.utcnow().date()})\n"
            f"⚠️ Error generating report: Please check logs\n"
            f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

async def summary(update, context):
    # Handle /summary command for daily report
    # Added chat ID validation for security
    if str(update.message.chat_id) != CHAT_ID:
        await update.message.reply_text("Unauthorized access.")
        return
    report = await generate_daily_summary()
    await update.message.reply_text(report)

async def report(update, context):
    # Handle /report command (same as /summary)
    # Updated to ensure consistent report format
    if str(update.message.chat_id) != CHAT_ID:
        await update.message.reply_text("Unauthorized access.")
        return
    report = await generate_daily_summary()
    await update.message.reply_text(report)

async def send_signal(signal):
    # Send signal to Telegram with user-specified format
    # Updated to handle missing conditions and ensure btc_trend is included
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        conditions_str = ", ".join(signal.get('conditions', [])) or "None"
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
            f"🔎 Conditions: {conditions_str}\n"
            f"🕒 Timestamp: {signal['timestamp']}\n"
            f"📊 Leverage: {signal['leverage']}x\n"
            f"📈 BTC Trend: {signal['btc_trend']:.2f}%\n"
            f"📊 MA200: {signal['ma200_status']}"
        )
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info(f"Signal sent to Telegram: {signal['direction']}")
    except Exception as e:
        logger.error(f"Error sending signal to Telegram: {str(e)}")

async def schedule_daily_report():
    # Schedule daily report at 00:00 UTC
    # Sends report to Telegram using generate_daily_summary
    while True:
        try:
            now = datetime.utcnow()
            next_report = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if now.hour >= 0:
                next_report += timedelta(days=1)
            wait_seconds = (next_report - now).total_seconds()
            logger.info(f"Waiting {wait_seconds:.0f} seconds for next daily report")
            await asyncio.sleep(wait_seconds)
            report = await generate_daily_summary()
            if report:
                bot = telegram.Bot(token=BOT_TOKEN)
                await bot.send_message(chat_id=CHAT_ID, text=report)
                logger.info("Daily report sent to Telegram")
        except Exception as e:
            logger.error(f"Error in scheduled report: {str(e)}")
            await asyncio.sleep(60)  # Retry after 1 minute

async def start_bot():
    # Start Telegram bot with polling and scheduled reports
    # Added robust error handling and conflict resolution
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Telegram webhook deleted successfully")
        webhook_info = await bot.get_webhook_info()
        if not webhook_info.url:
            logger.info("Webhook confirmed deleted with no pending updates")
        for _ in range(5):
            try:
                await bot.get_updates(offset=-1, timeout=5)
                logger.info("Pending updates cleared via getUpdates")
                break
            except Conflict as e:
                logger.warning(f"Conflict while clearing updates: {str(e)}")
                await asyncio.sleep(3)
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("summary", summary))
        application.add_handler(CommandHandler("report", report))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("signal", signal))
        application.add_handler(CommandHandler("help", help))
        await application.initialize()
        await application.start()
        # Start scheduled daily report
        asyncio.create_task(schedule_daily_report())
        await application.updater.start_polling(
            drop_pending_updates=True,
            poll_interval=4.0,
            timeout=15,
            error_callback=lambda e: logger.error(f"Polling error: {str(e)}")
        )
        logger.info("Telegram polling started successfully")
    except Exception as e:
        logger.error(f"Error starting Telegram bot: {str(e)}")
        await asyncio.sleep(60)  # Retry after 1 minute
