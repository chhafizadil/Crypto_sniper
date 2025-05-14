from typing import Dict, List, Optional
from model.predictor import SignalPredictor
import pandas as pd
import numpy as np
from utils.logger import logger

async def analyze_symbol_multi_timeframe(exchange, symbol: str, timeframes: List[str], predictor: SignalPredictor, bars: int = 200) -> Optional[Dict]:
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
                if df[['rsi', 'volume_sma_20', 'macd', 'macd_signal', 'atr']].isna().any().any():
                    logger.warning(f"[{symbol}] NaN values in indicators for {timeframe}")
                    continue
                
                signal = await predictor.predict_signal(symbol, df, timeframe)
                if signal:
                    signals.append(signal)
                    logger.info(f"[{symbol}] Signal for {timeframe}: {signal['direction']}, Confidence: {signal['confidence']:.2f}%")
                else:
                    logger.info(f"[{symbol}] No signal for {timeframe}")
            except Exception as e:
                logger.error(f"[{symbol}] Error in analysis for {timeframe}: {str(e)}")
                continue
        
        if not signals:
            logger.info(f"[{symbol}] No valid signals across any timeframe")
            return None

        timeframe_agreement = len([s for s in signals if s['direction'] == signals[0]['direction']]) / len(signals)
        if timeframe_agreement < 0.50:  # Relaxed to allow 2/4 timeframes
            logger.info(f"[{symbol}] Insufficient timeframe agreement ({timeframe_agreement:.2f})")
            return None

        avg_confidence = np.mean([s['confidence'] for s in signals])
        best_signal = max(signals, key=lambda x: x['confidence'])
        best_signal['confidence'] = min(avg_confidence, 100)  # Stable confidence
        logger.info(f"[{symbol}] Final signal selected with adjusted confidence: {best_signal['confidence']:.2f}%")

        return {"symbol": symbol, "signals": [best_signal]}
    except Exception as e:
        logger.error(f"[{symbol}] Error in multi-timeframe analysis: {str(e)}")
        return None
