import ccxt.async_support as ccxt
from model.predictor import SignalPredictor
from data.collector import fetch_realtime_data
from core.multi_timeframe import multi_timeframe_boost
from utils.logger import logger

async def analyze_symbol_multi_timeframe(symbol: str, exchange: ccxt.Exchange, timeframes: list) -> dict:
    try:
        predictor = SignalPredictor()
        signals = {}
        
        for timeframe in timeframes:
            logger.info(f"[{symbol}] Starting analysis on {timeframe}")
            df = await fetch_realtime_data(symbol, timeframe)
            if df is None or len(df) < 20:
                logger.warning(f"[{symbol}] Insufficient data for {timeframe}")
                continue
                
            signal = await predictor.predict_signal(symbol, df, timeframe)
            if signal:
                boost = await multi_timeframe_boost(symbol, exchange, signal['direction'])
                signal['confidence'] = min(100.0, signal['confidence'] + boost)
                signals[timeframe] = signal
            else:
                logger.info(f"[{symbol}] No signal generated for {timeframe}")
                
        return signals
    except Exception as e:
        logger.error(f"[{symbol}] Error in multi-timeframe analysis: {str(e)}")
        return {}
