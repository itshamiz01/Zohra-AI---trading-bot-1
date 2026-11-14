"""Run tests against disposable storage without broker/network/device side effects."""
import os
import sys
import tempfile
import socket
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import pytest
    requested = sys.argv[1:]
    args = [
        str((ROOT / argument).resolve()) if not argument.startswith("-") and not os.path.isabs(argument)
        else argument
        for argument in requested
    ]
    with tempfile.TemporaryDirectory(prefix="zohra-audit-") as directory:
        os.chdir(directory)
        os.environ.update({"DB_PATH": str(Path(directory) / "test.db"),
                           "ZOHRA_LOG_DIR": str(Path(directory) / "logs"),
                           "CHROMA_PATH": str(Path(directory) / "chroma"),
                           "USE_POSTGRES": "0", "DATABASE_URL": "", "CONNECT_MT5_STANDALONE": "0",
                           "NETWORK_AVAILABLE": "0", "GROQ_API_KEY": "", "GEMINI_API_KEY": "",
                           "OPENROUTER_API_KEY": "", "TRADING_EXECUTION_MODE": "paper"})
        from zohra.config import settings as config
        config.LOG_DIR = str(Path(directory) / "logs")
        Path(config.LOG_DIR).mkdir(exist_ok=True)
        os.environ["ZOHRA_DISABLE_BACKGROUND"] = "1"
        original_connect = socket.socket.connect
        def local_connect(sock, address):
            if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
                raise OSError("External network disabled in audit tests")
            return original_connect(sock, address)
        with patch("socket.socket.connect", local_connect):
            args = args or [str(ROOT / "zohra/tests"), "--ignore=" + str(ROOT / "zohra/tests/test_windows_v8.py")]
            result = pytest.main([*args, "--basetemp=" + str(Path(directory) / "pytest"), "--rootdir=" + str(ROOT), "--confcutdir=" + str(ROOT), "-q", "--tb=short", "--disable-warnings", "-p", "no:cacheprovider"])
        # Some modules hold SQLite connections open until process exit on Windows.
        os.chdir(ROOT)
        sys.stdout.flush()
        os._exit(result)
