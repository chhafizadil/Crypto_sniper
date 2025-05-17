import pandas as pd
import numpy as np
from core.indicators import calculate_indicators
from core.candle_patterns import (
    is_bullish_engulfing, is_bearish_engulfing, is_doji,
    is_hammer, is_shooting_star, is_three_white_soldiers, is_three_black_crows
)
from utils.fibonacci import calculate_fibonacci_levels
from utils.support_resistance import calculate_support_resistance
from core.trade_classifier import classify_trade
from utils.logger import logger

class SignalPredictor:
    def __init__(self):
        self.min_data_points = 20
        logger.info("Signal Predictor initialized")

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str) -> dict:
        try:
            if len(df) < self.min_data_points:
                logger.warning(f"[{symbol}] Insufficient data for {timeframe}: {len(df)} rows")
                return None

            df = df.copy()
            df = calculate_indicators(df)
            df = calculate_fibonacci_levels(df)
            sr_levels = calculate_support_resistance(symbol, df)
            
            latest = df.iloc[-1]
            conditions = []

            # Trend and momentum
            if latest['rsi'] < 35:  # Relaxed from 30
                conditions.append("Oversold RSI")
            elif latest['rsi'] > 65:  # Relaxed from 70
                conditions.append("Overbought RSI")
                
            if latest['macd'] > latest['macd_signal'] and latest['macd'] > 0:
                conditions.append("Bullish MACD")
            elif latest['macd'] < latest['macd_signal'] and latest['macd'] < 0:
                conditions.append("Bearish MACD")
                
            if latest['adx'] > 20:  # Relaxed from 25
                conditions.append("Strong Trend")
                
            # Candlestick patterns
            if is_bullish_engulfing(df).iloc[-1]:
                conditions.append("Bullish Engulfing")
            if is_bearish_engulfing(df).iloc[-1]:
                conditions.append("Bearish Engulfing")
            if is_doji(df).iloc[-1]:
                conditions.append("Doji")
            if is_hammer(df).iloc[-1]:
                conditions.append("Hammer")
            if is_shooting_star(df).iloc[-1]:
                conditions.append("Shooting Star")
            if is_three_white_soldiers(df).iloc[-1]:
                conditions.append("Three White Soldiers")
            if is_three_black_crows(df).iloc[-1]:
                conditions.append("Three Black Crows")

            # Support/Resistance proximity
            current_price = latest['close']
            support = sr_levels['support']
            resistance = sr_levels['resistance']
            
            if abs(current_price - support) / current_price < 0.03:  # Relaxed from 0.02
                conditions.append("Near Support")
            if abs(current_price - resistance) / current_price < 0.03:  # Relaxed from 0.02
                conditions.append("Near Resistance")

            # Volume confirmation
            if latest['volume'] > latest['volume_sma_20'] * 1.3:  # Relaxed from 1.5
                conditions.append("High Volume")

            # Confidence calculation
            confidence = 50.0
            if "Bullish MACD" in conditions or "Bullish Engulfing" in conditions or "Hammer" in conditions:
                confidence += 20.0  # Increased from 15.0
            if "Bearish MACD" in conditions or "Bearish Engulfing" in conditions or "Shooting Star" in conditions:
                confidence += 20.0  # Increased from 15.0
            if "Strong Trend" in conditions:
                confidence += 15.0  # Increased from 10.0
            if "Near Support" in conditions or "Near Resistance" in conditions:
                confidence += 15.0  # Increased from 10.0
            if "High Volume" in conditions:
                confidence += 15.0  # Increased from 10.0
            if "Oversold RSI" in conditions or "Overbought RSI" in conditions:
                confidence += 10.0  # Increased from 5.0

            # Direction logic
            direction = None
            if (
                ("Bullish MACD" in conditions or "Oversold RSI" in conditions or "Bullish Engulfing" in conditions) and
                current_price > latest['ema_fast']
            ):
                direction = "LONG"
            elif (
                ("Bearish MACD" in conditions or "Overbought RSI" in conditions or "Bearish Engulfing" in conditions) and
                current_price < latest['ema_fast']
            ):
                direction = "SHORT"

            if not direction:
                logger.info(f"[{symbol}] No clear direction for {timeframe}")
                return None

            # Calculate TP/SL
            atr = latest['atr']
            if direction == "LONG":
                entry = current_price
                sl = entry - 1.5 * atr
                tp1 = entry + 1.0 * atr
                tp2 = entry + 1.5 * atr
                tp3 = entry + 2.0 * atr
            else:  # SHORT
                entry = current_price
                sl = entry + 1.5 * atr
                tp1 = entry - 1.0 * atr
                tp2 = entry - 1.5 * atr
                tp3 = entry - 2.0 * atr

            trade_type = classify_trade(confidence)
            
            signal = {
                'symbol': symbol,
                'direction': direction,
                'entry': float(entry),
                'confidence': float(confidence),
                'timeframe': timeframe,
                'conditions': conditions,
                'tp1': float(tp1),
                'tp2': float(tp2),
                'tp3': float(tp3),
                'sl': float(sl),
                'tp1_possibility': 70.0 if confidence > 80 else 60.0,
                'tp2_possibility': 50.0 if confidence > 80 else 40.0,
                'tp3_possibility': 30.0 if confidence > 80 else 20.0,
                'volume': float(latest['volume']),
                'trade_type': trade_type
            }
            
            logger.info(f"[{symbol}] Signal generated for {timeframe}: {direction}, Confidence: {confidence}%")
            return signal
        except Exception as e:
            logger.error(f"[{symbol}] Error predicting signal for {timeframe}: {str(e)}")
            return None
