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

            df.replace([np.inf, -np.inf], np.nan, inplace=True)
            df.fillna(method='ffill', inplace=True)
            df.fillna(0.0, inplace=True)
            
            logger.info("Indicators calculated: rsi, volume_sma_20")
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
            if df[['rsi', 'volume_sma_20']].isna().any().any():
                logger.warning(f"[{symbol}] NaN values in critical indicators for {timeframe}")
                return None

            long_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] < 30,  # Tightened RSI condition
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'] * 1.2
            ]
            short_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] > 70,  # Tightened RSI condition
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] < latest['volume_sma_20'] * 0.9
            ]

            long_confidence = sum([40 for cond in long_conditions if cond]) + 20
            short_confidence = sum([40 for cond in short_conditions if cond]) + 20

            direction = None
            confidence = 0
            conditions_met = []

            if all(long_conditions):
                direction = "LONG"
                confidence = long_confidence
                conditions_met = ["rsi < 30", "volume > volume_sma_20 * 1.2"]
            elif all(short_conditions):
                direction = "SHORT"
                confidence = short_confidence
                conditions_met = ["rsi > 70", "volume < volume_sma_20 * 0.9"]

            if direction:
                current_price = latest['close']
                signal = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry": current_price,
                    "confidence": min(confidence, 100),
                    "timeframe": timeframe,
                    "conditions": conditions_met,
                    "tp1": current_price * 1.015 if direction == "LONG" else current_price * 0.985,
                    "tp2": current_price * 1.025 if direction == "LONG" else current_price * 0.975,
                    "tp3": current_price * 1.040 if direction == "LONG" else current_price * 0.960,
                    "sl": current_price * 0.990 if direction == "LONG" else current_price * 1.010,
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
