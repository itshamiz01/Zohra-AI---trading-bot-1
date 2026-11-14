"""Quick smoke test for the ZOHRA unified message bus."""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from zohra.core.message_bus import message_bus, ZohraMessage, MessageTopic

received = []

def on_signal(msg):
    received.append(msg.payload)

message_bus.subscribe(
    MessageTopic.STRATEGY_SIGNAL.value,
    on_signal,
    subscriber_id='test_sub'
)

async def test():
    # Test 1: Basic publish/subscribe
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
    print(f"[TEST 1] Delivered to {delivered} subscriber(s)")
    print(f"[TEST 1] Received payload: {received[0] if received else 'nothing'}")
    assert delivered == 1, "Expected 1 delivery"
    assert received[0]['strategy_id'] == 'ema_pullback'
    print("[TEST 1] PASSED: Basic pub/sub works")

    # Test 2: Targeted message
    targeted_received = []
    message_bus.subscribe(
        MessageTopic.EXECUTION_REQUEST.value,
        lambda m: targeted_received.append(m.payload),
        subscriber_id='account_01',
        filter_fn=lambda m: m.payload.get('account_id') == 'account_01'
    )
    message_bus.subscribe(
        MessageTopic.EXECUTION_REQUEST.value,
        lambda m: targeted_received.append(m.payload),
        subscriber_id='account_02',
        filter_fn=lambda m: m.payload.get('account_id') == 'account_02'
    )

    exec_msg = ZohraMessage(
        message_type=MessageTopic.EXECUTION_REQUEST.value,
        payload={'account_id': 'account_01', 'symbol': 'XAUUSD', 'volume': 0.1},
        source='risk_engine',
        target='account_01'
    )
    d = await message_bus.publish(exec_msg)
    print(f"\n[TEST 2] Targeted delivery: {d} subscriber(s)")
    assert len(targeted_received) == 1, f"Expected 1, got {len(targeted_received)}"
    assert targeted_received[0]['account_id'] == 'account_01'
    print("[TEST 2] PASSED: Targeted messages work (only account_01 received)")

    # Test 3: Stats
    stats = message_bus.get_stats()
    print(f"\n[TEST 3] Bus stats: {stats}")
    assert stats['total_messages'] >= 2
    print("[TEST 3] PASSED: Stats work")

    # Test 4: Account configs
    from zohra.config.settings import ACCOUNT_CONFIGS, ACTIVE_ACCOUNT_CONFIGS
    print(f"\n[TEST 4] Accounts: {len(ACCOUNT_CONFIGS)} total, {len(ACTIVE_ACCOUNT_CONFIGS)} active")
    for ac in ACCOUNT_CONFIGS:
        print(f"  {ac.account_id}: login={ac.login} enabled={ac.enabled}")
    print("[TEST 4] PASSED")

    # Test 5: Unified profile
    from zohra.config.bot_profile import ZOHRA_UNIFIED_PROFILE
    print(f"\n[TEST 5] Unified profile: {len(ZOHRA_UNIFIED_PROFILE.enabled_strategies)} strategies")
    for s in ZOHRA_UNIFIED_PROFILE.enabled_strategies:
        print(f"  - {s}")
    print("[TEST 5] PASSED")

    print("\n" + "=" * 50)
    print("  ALL TESTS PASSED ✅")
    print("=" * 50)

asyncio.run(test())
