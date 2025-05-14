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
                pd.notna(latest['rsi']) and latest['rsi'] < 38,  # Relaxed for more LONG signals
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'] * 1.2,
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] > latest['macd_signal']
            ]
            short_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] > 65,
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] < latest['volume_sma_20'] * 0.9,
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] < latest['macd_signal']
            ]

            long_confidence = sum([30 for cond in long_conditions if cond]) + 10
            short_confidence = sum([30 for cond in short_conditions if cond]) + 10

            direction = None
            confidence = 0
            conditions_met = []

            if long_conditions[2] and sum(long_conditions[:2]) >= 1:
                direction = "LONG"
                confidence = long_confidence
                conditions_met = [
                    "rsi < 38" if long_conditions[0] else "",
                    "volume > volume_sma_20 * 1.2" if long_conditions[1] else "",
                    "macd > macd_signal"
                ]
                conditions_met = [c for c in conditions_met if c]
            elif short_conditions[2] and sum(short_conditions[:2]) >= 1:
                direction = "SHORT"
                confidence = short_confidence
                conditions_met = [
                    "rsi > 65" if short_conditions[0] else "",
                    "volume < volume_sma_20 * 0.9" if short_conditions[1] else "",
                    "macd < macd_signal"
                ]
                conditions_met = [c for c in conditions_met if c]

            if direction:
                current_price = latest['close']
                atr = max(latest['atr'], 0.0001)  # Minimum ATR to avoid invalid TP/SL
                tp1_possibility = 0.85 if confidence >= 80 else 0.75
                tp2_possibility = 0.65 if confidence >= 80 else 0.55
                tp3_possibility = 0.45 if confidence >= 80 else 0.35
                signal = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry": round(current_price, 2),
                    "confidence": min(confidence, 100),
                    "timeframe": timeframe,
                    "conditions": conditions_met,
                    "tp1": round(current_price + atr * 1.5, 2) if direction == "LONG" else round(current_price - atr * 1.5, 2),
                    "tp2": round(current_price + atr * 2.5, 2) if direction == "LONG" else round(current_price - atr * 2.5, 2),
                    "tp3": round(current_price + atr * 4.0, 2) if direction == "LONG" else round(current_price - atr * 4.0, 2),
                    "sl": round(current_price - atr * 1.0, 2) if direction == "LONG" else round(current_price + atr * 1.0, 2),
                    "tp1_possibility": tp1_possibility,
                    "tp2_possibility": tp2_possibility,
                    "tp3_possibility": tp3_possibility,
                    "volume": latest['volume']
                }
                logger.info(
                    f"[{symbol}] Signal for {timeframe}: {direction}, Confidence: {confidence:.2f}%, "
                    f"TP1: {signal['tp1']:.2f} ({signal['tp1_possibility']*100:.0f}%), "
                    f"TP2: {signal['tp2']:.2f} ({signal['tp2_possibility']*100:.0f}%), "
                    f"TP3: {signal['tp3']:.2f} ({signal['tp3_possibility']*100:.0f}%), "
                    f"SL: {signal['sl']:.2f}"
                )
                return signal
            else:
                logger.info(f"[{symbol}] No signal for {timeframe}")
                return None
        except Exception as e:
            logger.error(f"[{symbol}] Error predicting signal for {timeframe}: {str(e)}")
            return None
