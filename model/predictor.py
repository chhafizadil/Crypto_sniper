# Updated model/predictor.py to address MACD bearish LONG signal issue, TP1/2/3 possibility clamping, add dynamic leverage, and prevent trend bias
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
        # Set minimum data points required for analysis
        self.min_data_points = 200  # Increased to 200 for 200-day MA calculation
        logger.info("Signal Predictor initialized")

    # Add Trade Duration based on timeframe
    def get_trade_duration(self, timeframe: str) -> str:
        # Define trade duration based on timeframe for signal metadata
        durations = {
            '15m': 'Up to 1 hour',
            '1h': 'Up to 6 hours',
            '4h': 'Up to 24 hours',
            '1d': 'Up to 3 days'
        }
        return durations.get(timeframe, 'Unknown')

    # Calculate dynamic leverage based on confidence and ADX
    def calculate_leverage(self, confidence: float, adx: float) -> int:
        # Calculate leverage (10x-40x) based on confidence and ADX strength
        # Higher confidence and ADX yield higher leverage
        try:
            if confidence > 80 and adx > 20:
                return 40
            elif confidence > 70 and adx > 15:
                return 30
            elif confidence > 60 and adx > 10:
                return 20
            else:
                return 10
        except Exception as e:
            logger.error(f"Error calculating leverage: {str(e)}")
            return 10

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str, btc_trend: float = 0) -> dict:
        # Predict trading signal with trend bias prevention
        # Added btc_trend parameter to incorporate market context
        try:
            if df is None or len(df) < self.min_data_points:
                logger.warning(f"[{symbol}] Insufficient data for {timeframe}: {len(df) if df is not None else 'None'}")
                return None

            df = df.copy()
            logger.info(f"[{symbol}] Calculating indicators for {timeframe}")
            df = calculate_indicators(df)
            logger.info(f"[{symbol}] Calculating Fibonacci levels for {timeframe}")
            df = calculate_fibonacci_levels(df)
            logger.info(f"[{symbol}] Calculating support/resistance for {timeframe}")
            sr_levels = calculate_support_resistance(symbol, df)

            latest = df.iloc[-1]
            conditions = []
            logger.info(f"[{symbol}] {timeframe} - RSI: {latest['rsi']:.2f}, MACD: {latest['macd']:.2f}, MACD Signal: {latest['macd_signal']:.2f}, ADX: {latest['adx']:.2f}, Close: {latest['close']:.2f}, MA200: {latest.get('ma200', 0):.2f}")

            # RSI conditions
            # Set RSI < 42 for oversold (potential LONG opportunity)
            if latest['rsi'] < 42:
                conditions.append("Oversold RSI")
            # Set RSI > 58 for overbought (potential SHORT opportunity)
            elif latest['rsi'] > 58:
                conditions.append("Overbought RSI")
            # Handle neutral RSI (45-55) with stricter conditions
            elif 45 <= latest['rsi'] <= 55:
                if latest['adx'] > 20 or latest['close'] > latest.get('ma50', 0):
                    conditions.append("Neutral RSI with Strong Trend")
                else:
                    logger.info(f"[{symbol}] Neutral RSI ({latest['rsi']:.2f}) without strong trend, skipping")
                    return None

            # MACD conditions
            # Bullish MACD for LONG signals
            if latest['macd'] > latest['macd_signal']:
                conditions.append("Bullish MACD")
            # Bearish MACD for SHORT signals
            elif latest['macd'] < latest['macd_signal']:
                conditions.append("Bearish MACD")

            # ADX condition
            # Set ADX > 15 to ensure strong trend (prevents signals in weak markets)
            if latest['adx'] > 15:
                conditions.append("Strong Trend")
            else:
                logger.info(f"[{symbol}] Weak trend (ADX: {latest['adx']:.2f} <= 15), skipping")
                return None

            # 200-day MA condition for global trend
            # Price below MA200 indicates bearish trend, skip LONG signals
            if 'ma200' in latest and latest['close'] < latest['ma200']:
                conditions.append("Bearish MA200")
            # Price above MA200 indicates bullish trend, skip SHORT signals
            elif 'ma200' in latest and latest['close'] > latest['ma200']:
                conditions.append("Bullish MA200")

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
            if abs(current_price - support) / current_price < 0.1:
                conditions.append("Near Support")
            if abs(current_price - resistance) / current_price < 0.1:
                conditions.append("Near Resistance")

            # Volume confirmation
            if 'volume_sma_20' in latest and latest['volume'] > latest['volume_sma_20'] * 1.05:
                conditions.append("High Volume")

            logger.info(f"[{symbol}] {timeframe} - Conditions: {', '.join(conditions) if conditions else 'None'}")

            # Confidence calculation
            # Base confidence set to 40%
            confidence = 40.0
            # Add 15% for MACD signals
            if "Bullish MACD" in conditions or "Bearish MACD" in conditions:
                confidence += 15.0
            # Reduced Candlestick weight to 10% to prevent bias
            if "Bullish Engulfing" in conditions or "Bearish Engulfing" in conditions or "Hammer" in conditions or "Shooting Star" in conditions:
                confidence += 10.0
            # Add 8% for strong ADX trend
            if "Strong Trend" in conditions:
                confidence += 8.0
            # Add 10% for support/resistance proximity
            if "Near Support" in conditions or "Near Resistance" in conditions:
                confidence += 10.0
            # Add 10% for high volume
            if "High Volume" in conditions:
                confidence += 10.0
            # Add 5% for RSI signals
            if "Oversold RSI" in conditions or "Overbought RSI" in conditions:
                confidence += 5.0
            # Reduced Three Soldiers/Crows weight to 10%
            if "Three White Soldiers" in conditions or "Three Black Crows" in conditions:
                confidence += 10.0
            # Add 5% for Doji
            if "Doji" in conditions:
                confidence += 5.0
            # Clamp confidence to 0-100%
            confidence = min(max(confidence, 0), 100)

            # Require minimum conditions
            # Set minimum conditions to 4 for robust signals
            if len(conditions) < 4:
                logger.info(f"[{symbol}] Insufficient conditions ({len(conditions)} < 4) for {timeframe}")
                return None

            # Direction logic with MACD and MA200 validation
            # Prevent LONG in bearish markets and SHORT in bullish markets
            direction = None
            bullish_conditions = ["Bullish MACD", "Oversold RSI", "Bullish Engulfing", "Hammer", "Near Support", "Three White Soldiers"]
            bearish_conditions = ["Bearish MACD", "Overbought RSI", "Bearish Engulfing", "Shooting Star", "Near Resistance", "Three Black Crows"]

            # LONG signal logic
            if (any(c in conditions for c in bullish_conditions) and 
                "Bullish MACD" in conditions and 
                confidence >= 40.0 and
                "Bearish MA200" not in conditions):  # Prevent LONG if below MA200
                # Skip LONG if overbought RSI and near resistance
                if "Overbought RSI" in conditions and "Near Resistance" in conditions:
                    logger.info(f"[{symbol}] Skipped LONG due to Overbought RSI and Near Resistance")
                    return None
                # Skip LONG if BTC trend is strongly bearish
                if btc_trend < -5:
                    if confidence < 80:
                        logger.info(f"[{symbol}] Skipped LONG due to bearish BTC trend ({btc_trend:.2f}%) and low confidence")
                        return None
                direction = "LONG"
            
            # SHORT signal logic
            elif (any(c in conditions for c in bearish_conditions) and 
                  "Bearish MACD" in conditions and 
                  confidence >= 40.0 and
                  "Bullish MA200" not in conditions):  # Prevent SHORT if above MA200
                # Skip SHORT if BTC trend is strongly bullish
                if btc_trend > 5:
                    if confidence < 80:
                        logger.info(f"[{symbol}] Skipped SHORT due to bullish BTC trend ({btc_trend:.2f}%) and low confidence")
                        return None
                direction = "SHORT"

            if not direction:
                logger.info(f"[{symbol}] No clear direction for {timeframe}")
                return None

            # Calculate TP/SL
            atr = latest.get('atr', max(0.1 * latest['close'], 0.02))
            entry = current_price
            if direction == "LONG":
                tp1 = entry + max(0.005 * entry, 0.5 * atr)
                tp2 = entry + max(0.015 * entry, 1.0 * atr)
                tp3 = entry + max(0.03 * entry, 2.0 * atr)
                sl = entry - max(0.008 * entry, 0.8 * atr)
            else:
                tp1 = entry - max(0.005 * entry, 0.5 * atr)
                tp2 = entry - max(0.015 * entry, 1.0 * atr)
                tp3 = entry - max(0.03 * entry, 2.0 * atr)
                sl = entry + max(0.008 * entry, 0.8 * atr)

            # Ensure TP1 is within 0.5-3% range
            tp1_percent = abs(tp1 - entry) / entry * 100
            if not (0.5 <= tp1_percent <= 3.0):
                logger.warning(f"[{symbol}] TP1 out of 0.5-3% range ({tp1_percent:.2f}%), adjusting")
                if direction == "LONG":
                    tp1 = entry + 0.015 * entry
                else:
                    tp1 = entry - 0.015 * entry

            # Calculate TP possibilities
            # Clamped TP1/2/3 possibilities to 0-100% and linked to confidence
            tp1_possibility = min(max(70.0 if confidence > 75 else 60.0, 0), 100)
            tp2_possibility = min(max(50.0 if confidence > 75 else 40.0, 0), 100)
            tp3_possibility = min(max(30.0 if confidence > 75 else 20.0, 0), 100)

            trade_type = classify_trade(confidence, timeframe) or "Scalp"
            leverage = self.calculate_leverage(confidence, latest['adx'])

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
                'tp1_possibility': float(tp1_possibility),
                'tp2_possibility': float(tp2_possibility),
                'tp3_possibility': float(tp3_possibility),
                'volume': float(latest['volume']),
                'quote_volume_24h': float(latest.get('quote_volume_24h', 0)),
                'trade_type': trade_type,
                'trade_duration': self.get_trade_duration(timeframe),
                'timestamp': pd.Timestamp.now().isoformat(),
                'macd_status': 'bullish' if latest['macd'] > latest['macd_signal'] else 'bearish',
                'leverage': leverage,
                'btc_trend': btc_trend,  # Added BTC trend to signal metadata
                'ma200_status': 'bullish' if latest['close'] > latest.get('ma200', float('inf')) else 'bearish'
            }

            logger.info(f"[{symbol}] Signal generated for {timeframe}: {direction}, Confidence: {signal['confidence']}%, TP1: {signal['tp1']:.4f} ({tp1_percent:.2f}%), BTC Trend: {btc_trend:.2f}%, MA200: {signal['ma200_status']}")
            return signal

        except Exception as e:
            logger.error(f"[{symbol}] Error predicting signal for {timeframe}: {str(e)}")
            return None
