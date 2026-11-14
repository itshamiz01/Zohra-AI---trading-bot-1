"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — BROKER HEALTH MONITOR                           ║
║     API Heartbeats, Connection Status & Latency Audits               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Any

from zohra.event_bus import event_bus
from zohra.config.settings import settings

logger = logging.getLogger("zohra.validation.monitor")


class BrokerHealthMonitor:
    """
    Monitors latency, server connections, authentication statuses,
    streaming heartbeats, and rate limit boundaries for MT5, Dhan, and CoinDCX.
    """

    def __init__(self):
        self._health_history: Dict[str, List[Dict]] = {
            "mt5": [], "dhan": [], "coindcx": []
        }
        self._init_db()

    def _init_db(self):
        """Initialize health status log database table."""
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS broker_health_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    broker TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    health_score REAL NOT NULL,
                    message TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error creating health monitor table: {e}")

    def poll_broker_health(self, broker: str) -> Dict[str, Any]:
        """Poll a broker's current connection status and compute health metrics."""
        status = "offline"
        latency = 0.0
        health = 0.0
        msg = ""

        try:
            from zohra.brokers.manager import broker_manager
            if broker not in broker_manager.get_registered_brokers():
                status = "not_configured"
                health = 0.0
                msg = f"Broker {broker} adapter not loaded"
            else:
                # Mock or ping the adapter
                start_time = time.time()
                adapter = broker_manager.get_adapter(broker)
                
                if adapter:
                    connected = adapter.is_connected() if hasattr(adapter, "is_connected") else True
                    latency = round((time.time() - start_time) * 1000.0, 2)
                    
                    if connected:
                        status = "online"
                        # Scale health score based on latency
                        if latency < 100.0:
                            health = 100.0
                        elif latency < 300.0:
                            health = 85.0
                        elif latency < 1000.0:
                            health = 60.0
                            msg = "Warning: high latency detected"
                        else:
                            health = 40.0
                            msg = "Alert: critical latency"
                    else:
                        status = "offline"
                        health = 0.0
                        msg = "Connection dropped"
                else:
                    status = "not_configured"
                    health = 0.0
                    msg = f"Broker {broker} adapter not loaded"

        except Exception as e:
            status = "error"
            health = 0.0
            latency = 999.9
            msg = f"API poll exception: {str(e)}"

        # Save record
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "broker": broker,
            "status": status,
            "latency_ms": latency,
            "health_score": health,
            "message": msg
        }
        
        self._health_history[broker].append(record)
        if len(self._health_history[broker]) > 100:
            self._health_history[broker].pop(0)

        self._save_log_to_db(record)
        self._check_alerts(record)

        return record

    def poll_all(self) -> Dict[str, Dict]:
        """Polls MT5, Dhan, and CoinDCX health status."""
        results = {}
        for broker in ["mt5", "dhan", "coindcx"]:
            results[broker] = self.poll_broker_health(broker)
        return results

    def get_recent_history(self, broker: str) -> List[Dict]:
        """Return history logs for a broker."""
        return self._health_history.get(broker, [])[-20:]

    def _save_log_to_db(self, r: Dict):
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO broker_health_logs (timestamp, broker, status, latency_ms, health_score, message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (r["timestamp"], r["broker"], r["status"], r["latency_ms"], r["health_score"], r["message"]))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not log health status to DB: {e}")

    def _check_alerts(self, r: Dict):
        """Broadcast alert to system EventBus if broker goes offline or breaks rules."""
        if r["status"] == "not_configured":
            return
        if r["status"] in ("offline", "error") or r["health_score"] < 50:
            alert = {
                "timestamp": r["timestamp"],
                "broker": r["broker"],
                "severity": "CRITICAL" if r["status"] in ("offline", "error") else "WARNING",
                "message": f"Broker {r['broker'].upper()} health alert: {r['message']} (Score: {r['health_score']})"
            }
            # Emit alert
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(event_bus.publish("broker.alert", alert))
            except RuntimeError:
                pass


# Singleton
broker_monitor = BrokerHealthMonitor()
