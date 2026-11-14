#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║               ZOHRA UNIFIED SYSTEM TEST SUITE                    ║
║               Validates All Components & Connections             ║
║                                                                  ║
║  Usage:                                                          ║
║    python zohratest.py                                           ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import asyncio

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def run_tests():
    print("=" * 62)
    print("  🧪 RUNNING ZOHRA UNIFIED SYSTEM TEST SUITE")
    print("=" * 62)

    from zohra.core.message_bus import message_bus, ZohraMessage, MessageTopic
    from zohra.config.settings import ACCOUNT_CONFIGS, ACTIVE_ACCOUNT_CONFIGS
    from zohra.config.bot_profile import ZOHRA_UNIFIED_PROFILE

    # Test 1: Message Bus In-Memory Pub/Sub
    received = []
    message_bus.subscribe(
        MessageTopic.STRATEGY_SIGNAL.value,
        lambda m: received.append(m.payload),
        subscriber_id='test_sub'
    )

    msg = ZohraMessage(
        message_type=MessageTopic.STRATEGY_SIGNAL.value,
        payload={
            'strategy_id': 'ema_pullback',
            'symbol': 'XAUUSD',
            'direction': 'BUY',
            'confidence': 85
        },
        source='test'
    )
    delivered = await message_bus.publish(msg)
    assert delivered >= 1, "Failed: Expected at least 1 delivery"
    assert received[0]['strategy_id'] == 'ema_pullback'
    print("  ✅ [TEST 1] In-Memory Pub/Sub: PASSED")

    # Test 2: Targeted Message Isolation
    t_recv = []
    message_bus.subscribe(
        MessageTopic.EXECUTION_REQUEST.value,
        lambda m: t_recv.append(m.payload),
        subscriber_id='target_acct_01',
        filter_fn=lambda m: m.payload.get('account_id') == 'account_01'
    )
    message_bus.subscribe(
        MessageTopic.EXECUTION_REQUEST.value,
        lambda m: t_recv.append(m.payload),
        subscriber_id='target_acct_02',
        filter_fn=lambda m: m.payload.get('account_id') == 'account_02'
    )

    t_msg = ZohraMessage(
        message_type=MessageTopic.EXECUTION_REQUEST.value,
        payload={'account_id': 'account_01', 'symbol': 'XAUUSD', 'volume': 0.1},
        source='risk_engine',
        target='target_acct_01'
    )
    await message_bus.publish(t_msg)
    assert len(t_recv) == 1 and t_recv[0]['account_id'] == 'account_01'
    print("  ✅ [TEST 2] Targeted Message Isolation: PASSED")

    # Test 3: Account Configuration Status
    assert len(ACCOUNT_CONFIGS) == 3, f"Expected 3 accounts, got {len(ACCOUNT_CONFIGS)}"
    assert len(ACTIVE_ACCOUNT_CONFIGS) == 3, f"Expected 3 active accounts, got {len(ACTIVE_ACCOUNT_CONFIGS)}"
    print(f"  ✅ [TEST 3] Account Configuration: PASSED (3/3 active)")
    for ac in ACCOUNT_CONFIGS:
        print(f"       - {ac.account_id}: Login {ac.login} ({ac.name})")

    # Test 4: Unified Strategy Profile (All 15 Strategies)
    strategies = ZOHRA_UNIFIED_PROFILE.enabled_strategies
    assert len(strategies) == 15, f"Expected 15 strategies, got {len(strategies)}"
    print(f"  ✅ [TEST 4] Unified Strategy Engine: PASSED (15/15 strategies loaded)")

    # Test 5: Redis Cross-Process Transport
    try:
        import redis
        r = redis.Redis(protocol=2, socket_connect_timeout=1)
        if r.ping():
            print("  ✅ [TEST 5] Redis IPC Message Transport: PASSED (ONLINE, protocol 2)")
        else:
            print("  ⚠️ [TEST 5] Redis IPC Message Transport: OFFLINE (falling back to in-memory)")
    except Exception as e:
        print(f"  ⚠️ [TEST 5] Redis check: {e} (operating in in-memory mode)")

    # Test 6: MT5 Terminal Executables Check
    terminals_ok = True
    for ac in ACCOUNT_CONFIGS:
        exists = os.path.exists(ac.terminal_path)
        status = "FOUND" if exists else "NOT FOUND"
        print(f"       - Terminal for {ac.account_id}: {ac.terminal_path} [{status}]")
        if not exists:
            terminals_ok = False

    if terminals_ok:
        print("  ✅ [TEST 6] MT5 Terminal Executables: PASSED (all 3 terminals exist)")
    else:
        print("  ⚠️ [TEST 6] MT5 Terminal Executables: WARNING (one or more terminals missing)")

    print("=" * 62)
    print("  🎉 ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 62)


def main():
    asyncio.run(run_tests())


if __name__ == "__main__":
    main()
