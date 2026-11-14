"""
╔══════════════════════════════════════════════════════════════════════╗
║            ZOHRA — UNIFIED MESSAGE BUS (Inter-Process IPC)          ║
║      Topic-based async pub/sub for process isolation                ║
║      Pure Python — No external dependencies (no Redis required)     ║
╚══════════════════════════════════════════════════════════════════════╝

Message Topics:
    market.data          — OHLCV candle data (Market Data Service → Strategy Engine)
    market.tick          — Tick data (bid/ask/spread)
    strategy.signal      — Trading signal from a strategy (Strategy Engine → Risk Engine)
    strategy.status      — Strategy health/state
    risk.approved        — Risk-approved execution authorization
    risk.rejected        — Risk-rejected signal
    execution.request    — Order to execute on a specific account (Risk Engine → Account Worker)
    execution.result     — Execution result (Account Worker → Trade Event Bus)
    account.snapshot     — Account state broadcast (Account Worker → Risk Engine)
    account.position     — Position update events
    system.heartbeat     — Process liveness
    system.alert         — System alerts
    system.command       — Control commands (kill switch, restart, etc.)
    trading.kill_switch  — Emergency stop signals
"""

import asyncio
import logging
import uuid
import threading
import time as _time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger("zohra.message_bus")


# ════════════════════════════════════════════════════════════════
#  MESSAGE TOPICS
# ════════════════════════════════════════════════════════════════

class MessageTopic(str, Enum):
    """Canonical message topics for the ZOHRA trading pipeline."""
    # Market Data
    MARKET_DATA = "market.data"
    MARKET_TICK = "market.tick"

    # Strategy
    STRATEGY_SIGNAL = "strategy.signal"
    STRATEGY_STATUS = "strategy.status"

    # Risk
    RISK_APPROVED = "risk.approved"
    RISK_REJECTED = "risk.rejected"

    # Execution
    EXECUTION_REQUEST = "execution.request"
    EXECUTION_RESULT = "execution.result"

    # Account
    ACCOUNT_SNAPSHOT = "account.snapshot"
    ACCOUNT_POSITION = "account.position"

    # System
    SYSTEM_HEARTBEAT = "system.heartbeat"
    SYSTEM_ALERT = "system.alert"
    SYSTEM_COMMAND = "system.command"

    # Kill Switch
    TRADING_KILL_SWITCH = "trading.kill_switch"


# ════════════════════════════════════════════════════════════════
#  MESSAGE SCHEMA
# ════════════════════════════════════════════════════════════════

@dataclass
class ZohraMessage:
    """
    Standard message envelope for all inter-process communication.

    Fields:
        message_type:   The topic/type of the message (from MessageTopic)
        message_id:     Unique UUID for this message
        timestamp:      ISO-8601 UTC timestamp
        source:         Identifier of the sending process/service
        payload:        The actual message data (dict)
        target:         Optional target process/account (for directed messages)
        priority:       Message priority (0=low, 1=normal, 2=high, 3=critical)
        origin_bus_id:  Bus instance ID to prevent self-echo on Redis transport
    """
    message_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    target: Optional[str] = None
    priority: int = 1
    origin_bus_id: str = ""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ZohraMessage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ════════════════════════════════════════════════════════════════
#  EXECUTION STATUS CODES
# ════════════════════════════════════════════════════════════════

class ExecutionStatus(str, Enum):
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


# ════════════════════════════════════════════════════════════════
#  KILL SWITCH LEVELS
# ════════════════════════════════════════════════════════════════

class KillSwitchLevel(str, Enum):
    GLOBAL = "GLOBAL"       # Stop everything
    ACCOUNT = "ACCOUNT"     # Stop specific account
    STRATEGY = "STRATEGY"   # Stop specific strategy


# ════════════════════════════════════════════════════════════════
#  SUBSCRIPTION
# ════════════════════════════════════════════════════════════════

@dataclass
class Subscription:
    """A subscriber registered for a specific topic."""
    subscriber_id: str
    topic: str
    callback: Callable
    is_async: bool = False
    filter_fn: Optional[Callable] = None  # Optional message filter


# ════════════════════════════════════════════════════════════════
#  MESSAGE BUS
# ════════════════════════════════════════════════════════════════

class ZohraMessageBus:
    """
    Topic-based asynchronous message bus for ZOHRA process isolation.

    Key Design Principles:
    - Cross-process IPC via Redis Pub/Sub (when available)
    - Pure in-memory async fallback (when Redis is offline)
    - Processes communicate ONLY through messages, never via direct function calls
    - Supports targeted messages (to specific account workers)
    - Supports wildcard topic subscriptions (e.g., "market.*")
    - Zero self-echo loops via origin_bus_id tracking
    """

    def __init__(self, max_queue_size: int = 10000, enable_redis: bool = True):
        self._subscriptions: Dict[str, List[Subscription]] = {}
        self._subscriber_queues: Dict[str, asyncio.Queue] = {}
        self._lock = threading.Lock()
        self._max_queue_size = max_queue_size
        self._running = True
        self._message_count = 0
        self._dropped_count = 0
        self.bus_id = uuid.uuid4().hex[:8]

        # Redis Cross-Process Transport
        self._redis_client = None
        self._redis_pubsub = None
        self._redis_thread = None

        if enable_redis:
            self._init_redis()

        mode = "REDIS (cross-process)" if self._redis_client else "IN-MEMORY (local)"
        logger.info(f"ZohraMessageBus initialized [{mode}] (bus_id={self.bus_id})")

    def _init_redis(self):
        """Initialize connection to local Redis server for cross-process IPC."""
        try:
            import redis
            import os
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", 6379))
            r = redis.Redis(host=host, port=port, db=0, protocol=2, socket_connect_timeout=2)
            if r.ping():
                self._redis_client = r
                self._redis_pubsub = r.pubsub()
                self._redis_pubsub.psubscribe("zohra.*")
                self._redis_thread = threading.Thread(target=self._redis_listen_loop, daemon=True)
                self._redis_thread.start()
                logger.info("Connected to Redis message bus for cross-process IPC (protocol 2)")
        except Exception as e:
            logger.info(f"Redis not available ({e}) — operating in in-memory mode")
            self._redis_client = None

    def _redis_listen_loop(self):
        """Background thread listening to Redis pubsub channels."""
        import json
        while self._running and self._redis_pubsub:
            try:
                for item in self._redis_pubsub.listen():
                    if not self._running:
                        break
                    if item and item.get('type') == 'pmessage':
                        raw_data = item.get('data')
                        if isinstance(raw_data, bytes):
                            raw_data = raw_data.decode('utf-8')
                        data = json.loads(raw_data)
                        origin = data.get('origin_bus_id')
                        if origin == self.bus_id:
                            continue  # Ignore self-echo
                        msg = ZohraMessage.from_dict(data)
                        self._dispatch_local(msg)
            except Exception as e:
                if self._running:
                    logger.debug(f"Redis listen loop warning: {e}")
                    _time.sleep(1.0)

    def _dispatch_local(self, message: ZohraMessage):
        """Dispatch a message received from Redis to local subscribers."""
        topic = message.message_type
        matching_subs = self._get_matching_subscriptions(topic)

        for sub in matching_subs:
            if message.target and message.target != sub.subscriber_id:
                continue
            if sub.filter_fn:
                try:
                    if not sub.filter_fn(message):
                        continue
                except Exception:
                    continue
            try:
                if sub.is_async:
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.run_coroutine_threadsafe(sub.callback(message), loop)
                    except RuntimeError:
                        asyncio.run(sub.callback(message))
                else:
                    sub.callback(message)
            except Exception as e:
                logger.error(f"Error dispatching remote {topic} to {sub.subscriber_id}: {e}")

    # ─── Subscribe ─────────────────────────────────────────

    def subscribe(self, topic: str, callback: Callable,
                  subscriber_id: str = None,
                  filter_fn: Callable = None) -> str:
        """
        Subscribe to a message topic.

        Args:
            topic: Message topic (from MessageTopic enum or string)
            callback: Function to call when message arrives (sync or async)
            subscriber_id: Unique ID for this subscriber (auto-generated if None)
            filter_fn: Optional filter function(msg) -> bool

        Returns:
            subscriber_id for later unsubscription
        """
        sub_id = subscriber_id or f"sub_{uuid.uuid4().hex[:8]}"
        is_async = asyncio.iscoroutinefunction(callback)

        sub = Subscription(
            subscriber_id=sub_id,
            topic=topic,
            callback=callback,
            is_async=is_async,
            filter_fn=filter_fn,
        )

        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(sub)

        logger.debug(f"Subscribed {sub_id} to topic: {topic} (async={is_async})")
        return sub_id

    def unsubscribe(self, subscriber_id: str) -> None:
        """Remove a subscriber by ID."""
        with self._lock:
            for topic in list(self._subscriptions.keys()):
                self._subscriptions[topic] = [
                    s for s in self._subscriptions[topic]
                    if s.subscriber_id != subscriber_id
                ]
                if not self._subscriptions[topic]:
                    del self._subscriptions[topic]
        logger.debug(f"Unsubscribed: {subscriber_id}")

    # ─── Publish ───────────────────────────────────────────

    async def publish(self, message: ZohraMessage) -> int:
        """
        Publish a message to all matching subscribers (local and cross-process).

        Returns:
            Number of subscribers that received the message locally.
        """
        if not self._running:
            return 0

        self._message_count += 1
        topic = message.message_type
        delivered = 0

        # Broadcast via Redis to other processes
        if self._redis_client:
            try:
                import json
                message.origin_bus_id = self.bus_id
                channel = f"zohra.{topic}"
                self._redis_client.publish(channel, json.dumps(message.to_dict()))
            except Exception as e:
                logger.warning(f"Failed to publish {topic} to Redis: {e}")

        # Deliver to local subscribers
        matching_subs = self._get_matching_subscriptions(topic)

        for sub in matching_subs:
            # Apply target filter
            if message.target and message.target != sub.subscriber_id:
                continue

            # Apply custom filter function
            if sub.filter_fn:
                try:
                    if not sub.filter_fn(message):
                        continue
                except Exception:
                    continue

            # Deliver the message
            try:
                if sub.is_async:
                    await sub.callback(message)
                else:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, sub.callback, message)
                delivered += 1
            except Exception as e:
                logger.error(f"Error delivering {topic} to {sub.subscriber_id}: {e}", exc_info=True)

        return delivered

    def publish_sync(self, message: ZohraMessage) -> None:
        """
        Synchronous publish — fires callbacks directly and broadcasts to Redis.
        """
        if not self._running:
            return

        self._message_count += 1
        topic = message.message_type

        # Broadcast via Redis
        if self._redis_client:
            try:
                import json
                message.origin_bus_id = self.bus_id
                channel = f"zohra.{topic}"
                self._redis_client.publish(channel, json.dumps(message.to_dict()))
            except Exception as e:
                logger.warning(f"Failed to publish {topic} to Redis: {e}")

        matching_subs = self._get_matching_subscriptions(topic)

        for sub in matching_subs:
            if message.target and message.target != sub.subscriber_id:
                continue
            if sub.filter_fn:
                try:
                    if not sub.filter_fn(message):
                        continue
                except Exception:
                    continue
            try:
                if not sub.is_async:
                    sub.callback(message)
                else:
                    logger.warning(f"Skipping async subscriber {sub.subscriber_id} in sync publish")
            except Exception as e:
                logger.error(f"Error in sync deliver {topic} to {sub.subscriber_id}: {e}", exc_info=True)

    # ─── Helper: Topic Matching (supports wildcards) ───────

    def _get_matching_subscriptions(self, topic: str) -> List[Subscription]:
        """Get all subscriptions matching a topic (exact + wildcard)."""
        result = []
        with self._lock:
            # Exact match
            if topic in self._subscriptions:
                result.extend(self._subscriptions[topic])

            # Wildcard match: "market.*" matches "market.data", "market.tick"
            topic_parts = topic.split(".")
            for sub_topic, subs in self._subscriptions.items():
                if "*" in sub_topic:
                    sub_parts = sub_topic.split(".")
                    if len(sub_parts) == len(topic_parts):
                        if all(sp == tp or sp == "*" for sp, tp in zip(sub_parts, topic_parts)):
                            result.extend(subs)
        return result

    # ─── Convenience Publish Methods ────────────────────────

    async def publish_market_data(self, symbol: str, timeframe: str,
                                   data: dict, source: str = "market_data_service") -> int:
        """Publish normalized market data."""
        msg = ZohraMessage(
            message_type=MessageTopic.MARKET_DATA.value,
            payload={"symbol": symbol, "timeframe": timeframe, **data},
            source=source,
        )
        return await self.publish(msg)

    async def publish_market_tick(self, symbol: str, bid: float, ask: float,
                                   spread: float, source: str = "market_data_service") -> int:
        """Publish a tick update."""
        msg = ZohraMessage(
            message_type=MessageTopic.MARKET_TICK.value,
            payload={
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "spread": spread,
            },
            source=source,
        )
        return await self.publish(msg)

    async def publish_strategy_signal(self, signal_id: str, strategy_id: str,
                                       symbol: str, timeframe: str, direction: str,
                                       entry: float, stop_loss: float, take_profit: float,
                                       confidence: float, source: str = "strategy_engine",
                                       target_account: Optional[str] = None) -> int:
        """Publish a strategy trading signal."""
        payload = {
            "signal_id": signal_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": confidence,
        }
        if target_account:
            payload["target_account"] = target_account

        msg = ZohraMessage(
            message_type=MessageTopic.STRATEGY_SIGNAL.value,
            payload=payload,
            source=source,
            # Keep account routing in the payload so RiskDecisionEngine receives the signal.
            priority=2,
        )
        return await self.publish(msg)

    async def publish_execution_request(self, signal_id: str, account_id: str,
                                         strategy_id: str, symbol: str, direction: str,
                                         volume: float, stop_loss: float, take_profit: float,
                                         max_slippage: int = 20,
                                         source: str = "risk_engine") -> int:
        """Publish an authorized execution request to a specific account worker."""
        request_id = str(uuid.uuid4())
        msg = ZohraMessage(
            message_type=MessageTopic.EXECUTION_REQUEST.value,
            payload={
                "request_id": request_id,
                "signal_id": signal_id,
                "account_id": account_id,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "direction": direction,
                "volume": volume,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "max_slippage": max_slippage,
            },
            source=source,
            target=account_id,
            priority=3,
        )
        return await self.publish(msg)

    async def publish_heartbeat(self, process_name: str, status: str = "HEALTHY",
                                 uptime: float = 0) -> int:
        """Publish a process heartbeat."""
        msg = ZohraMessage(
            message_type=MessageTopic.SYSTEM_HEARTBEAT.value,
            payload={
                "process": process_name,
                "status": status,
                "uptime": uptime,
            },
            source=process_name,
        )
        return await self.publish(msg)

    async def publish_kill_switch(self, level: str, target: str = None,
                                   reason: str = "", source: str = "supervisor") -> int:
        """Publish a kill switch command."""
        msg = ZohraMessage(
            message_type=MessageTopic.TRADING_KILL_SWITCH.value,
            payload={
                "level": level,
                "target": target,
                "reason": reason,
            },
            source=source,
            priority=3,
        )
        return await self.publish(msg)

    # ─── Stats & Control ────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics."""
        with self._lock:
            topics = {t: len(subs) for t, subs in self._subscriptions.items()}
        return {
            "running": self._running,
            "total_messages": self._message_count,
            "dropped_messages": self._dropped_count,
            "topics": topics,
            "total_subscriptions": sum(topics.values()),
        }

    def shutdown(self) -> None:
        """Gracefully shutdown the message bus."""
        logger.info("ZohraMessageBus shutting down...")
        self._running = False
        if self._redis_pubsub:
            try:
                self._redis_pubsub.close()
            except Exception:
                pass
        if self._redis_client:
            try:
                self._redis_client.close()
            except Exception:
                pass

    def reset(self) -> None:
        """Reset the message bus (for testing)."""
        with self._lock:
            self._subscriptions.clear()
            self._subscriber_queues.clear()
            self._message_count = 0
            self._dropped_count = 0
            self._running = True


# ════════════════════════════════════════════════════════════════
#  SINGLETON INSTANCE
# ════════════════════════════════════════════════════════════════

message_bus = ZohraMessageBus()
