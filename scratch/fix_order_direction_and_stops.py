import os
import re

folders = [
    r"C:\Users\dell\Desktop\trading_bot",
    r"C:\Users\dell\Desktop\Trading Bot 2.0",
    r"C:\Users\dell\Desktop\Trading Bot 3.0"
]

open_trade_replacement = '''    def open_trade(self, symbol: str, direction: str, lots: float,
                   stop_loss: float, take_profit: float,
                   magic: int = None, comment: str = "Zohra") -> Optional[Dict]:
        """
        Open a market order.
        Returns trade dict with ticket, or None on failure.
        """
        # 0. Hard Symbol Guard check
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading disabled for {symbol}. Allowed symbols only.")
            return None

        if not MT5_AVAILABLE:
            logger.warning("MT5 not available — simulating trade open")
            return {"ticket": 99999, "price": 0, "symbol": symbol}

        if not mt5.symbol_select(symbol, True):
            logger.error(f"Cannot select {symbol}")
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"No tick data for {symbol}")
            return None

        # Snap lots to broker step
        lots = round(round(lots / LOT_STEP) * LOT_STEP, 2)
        lots = max(MIN_LOT_SIZE, min(lots, MAX_LOT_SIZE))

        # Precision & minimum stop level check
        info = mt5.symbol_info(symbol)
        digits = info.digits if info else (3 if "JPY" in symbol else 2 if "XAU" in symbol else 5)
        point = info.point if info else (0.001 if "JPY" in symbol else 0.01 if "XAU" in symbol else 0.00001)
        stops_level = getattr(info, "stops_level", 0) if info else 0
        min_stop_dist = max(stops_level * point, point * 10)

        clean_dir = str(direction).upper().strip()
        if clean_dir in ("LONG", "BUY"):
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            # Ensure SL is strictly below entry price
            if stop_loss > 0:
                if stop_loss >= price:
                    stop_loss = price - max(abs(price - stop_loss), min_stop_dist * 2)
                elif (price - stop_loss) < min_stop_dist:
                    stop_loss = price - min_stop_dist * 1.5
            # Ensure TP is strictly above entry price
            if take_profit > 0:
                if take_profit <= price:
                    take_profit = price + max(abs(take_profit - price), min_stop_dist * 2)
                elif (take_profit - price) < min_stop_dist:
                    take_profit = price + min_stop_dist * 1.5
        elif clean_dir in ("SHORT", "SELL"):
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            # Ensure SL is strictly above entry price
            if stop_loss > 0:
                if stop_loss <= price:
                    stop_loss = price + max(abs(stop_loss - price), min_stop_dist * 2)
                elif (stop_loss - price) < min_stop_dist:
                    stop_loss = price + min_stop_dist * 1.5
            # Ensure TP is strictly below entry price
            if take_profit > 0:
                if take_profit >= price:
                    take_profit = price - max(abs(price - take_profit), min_stop_dist * 2)
                elif (price - take_profit) < min_stop_dist:
                    take_profit = price - min_stop_dist * 1.5
        else:
            logger.error(f"Unknown order direction: {direction}")
            return None

        magic_num = magic or MAGIC_SMC
        sl_final = round(stop_loss, digits) if stop_loss > 0 else 0.0
        tp_final = round(take_profit, digits) if take_profit > 0 else 0.0
        price_final = round(price, digits)

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      symbol,
            "volume":      lots,
            "type":        order_type,
            "price":       price_final,
            "sl":          sl_final,
            "tp":          tp_final,
            "deviation":   10,
            "magic":       magic_num,
            "comment":     comment[:31],            # MT5 max 31 chars
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling(symbol),
        }

        # ── Pre-execution Order Check ──
        logger.info(f"📋 ORDER_REQUEST_CREATED: {clean_dir} {symbol} {lots}L @ {price_final} | SL={sl_final} TP={tp_final}")
        check_result = mt5.order_check(request)
        if check_result is not None and check_result.retcode != 0:
            logger.warning(f"⚠️ ORDER_CHECK_FAILED (retcode={check_result.retcode}): {check_result.comment} | MarginReq={getattr(check_result, 'margin', 'N/A')} | FreeMargin={getattr(check_result, 'margin_free', 'N/A')}")
            # If stops were invalid, retry with adjusted safety margin
            if check_result.retcode == 10016:
                logger.info("🔧 Auto-adjusting stops to meet broker minimum distance...")
                if order_type == mt5.ORDER_TYPE_BUY:
                    request["sl"] = round(price_final - (min_stop_dist * 3), digits)
                    request["tp"] = round(price_final + (min_stop_dist * 3), digits)
                else:
                    request["sl"] = round(price_final + (min_stop_dist * 3), digits)
                    request["tp"] = round(price_final - (min_stop_dist * 3), digits)
                logger.info(f"📋 REVISED_ORDER_REQUEST: {clean_dir} {symbol} SL={request['sl']} TP={request['tp']}")
        else:
            logger.info("✅ ORDER_CHECK_PASSED: Pre-execution broker validation successful.")

        result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            logger.error(f"❌ Order failed: mt5.order_send returned None. Last error: {err}")
            return None

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ TRADE OPENED: {symbol} {clean_dir} {lots}L @ {price_final} "
                        f"| SL={request['sl']} TP={request['tp']} | Ticket={result.order}")
            return {
                "ticket":    result.order,
                "symbol":    symbol,
                "direction": clean_dir,
                "lots":      lots,
                "price":     price_final,
                "stop_loss": request["sl"],
                "take_profit": request["tp"],
                "opened_at": datetime.utcnow().isoformat(),
            }
'''

for folder in folders:
    broker_path = os.path.join(folder, "zohra", "brokers", "mt5_broker.py")
    if os.path.exists(broker_path):
        with open(broker_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # Replace open_trade implementation up to `elif result.retcode == 10027:`
        pattern = r"    def open_trade\(self, symbol: str, direction: str, lots: float,.*?(?=        elif result\.retcode == 10027:)"
        
        if re.search(pattern, code, re.DOTALL):
            code = re.sub(pattern, open_trade_replacement, code, flags=re.DOTALL)
            with open(broker_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"Successfully updated open_trade in {broker_path}")
        else:
            print(f"Pattern match failed in {broker_path}")

print("Order execution fix completed across all 3 bots!")
