import polars as pl
import httpx
import asyncio
from datetime import datetime
import pytz
import os
from utils.logger import logger
from model.predictor import SignalPredictor

BOT_TOKEN = "7620836100:AAEEe4yAP18Lxxj0HoYfH8aeX4PetAxYsV0"
CHAT_ID = "-4694205383"

async def send_telegram_message(message: str):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }

        async with httpx.AsyncClient() as client:
            for attempt in range(3):
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        logger.info("Telegram message sent successfully")
                        log_report_status(True, "Success")
                        return
                    else:
                        logger.error(f"Failed to send Telegram message: {response.text}")
                        log_report_status(False, response.text)
                except Exception as e:
                    logger.error(f"Error sending Telegram message: {e}")
                    log_report_status(False, str(e))
                await asyncio.sleep(2)

            logger.error("Failed to send daily report after 3 attempts")
    except Exception as e:
        logger.error(f"Error in send_telegram_message: {e}")
        log_report_status(False, str(e))

def log_report_status(success: bool, message: str):
    try:
        csv_path = "logs/report_status.csv"
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        data = pl.DataFrame({
            "success": [success],
            "message": [message],
            "timestamp": [timestamp]
        })

        if os.path.exists(csv_path):
            old_df = pl.read_csv(csv_path, columns=['success', 'message', 'timestamp'])
            if not data.is_empty():
                data = old_df.vstack(data)

        if not data.is_empty():
            data.write_csv(csv_path)
            logger.info(f"Report status logged: Success={success}")
        else:
            logger.error("No valid data to log report status")
    except Exception as e:
        logger.error(f"Error logging report status: {e}")

async def generate_daily_summary():
    try:
        predictor = SignalPredictor()
        columns = [
            'timestamp', 'symbol', 'direction', 'price', 'tp1', 'tp2', 'tp3', 'sl',
            'volume', 'confidence', 'tp1_possibility', 'tp2_possibility', 'tp3_possibility',
            'timeframe', 'status', 'trade_type', 'hit_timestamp'
        ]
        df = pl.read_csv("logs/signals_log_new.csv", columns=columns)
        today = datetime.utcnow().date()
        df = df.with_columns(pl.col("timestamp").cast(pl.DateTime))

        # Update signal statuses
        for row in df.rows(named=True):
            if row['status'] == "pending":
                status = await predictor.check_signal_status(row['symbol'], row)
                if status != "pending":
                    df = df.with_columns(
                        pl.when(pl.col("symbol") == row['symbol']).then(status).otherwise(pl.col("status")).alias("status"),
                        pl.when(pl.col("symbol") == row['symbol']).then(datetime.utcnow()).otherwise(pl.col("hit_timestamp")).alias("hit_timestamp")
                    )

        # Save updated signals
        df.write_csv("logs/signals_log_new.csv")

        # Filter signals
        today_signals = df.filter(
            (pl.col("timestamp").dt.date() == today) &
            (pl.col("price") > 0) &
            (pl.col("tp1") > 0) &
            (pl.col("tp2") > 0) &
            (pl.col("tp3") > 0) &
            (pl.col("sl") > 0) &
            (pl.col("volume") >= 3000000) &
            (pl.col("confidence") >= 70) &
            (pl.col("tp1_possibility") >= 0.70) &
            (pl.col("status").is_in(["tp1", "tp2", "tp3", "sl"]))
        )

        if today_signals.is_empty():
            summary = f"📋 *Daily Report ({today})*\n\nNo valid signals generated today."
            await send_telegram_message(summary)
            logger.info("Daily Report Sent (No signals)")
            return

        total = len(today_signals)
        long_signals = len(today_signals.filter(pl.col("direction") == "LONG"))
        short_signals = len(today_signals.filter(pl.col("direction") == "SHORT"))
        scalping_signals = len(today_signals.filter(pl.col("trade_type") == "Scalping"))
        normal_signals = len(today_signals.filter(pl.col("trade_type") == "Normal"))
        tp1_hits = len(today_signals.filter(pl.col("status") == "tp1"))
        tp2_hits = len(today_signals.filter(pl.col("status") == "tp2"))
        tp3_hits = len(today_signals.filter(pl.col("status") == "tp3"))
        sl_hits = len(today_signals.filter(pl.col("status") == "sl"))

        total_hits = tp1_hits + tp2_hits + tp3_hits
        accuracy = round((total_hits / total * 100) if total > 0 else 0, 2)

        avg_tp1_chance = round(today_signals["tp1_possibility"].mean() * 100, 2)
        avg_tp2_chance = round(today_signals["tp2_possibility"].mean() * 100, 2)
        avg_tp3_chance = round(today_signals["tp3_possibility"].mean() * 100, 2)

        # Top performing symbols
        successful_pairs = today_signals.filter(pl.col("status").is_in(["tp1", "tp2", "tp3"]))
        top_pairs = successful_pairs.group_by("symbol").agg(
            tp1_hits=pl.col("status").eq("tp1").sum(),
            tp2_hits=pl.col("status").eq("tp2").sum(),
            tp3_hits=pl.col("status").eq("tp3").sum()
        ).sort(pl.col("tp1_hits") + pl.col("tp2_hits") + pl.col("tp3_hits"), descending=True).head(3)
        top_pairs_str = "\n".join([
            f"{row['symbol']}: {row['tp1_hits']} TP1, {row['tp2_hits']} TP2, {row['tp3_hits']} TP3"
            for row in top_pairs.to_dicts()
        ]) if not top_pairs.is_empty() else "None"

        # Average trade duration
        durations = {
            "tp1": [],
            "tp2": [],
            "tp3": [],
            "sl": []
        }
        for row in today_signals.rows(named=True):
            if row['hit_timestamp'] and row['status'] != "pending":
                duration = (pd.to_datetime(row['hit_timestamp']) - pd.to_datetime(row['timestamp'])).total_seconds() / 3600
                durations[row['status']].append(duration)
        
        avg_durations = {
            key: round(sum(values) / len(values), 1) if values else 0
            for key, values in durations.items()
        }

        # Market trend summary
        short_percentage = round((short_signals / total * 100) if total > 0 else 0, 2)
        market_trend = "Bearish Market" if short_percentage >= 60 else "Bullish Market" if short_percentage <= 40 else "Neutral Market"

        # Success by timeframe
        timeframe_success = today_signals.group_by("timeframe").agg(
            tp1_hits=pl.col("status").eq("tp1").sum(),
            total=pl.count()
        ).with_columns(
            success_rate=pl.col("tp1_hits") / pl.col("total") * 100
        ).sort("success_rate", descending=True)
        timeframe_str = "\n".join([
            f"{row['timeframe']}: {row['success_rate']:.0f}% TP1 Hits"
            for row in timeframe_success.to_dicts()
        ]) if not timeframe_success.is_empty() else "N/A"

        # Backtest success rate
        backtest_success = len(today_signals.filter(pl.col("confidence") >= 70))
        backtest_rate = round((backtest_success / total * 100) if total > 0 else 0, 2)

        # Invalid signals warning
        zero_signals = df.filter(
            (pl.col("timestamp").dt.date() == today) &
            ((pl.col("price") == 0) | (pl.col("tp1") == 0) | (pl.col("tp2") == 0) |
             (pl.col("tp3") == 0) | (pl.col("sl") == 0))
        )
        invalid_signals_str = f"{len(zero_signals)} signals with zero values detected ({', '.join(zero_signals['symbol'].to_list())})" if not zero_signals.is_empty() else "None"
        if not zero_signals.is_empty():
            zero_signals.write_csv("logs/zero_value_errors.csv")
            logger.warning(f"Logged {len(zero_signals)} zero-value signals")

        summary = (
            f"📋 *Daily Report ({today})*\n\n"
            f"📊 *Total Signals*: {total}\n"
            f"🔼 *LONG Signals*: {long_signals}\n"
            f"🔽 *SHORT Signals*: {short_signals}\n"
            f"⚡ *Scalping Signals*: {scalping_signals}\n"
            f"📈 *Normal Signals*: {normal_signals}\n"
            f"🎯 *TP1 Hits*: {tp1_hits} (Avg Chance: {avg_tp1_chance:.2f}%)\n"
            f"🎯 *TP2 Hits*: {tp2_hits} (Avg Chance: {avg_tp2_chance:.2f}%)\n"
            f"🎯 *TP3 Hits*: {tp3_hits} (Avg Chance: {avg_tp3_chance:.2f}%)\n"
            f"🛑 *SL Hits*: {sl_hits}\n"
            f"✅ *Accuracy*: {accuracy:.2f}%\n\n"
            f"🏆 *Top Performing Symbols*:\n{top_pairs_str}\n\n"
            f"⏱ *Average Trade Duration*:\n"
            f"  TP1 Hits: {avg_durations['tp1']} hours\n"
            f"  TP2 Hits: {avg_durations['tp2']} hours\n"
            f"  TP3 Hits: {avg_durations['tp3']} hours\n"
            f"  SL Hits: {avg_durations['sl']} hours\n\n"
            f"📡 *Market Trend Summary*:\n"
            f"  {market_trend}\n\n"
            f"🕒 *Success by Timeframe*:\n{timeframe_str}\n\n"
            f"🔍 *Backtest Success Rate*: {backtest_rate:.2f}%\n\n"
            f"⚠️ *Invalid Signals Warning*: {invalid_signals_str}\n\n"
            f"🕙 *Generated*: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        # Save report to CSV
        csv_path = "logs/daily_reports.csv"
        report_data = pl.DataFrame({
            "date": [str(today)],
            "total_signals": [total],
            "long_signals": [long_signals],
            "short_signals": [short_signals],
            "scalping_signals": [scalping_signals],
            "normal_signals": [normal_signals],
            "tp1_hits": [tp1_hits],
            "tp1_chance": [avg_tp1_chance],
            "tp2_hits": [tp2_hits],
            "tp2_chance": [avg_tp2_chance],
            "tp3_hits": [tp3_hits],
            "tp3_chance": [avg_tp3_chance],
            "sl_hits": [sl_hits],
            "accuracy": [accuracy],
            "top_pairs": [str(top_pairs_str)],
            "avg_tp1_duration": [avg_durations['tp1']],
            "avg_tp2_duration": [avg_durations['tp2']],
            "avg_tp3_duration": [avg_durations['tp3']],
            "avg_sl_duration": [avg_durations['sl']],
            "market_trend": [market_trend],
            "timeframe_success": [str(timeframe_str)],
            "backtest_rate": [backtest_rate],
            "invalid_signals": [invalid_signals_str],
            "timestamp": [datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')]
        })

        if os.path.exists(csv_path):
            old_df = pl.read_csv(csv_path, columns=report_data.columns)
            if not report_data.is_empty():
                report_data = old_df.vstack(report_data)

        if not report_data.is_empty():
            report_data.write_csv(csv_path)
            logger.info("Daily report saved to CSV")

        await send_telegram_message(summary)
        logger.info("Daily Report Sent")

    except Exception as e:
        logger.error(f"Report Error: {e}")
        log_report_status(False, str(e))
