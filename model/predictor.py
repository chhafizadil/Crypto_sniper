# model/predictor.py
import pandas as pd
import numpy as np
from typing import Dict, Optional
from utils.logger import logger
import ta
import ccxt.async_support as ccxt

class SignalPredictor:
    def __init__(self):
        self.min_data_points = 20
        self.exchange = ccxt.binance()
        logger.info("Signal Predictor initialized")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df = df.copy()
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14, fillna=True).rsi()
            df['volume_sma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()
            df['macd'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True).macd()
            df['macd_signal'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9, fillna=True).macd_signal()
            df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14, fillna=True).average_true_range()
            df['bb_upper'] = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2, fillna=True).bollinger_hband()
            df['bb_lower'] = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2, fillna=True).bollinger_lband()
            df['ema_fast'] = ta.trend.EMAIndicator(df['close'], window=12, fillna=True).ema_indicator()
            df['ema_slow'] = ta.trend.EMAIndicator(df['close'], window=26, fillna=True).ema_indicator()
            df['stoch_k'] = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3, fillna=True).stoch()

            df.replace([np.inf, -np.inf], np.nan, inplace=True)
            df.ffill(inplace=True)
            df.fillna(0.0, inplace=True)
            
            logger.info("Indicators calculated: rsi, volume_sma_20, macd, atr, bb_upper, bb_lower, ema_fast, ema_slow, stoch_k")
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
            if df[['rsi', 'volume_sma_20', 'macd', 'macd_signal', 'atr', 'bb_upper', 'bb_lower', 'ema_fast', 'ema_slow', 'stoch_k']].isna().any().any():
                logger.warning(f"[{symbol}] NaN values in critical indicators for {timeframe}")
                return None

            long_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] < 50,
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] > latest['volume_sma_20'],
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] > latest['macd_signal'],
                pd.notna(latest['bb_lower']) and latest['close'] < latest['bb_lower'],
                pd.notna(latest['ema_fast']) and pd.notna(latest['ema_slow']) and latest['ema_fast'] > latest['ema_slow'],
                pd.notna(latest['stoch_k']) and latest['stoch_k'] < 20
            ]
            short_conditions = [
                pd.notna(latest['rsi']) and latest['rsi'] > 50,
                pd.notna(latest['volume']) and pd.notna(latest['volume_sma_20']) and latest['volume'] < latest['volume_sma_20'],
                pd.notna(latest['macd']) and pd.notna(latest['macd_signal']) and latest['macd'] < latest['macd_signal'],
                pd.notna(latest['bb_upper']) and latest['close'] > latest['bb_upper'],
                pd.notna(latest['ema_fast']) and pd.notna(latest['ema_slow']) and latest['ema_fast'] < latest['ema_slow'],
                pd.notna(latest['stoch_k']) and latest['stoch_k'] > 80
            ]

            long_confidence = sum([20 for cond in long_conditions if cond])
            short_confidence = sum([20 for cond in short_conditions if cond])

            direction = None
            confidence = 0
            conditions_met = []

            if sum(long_conditions) >= 3:
                direction = "LONG"
                confidence = long_confidence
                conditions_met = [
                    "rsi < 50" if long_conditions[0] else "",
                    "volume > volume_sma_20" if long_conditions[1] else "",
                    "macd > macd_signal" if long_conditions[2] else "",
                    "close < bb_lower" if long_conditions[3] else "",
                    "ema_fast > ema_slow" if long_conditions[4] else "",
                    "stoch_k < 20" if long_conditions[5] else ""
                ]
                conditions_met = [c for c in conditions_met if c]
            elif sum(short_conditions) >= 3:
                direction = "SHORT"
                confidence = short_confidence
                conditions_met = [
                    "rsi > 50" if short_conditions[0] else "",
                    "volume < volume_sma_20" if short_conditions[1] else "",
                    "macd < macd_signal" if short_conditions[2] else "",
                    "close > bb_upper" if short_conditions[3] else "",
                    "ema_fast < ema_slow" if short_conditions[4] else "",
                    "stoch_k > 80" if short_conditions[5] else ""
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
                if direction == "LONG":
                    tp1 = round(current_price + max(atr * multiplier, min_diff), 8)
                    tp2 = round(tp1 + max(atr * 0.5, min_diff), 8)
                    tp3 = round(tp2 + max(atr * 0.5, min_diff), 8)
                    sl = round(current_price - max(atr * 1.5, min_diff), 8)
                else:  # SHORT
                    tp1 = round(current_price - max(atr * multiplier, min_diff), 8)
                    tp2 = round(tp1 - max(atr * 0.5, min_diff), 8)
                    tp3 = round(tp2 - max(atr * 0.5, min_diff), 8)
                    sl = round(current_price + max(atr * 1.5, min_diff), 8)
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
                    "hit_timestamp": None
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
