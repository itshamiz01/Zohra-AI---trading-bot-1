Integration Guide: Adding Scalping Module to Your Bot
======================================================

This is an ADD-ON, not a replacement.
Your 1H swing system continues running.
This runs in parallel during London/NY overlap only.

STEPS TO INTEGRATE:
===================

1. COPY FILE
   Copy `scalping_module.py` into your trading_bot/ folder

2. IMPORT IN SCHEDULER
   Edit your `scheduler.py` and add:

   ```python
   from scalping_module import run_scalping_cycle
   ```

3. ADD TO MAIN LOOP
   In `scheduler.py`, inside the `run_cycle()` method or as a separate thread,
   call every 5 minutes:

   ```python
   # In your main loop, check if it's time for 5M scalp check
   now = datetime.utcnow()
   if now.minute % 5 == 0 and now.second < 10:  # Every 5 min
       run_scalping_cycle()
   ```

   OR use a separate thread (better):

   ```python
   import threading
   import time

   def scalp_loop():
       while scheduler.running:
           run_scalping_cycle()
           time.sleep(300)  # 5 minutes

   # Start in __init__ or start()
   self.scalp_thread = threading.Thread(target=scalp_loop)
   self.scalp_thread.daemon = True
   self.scalp_thread.start()
   ```

4. UPDATE TELEGRAM COMMANDS
   Add to `telegram_bot.py` process_command():

   ```python
   elif command == "/scalp_status":
       from scalping_module import SCALP_STATE
       msg = (
           f"SCALPING STATUS
"
           f"Session: {'ACTIVE' if scalping_engine._is_session_active() else 'CLOSED'}
"
           f"Trades today: {SCALP_STATE.daily_trade_count}/{MAX_DAILY_TRADES}
"
           f"Active scalps: {len(SCALP_STATE.active_scalps)}"
       )
       return msg
   ```

HARD LIMITS (CANNOT BE CHANGED):
================================
- Max 2 scalp trades per day
- 0.5% risk per trade (half of swing system)
- Max 3 micro lots (3,000 units) per trade
- Only London/NY overlap (13:00-17:00 UTC)
- No weekend trading
- Spread must be < 2 pips
- Minimum ADX 20
- 1:1.5 minimum R:R

HOW "SMART EXITS" WORK:
=======================
The module does NOT "feel" the market. It uses mechanical rules:

STRONG MOVE (ADX >= 25 + volume confirmation):
  -> Hold for TP2 (2R)
  -> Trail stop from 1R onward
  -> Only exit on stall OR volume drop

NORMAL MOVE (ADX 20-25):
  -> Close 50% at TP1 (1R)
  -> If TP1 hit and still strong, hold rest for TP2
  -> If momentum fades, close remaining at TP1

WEAK MOVE (stall detected OR volume drops):
  -> Close immediately at current price
  -> Take whatever profit/loss is available
  -> Do NOT wait for TP

THIS IS NOT AI. THIS IS RULE-BASED.
The "intelligence" is in the filters that PREVENT bad trades.

EXPECTED PERFORMANCE:
=====================
Realistic targets for this scalping module:

Trades per day: 0-2 (often 0 - filters work)
Win rate: 50-60% (higher than swing due to tight stops)
Avg winner: 1.2R (TP1 hits, some TP2)
Avg loser: 1.0R (hard stop)
Expectancy: +0.1R to +0.3R per trade
Monthly return: 2-5% (if edge exists)

IMPORTANT: Scalping has HIGHER costs (spread, slippage)
and LOWER win rates than swing trading.
The edge comes from volume and speed of exit, not prediction.

WARNING:
========
Do NOT increase these limits:
- Do NOT change MAX_DAILY_TRADES above 2
- Do NOT increase position size above 3,000 units
- Do NOT remove the session filter
- Do NOT trade outside 13:00-17:00 UTC

If you override these, you will lose money.
The limits are there to protect you from yourself.
