# core/analysis.py
from typing import Dict, List, Optional
from model.predictor import SignalPredictor
import pandas as pd
import numpy as np
from utils.logger import logger

async def analyze_symbol_multi_timeframe(exchange, symbol: str, timeframes: List[str], predictor: SignalPredictor, bars: int = 100) -> Optional[Dict]:
    try:
        signals = []
        timeframe_data = {}
        
        for timeframe in timeframes:
            logger.info(f"[{symbol}] Fetching data for {timeframe}")
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=bars)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                if df.empty or len(df) < 20:
                    logger.warning(f"[{symbol}] Empty or insufficient data for {timeframe} (rows: {len(df)})")
                    continue
                if df[['open', 'high', 'low', 'close', 'volume']].isna().any().any():
                    logger.warning(f"[{symbol}] NaN values in OHLCV data for {timeframe}")
                    continue
                
                timeframe_data[timeframe] = df
            except Exception as e:
                logger.error(f"[{symbol}] Error fetching OHLCV for {timeframe}: {str(e)}")
                continue

        if not timeframe_data:
            logger.info(f"[{symbol}] No data available for any timeframe")
            return None

        for timeframe, df in timeframe_data.items():
            logger.info(f"[{symbol}] Starting analysis on {timeframe}")
            try:
                df = predictor.calculate_indicators(df)
                if df.empty or len(df) < 20:
                    logger.warning(f"[{symbol}] Insufficient data after indicators for {timeframe}")
                    continue
                if df[['rsi', 'volume_sma_20', 'macd', 'macd_signal', 'atr', 'bb_upper', 'bb_lower', 'ema_fast', 'ema_slow', 'stoch_k']].isna().any().any():
                    logger.warning(f"[{symbol}] NaN values in indicators for {timeframe}")
                    continue
                
                signal = await predictor.predict_signal(symbol, df, timeframe)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"[{symbol}] Error in analysis for {timeframe}: {str(e)}")
                continue
        
        if not signals:
            logger.info(f"[{symbol}] No valid signals across any timeframe")
            return None

        # Check timeframe agreement
        primary_direction = max(set(s['direction'] for s in signals), key=lambda d: sum(1 for s in signals if s['direction'] == d))
        timeframe_agreement = len([s for s in signals if s['direction'] == primary_direction]) / len(signals)
        
        # Calculate weighted confidence
        total_confidence = sum(s['confidence'] for s in signals if s['direction'] == primary_direction)
        count_signals = len([s for s in signals if s['direction'] == primary_direction])
        avg_confidence = total_confidence / count_signals if count_signals > 0 else 0
        
        if timeframe_agreement < 0.5 or avg_confidence < 60.0:
            logger.info(f"[{symbol}] Insufficient timeframe agreement ({timeframe_agreement:.2f}) or avg confidence ({avg_confidence:.2f})")
            return None

        best_signal = max([s for s in signals if s['direction'] == primary_direction], key=lambda x: x['confidence'])
        best_signal['confidence'] = min(avg_confidence, 100)
        logger.info(f"[{symbol}] Final signal selected: {best_signal['direction']}, Confidence: {best_signal['confidence']:.2f}%")

        return {"symbol": symbol, "signals": [best_signal]}
    except Exception as e:
        logger.error(f"[{symbol}] Error in multi-timeframe analysis: {str(e)}")
        return None
