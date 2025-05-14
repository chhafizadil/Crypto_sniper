import polars as pl
import httpx
import asyncio
from datetime import datetime
import pytz
import os
from utils.logger import log

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
                        log("Telegram message sent successfully", level='INFO')
                        log_report_status(True, "Success")
                        return
                    else:
                        log(f"Failed to send Telegram message: {response.text}", level='ERROR')
                        log_report_status(False, response.text)
                except Exception as e:
                    log(f"Error sending Telegram message: {e}", level='ERROR')
                    log_report_status(False, str(e))
                await asyncio.sleep(2)

            log("Failed to send daily report after 3 attempts", level='ERROR')

    except Exception as e:
        log(f"Error in send_telegram_message: {e}", level='ERROR')
        log_report_status(False, str(e))

def log_report_status(success: bool, message: str):
    try:
        csv_path = "logs/report_status.csv"
        timestamp = datetime.now(pytz.timezone('Asia/Karachi')).strftime('%Y-%m-%d %H:%M:%S')
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
            log(f"Report status logged: Success={success}", level='INFO')
        else:
            log("No valid data to log report status", level='ERROR')
    except Exception as e:
        log(f"Error logging report status: {e}", level='ERROR')

async def generate_daily_summary():
    try:
        columns = [
            'timestamp', 'symbol', 'direction', 'price', 'tp1', 'tp2', 'tp3', 'sl',
            'volume', 'confidence', 'tp1_possibility', 'tp2_possibility', 'tp3_possibility',
            'timeframe', 'status', 'indicators_used', 'backtest_result', 'trade_type'
        ]
        df = pl.read_csv("logs/signals_log_new.csv", columns=columns)
        today = datetime.now(pytz.timezone('Asia/Karachi')).date()
        df = df.with_columns(pl.col("timestamp").cast(pl.DateTime))

        # Strict filters
        today_signals = df.filter(
            (pl.col("timestamp").dt.date() == today) &
            (pl.col("price") > 0) &
            (pl.col("tp1") > 0) &
            (pl.col("tp2") > 0) &
            (pl.col("tp3") > 0) &
            (pl.col("sl") > 0) &
            (pl.col("volume") >= 100000) &
            (pl.col("confidence") >= 75) &
            (pl.col("tp1_possibility") >= 0.75)
        )

        if today_signals.is_empty():
            summary = f"📋 *Daily Report ({today})*\n\nNo valid signals generated today."
            await send_telegram_message(summary)
            log("Daily Report Sent (No signals)", level='INFO')
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

        successful_pairs = today_signals.filter(pl.col("status").is_in(["tp1", "tp2", "tp3"]))
        top_pairs = successful_pairs.group_by("symbol").len().sort("len", descending=True).head(3).to_dicts()
        top_pairs_str = "\n".join([f"{pair['symbol']}: {pair['len']} hits" for pair in top_pairs]) if top_pairs else "None"

        indicators_used = today_signals.group_by("indicators_used").len().sort("len", descending=True).head(3).to_dicts()
        indicators_str = "\n".join([f"{ind['indicators_used']}: {ind['len']} signals" for ind in indicators_used]) if indicators_used else "N/A"

        backtest_success = len(today_signals.filter(pl.col("backtest_result") >= 70))
        backtest_rate = round((backtest_success / total * 100) if total > 0 else 0, 2)

        # Log zero-value signals
        zero_signals = df.filter(
            (pl.col("timestamp").dt.date() == today) &
            ((pl.col("price") == 0) | (pl.col("tp1") == 0) | (pl.col("tp2") == 0) |
             (pl.col("tp3") == 0) | (pl.col("sl") == 0))
        )
        if not zero_signals.is_empty():
            zero_signals.write_csv("logs/zero_value_errors.csv")
            log(f"Logged {len(zero_signals)} zero-value signals", level='WARNING')

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
            f"✅ *Accuracy*: {accuracy:.2f}%\n"
            f"🏆 *Top Pairs*:\n{top_pairs_str}\n"
            f"📡 *Indicators Used*:\n{indicators_str}\n"
            f"🔍 *Backtest Success Rate*: {backtest_rate:.2f}%\n"
            f"🕒 *Generated*: {datetime.now(pytz.timezone('Asia/Karachi')).strftime('%Y-%m-%d %H:%M:%S')}"
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
            "top_pairs": [str(top_pairs)],
            "indicators": [str(indicators_used)],
            "backtest_rate": [backtest_rate],
            "timestamp": [datetime.now(pytz.timezone('Asia/Karachi')).strftime('%Y-%m-%d %H:%M:%S')]
        })

        if os.path.exists(csv_path):
            old_df = pl.read_csv(csv_path, columns=report_data.columns)
            if not report_data.is_empty():
                report_data = old_df.vstack(report_data)

        if not report_data.is_empty():
            report_data.write_csv(csv_path)
            log("Daily report saved to CSV", level='INFO')

        await send_telegram_message(summary)
        log("Daily Report Sent", level='INFO')

    except Exception as e:
        log(f"Report Error: {e}", level='ERROR')
        log_report_status(False, str(e))

if __name__ == "__main__":
    asyncio.run(generate_daily_summary())
