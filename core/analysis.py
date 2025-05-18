import pandas as pd
import asyncio
import ccxt.async_support as ccxt
from model.predictor import SignalPredictor
from data.collector import fetch_realtime_data
from core.multi_timeframe import multi_timeframe_boost
from utils.logger import logger

async def analyze_symbol_multi_timeframe(symbol: str, exchange: ccxt.Exchange, timeframes: list) -> dict:
    try:
        predictor = SignalPredictor()
        signals = {}
        # Initialize SignalPredictor and signals dictionary

        for timeframe in timeframes:
            try:
                logger.info(f"[{symbol}] Fetching OHLCV data for {timeframe}")
                df = await fetch_realtime_data(symbol, timeframe, limit=100)  # Limit to 100 candles
                if df is None or len(df) < 20:
                    logger.warning(f"[{symbol}] Insufficient data for {timeframe}: {len(df) if df is not None else 'None'}")
                    signals[timeframe] = None
                    continue
                # Fetch OHLCV data with limit to reduce memory usage

                logger.info(f"[{symbol}] OHLCV data fetched for {timeframe}: {len(df)} rows")
                signal = await predictor.predict_signal(symbol, df, timeframe)
                if signal:
                    logger.info(f"[{symbol}] Applying multi-timeframe boost for {timeframe}")
                    boost = await asyncio.wait_for(multi_timeframe_boost(symbol, exchange, signal['direction']), timeout=5.0)
                    signal['confidence'] = min(100.0, signal['confidence'] + boost)
                    signals[timeframe] = signal
                    logger.info(f"[{symbol}] Signal generated for {timeframe}: {signal['direction']}, Confidence: {signal['confidence']}%")
                else:
                    signals[timeframe] = None
                    logger.info(f"[{symbol}] No signal generated for {timeframe}")
                # Generate signal and apply multi-timeframe boost with timeout
            except asyncio.TimeoutError:
                logger.error(f"[{symbol}] Multi-timeframe boost timed out for {timeframe}")
                signals[timeframe] = signal if signal else None
            except Exception as e:
                logger.error(f"[{symbol}] Error analyzing {timeframe}: {str(e)}")
                signals[timeframe] = None
                continue

        # Timeframe agreement check
        valid_signals = [s for s in signals.values() if s is not None]
        if not valid_signals:
            logger.info(f"[{symbol}] No valid signals across any timeframe")
            return signals
        # Check if any valid signals exist

        directions = [s['direction'] for s in valid_signals]
        if directions:
            timeframe_agreement = len([d for d in directions if d == directions[0]]) / len(directions)
            logger.info(f"[{symbol}] Timeframe agreement: {timeframe_agreement:.2f}")
            if timeframe_agreement < 0.33:  # Relaxed to 1/3 timeframes
                logger.info(f"[{symbol}] Insufficient timeframe agreement ({timeframe_agreement:.2f})")
                # Try adjusting to 2 timeframes
                valid_subset = [s for s in valid_signals[:2] if s is not None]
                if len(valid_subset) >= 2:
                    subset_directions = [s['direction'] for s in valid_subset]
                    subset_agreement = len([d for d in subset_directions if d == subset_directions[0]]) / len(subset_directions)
                    if subset_agreement >= 0.50:
                        logger.info(f"[{symbol}] Adjusted to 2 timeframes with agreement: {subset_agreement:.2f}")
                        return {tf: s for tf, s in signals.items() if s in valid_subset}
                logger.info(f"[{symbol}] No sufficient agreement even with 2 timeframes")
                return signals  # Return signals even with low agreement
            # Calculate timeframe agreement and adjust to 2 timeframes if needed
        return signals
        # Return signals

    except Exception as e:
        logger.error(f"[{symbol}] Error in multi-timeframe analysis: {str(e)}")
        return {}
        # Log any errors during multi-timeframe analysis
