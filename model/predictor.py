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
            df['volume_sma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()
            df['macd'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True).macd()
            df['macd_signal'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True).macd_signal()
            df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14, fillna=True).average_true_range()

            df.replace([np.inf, -np.inf], np.nan, inplace=True)
            df.ffill(inplace=True)
            df.fillna(0.0, inplace=True)
            
            logger.info("Indicators calculated: rsi, volume_sma_20, macd, atr")
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
            if df[['rsi', 'volume_sma_20', 'macd', 'macd_signal', 'atr']].isna().any().any():
                logger.warning(f"[{symbol}] NaN values in critical indicators for {timeframe}")
                return None

            long_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] < 35,  # Softened from 30
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'] * 1.2,
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] > latest['macd_signal']  # Bullish MACD crossover
            ]
            short_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] > 65,  # Softened from 70
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] < latest['volume_sma_20'] * 0.9,
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] < latest['macd_signal']  # Bearish MACD crossover
            ]

            long_confidence = sum([25 for cond in long_conditions if cond]) + 25
            short_confidence = sum([25 for cond in short_conditions if cond]) + 25

            direction = None
            confidence = 0
            conditions_met = []

            if sum(long_conditions) >= 2:  # At least 2 conditions for LONG
                direction = "LONG"
                confidence = long_confidence
                conditions_met = [
                    "rsi < 35" if long_conditions[0] else "",
                    "volume > volume_sma_20 * 1.2" if long_conditions[1] else "",
                    "macd > macd_signal" if long_conditions[2] else ""
                ]
                conditions_met = [c for c in conditions_met if c]
            elif sum(short_conditions) >= 2:  # At least 2 conditions for SHORT
                direction = "SHORT"
                confidence = short_confidence
                conditions_met = [
                    "rsi > 65" if short_conditions[0] else "",
                    "volume < volume_sma_20 * 0.9" if short_conditions[1] else "",
                    "macd < macd_signal" if short_conditions[2] else ""
                ]
                conditions_met = [c for c in conditions_met if c]

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
                    "tp3": current_price + atr * 4.0 if direction == "LONG" else current_price - atr * 4.0,
                    "sl": current_price - atr * 1.0 if direction == "LONG" else current_price + atr * 1.0,
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
