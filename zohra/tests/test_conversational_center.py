import unittest
from unittest.mock import patch
import os
import sys

# Inject paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.services.chat.session_manager import SessionManager
from zohra.services.chat.intent_layer import IntentRecognizer
from zohra.services.chat.command_router import CommandRouter
import zohra.config.settings as settings

try:
    from fastapi.testclient import TestClient
    from zohra.api.app import create_app
    FASTAPI_TEST_AVAILABLE = True
except ImportError:
    FASTAPI_TEST_AVAILABLE = False


class TestConversationalCenter(unittest.TestCase):
    """
    Unit tests asserting intent parsing, command routing, and
    Conversational API endpoint behaviors.
    """

    def setUp(self):
        self.session_id = "test-session-999"
        self.session_mgr = SessionManager()
        self.intent_layer = IntentRecognizer()
        self.router = CommandRouter()

        # Save active risk to restore later
        self.saved_risk = settings.RISK_PER_TRADE_PCT

    def tearDown(self):
        # Restore risk
        settings.RISK_PER_TRADE_PCT = self.saved_risk
        
        # Clean up test session records
        from zohra.db.schema import db
        db._execute("DELETE FROM chat_sessions WHERE session_id = ?", (self.session_id,))

    def test_regex_intent_parsing(self):
        """Verify that the rule-based intent layer accurately classifies input strings."""
        # positions
        intent, params = self.intent_layer.parse("show my active positions")
        self.assertEqual(intent, "GET_POSITIONS")

        # performance
        intent, params = self.intent_layer.parse("how is the bot performing today?")
        self.assertEqual(intent, "GET_PERFORMANCE")
        self.assertEqual(params.get("days"), 1)

        intent, params = self.intent_layer.parse("show weekly stats")
        self.assertEqual(intent, "GET_PERFORMANCE")
        self.assertEqual(params.get("days"), 7)

        # modify risk
        intent, params = self.intent_layer.parse("change risk to 0.75%")
        self.assertEqual(intent, "MODIFY_RISK")
        self.assertAlmostEqual(params.get("risk_pct"), 0.75)

        # halt & resume
        intent, params = self.intent_layer.parse("pause trading please")
        self.assertEqual(intent, "HALT_TRADING")

        intent, params = self.intent_layer.parse("resume the engine scans")
        self.assertEqual(intent, "RESUME_TRADING")

        # close commands
        intent, params = self.intent_layer.parse("close all profitable trades.")
        self.assertEqual(intent, "CLOSE_PROFITABLE")

        intent, params = self.intent_layer.parse("emergency close all positions")
        self.assertEqual(intent, "CLOSE_ALL")

        # explanations
        intent, params = self.intent_layer.parse("explain why EURUSD was rejected?")
        self.assertEqual(intent, "EXPLAIN_REJECTION")
        self.assertEqual(params.get("symbol"), "EURUSD")

        intent, params = self.intent_layer.parse("why did you enter gold?")
        self.assertEqual(intent, "EXPLAIN_TRADE")
        self.assertEqual(params.get("symbol"), "XAUUSD")

        # market analysis
        intent, params = self.intent_layer.parse("analyze GBPUSD")
        self.assertEqual(intent, "ANALYZE_MARKET")
        self.assertEqual(params.get("symbol"), "GBPUSD")

    def test_session_manager(self):
        """Verify session persistence layers can write and load histories correctly."""
        # Add messages
        self.session_mgr.add_message(self.session_id, "user", "Hello bot")
        self.session_mgr.add_message(self.session_id, "assistant", "Hello user", intent="GENERAL_QNA")

        # Retrieve history
        history = self.session_mgr.get_history(self.session_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["message"], "Hello bot")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[1]["intent"], "GENERAL_QNA")

        # Get context
        context = self.session_mgr.get_session_context(self.session_id)
        self.assertEqual(len(context), 2)
        self.assertEqual(context[0]["role"], "user")
        self.assertEqual(context[0]["content"], "Hello bot")

    def test_command_routing_modify_risk(self):
        """Verify that routing MODIFY_RISK correctly modifies active memory settings."""
        # Initial settings check
        self.assertEqual(settings.RISK_PER_TRADE_PCT, self.saved_risk)

        # Dispatch modify risk
        explanation, raw_data = self.router.dispatch("MODIFY_RISK", {"risk_pct": 0.8})
        self.assertTrue(raw_data["success"])
        self.assertEqual(raw_data["new_risk_pct"], 0.8)

        # Assert memory changes
        self.assertAlmostEqual(settings.RISK_PER_TRADE_PCT, 0.008)

    def test_api_endpoint(self):
        """Verify the FastAPI routing endpoint returns structured JSON replies."""
        if not FASTAPI_TEST_AVAILABLE:
            self.skipTest("FastAPI TestClient not available")

        # Mock all LLM keys to force offline fallback routing
        with patch.dict(os.environ, {"GROQ_API_KEY": "", "OPENROUTER_API_KEY": "", "GEMINI_API_KEY": ""}):
            # Temporarily clear keys in settings too
            orig_groq = settings.GROQ_API_KEY
            orig_openrouter = settings.OPENROUTER_API_KEY
            orig_gemini = settings.GEMINI_API_KEY
            
            settings.GROQ_API_KEY = ""
            settings.OPENROUTER_API_KEY = ""
            settings.GEMINI_API_KEY = ""
            
            try:
                app = create_app()
                client = TestClient(app, base_url="http://127.0.0.1")
                
                # Submit message
                response = client.post("/api/v1/chat/message", json={
                    "session_id": self.session_id,
                    "message": "modify risk to 0.4%"
                })
                
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["session_id"], self.session_id)
                self.assertEqual(data["intent"], "TRADING")
                self.assertTrue("response" in data)
                self.assertEqual(data["status"], "blocked")
                self.assertIsNone(data["raw_data"])
            finally:
                settings.GROQ_API_KEY = orig_groq
                settings.OPENROUTER_API_KEY = orig_openrouter
                settings.GEMINI_API_KEY = orig_gemini


if __name__ == "__main__":
    unittest.main()
