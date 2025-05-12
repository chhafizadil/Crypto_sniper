import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from utils.logger import logger
import ccxt.async_support as ccxt

class SignalPredictor:
    def __init__(self):
        self.indicators = [
            "rsi", "macd", "atr", "volume", "bollinger", "volume_sma_20", 
            "ema_20", "ema_50", "stoch_rsi", "adx", "cci", "vwap", "momentum"
        ]
        self.candle_patterns = ["doji", "engulfing", "harami"]
        self.previous_signals = {}
        self.exchange = ccxt.binance()
        logger.info("Signal Predictor initialized with %d indicators and candle patterns", len(self.indicators))

    async def get_symbol_precision(self, symbol: str) -> int:
        try:
            await self.exchange.load_markets()
            market = self.exchange.markets[symbol]
            precision = market['precision']['price']
            return precision
        except Exception as e:
            logger.error(f"[{symbol}] Error fetching precision: {str(e)}")
            return 3

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df['rsi'] = self._calculate_rsi(df['close'], 14)
            df['macd'], df['macd_signal'] = self._calculate_macd(df['close'])
            df['atr'] = self._calculate_atr(df, 14)
            df['volume_sma_20'] = df['volume'].rolling(window=20).mean()
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['stoch_rsi'] = self._calculate_stoch_rsi(df['rsi'], 14)
            df['adx'] = self._calculate_adx(df, 14)
            df['cci'] = self._calculate_cci(df, 20)
            df['vwap'] = self._calculate_vwap(df)
            df['momentum'] = df['close'].diff(10)
            logger.info("Indicators calculated: %s", ", ".join(self.indicators))
            return df
        except Exception as e:
            logger.error("Error calculating indicators: %s", str(e))
            return df

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_macd(self, series: pd.Series) -> tuple:
        exp1 = series.ewm(span=12, adjust=False).mean()
        exp2 = series.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return true_range.rolling(window=period).mean()

    def _calculate_stoch_rsi(self, rsi: pd.Series, period: int) -> pd.Series:
        min_rsi = rsi.rolling(window=period).min()
        max_rsi = rsi.rolling(window=period).max()
        stoch_rsi = (rsi - min_rsi) / (max_rsi - min_rsi) * 100
        return stoch_rsi

    def _calculate_adx(self, df: pd.DataFrame, period: int) -> pd.Series:
        high = df['high']
        low = df['low']
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        tr = self._calculate_atr(df, period)
        plus_di = 100 * plus_dm.rolling(window=period).mean() / tr
        minus_di = 100 * (-minus_dm).rolling(window=period).mean() / tr
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        return adx

    def _calculate_cci(self, df: pd.DataFrame, period: int) -> pd.Series:
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        sma = typical_price.rolling(window=period).mean()
        mean_deviation = typical_price.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())))
        cci = (typical_price - sma) / (0.015 * mean_deviation)
        return cci

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        return vwap

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str) -> Optional[Dict]:
        try:
            if symbol in self.previous_signals and timeframe in self.previous_signals[symbol]:
                last_signal_time = self.previous_signals[symbol][timeframe]
                if datetime.utcnow() - last_signal_time < timedelta(hours=1):
                    logger.info("[%s] Signal already generated for %s within last hour", symbol, timeframe)
                    return None

            df = self.calculate_indicators(df)
            if df.empty or len(df) < 20:
                logger.warning("[%s] Insufficient data for %s", symbol, timeframe)
                return None

            latest = df.iloc[-1]
            confidence = 0.0
            direction = None
            conditions = []

            if (latest['rsi'] < 35 and latest['macd'] > latest['macd_signal'] and latest['ema_20'] > latest['ema_50'] and
                latest['stoch_rsi'] < 25 and latest['adx'] > 30 and latest['cci'] > 120 and latest['momentum'] > 0):
                direction = "LONG"
                confidence += 25
                conditions.append("Oversold RSI, bullish MACD crossover, EMA trend, strong ADX, high CCI, positive momentum")
                if latest['volume'] > latest['volume_sma_20'] * 1.2:
                    confidence += 15
                    conditions.append("Elevated volume")
                if latest['close'] > latest['vwap']:
                    confidence += 10
                    conditions.append("Price above VWAP")

            elif (latest['rsi'] > 65 and latest['macd'] < latest['macd_signal'] and latest['ema_20'] < latest['ema_50'] and
                  latest['stoch_rsi'] > 75 and latest['adx'] > 30 and latest['cci'] < -120 and latest['momentum'] < 0):
                direction = "SHORT"
                confidence += 25
                conditions.append("Overbought RSI, bearish MACD crossover, EMA trend, strong ADX, low CCI, negative momentum")
                if latest['volume'] > latest['volume_sma_20'] * 1.2:
                    confidence += 15
                    conditions.append("Elevated volume")
                if latest['close'] < latest['vwap']:
                    confidence += 10
                    conditions.append("Price below VWAP")

            timeframe_weights = {"15m": 0.85, "1h": 0.9, "4h": 1.0, "1d": 1.1}
            confidence *= timeframe_weights.get(timeframe, 1.0)

            confidence = min(max(confidence, 0), 100)

            if confidence >= 60:
                precision = await self.get_symbol_precision(symbol)
                atr = latest['atr']
                current_price = latest['close']
                
                signal = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "confidence": confidence,
                    "entry": round(current_price, precision),
                    "tp1": round(current_price + atr * 1.2 if direction == "LONG" else current_price - atr * 1.2, precision),
                    "tp2": round(current_price + atr * 1.8 if direction == "LONG" else current_price - atr * 1.8, precision),
                    "tp3": round(current_price + atr * 2.5 if direction == "LONG" else current_price - atr * 2.5, precision),
                    "sl": round(current_price - atr * 1.2 if direction == "LONG" else current_price + atr * 1.2, precision),
                    "tp1_possibility": 0.75,
                    "tp2_possibility": 0.55,
                    "tp3_possibility": 0.35,
                    "conditions": conditions,
                    "volume": latest['volume']
                }
                logger.info("[%s] Signal generated - Direction: %s, Confidence: %.2f%%", 
                           symbol, direction, confidence)
                
                if symbol not in self.previous_signals:
                    self.previous_signals[symbol] = {}
                self.previous_signals[symbol][timeframe] = datetime.utcnow()
                
                return signal
            else:
                logger.info("[%s] No valid signal or low confidence: %.2f%%", symbol, confidence)
                return None
        except Exception as e:
            logger.error("[%s] Error predicting signal for %s: %s", symbol, timeframe, str(e))
            return None
