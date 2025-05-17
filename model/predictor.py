import pandas as pd
import numpy as np
from typing import Dict, Optional
from utils.logger import logger
import ccxt.async_support as ccxt
from core.indicators import calculate_indicators
from core.candle_patterns import is_bullish_engulfing, is_bearish_engulfing, is_doji, is_hammer, is_shooting_star, is_three_white_soldiers, is_three_black_crows
from utils.fibonacci import calculate_fibonacci_levels
from utils.support_resistance import calculate_support_resistance
from core.trade_classifier import classify_trade

class SignalPredictor:
    def __init__(self):
        self.min_data_points = 20
        self.exchange = ccxt.binance()
        logger.info("Signal Predictor initialized")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df = calculate_indicators(df)  # Call core/indicators.py
            df = calculate_fibonacci_levels(df)  # Add Fibonacci levels
            sr_levels = calculate_support_resistance(df['symbol'].iloc[0] if 'symbol' in df.columns else "Unknown", df)
            df['support'] = sr_levels['support']
            df['resistance'] = sr_levels['resistance']
            return df
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return df

    async def check_signal_status(self, symbol: str, signal: Dict) -> str:
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            if signal['direction'] == "LONG":
                if current_price >= signal['tp3']:
                    return "tp3"
                elif current_price >= signal['tp2']:
                    return "tp2"
                elif current_price >= signal['tp1']:
                    return "tp1"
                elif current_price <= signal['sl']:
                    return "sl"
            else:  # SHORT
                if current_price <= signal['tp3']:
                    return "tp3"
                elif current_price <= signal['tp2']:
                    return "tp2"
                elif current_price <= signal['tp1']:
                    return "tp1"
                elif current_price >= signal['sl']:
                    return "sl"
            return "pending"
        except Exception as e:
            logger.error(f"Error checking signal status for {symbol}: {str(e)}")
            return "pending"

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str) -> Optional[Dict]:
        try:
            if df.empty or len(df) < self.min_data_points:
                logger.warning(f"[{symbol}] DataFrame empty or too short for {timeframe} (rows: {len(df)})")
                return None

            latest = df.iloc[-1]
            required_indicators = ['rsi', 'volume_sma_20', 'macd', 'macd_signal', 'atr', 'bb_upper', 'bb_lower',
                                  'ema_fast', 'ema_slow', 'stoch_k', 'adx', 'obv', 'cci', 'mfi', 'vwap',
                                  'ichimoku_a', 'ichimoku_b', 'williams_r', 'parabolic_sar']
            if df[required_indicators].isna().any().any():
                logger.warning(f"[{symbol}] NaN values in critical indicators for {timeframe}")
                return None

            # Candle pattern checks
            bullish_engulfing = is_bullish_engulfing(df)[-1]
            bearish_engulfing = is_bearish_engulfing(df)[-1]
            doji = is_doji(df)[-1]
            hammer = is_hammer(df)[-1]
            shooting_star = is_shooting_star(df)[-1]
            three_white_soldiers = is_three_white_soldiers(df)[-1]
            three_black_crows = is_three_black_crows(df)[-1]

            long_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] < 50,  # RSI oversold
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'],  # High volume
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] > latest['macd_signal'],  # MACD bullish
                pd.notna(latest['bb_lower']) and latest['close'] < latest['bb_lower'],  # Below BB lower
                pd.notna(latest['ema_fast']) and pd.notna(latest['ema_slow']) and latest['ema_fast'] > latest['ema_slow'],  # EMA bullish
                pd.notna(latest['stoch_k']) and latest['stoch_k'] < 20,  # Stochastic oversold
                pd.notna(latest['adx']) and latest['adx'] > 25,  # Strong trend
                pd.notna(latest['obv']) and latest['obv'] > df['obv'].shift(1).iloc[-1],  # OBV increasing
                pd.notna(latest['cci']) and latest['cci'] < -100,  # CCI oversold
                pd.notna(latest['mfi']) and latest['mfi'] < 20,  # MFI oversold
                pd.notna(latest['vwap']) and latest['close'] < latest['vwap'],  # Below VWAP
                pd.notna(latest['ichimoku_a']) and pd.notna(latest['ichimoku_b']) and latest['close'] > latest['ichimoku_a'],  # Above Ichimoku cloud
                pd.notna(latest['williams_r']) and latest['williams_r'] < -80,  # Williams %R oversold
                pd.notna(latest['parabolic_sar']) and latest['close'] > latest['parabolic_sar'],  # Above SAR
                bullish_engulfing or hammer or three_white_soldiers,  # Bullish candle patterns
            ]
            short_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] > 50,  # RSI overbought
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] < latest['volume_sma_20'],  # Low volume
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] < latest['macd_signal'],  # MACD bearish
                pd.notna(latest['bb_upper']) and latest['close'] > latest['bb_upper'],  # Above BB upper
                pd.notna(latest['ema_fast']) and pd.notna(latest['ema_slow']) and latest['ema_fast'] < latest['ema_slow'],  # EMA bearish
                pd.notna(latest['stoch_k']) and latest['stoch_k'] > 80,  # Stochastic overbought
                pd.notna(latest['adx']) and latest['adx'] > 25,  # Strong trend
                pd.notna(latest['obv']) and latest['obv'] < df['obv'].shift(1).iloc[-1],  # OBV decreasing
                pd.notna(latest['cci']) and latest['cci'] > 100,  # CCI overbought
                pd.notna(latest['mfi']) and latest['mfi'] > 80,  # MFI overbought
                pd.notna(latest['vwap']) and latest['close'] > latest['vwap'],  # Above VWAP
                pd.notna(latest['ichimoku_a']) and pd.notna(latest['ichimoku_b']) and latest['close'] < latest['ichimoku_a'],  # Below Ichimoku cloud
                pd.notna(latest['williams_r']) and latest['williams_r'] > -20,  # Williams %R overbought
                pd.notna(latest['parabolic_sar']) and latest['close'] < latest['parabolic_sar'],  # Below SAR
                bearish_engulfing or shooting_star or three_black_crows,  # Bearish candle patterns
            ]

            long_confidence = sum([20 for cond in long_conditions[:14]] + [10 for cond in long_conditions[14:15] if cond])
            short_confidence = sum([20 for cond in short_conditions[:14]] + [10 for cond in short_conditions[14:15] if cond])

            direction = None
            confidence = 0
            conditions_met = []

            if sum(long_conditions[:14]) >= 5 or (sum(long_conditions[:14]) >= 3 and long_conditions[14]):  # At least 5 indicators or 3 + candle pattern
                direction = "LONG"
                confidence = long_confidence
                conditions_met = [
                    "rsi < 50" if long_conditions[0] else "",
                    "volume > volume_sma_20" if long_conditions[1] else "",
                    "macd > macd_signal" if long_conditions[2] else "",
                    "close < bb_lower" if long_conditions[3] else "",
                    "ema_fast > ema_slow" if long_conditions[4] else "",
                    "stoch_k < 20" if long_conditions[5] else "",
                    "adx > 25" if long_conditions[6] else "",
                    "obv increasing" if long_conditions[7] else "",
                    "cci < -100" if long_conditions[8] else "",
                    "mfi < 20" if long_conditions[9] else "",
                    "close < vwap" if long_conditions[10] else "",
                    "close > ichimoku_a" if long_conditions[11] else "",
                    "williams_r < -80" if long_conditions[12] else "",
                    "close > parabolic_sar" if long_conditions[13] else "",
                    "bullish candle pattern" if long_conditions[14] else ""
                ]
                conditions_met = [c for c in conditions_met if c]
            elif sum(short_conditions[:14]) >= 5 or (sum(short_conditions[:14]) >= 3 and short_conditions[14]):
                direction = "SHORT"
                confidence = short_confidence
                conditions_met = [
                    "rsi > 50" if short_conditions[0] else "",
                    "volume < volume_sma_20" if short_conditions[1] else "",
                    "macd < macd_signal" if short_conditions[2] else "",
                    "close > bb_upper" if short_conditions[3] else "",
                    "ema_fast < ema_slow" if short_conditions[4] else "",
                    "stoch_k > 80" if short_conditions[5] else "",
                    "adx > 25" if short_conditions[6] else "",
                    "obv decreasing" if short_conditions[7] else "",
                    "cci > 100" if short_conditions[8] else "",
                    "mfi > 80" if short_conditions[9] else "",
                    "close > vwap" if short_conditions[10] else "",
                    "close < ichimoku_a" if short_conditions[11] else "",
                    "williams_r > -20" if short_conditions[12] else "",
                    "close < parabolic_sar" if short_conditions[13] else "",
                    "bearish candle pattern" if short_conditions[14] else ""
                ]
                conditions_met = [c for c in conditions_met if c]

            if direction:
                current_price = latest['close']
                atr = max(latest['atr'], current_price * 0.005)
                min_diff = 0.002
                multiplier = 2.0
                tp1_possibility = 0.80
                tp2_possibility = 0.65
                tp3_possibility = 0.50

                # Adjust TP/SL with Fibonacci and Support/Resistance
                fib_levels = {k: latest[k] for k in ['fib_0.236', 'fib_0.382', 'fib_0.5', 'fib_0.618', 'fib_0.786']}
                support = latest['support']
                resistance = latest['resistance']

                if direction == "LONG":
                    tp1 = round(max(current_price + atr * multiplier, fib_levels['fib_0.382'], support), 8)
                    tp2 = round(max(tp1 + atr * 0.5, fib_levels['fib_0.618'], support), 8)
                    tp3 = round(max(tp2 + atr * 0.5, fib_levels['fib_0.786'], support), 8)
                    sl = round(min(current_price - atr * 1.5, support, fib_levels['fib_0.236']), 8)
                else:  # SHORT
                    tp1 = round(min(current_price - atr * multiplier, fib_levels['fib_0.382'], resistance), 8)
                    tp2 = round(min(tp1 - atr * 0.5, fib_levels['fib_0.618'], resistance), 8)
                    tp3 = round(min(tp2 - atr * 0.5, fib_levels['fib_0.786'], resistance), 8)
                    sl = round(max(current_price + atr * 1.5, resistance, fib_levels['fib_0.236']), 8)

                signal = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry": round(current_price, 8),
                    "confidence": min(confidence, 100),
                    "timeframe": timeframe,
                    "conditions": conditions_met,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "sl": sl,
                    "tp1_possibility": tp1_possibility,
                    "tp2_possibility": tp2_possibility,
                    "tp3_possibility": tp3_possibility,
                    "volume": latest['volume'],
                    "status": "pending",
                    "hit_timestamp": None,
                    "trade_type": classify_trade(confidence)
                }
                if signal['tp1'] == signal['entry']:
                    logger.warning(f"[{symbol}] TP1 ({signal['tp1']}) and Entry ({signal['entry']}) are the same, check ATR or rounding")
                logger.info(
                    f"[{symbol}] Signal for {timeframe}: {direction}, Confidence: {confidence:.2f}%, "
                    f"TP1: {signal['tp1']:.8f} ({signal['tp1_possibility']*100:.0f}%), "
                    f"TP2: {signal['tp2']:.8f} ({signal['tp2_possibility']*100:.0f}%), "
                    f"TP3: {signal['tp3']:.8f} ({signal['tp3_possibility']*100:.0f}%), "
                    f"SL: {signal['sl']:.8f}"
                )
                return signal
            logger.info(f"[{symbol}] No signal for {timeframe}")
            return None
        except Exception as e:
            logger.error(f"[{symbol}] Error predicting signal for {timeframe}: {str(e)}")
            return None
