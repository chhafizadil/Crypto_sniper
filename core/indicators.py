import pandas as pd
import numpy as np
import ta
from utils.logger import logger

def calculate_indicators(df):
    try:
        df = df.copy()

        # RSI
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14, fillna=True).rsi()

        # Volume SMA 20
        df['volume_sma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()

        # MACD
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()

        # ATR
        df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14, fillna=True).average_true_range()

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2, fillna=True)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()

        # EMA Fast and Slow
        df['ema_fast'] = ta.trend.EMAIndicator(df['close'], window=12, fillna=True).ema_indicator()
        df['ema_slow'] = ta.trend.EMAIndicator(df['close'], window=26, fillna=True).ema_indicator()

        # Stochastic Oscillator
        df['stoch_k'] = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3, fillna=True).stoch()

        # ADX
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14, fillna=True).adx()

        # OBV
        df['obv'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume'], fillna=True).on_balance_volume()

        # CCI
        df['cci'] = ta.trend.CCIIndicator(df['high'], df['low'], df['close'], window=20, fillna=True).cci()

        # MFI
        df['mfi'] = ta.volume.MFIIndicator(df['high'], df['low'], df['close'], df['volume'], window=14, fillna=True).money_flow_index()

        # VWAP
        df['vwap'] = ta.volume.VolumeWeightedAveragePrice(df['high'], df['low'], df['close'], df['volume'], window=14, fillna=True).volume_weighted_average_price()

        # Ichimoku Cloud
        ichimoku = ta.trend.IchimokuIndicator(df['high'], df['low'], window1=9, window2=26, window3=52, fillna=True)
        df['ichimoku_a'] = ichimoku.ichimoku_a()
        df['ichimoku_b'] = ichimoku.ichimoku_b()

        # Williams %R
        df['williams_r'] = ta.momentum.WilliamsRIndicator(df['high'], df['low'], df['close'], lbp=14, fillna=True).williams_r()

        # Parabolic SAR
        df['parabolic_sar'] = ta.trend.PSARIndicator(df['high'], df['low'], df['close'], step=0.02, max_step=0.2, fillna=True).psar()

        # Handle NaN and Inf
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.ffill(inplace=True)
        df.fillna(0.0, inplace=True)

        logger.info("Indicators calculated: rsi, volume_sma_20, macd, atr, bb_upper, bb_lower, ema_fast, ema_slow, stoch_k, adx, obv, cci, mfi, vwap, ichimoku, williams_r, parabolic_sar")
        return df
    except Exception as e:
        logger.error(f"Error calculating indicators: {str(e)}")
        return df
