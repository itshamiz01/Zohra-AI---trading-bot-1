import unittest
from zohra.core.engine_registry import EngineRegistry

class MockEngine:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

class TestEngineRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = EngineRegistry()

    def test_registration_and_status(self):
        # Initial status should be not registered or stopped
        status = self.registry.get_status()
        self.assertFalse(status["forex"]["registered"])
        self.assertFalse(status["forex"]["running"])

        # Register mock engines
        mock_forex = MockEngine()
        self.registry.register(
            "forex", mock_forex,
            start_callback=mock_forex.start,
            stop_callback=mock_forex.stop
        )

        status = self.registry.get_status()
        self.assertTrue(status["forex"]["registered"])
        self.assertFalse(status["forex"]["running"])

    def test_start_stop_callbacks(self):
        mock_forex = MockEngine()
        self.registry.register(
            "forex", mock_forex,
            start_callback=mock_forex.start,
            stop_callback=mock_forex.stop
        )

        # Start engine
        success, msg = self.registry.start_engine("forex")
        self.assertTrue(success)
        self.assertTrue(mock_forex.started)
        self.assertTrue(self.registry.is_running("forex"))

        # Stop engine
        success, msg = self.registry.stop_engine("forex")
        self.assertTrue(success)
        self.assertTrue(mock_forex.stopped)
        self.assertFalse(self.registry.is_running("forex"))

    def test_invalid_engine_handling(self):
        success, msg = self.registry.start_engine("invalid_engine_name")
        self.assertFalse(success)
        self.assertIn("Unknown engine", msg)

        success, msg = self.registry.stop_engine("invalid_engine_name")
        self.assertFalse(success)
        self.assertIn("Unknown engine", msg)

if __name__ == "__main__":
    unittest.main()
