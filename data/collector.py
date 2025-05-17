import asyncio
import ccxt.async_support as ccxt
import pandas as pd
from utils.logger import logger
import cachetools

data_cache = cachetools.TTLCache(maxsize=100, ttl=300)  # 5-minute cache

async def fetch_realtime_data(symbol, timeframe="15m"):
    try:
        if symbol in data_cache:
            log(f"[{symbol}] Using cached OHLCV data")
            return data_cache[symbol]

        exchange = ccxt.binance({"enableRateLimit": True})
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv or len(ohlcv) < 50:
            log(f"[{symbol}] Insufficient OHLCV data", level='WARNING')
            await exchange.close()
            return None

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"], dtype="float32")
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        data_cache[symbol] = df
        log(f"[{symbol}] Fetched OHLCV data")
        await exchange.close()
        return df
    except Exception as e:
        log(f"[{symbol}] Error fetching OHLCV: {e}", level='ERROR')
        await exchange.close()
        return None

async def websocket_collector(symbol, timeframe="15m"):
    try:
        exchange = ccxt.binance({"enableRateLimit": True})
        while True:
            ohlcv = await exchange.watch_ohlcv(symbol, timeframe, limit=100)
            if not ohlcv or len(ohlcv) < 50:
                log(f"[{symbol}] Insufficient WebSocket OHLCV data", level='WARNING')
                continue

            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"], dtype="float32")
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            data_cache[symbol] = df
            log(f"[{symbol}] Updated WebSocket OHLCV data")
            await asyncio.sleep(60)  # Update every minute
    except Exception as e:
        log(f"[{symbol}] Error in WebSocket collector: {e}", level='ERROR')
    finally:
        await exchange.close()
