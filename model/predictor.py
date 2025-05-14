import pandas as pd
import numpy as np
from typing import Dict, Optional
from utils.logger import logger
import ta

class SignalPredictor:
    def __init__(self):
        self.min_data_points = 20
        logger.info("Signal Predictor initialized")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df = df.copy()
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14, fillna=True).rsi()
            df['macd'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True).macd()
            df['macd_signal'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True).macd_signal()
            df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14, fillna=True).average_true_range()
            df['volume_sma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()
            df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20, fillna=True).ema_indicator()
            df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50, fillna=True).ema_indicator()
            df['stoch_rsi'] = ta.momentum.StochasticRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3, fillna=True).stochrsi()
            df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14, fillna=True).adx()
            df['cci'] = ta.trend.CCIIndicator(df['high'], df['low'], df['close'], window=20, fillna=True).cci()
            df['vwap'] = ta.volume.VolumeWeightedAveragePrice(df['high'], df['low'], df['close'], df['volume'], window=14, fillna=True).volume_weighted_average_price()
            df['momentum'] = ta.momentum.ROCIndicator(df['close'], window=10, fillna=True).roc()

            df.replace([np.inf, -np.inf], np.nan, inplace=True)
            df.fillna(method='ffill', inplace=True)
            df.fillna(0.0, inplace=True)
            
            logger.info("Indicators calculated: rsi, macd, atr, volume_sma_20, ema_20, ema_50, stoch_rsi, adx, cci, vwap, momentum")
            return df
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return df

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str) -> Optional[Dict]:
        try:
            if df.empty or len(df) < self.min_data_points:
                logger.warning(f"[{symbol}] DataFrame empty or too short for {timeframe} (rows: {len(df)})")
                return None

            latest = df.iloc[-1]
            if df[['rsi', 'macd', 'volume_sma_20']].isna().any().any():
                logger.warning(f"[{symbol}] NaN values in critical indicators for {timeframe}")
                return None

            long_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] < 35,
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'] * 1.2
            ]
            short_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] > 65,
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] < latest['volume_sma_20'] * 0.9
            ]

            long_confidence = sum([25 for cond in long_conditions if cond]) + 20
            short_confidence = sum([25 for cond in short_conditions if cond]) + 20

            direction = None
            confidence = 0
            conditions_met = []

            if all(long_conditions):
                direction = "LONG"
                confidence = long_confidence
                conditions_met = ["rsi < 35", "volume > volume_sma_20 * 1.2"]
            elif all(short_conditions):
                direction = "SHORT"
                confidence = short_confidence
                conditions_met = ["rsi > 65", "volume < volume_sma_20 * 0.9"]

            if direction:
                current_price = latest['close']
                atr = latest['atr']
                signal = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry": current_price,
                    "confidence": min(confidence, 100),
                    "timeframe": timeframe,
                    "conditions": conditions_met,
                    "tp1": current_price + atr * 1.5 if direction == "LONG" else current_price - atr * 1.5,
                    "tp2": current_price + atr * 2.5 if direction == "LONG" else current_price - atr * 2.5,
                    "tp3": current_price + atr * 4 if direction == "LONG" else current_price - atr * 4,
                    "sl": current_price - atr * 1 if direction == "LONG" else current_price + atr * 1,
                    "tp1_possibility": 0.85,
                    "tp2_possibility": 0.65,
                    "tp3_possibility": 0.45,
                    "volume": latest['volume']
                }
                logger.info(f"[{symbol}] Signal for {timeframe}: {direction}, Confidence: {confidence:.2f}%")
                return signal
            else:
                logger.info(f"[{symbol}] No signal for {timeframe}")
                return None
        except Exception as e:
            logger.error(f"[{symbol}] Error predicting signal for {timeframe}: {str(e)}")
            return None
