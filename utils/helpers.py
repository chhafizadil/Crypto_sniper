import pandas as pd
from datetime import datetime
import pytz
from utils.logger import log

def round_price(value, symbol=None):
    """
    Round price based on symbol-specific decimal places or default to 3 decimals.
    
    Args:
        value (float): Price value to round.
        symbol (str, optional): Trading pair (e.g., 'BTC/USDT'). Defaults to None.
    
    Returns:
        float: Rounded price.
    """
    try:
        if symbol:
            # Define decimal places for specific symbols
            symbol_decimals = {
                'BTC/USDT': 2,
                'ETH/USDT': 3,
                'BNB/USDT': 3,
                'DOGE/USDT': 6,
                'XRP/USDT': 5,
                'FET/USDT': 4,  # Based on log price (e.g., 0.8737)
                'BAT/USDT': 5,  # Based on log price (e.g., 0.16723)
                'ZEC/USDT': 3,  # Based on log price (e.g., 43.985)
                'IOST/USDT': 6, # Based on log price (e.g., 0.004381)
                'CELR/USDT': 5  # Based on log price range
            }
            decimals = symbol_decimals.get(symbol, 3)  # Default to 3 if symbol not found
        else:
            decimals = 3
        return round(float(value), decimals)
    except Exception as e:
        log(f"Error rounding price: {e}", level="ERROR")
        return round(float(value), 3)

def calculate_percentage_change(current_price, reference_price):
    """
    Calculate percentage change between current and reference price.
    
    Args:
        current_price (float): Current price.
        reference_price (float): Reference price (e.g., entry, TP, SL).
    
    Returns:
        float: Percentage change.
    """
    try:
        if reference_price == 0:
            return 0.0
        return ((current_price - reference_price) / reference_price) * 100
    except Exception as e:
        log(f"Error calculating percentage change: {e}", level="ERROR")
        return 0.0

def format_timestamp(timestamp, timezone="Asia/Karachi"):
    """
    Format timestamp to a readable string in specified timezone.
    
    Args:
        timestamp (pd.Timestamp or str): Timestamp to format.
        timezone (str): Timezone name. Defaults to 'Asia/Karachi'.
    
    Returns:
        str: Formatted timestamp (e.g., '2025-05-12 14:30:00').
    """
    try:
        if isinstance(timestamp, str):
            timestamp = pd.Timestamp(timestamp)
        tz = pytz.timezone(timezone)
        return timestamp.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        log(f"Error formatting timestamp: {e}", level="ERROR")
        return str(timestamp)

def validate_numeric(value, name="value", positive=False):
    """
    Validate if a value is numeric and optionally positive.
    
    Args:
        value: Value to validate.
        name (str): Name of the value for logging.
        positive (bool): If True, ensures value is positive.
    
    Returns:
        bool: True if valid, False otherwise.
    """
    try:
        value = float(value)
        if positive and value <= 0:
            log(f"{name} must be positive, got {value}", level="WARNING")
            return False
        return True
    except (TypeError, ValueError):
        log(f"Invalid {name}: {value}", level="WARNING")
        return False

def format_signal_for_telegram(signal):
    """
    Format signal dictionary into a Telegram-friendly string.
    
    Args:
        signal (dict): Signal dictionary with symbol, direction, entry, tp1, etc.
    
    Returns:
        str: Formatted string for Telegram.
    """
    try:
        symbol = signal.get("symbol", "Unknown")
        direction = signal.get("direction", "Unknown")
        entry = round_price(signal.get("entry", 0), symbol)
        tp1 = round_price(signal.get("tp1", 0), symbol)
        tp2 = round_price(signal.get("tp2", 0), symbol)
        tp3 = round_price(signal.get("tp3", 0), symbol)
        sl = round_price(signal.get("sl", 0), symbol)
        confidence = signal.get("confidence", 0)
        tp1_possibility = signal.get("tp1_possibility", 0.7) * 100
        tp2_possibility = signal.get("tp2_possibility", 0.5) * 100
        tp3_possibility = signal.get("tp3_possibility", 0.3) * 100
        trade_type = signal.get("trade_type", "Scalping")
        timeframe = signal.get("timeframe", "Unknown")
        timestamp = format_timestamp(signal.get("timestamp", pd.Timestamp.now()))

        message = (
            f"🚀 *{symbol} Signal*\n\n"
            f"📊 *Direction*: {direction}\n"
            f"⏰ *Timeframe*: {timeframe}\n"
            f"💰 *Entry Price*: {entry}\n"
            f"🎯 *TP1*: {tp1} ({tp1_possibility:.2f}%)\n"
            f"🎯 *TP2*: {tp2} ({tp2_possibility:.2f}%)\n"
            f"🎯 *TP3*: {tp3} ({tp3_possibility:.2f}%)\n"
            f"🛑 *SL*: {sl}\n"
            f"🔍 *Confidence*: {confidence:.2f}%\n"
            f"⚡ *Trade Type*: {trade_type}\n"
            f"🕒 *Timestamp*: {timestamp}"
        )
        return message
    except Exception as e:
        log(f"Error formatting signal for Telegram: {e}", level="ERROR")
        return "Error formatting signal"
