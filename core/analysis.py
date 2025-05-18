# Core module for multi-timeframe analysis of trading symbols
# Updated to add stricter data validation for OHLCV fetching
import pandas as pd
import asyncio
import ccxt.async_support as ccxt
from model.predictor import SignalPredictor
from data.collector import fetch_realtime_data
from utils.logger import logger

# Main function to analyze a symbol across multiple timeframes
async def analyze_symbol_multi_timeframe(symbol: str, exchange: ccxt.Exchange, timeframes: list) -> dict:
    try:
        # Initialize the signal predictor
        predictor = SignalPredictor()
        signals = {}

        # Iterate through each timeframe for analysis
        for timeframe in timeframes:
            try:
                logger.info(f"[{symbol}] Fetching OHLCV data for {timeframe}")
                # Fetch OHLCV data with a limit of 50 candles
                df = await fetch_realtime_data(symbol, timeframe, limit=50)
                # Stricter validation: ensure dataframe is not empty and has valid price/volume
                if df is None or len(df) < 50 or df['close'].isnull().any() or (df['close'] <= 0).any() or (df['volume'] <= 0).any():
                    logger.warning(f"[{symbol}] Invalid or insufficient data for {timeframe}: {len(df) if df is not None else 'None'} rows")
                    signals[timeframe] = None
                    continue

                logger.info(f"[{symbol}] OHLCV data fetched for {timeframe}: {len(df)} rows")
                # Predict signal for the timeframe
                signal = await predictor.predict_signal(symbol, df, timeframe)
                signals[timeframe] = signal
            except Exception as e:
                logger.error(f"[{symbol}] Error analyzing {timeframe}: {str(e)}")
                signals[timeframe] = None
                continue

        # Filter valid signals
        valid_signals = [s for s in signals.values() if s is not None]
        if not valid_signals:
            logger.info(f"[{symbol}] No valid signals across any timeframe")
            return signals

        # Calculate timeframe agreement for signal consistency
        directions = [s['direction'] for s in valid_signals]
        if directions:
            timeframe_agreement = len([d for d in directions if d == directions[0]]) / len(directions)
            logger.info(f"[{symbol}] Timeframe agreement: {timeframe_agreement:.2f}")
            # Lowered threshold to 15% for flexibility
            if timeframe_agreement < 0.15:
                logger.info(f"[{symbol}] Insufficient timeframe agreement ({timeframe_agreement:.2f})")
                return signals
        return signals

    except Exception as e:
        logger.error(f"[{symbol}] Error in multi-timeframe analysis: {str(e)}")
        return {}
