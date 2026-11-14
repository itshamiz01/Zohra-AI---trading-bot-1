"""Shared MetaTrader 5 utilities — extracted from duplicated project code."""

from zohra.config.settings import settings

from zohra.utils.mt5_connection import mt5, MT5_AVAILABLE


def units_to_lots(units: int) -> float:
    """Convert standard FX units to MT5 lots."""
    lots = units / 100_000
    step = 0.01
    lots = round(round(lots / step) * step, 2)
    return max(settings.risk.min_lot, min(lots, settings.risk.max_lot))


def round_price(symbol: str, price: float) -> float:
    if not MT5_AVAILABLE:
        return round(price, 5)
    info = mt5.symbol_info(symbol)
    if info is None:
        return round(price, 5)
    return round(price, info.digits)


def get_filling_mode(symbol: str) -> int:
    if not MT5_AVAILABLE:
        return 0
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    if fm & 4:
        return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK
