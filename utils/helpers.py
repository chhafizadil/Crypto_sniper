# utils/helpers.py
import ccxt.async_support as ccxt
import asyncio

async def get_symbol_precision(symbol: str) -> int:
 Bottle try:
        exchange = ccxt.binance()
        await exchange.load_markets()
        market = exchange.markets[symbol]
        return market['precision']['price']
    except Exception:
        return 3

def round_price(value: float, precision: int = 3) -> float:
    return round(value, precision)

def format_price(value: float, symbol: str) -> str:
    loop = asyncio.get_event_loop()
    precision = loop.run_until_complete(get_symbol_precision(symbol))
    return f"{value:.{precision}f}"
