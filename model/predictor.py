import os
import pandas as pd
from core.engine import analyze_single_symbol
from core.whale_detector import detect_whale_activity
from utils.helpers import calculate_trade_score
from utils.logger import log_info
from data.collector import fetch_klines
from core.trade_classifier import classify_trade

def predict_signal(symbol: str, interval: str = '5m'):
    try:
        # Step 1: Fetch market data
        df = fetch_klines(symbol, interval)
        if df is None or df.empty:
            log_info(f"[{symbol}] ❌ No data found.")
            return None

        # Step 2: Analyze data using core logic
        analysis = analyze_single_symbol(df)
        if analysis is None:
            log_info(f"[{symbol}] ❌ Analysis failed.")
            return None

        # Step 3: Whale Activity Detection
        whale_activity = detect_whale_activity(symbol, df)
        analysis["whale_activity"] = whale_activity

        # Step 4: Calculate trade score from indicators
        score, indicator_results = calculate_trade_score(df)
        analysis["score"] = score
        analysis["indicators"] = indicator_results

        # Step 5: Only proceed if score >= 4
        if score < 4:
            log_info(f"[{symbol}] ⚠️ Score too low: {score}/6. Skipping.")
            return None

        # Step 6: Triple Verification
        triple_confirmation = (
            analysis["trend_strength"] == "strong" and
            analysis["sentiment"] == "positive" and
            whale_activity
        )

        if not triple_confirmation:
            log_info(f"[{symbol}] ❌ Triple verification failed.")
            return None

        # Step 7: Trade Classification (Scalping, Normal, Spot)
        trade_type = classify_trade(df)
        analysis["trade_type"] = trade_type

        # Step 8: Add Meta Info
        analysis["symbol"] = symbol
        analysis["interval"] = interval
        analysis["confidence"] = "High"
        analysis["status"] = "✅ Signal Confirmed"

        log_info(f"[{symbol}] ✅ High Confidence Signal Generated.")
        return analysis

    except Exception as e:
        log_info(f"[{symbol}] ❌ Exception: {str(e)}")
        return None
