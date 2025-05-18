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
            logger.info(f"[{symbol}] Starting analysis on {timeframe}")
            df = await fetch_realtime_data(symbol, timeframe, limit=100)  # Limit to 100 candles
            if df is None or len(df) < 20:
                logger.warning(f"[{symbol}] Insufficient data for {timeframe}: {len(df) if df is not None else 'None'}")
                signals[timeframe] = None
                continue
            # Fetch OHLCV data with limit to reduce memory usage

            signal = await predictor.predict_signal(symbol, df, timeframe)
            if signal:
                boost = await multi_timeframe_boost(symbol, exchange, signal['direction'])
                signal['confidence'] = min(100.0, signal['confidence'] + boost)
                signals[timeframe] = signal
                logger.info(f"[{symbol}] Signal generated for {timeframe}: {signal['direction']}, Confidence: {signal['confidence']}%")
            else:
                signals[timeframe] = None
                logger.info(f"[{symbol}] No signal generated for {timeframe}")
            # Generate signal and apply multi-timeframe boost

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
            if timeframe_agreement < 0.50:  # Relaxed to allow 2/4 timeframes
                logger.info(f"[{symbol}] Insufficient timeframe agreement ({timeframe_agreement:.2f})")
                # Try adjusting to 3 or 2 timeframes
                for min_timeframes in [3, 2]:
                    valid_subset = [s for s in valid_signals[:min_timeframes] if s is not None]
                    if len(valid_subset) >= min_timeframes:
                        subset_directions = [s['direction'] for s in valid_subset]
                        subset_agreement = len([d for d in subset_directions if d == subset_directions[0]]) / len(subset_directions)
                        if subset_agreement >= 0.50:
                            logger.info(f"[{symbol}] Adjusted to {min_timeframes} timeframes with agreement: {subset_agreement:.2f}")
                            return {tf: s for tf, s in signals.items() if s in valid_subset}
                logger.info(f"[{symbol}] No sufficient agreement even with {min_timeframes} timeframes")
                return {}
            # Calculate timeframe agreement and adjust to 3 or 2 timeframes if needed
        return signals
        # Return signals if agreement is sufficient

    except Exception as e:
        logger.error(f"[{symbol}] Error in multi-timeframe analysis: {str(e)}")
        return {}
        # Log any errors during multi-timeframe analysis
