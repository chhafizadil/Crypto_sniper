import pandas as pd
import numpy as np
from core.candle_patterns import (
    is_bullish_engulfing, is_bearish_engulfing, is_doji, is_hammer, is_shooting_star,
    is_three_white_soldiers, is_three_black_crows
)
from utils.logger import log
import pytz

class SignalPredictor:
    def __init__(self):
        self.min_confidence_threshold = 0.65
        self.last_signals = {}  # {symbol_timeframe: timestamp}
        self.candle_patterns = {
            "bullish_engulfing": is_bullish_engulfing,
            "bearish_engulfing": is_bearish_engulfing,
            "doji": is_doji,
            "hammer": is_hammer,
            "shooting_star": is_shooting_star,
            "three_white_soldiers": is_three_white_soldiers,
            "three_black_crows": is_three_black_crows
        }
        self.indicators = [
            "rsi", "macd", "macd_signal", "atr", "volume", "volume_sma_20",
            "bb_upper", "bb_lower", "ema_20", "ema_50", "stoch_rsi", "adx",
            "cci", "vwap", "momentum"
        ]
        log("Signal Predictor initialized with 15 indicators and candle patterns")

    async def calculate_take_profits(self, df: pd.DataFrame, direction: str, current_price: float):
        try:
            atr = df["atr"].iloc[-1]
            if pd.isna(atr) or atr <= 0:
                log("Invalid ATR value for TP/SL calculation", level="WARNING")
                return None, None, None, None
            
            if direction == "LONG":
                tp1 = current_price + (0.15 * atr)
                tp2 = current_price + (0.3 * atr)
                tp3 = current_price + (0.45 * atr)
                sl = current_price - (1.2 * atr)
            else:  # SHORT
                tp1 = current_price - (0.15 * atr)
                tp2 = current_price - (0.3 * atr)
                tp3 = current_price - (0.45 * atr)
                sl = current_price + (1.2 * atr)
            
            if not all([tp1, tp2, tp3, sl]) or any(np.isclose([tp1, tp2, tp3, sl], current_price, rtol=1e-5)):
                log("Invalid TP/SL values calculated", level="WARNING")
                return None, None, None, None
            
            return tp1, tp2, tp3, sl
        except Exception as e:
            log(f"Error calculating TP/SL: {str(e)}", level="ERROR")
            return None, None, None, None

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str = "15m"):
        try:
            signal_key = f"{symbol}_{timeframe}"
            last_signal_time = self.last_signals.get(signal_key)
            if last_signal_time and (pd.Timestamp.now() - last_signal_time).total_seconds() < 3600:
                log(f"[{symbol}] Skipping duplicate signal within 1 hour", level="INFO")
                return None

            # Check if all required indicators are present
            missing_indicators = [ind for ind in self.indicators if ind not in df.columns]
            if missing_indicators:
                log(f"[{symbol}] Missing indicators: {missing_indicators}", level="WARNING")
                return None

            # Calculate candle patterns
            pattern_results = {}
            for name, func in self.candle_patterns.items():
                try:
                    result = func(df)
                    pattern_results[name] = result.iloc[-1] if isinstance(result, pd.Series) else result
                except Exception as e:
                    log(f"Error calculating {name}: {e}", level="WARNING")
                    pattern_results[name] = 0.0

            # Initialize signal parameters
            direction = None
            confidence = 0.0

            # Bullish signals
            if pattern_results["bullish_engulfing"] or pattern_results["hammer"] or pattern_results["three_white_soldiers"]:
                direction = "LONG"
                confidence = 0.65  # Base confidence for bullish patterns
                # Adjust confidence based on indicators
                if df["rsi"].iloc[-1] < 30:  # Oversold RSI
                    confidence += 0.05
                if df["macd"].iloc[-1] > df["macd_signal"].iloc[-1]:  # MACD bullish crossover
                    confidence += 0.05
                if df["close"].iloc[-1] > df["vwap"].iloc[-1]:  # Price above VWAP
                    confidence += 0.03
                if df["stoch_rsi"].iloc[-1] < 20:  # Oversold Stochastic RSI
                    confidence += 0.03
                if df["adx"].iloc[-1] > 25:  # Strong trend
                    confidence += 0.03
                if df["cci"].iloc[-1] > 100:  # Bullish CCI
                    confidence += 0.03
                if df["ema_20"].iloc[-1] > df["ema_50"].iloc[-1]:  # Bullish EMA crossover
                    confidence += 0.03
                if df["momentum"].iloc[-1] > 0:  # Positive momentum
                    confidence += 0.03
                if df["close"].iloc[-1] > df["bb_upper"].iloc[-1]:  # Breakout above Bollinger Band
                    confidence += 0.03

            # Bearish signals
            elif pattern_results["bearish_engulfing"] or pattern_results["shooting_star"] or pattern_results["three_black_crows"]:
                direction = "SHORT"
                confidence = 0.65  # Base confidence for bearish patterns
                # Adjust confidence based on indicators
                if df["rsi"].iloc[-1] > 70:  # Overbought RSI
                    confidence += 0.05
                if df["macd"].iloc[-1] < df["macd_signal"].iloc[-1]:  # MACD bearish crossover
                    confidence += 0.05
                if df["close"].iloc[-1] < df["vwap"].iloc[-1]:  # Price below VWAP
                    confidence += 0.03
                if df["stoch_rsi"].iloc[-1] > 80:  # Overbought Stochastic RSI
                    confidence += 0.03
                if df["adx"].iloc[-1] > 25:  # Strong trend
                    confidence += 0.03
                if df["cci"].iloc[-1] < -100:  # Bearish CCI
                    confidence += 0.03
                if df["ema_20"].iloc[-1] < df["ema_50"].iloc[-1]:  # Bearish EMA crossover
                    confidence += 0.03
                if df["momentum"].iloc[-1] < 0:  # Negative momentum
                    confidence += 0.03
                if df["close"].iloc[-1] < df["bb_lower"].iloc[-1]:  # Breakout below Bollinger Band
                    confidence += 0.03

            # Adjust confidence based on volume
            if df["volume"].iloc[-1] > df["volume_sma_20"].iloc[-1]:
                confidence += 0.05

            confidence = min(confidence, 0.95)  # Cap confidence at 95%

            if direction is None or confidence < self.min_confidence_threshold:
                log(f"[{symbol}] No valid signal or low confidence: {confidence*100:.2f}%", level="INFO")
                return None

            current_price = df["close"].iloc[-1]
            tp1, tp2, tp3, sl = await self.calculate_take_profits(df, direction, current_price)
            if any(x is None for x in [tp1, tp2, tp3, sl]):
                log(f"[{symbol}] Invalid TP/SL values", level="WARNING")
                return None

            # Dynamic TP hit rates
            atr = df["atr"].iloc[-1]
            atr_factor = min(atr / current_price, 1.0)
            tp1_hit_rate = min(0.75 + (confidence - 0.65) * 0.15 - atr_factor * 0.1, 0.90)
            tp2_hit_rate = min(0.50 + (confidence - 0.65) * 0.20 - atr_factor * 0.15, 0.75)
            tp3_hit_rate = min(0.25 + (confidence - 0.65) * 0.25 - atr_factor * 0.2, 0.60)

            signal = {
                "symbol": symbol,
                "direction": direction,
                "entry": current_price,
                "tp1": round(tp1, 4),
                "tp2": round(tp2, 4),
                "tp3": round(tp3, 4),
                "sl": round(sl, 4),
                "confidence": confidence * 100,
                "tp1_possibility": round(tp1_hit_rate, 2),
                "tp2_possibility": round(tp2_hit_rate, 2),
                "tp3_possibility": round(tp3_hit_rate, 2),
                "timeframe": timeframe,
                "timestamp": pd.Timestamp.now(tz=pytz.timezone("Asia/Karachi")).isoformat()
            }

            self.last_signals[signal_key] = pd.Timestamp.now()
            log(f"[{symbol}] Signal generated - Direction: {direction}, Confidence: {confidence*100:.2f}%")
            return signal
        except Exception as e:
            log(f"[{symbol}] Error predicting signal: {str(e)}", level="ERROR")
            return None
