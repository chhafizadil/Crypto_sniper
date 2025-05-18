# Module to calculate technical indicators for trading analysis
# Updated to fix MACD calculation and add validation for bullish/bearish status
import pandas as pd
import numpy as np
import ta
from utils.logger import logger

# Function to calculate indicators for a given dataframe
def calculate_indicators(df):
    try:
        df = df.copy()

        # RSI calculation with softened thresholds
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14, fillna=True).rsi()

        # Volume SMA 20 for volume trend analysis
        df['volume_sma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()

        # MACD calculation with validation for bullish/bearish status
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        # Add MACD status for validation
        df['macd_status'] = np.where(df['macd'] > df['macd_signal'], 'bullish', 'bearish')

        # ATR for TP/SL calculation
        df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14, fillna=True).average_true_range()

        # ADX for trend strength with softened threshold
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14, fillna=True).adx()

        # Handle NaN and Inf values
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.ffill(inplace=True)
        df.fillna(0.0, inplace=True)

        logger.info("Indicators calculated: rsi, volume_sma_20, macd, atr, adx, macd_status")
        return df
    except Exception as e:
        logger.error(f"Error calculating indicators: {str(e)}")
        return df
