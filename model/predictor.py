import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from utils.logger import log
import ccxt.async_support as ccxt

class SignalPredictor:
    def __init__(self):
        self.indicators = [
            "rsi", "macd", "atr", "volume", "bollinger", "volume_sma_20", 
            "ema_20", "ema_50", "stoch_rsi", "adx", "cci", "vwap", "momentum"
        ]
        self.candle_patterns = ["doji", "engulfing", "harami"]
        self.previous_signals = {}  # {symbol: {timeframe: timestamp}}
        self.exchange = ccxt.binance()
        log.info("Signal Predictor initialized with %d indicators and candle patterns", len(self.indicators))

    async def get_symbol_precision(self, symbol: str) -> int:
        try:
            await self.exchange.load_markets()
            market = self.exchange.markets[symbol]
            precision = market['precision']['price']
            return precision
        except Exception as e:
            log.error(f"[{symbol}] Error fetching precision: {str(e)}")
            return 3  # Default to 3 decimals

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            # Placeholder for indicator calculations
            df['rsi'] = np.random.uniform(30, 70, len(df))  # Simulated RSI
            df['macd'] = np.random.uniform(-1, 1, len(df))
            df['atr'] = np.random.uniform(0.1, 1, len(df))
            df['volume_sma_20'] = df['volume'].rolling(window=20).mean()
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['stoch_rsi'] = np.random.uniform(0, 100, len(df))
            df['adx'] = np.random.uniform(10, 50, len(df))
            df['cci'] = np.random.uniform(-100, 100, len(df))
            df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
            df['momentum'] = df['close'].diff(4)
            log.info("Indicators calculated: %s", ", ".join(self.indicators))
            return df
        except Exception as e:
            log.error("Error calculating indicators: %s", str(e))
            return df

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str) -> Optional[Dict]:
        try:
            # Check for recent signals to avoid duplicates
            if symbol in self.previous_signals and timeframe in self.previous_signals[symbol]:
                last_signal_time = self.previous_signals[symbol][timeframe]
                if datetime.utcnow() - last_signal_time < timedelta(hours=1):
                    log.info("[%s] Signal already generated for %s within last hour", symbol, timeframe)
                    return None

            df = self.calculate_indicators(df)
            if df.empty or len(df) < 20:
                log.warning("[%s] Insufficient data for %s", symbol, timeframe)
                return None

            latest = df.iloc[-1]
            confidence = 0.0
            direction = None
            conditions = []

            # LONG signal conditions
            if (latest['rsi'] < 40 and latest['macd'] > 0 and latest['ema_20'] > latest['ema_50'] and
                latest['stoch_rsi'] < 30 and latest['adx'] > 25 and latest['cci'] > 100):
                direction = "LONG"
                confidence += 20  # Base confidence
                conditions.append("Oversold RSI, bullish MACD, EMA crossover, strong trend")
                if latest['volume'] > latest['volume_sma_20']:
                    confidence += 10  # Volume confirmation
                    conditions.append("High volume")
                if latest['momentum'] > 0:
                    confidence += 10  # Positive momentum
                    conditions.append("Positive momentum")

            # SHORT signal conditions
            elif (latest['rsi'] > 60 and latest['macd'] < 0 and latest['ema_20'] < latest['ema_50'] and
                  latest['stoch_rsi'] > 70 and latest['adx'] > 25 and latest['cci'] < -100):
                direction = "SHORT"
                confidence += 20  # Base confidence
                conditions.append("Overbought RSI, bearish MACD, EMA crossover, strong trend")
                if latest['volume'] > latest['volume_sma_20']:
                    confidence += 10  # Volume confirmation
                    conditions.append("High volume")
                if latest['momentum'] < 0:
                    confidence += 10  # Negative momentum
                    conditions.append("Negative momentum")

            # Adjust confidence based on timeframe
            timeframe_weights = {"15m": 0.9, "1h": 0.95, "4h": 1.0, "1d": 1.05}
            confidence *= timeframe_weights.get(timeframe, 1.0)

            # Ensure confidence is within 0-100
            confidence = min(max(confidence, 0), 100)

            if confidence >= 70:  # Keep threshold tight at 60%
                # Get symbol precision
                precision = await self.get_symbol_precision(symbol)

                # Calculate ATR-based TP/SL
                atr = latest['atr']
                current_price = latest['close']
                
                # Adjust ATR multipliers to ensure TP1 is distinct from entry
                signal = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "confidence": confidence,
                    "entry": round(current_price, precision),
                    "tp1": round(current_price + atr * 1.0 if direction == "LONG" else current_price - atr * 1.0, precision),
                    "tp2": round(current_price + atr * 1.5 if direction == "LONG" else current_price - atr * 1.5, precision),
                    "tp3": round(current_price + atr * 2.0 if direction == "LONG" else current_price - atr * 2.0, precision),
                    "sl": round(current_price - atr * 1.0 if direction == "LONG" else current_price + atr * 1.0, precision),
                    "tp1_possibility": 0.7,
                    "tp2_possibility": 0.5,
                    "tp3_possibility": 0.3,
                    "conditions": conditions
                }
                # Log signal generation
                log.info("[%s] Signal generated - Direction: %s, Confidence: %.2f%%", 
                        symbol, direction, confidence)
                
                # Update previous signals
                if symbol not in self.previous_signals:
                    self.previous_signals[symbol] = {}
                self.previous_signals[symbol][timeframe] = datetime.utcnow()
                
                return signal
            else:
                log.info("[%s] No valid signal or low confidence: %.2f%%", symbol, confidence)
                return None
        except Exception as e:
            log.error("[%s] Error predicting signal for %s: %s", symbol, timeframe, str(e))
            return None
