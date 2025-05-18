# Module to classify trade types based on confidence and timeframe
# Updated to remove Swing and set trade type dynamically based on timeframe

# Function to classify trade type
def classify_trade(confidence: float, timeframe: str) -> str:
    # Check timeframe to determine trade type (Scalp for short, Normal for longer)
    if timeframe == "15m":
        # Scalp for 15-minute timeframe
        return "Scalp"
    elif timeframe in ["1h", "4h", "1d"]:
        # Normal for longer timeframes
        return "Normal"
    else:
        # Default to Scalp for unknown timeframes
        logger.warning(f"Unknown timeframe {timeframe}, defaulting to Scalp")
        return "Scalp"
