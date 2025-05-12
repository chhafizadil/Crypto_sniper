import pandas as pd
import numpy as np
import logging
from typing import Tuple, Dict

class TechnicalAnalysis:
    def __init__(self):
        self.log = logging.getLogger("crypto-signal-bot")

    async def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for the given DataFrame."""
        try:
            # RSI
            df['rsi'] = self._calculate_rsi(df['close'], 14)

            # MACD
            df['macd'], df['macd_signal'] = self._calculate_macd(df['close'])

            # ATR
            df['atr'] = self._calculate_atr(df, 14)

            # Volume SMA 20
            df['volume_sma_20'] = df['volume'].rolling(window=20).mean()

            # Bollinger Bands
            df['bb_upper'], df['bb_lower'] = self._calculate_bollinger_bands(df['close'])

            # EMA 20 and 50
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

            # Stochastic RSI
            df['stoch_rsi'] = self._calculate_stoch_rsi(df['rsi'], 14)

            # ADX
            df['adx'] = self._calculate_adx(df, 14)

            # CCI
            df['cci'] = self._calculate_cci(df, 20)

            # VWAP
            df['vwap'] = self._calculate_vwap(df)

            # Momentum
            df['momentum'] = df['close'].diff(10)

            self.log.info("Indicators calculated: RSI, MACD, ATR, Volume, Bollinger Bands, Volume SMA 20, EMA 20, EMA 50, Stochastic RSI, ADX, CCI, VWAP, Momentum")
            return df

        except Exception as e:
            self.log.error(f"Error calculating indicators: {str(e)}")
            return df

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_macd(self, series: pd.Series) -> Tuple[pd.Series, pd.Series]:
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

    def _calculate_bollinger_bands(self, series: pd.Series, period: int = 20) -> Tuple[pd.Series, pd.Series]:
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
        close = df['close']
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
