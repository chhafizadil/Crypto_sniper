# telebot/report_generator.py
import pandas as pd
from datetime import datetime, timedelta
from telebot.sender import send_telegram_signal
from utils.logger import logger

async def generate_daily_summary():
    try:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        
        try:
            df = pd.read_csv('logs/signals_log_new.csv')
            if df.empty:
                logger.info("No signals found in CSV")
                message = (
                    f"📊 *Daily Trading Summary* ({today.strftime('%Y-%m-%d')})\n\n"
                    f"📈 *Total Signals*: 0\n"
                    f"📅 *Yesterday's Signals*: 0\n"
                    f"🚀 *Long Signals*: 0\n"
                    f"📉 *Short Signals*: 0\n"
                    f"🎯 *Successful Signals*: 0 (0.00%)\n"
                    f"🔍 *Average Confidence*: 0.00%\n"
                    f"🏆 *Top Symbol*: None\n"
                    f"📊 *Most Active Timeframe*: None\n"
                    f"⚡ *Total Volume Analyzed*: 0 (USDT)\n"
                    f"🔎 *Signal Status Breakdown*:\n"
                    f"   - TP1 Hit: 0\n"
                    f"   - TP2 Hit: 0\n"
                    f"   - TP3 Hit: 0\n"
                    f"   - SL Hit: 0\n"
                    f"   - Pending: 0\n"
                    f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                await send_telegram_signal("Daily Summary", {"message": message})
                return
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        except FileNotFoundError:
            logger.error("Signals log file not found")
            message = (
                f"📊 *Daily Trading Summary* ({today.strftime('%Y-%m-%d')})\n\n"
                f"📈 *Total Signals*: 0\n"
                f"📅 *Yesterday's Signals*: 0\n"
                f"🚀 *Long Signals*: 0\n"
                f"📉 *Short Signals*: 0\n"
                f"🎯 *Successful Signals*: 0 (0.00%)\n"
                f"🔍 *Average Confidence*: 0.00%\n"
                f"🏆 *Top Symbol*: None\n"
                f"📊 *Most Active Timeframe*: None\n"
                f"⚡ *Total Volume Analyzed*: 0 (USDT)\n"
                f"🔎 *Signal Status Breakdown*:\n"
                f"   - TP1 Hit: 0\n"
                f"   - TP2 Hit: 0\n"
                f"   - TP3 Hit: 0\n"
                f"   - SL Hit: 0\n"
                f"   - Pending: 0\n"
                f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await send_telegram_signal("Daily Summary", {"message": message})
            return
        
        today_signals = df[df['timestamp'].dt.date == today.date()]
        yesterday_signals = df[df['timestamp'].dt.date == yesterday.date()]
        
        total_signals = len(today_signals)
        total_yesterday = len(yesterday_signals)
        
        long_signals = today_signals[today_signals['direction'] == 'LONG']
        short_signals = today_signals[today_signals['direction'] == 'SHORT']
        
        avg_confidence = today_signals['confidence'].mean() if total_signals > 0 else 0
        long_count = len(long_signals)
        short_count = len(short_signals)
        
        successful_signals = today_signals[today_signals['status'].isin(['tp1', 'tp2', 'tp3'])]
        success_count = len(successful_signals)
        success_rate = (success_count / total_signals * 100) if total_signals > 0 else 0
        
        top_symbol = today_signals.groupby('symbol').size().idxmax() if total_signals > 0 else "None"
        most_active_timeframe = today_signals.groupby('timeframe').size().idxmax() if total_signals > 0 else "None"
        total_volume = today_signals['volume'].sum() if total_signals > 0 else 0
        
        status_breakdown = today_signals['status'].value_counts().to_dict()
        tp1_count = status_breakdown.get('tp1', 0)
        tp2_count = status_breakdown.get('tp2', 0)
        tp3_count = status_breakdown.get('tp3', 0)
        sl_count = status_breakdown.get('sl', 0)
        pending_count = status_breakdown.get('pending', 0)
        
        message = (
            f"📊 *Daily Trading Summary* ({today.strftime('%Y-%m-%d')})\n\n"
            f"📈 *Total Signals*: {total_signals}\n"
            f"📅 *Yesterday's Signals*: {total_yesterday}\n"
            f"🚀 *Long Signals*: {long_count}\n"
            f"📉 *Short Signals*: {short_count}\n"
            f"🎯 *Successful Signals*: {success_count} ({success_rate:.2f}%)\n"
            f"🔍 *Average Confidence*: {avg_confidence:.2f}%\n"
            f"🏆 *Top Symbol*: {top_symbol}\n"
            f"📊 *Most Active Timeframe*: {most_active_timeframe}\n"
            f"⚡ *Total Volume Analyzed*: {total_volume:.2f} (USDT)\n"
            f"🔎 *Signal Status Breakdown*:\n"
            f"   - TP1 Hit: {tp1_count}\n"
            f"   - TP2 Hit: {tp2_count}\n"
            f"   - TP3 Hit: {tp3_count}\n"
            f"   - SL Hit: {sl_count}\n"
            f"   - Pending: {pending_count}\n"
            f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        await send_telegram_signal("Daily Summary", {"message": message})
        logger.info("Daily summary sent to Telegram")
    except Exception as e:
        logger.error(f"Error generating daily summary: {str(e)}")
