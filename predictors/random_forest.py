import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict
from sklearn.ensemble import RandomForestClassifier
import joblib

class RandomForestPredictor:
    def __init__(self):
        # Load pre-trained model
        self.model = joblib.load('models/rf_model.joblib')
        self.log = logging.getLogger("crypto-signal-bot")
        self.log.info("RandomForestPredictor initialized with pre-trained model")

    async def predict_signal(self, symbol: str, df: pd.DataFrame, timeframe: str) -> Optional[Dict]:
        try:
            # Prepare 15 features to match the pre-trained model
            features = [
                df['rsi'].iloc[-1],              # 1: RSI
                df['macd'].iloc[-1],             # 2: MACD
                df['macd_signal'].iloc[-1],      # 3: MACD Signal
                df['bb_upper'].iloc[-1],         # 4: Bollinger Band Upper
                df['bb_lower'].iloc[-1],         # 5: Bollinger Band Lower
                df['atr'].iloc[-1],              # 6: ATR
                df['volume'].iloc[-1],           # 7: Volume
                df['volume_sma_20'].iloc[-1],    # 8: Volume SMA 20
                df['ema_20'].iloc[-1],           # 9: EMA 20
                df['ema_50'].iloc[-1],           # 10: EMA 50
                df['stoch_rsi'].iloc[-1],        # 11: Stochastic RSI
                df['adx'].iloc[-1],              # 12: ADX
                df['cci'].iloc[-1],              # 13: CCI
                df['vwap'].iloc[-1],             # 14: VWAP
                df['momentum'].iloc[-1]          # 15: Momentum
            ]

            # Ensure features are valid
            if any(np.isnan(f) for f in features):
                self.log.error(f"[{symbol}] Invalid features for {timeframe}: {features}")
                return None

            # Convert features to DataFrame with correct feature names
            feature_names = [
                'rsi', 'macd', 'macd_signal', 'bb_upper', 'bb_lower', 'atr', 'volume',
                'volume_sma_20', 'ema_20', 'ema_50', 'stoch_rsi', 'adx', 'cci', 'vwap', 'momentum'
            ]
            X = pd.DataFrame([features], columns=feature_names)

            # Predict
            prediction = self.model.predict(X)[0]
            confidence = self.model.predict_proba(X)[0][prediction] * 100

            # Determine direction
            direction = "LONG" if prediction == 1 else "SHORT"

            self.log.info(f"[{symbol}] Prediction for {timeframe}: {direction}, Confidence: {confidence:.2f}%")

            return {
                "direction": direction,
                "confidence": confidence
            }

        except Exception as e:
            self.log.error(f"[{symbol}] Error in prediction for {timeframe}: {str(e)}")
            return None
