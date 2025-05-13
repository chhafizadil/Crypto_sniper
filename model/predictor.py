import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from utils.logger import logger
import ccxt.async_support as ccxt
from utils.helpers import format_price

class SignalPredictor:
    def __init__(self):
        self.indicators = [
            "rsi", "macd", "atr", "volume", "bollinger", "volume_sma_20", 
            "ema_20", "ema_50", "stoch_rsi", "adx", "cci", "vwap", "momentum", "obv"
        ]
        self.candle_patterns = ["doji", "engulfing", "harami", "morning_star", "evening_star"]
        self.previous_signals = {}
        self.exchange = ccxt.binance()
        logger.info("Signal Predictor initialized with %d indicators and candle patterns", len(self.indicators))

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df['rsi'] = self._calculate_rsi(df['close'], 14)
            df['macd'], df['macd_signal'] = self._calculate_macd(df['close'])
            df['atr'] = self._calculate_atr(df, 14)
            df['volume_sma_20'] = df['volume'].rolling(window=20).mean()
            df['bb_upper'], df['bb_lower'] = self._calculate_bollinger_bands(df['close'])
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['stoch_rsi'] = self._calculate_stoch_rsi(df['rsi'], 14)
            df['adx'] = self._calculate_adx(df, 14)
            df['cci'] = self._calculate_cci(df, 20)
            df['vwap'] = self._calculate_vwap(df)
            df['momentum'] = df['close'].diff(10)
            df['obv'] = self._calculate_obv(df)
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

    def _calculate_bollinger_bands(self, series: pd.Series, period: int = 20) -> tuple:
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper_band = sma + (std * 2)
        lower_band = sma - (std * 2)
        return upper_band, lower_band

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

    def _calculate_obv(self, df: pd.DataFrame) -> pd.Series:
        obv = [0]
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['close'].iloc[i-1]:
                obv.append(obv[-1] + df['volume'].iloc[i])
            elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                obv.append(obv[-1] - df['volume'].iloc[i])
            else:
                obv.append(obv[-1])
        return pd.Series(obv, index=df.index)

    async def detect_candle_patterns(self, df: pd.DataFrame) -> list:
        patterns = []
        try:
            for i in range(2, len(df)):
                open_price = df['open'].iloc[i]
                close_price = df['close'].iloc[i]
                high_price = df['high'].iloc[i]
                low_price = df['low'].iloc[i]
                prev_open = df['open'].iloc[i-1]
                prev_close = df['close'].iloc[i-1]
                prev2_open = df['open'].iloc[i-2]
                prev2_close = df['close'].iloc[i-2]
                
                body = abs(close_price - open_price)
                if body < (high_price - low_price) * 0.1:
                    patterns.append("doji")
                
                if (close_price > prev_open and open_price < prev_close and
                    close_price > prev_close and open_price < prev_open):
                    patterns.append("engulfing")
                
                if (body < abs(prev_open - prev_close) * 0.5 and
                    high_price < prev_close and low_price > prev_open):
                    patterns.append("harami")
                
                if (prev2_close > prev2_open and prev_close < prev_open and
                    close_price > prev_open and close_price > (prev2_open + prev2_close) / 2):
                    patterns.append("morning_star")
                
                if (prev2_close < prev2_open and prev_close > prev_open and
                    close_price < prev_open and close_price < (prev2_open + prev2_close) / 2):
                    patterns.append("evening_star")
            return patterns
        except Exception as e:
            logger.error("Error detecting candle patterns: %s", str(e))
            return []

    async def get_symbol_precision(self, symbol: str) -> int:
        try:
            await self.exchange.load_markets()
            market = self.exchange.markets[symbol]
            precision = market['precision']['price']
            return precision
        except Exception as e:
            logger.error(f"[{symbol}] Error fetching precision: {str(e)}")
            return 3

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

            # Volatility check
            latest = df.iloc[-1]
            if latest['atr'] > df['atr'].rolling(window=20).mean() * 1.5:
                logger.info(f"[{symbol}] High volatility for {timeframe}, skipping signal")
                return None

            patterns = await self.detect_candle_patterns(df)
            confidence = 0.0
            direction = None
            conditions = []

            # LONG condition
            if (pd.notna(latest['rsi']) and latest['rsi'] < 35 and 
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] > latest['macd_signal'] and 
                pd.notna(latest['ema_20']) and pd.notna(latest['ema_50']) and latest['ema_20'] > latest['ema_50'] and
                pd.notna(latest['stoch_rsi']) and latest['stoch_rsi'] < 25 and 
                pd.notna(latest['adx']) and latest['adx'] > 30 and 
                pd.notna(latest['cci']) and latest['cci'] > 120 and 
                pd.notna(latest['momentum']) and latest['momentum'] > 0 and
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'] * 1.2 and
                pd.notna(latest['obv']) and pd.notna(df['obv'].shift(1).iloc[-1]) and latest['obv'] > df['obv'].shift(1).iloc[-1] * 1.1):
                direction = "LONG"
                confidence += 25
                conditions.append("Oversold RSI, bullish MACD crossover, EMA trend, strong ADX, high CCI, positive momentum, high volume, rising OBV")
                if pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'] * 1.2:
                    confidence += 15
                    conditions.append("Elevated volume")
                if pd.notna(latest['close']) and pd.notna(latest['vwap']) and latest['close'] > latest['vwap']:
                    confidence += 10
                    conditions.append("Price above VWAP")
                if any(p in patterns for p in ["engulfing", "morning_star"]):
                    confidence += 10
                    conditions.append(f"Bullish pattern: {patterns[-1] if patterns else 'none'}")

            # SHORT condition
            elif (pd.notna(latest['rsi']) and latest['rsi'] > 65 and 
                  pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] < latest['macd_signal'] and 
                  pd.notna(latest['ema_20']) and pd.notna(latest['ema_50']) and latest['ema_20'] < latest['ema_50'] and
                  pd.notna(latest['stoch_rsi']) and latest['stoch_rsi'] > 75 and 
                  pd.notna(latest['adx']) and latest['adx'] > 30 and 
                  pd.notna(latest['cci']) and latest['cci'] < -120 and 
                  pd.notna(latest['momentum']) and latest['momentum'] < 0 and
                  pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] < latest['volume_sma_20'] * 0.9 and
                  pd.notna(latest['obv']) and pd.notna(df['obv'].shift(1).iloc[-1]) and latest['obv'] < df['obv'].shift(1).iloc[-1] * 0.9):
                direction = "SHORT"
                confidence += 25
                conditions.append("Overbought RSI, bearish MACD crossover, EMA trend, strong ADX, low CCI, negative momentum, low volume, falling OBV")
                if pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'] * 1.2:
                    confidence += 15
                    conditions.append("Elevated volume")
                if pd.notna(latest['close']) and pd.notna(latest['vwap']) and latest['close'] < latest['vwap']:
                    confidence += 10
                    conditions.append("Price below VWAP")
                if any(p in patterns for p in ["engulfing", "evening_star"]):
                    confidence += 10
                    conditions.append(f"Bearish pattern: {patterns[-1] if patterns else 'none'}")

            timeframe_weights = {"15m": 0.85, "1h": 0.9, "4h": 1.0, "1d": 1.1}
            confidence *= timeframe_weights.get(timeframe, 1.0)

            confidence = min(max(confidence, 0), 100)

            if confidence >= 80:
                precision = await self.get_symbol_precision(symbol)
                atr = latest['atr']
                current_price = latest['close']
                
                signal = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "confidence": confidence,
                    "entry": format_price(current_price, symbol),
                    "tp1": format_price(current_price + atr * 1.2 if direction == "LONG" else current_price - atr * 1.2, symbol),
                    "tp2": format_price(current_price + atr * 1.8 if direction == "LONG" else current_price - atr * 1.8, symbol),
                    "tp3": format_price(current_price + atr * 2.5 if direction == "LONG" else current_price - atr * 2.5, symbol),
                    "sl": format_price(current_price - atr * 1.2 if direction == "LONG" else current_price + atr * 1.2, symbol),
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
