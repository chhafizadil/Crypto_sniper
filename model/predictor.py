import pandas as pd
import numpy as np
import asyncio
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
        # Initialize SignalPredictor with minimum data points

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str) -> dict:
        try:
            # Timeout to prevent hanging
            async def run_with_timeout():
                if len(df) < self.min_data_points:
                    logger.warning(f"[{symbol}] Insufficient data for {timeframe}: {len(df)} rows")
                    return None
                # Check if sufficient data is available

                df = df.copy()
                logger.info(f"[{symbol}] Calculating indicators for {timeframe}")
                df = calculate_indicators(df)
                logger.info(f"[{symbol}] Calculating Fibonacci levels for {timeframe}")
                df = calculate_fibonacci_levels(df)
                logger.info(f"[{symbol}] Calculating support/resistance for {timeframe}")
                sr_levels = calculate_support_resistance(symbol, df)
                # Calculate technical indicators, Fibonacci levels, and support/resistance

                latest = df.iloc[-1]
                conditions = []
                # Initialize conditions list for signal generation

                # Log indicator values
                logger.info(f"[{symbol}] {timeframe} - RSI: {latest['rsi']:.2f}, MACD: {latest['macd']:.2f}, MACD Signal: {latest['macd_signal']:.2f}, ADX: {latest['adx']:.2f}, EMA Fast: {latest['ema_fast']:.2f}, Volume: {latest['volume']:.2f}, Volume SMA: {latest['volume_sma_20']:.2f}")

                # Trend and momentum
                if latest['rsi'] < 35:
                    conditions.append("Oversold RSI")
                elif latest['rsi'] > 65:
                    conditions.append("Overbought RSI")
                # Check RSI for oversold/overbought conditions

                if latest['macd'] > latest['macd_signal'] and latest['macd'] > 0:
                    conditions.append("Bullish MACD")
                elif latest['macd'] < latest['macd_signal'] and latest['macd'] < 0:
                    conditions.append("Bearish MACD")
                # Check MACD for bullish/bearish signals

                if latest['adx'] > 20:
                    conditions.append("Strong Trend")
                # Check ADX for trend strength

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
                # Check for candlestick patterns

                # Support/Resistance proximity
                current_price = latest['close']
                support = sr_levels['support']
                resistance = sr_levels['resistance']
                if abs(current_price - support) / current_price < 0.03:
                    conditions.append("Near Support")
                if abs(current_price - resistance) / current_price < 0.03:
                    conditions.append("Near Resistance")
                # Check if price is near support or resistance

                # Volume confirmation
                if latest['volume'] > latest['volume_sma_20'] * 1.3:
                    conditions.append("High Volume")
                # Check for high volume confirmation

                # Log conditions
                logger.info(f"[{symbol}] {timeframe} - Conditions: {', '.join(conditions) if conditions else 'None'}")

                # Confidence calculation
                confidence = 50.0
                if "Bullish MACD" in conditions or "Bullish Engulfing" in conditions or "Hammer" in conditions:
                    confidence += 20.0
                if "Bearish MACD" in conditions or "Bearish Engulfing" in conditions or "Shooting Star" in conditions:
                    confidence += 20.0
                if "Strong Trend" in conditions:
                    confidence += 15.0
                if "Near Support" in conditions or "Near Resistance" in conditions:
                    confidence += 15.0
                if "High Volume" in conditions:
                    confidence += 15.0
                if "Oversold RSI" in conditions or "Overbought RSI" in conditions:
                    confidence += 10.0
                # Calculate confidence based on conditions

                # Relaxed direction logic
                direction = None
                if (
                    ("Bullish MACD" in conditions or "Oversold RSI" in conditions or "Bullish Engulfing" in conditions or "Hammer" in conditions or "Near Support" in conditions) and
                    confidence >= 50.0
                ):
                    direction = "LONG"
                elif (
                    ("Bearish MACD" in conditions or "Overbought RSI" in conditions or "Bearish Engulfing" in conditions or "Shooting Star" in conditions or "Near Resistance" in conditions) and
                    confidence >= 50.0
                ):
                    direction = "SHORT"
                # Relaxed conditions: Removed strict EMA check and added more triggers

                if not direction:
                    logger.info(f"[{symbol}] No clear direction for {timeframe}")
                    return None
                # Return None if no clear direction is determined

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
                # Calculate take-profit and stop-loss levels using ATR

                trade_type = classify_trade(confidence)
                # Classify trade based on confidence

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
                # Create signal dictionary with all details

                logger.info(f"[{symbol}] Signal generated for {timeframe}: {direction}, Confidence: {signal['confidence']}%")
                return signal
                # Log and return generated signal

            # Run with 10-second timeout
            return await asyncio.wait_for(run_with_timeout(), timeout=10.0)

        except asyncio.TimeoutError:
            logger.error(f"[{symbol}] Signal prediction timed out for {timeframe}")
            return None
        except Exception as e:
            logger.error(f"[{symbol}] Error predicting signal for {timeframe}: {str(e)}")
            return None
            # Log any errors during signal prediction
