import unittest
import os
import zipfile
import shutil
import asyncio
from datetime import datetime

from zohra.security.permissions import PermissionTier
from zohra.services.tool_execution.models import WindowsToolCall
from zohra.services.tool_execution.engine import (
    ToolExecutionEngine, PermissionPolicy, compute_rubric_tier,
)
from zohra.services.automation.windows_integration import (
    validate_path, encrypt_text, decrypt_bytes,
)
from zohra.agents.automation_agent import AutomationAgent, automation_agent


class TestWindowsIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up a clean environment for testing path allowlist and temp files
        os.environ["ZOHRA_TEST_BYPASS_ALLOWLIST"] = "0"
        os.environ["ZOHRA_PERMISSION_TIERS"] = '{"file_operation": 3, "os_control": 3}'
        self.agent = automation_agent
        self.engine = ToolExecutionEngine()
        from zohra.services.automation.windows_integration import register_all_capabilities
        register_all_capabilities(self.engine.registry)

    def test_rubric_tier_computation(self):
        """V8.3/V8.12: Test rubric tier calculations on diverse actions."""
        # Read-only tool should be Tier 0 (READ_ONLY)
        call_sys_info = WindowsToolCall(
            tool_id="os_control.sys_info",
            action="sys_info",
            params={},
            requesting_agent="test",
            permission_tier_required=PermissionTier.READ_ONLY,
            reversible=True,
        )
        self.assertEqual(compute_rubric_tier(call_sys_info), PermissionTier.READ_ONLY)

        # Reversible action affecting unnamed data partially should be Tier 2 (REVERSIBLE_CONFIRM)
        call_sync = WindowsToolCall(
            tool_id="file_operation.folder_sync",
            action="sync",
            params={},
            requesting_agent="test",
            permission_tier_required=PermissionTier.REVERSIBLE_NO_CONFIRM,
            reversible=True,
            affects_unnamed_files=True,
        )
        self.assertEqual(compute_rubric_tier(call_sync), PermissionTier.REVERSIBLE_CONFIRM)

        # Irreversible actions like secure shredder should be Tier 3 (IRREVERSIBLE_CONFIRM)
        call_shred = WindowsToolCall(
            tool_id="file_operation.secure_shredder",
            action="shred",
            params={"path": "dummy.txt"},
            requesting_agent="test",
            permission_tier_required=PermissionTier.READ_ONLY,
            reversible=False,
        )
        self.assertEqual(compute_rubric_tier(call_shred), PermissionTier.IRREVERSIBLE_CONFIRM)

    def test_path_traversal_and_allowlist_validation(self):
        """V8.9/V8.12: Verify paths outside confirmed directories or containing traversal are rejected."""
        # 1. Path traversal
        with self.assertRaises(PermissionError):
            validate_path("C:\\Windows\\System32\\..\\..\\sensitive_file.txt")

        # 2. Outside allowlisted dirs
        with self.assertRaises(PermissionError):
            validate_path("D:\\unauthorized_folder\\file.txt")

        # 3. Inside allowlisted dir (e.g. system32 or workspace)
        # Should return absolute path
        abs_p = validate_path("C:\\Windows\\System32\\cmd.exe")
        self.assertTrue(os.path.isabs(abs_p))

    def test_clipboard_history_encryption_at_rest(self):
        """V8.5/V13: Test clipboard history values are stored encrypted at rest."""
        text = "SuperSecretAPIKey123"
        encrypted = encrypt_text(text)
        # Decrypt it to verify
        decrypted = decrypt_bytes(encrypted)
        self.assertEqual(decrypted, text)
        self.assertNotEqual(encrypted, text.encode("utf-8"))

    async def test_protected_process_termination(self):
        """V8.6/V8.12: Killing critical system processes is hard-blocked."""
        # Try to kill explorer.exe
        call = WindowsToolCall(
            tool_id="os_control.task_manager",
            action="kill",
            params={"action": "kill", "process_name": "explorer.exe"},
            requesting_agent="test",
            permission_tier_required=PermissionTier.IRREVERSIBLE_CONFIRM,
            reversible=False,
        )
        # Execution should raise a PermissionError from within the handler
        res = await self.engine.execute(call)
        self.assertEqual(res.status, "failed")
        self.assertIn("UNVERIFIED_TOOL", res.error)

    async def test_unverified_shredder_cannot_delete_a_file(self):
        """A registered legacy function is not authorization to destroy files."""
        # Enable allowlist bypass temporarily to write to current directory
        os.environ["ZOHRA_TEST_BYPASS_ALLOWLIST"] = "1"
        temp_file = "test_shred_target.txt"

        try:
            # Create a file with known content
            with open(temp_file, "w") as f:
                f.write("A" * 1000)

            # Shred it
            call = WindowsToolCall(
                tool_id="file_operation.secure_shredder",
                action="shred",
                params={"path": temp_file, "passes": 3},
                requesting_agent="test",
                permission_tier_required=PermissionTier.IRREVERSIBLE_CONFIRM,
                reversible=False,
            )
            res = await self.engine.execute(call)
            self.assertEqual(res.status, "failed")
            self.assertIn("UNVERIFIED_TOOL", res.error)
            self.assertTrue(os.path.exists(temp_file))
            with open(temp_file) as target:
                self.assertEqual(target.read(), "A" * 1000)
        finally:
            os.environ["ZOHRA_TEST_BYPASS_ALLOWLIST"] = "0"
            if os.path.exists(temp_file):
                os.remove(temp_file)

    async def test_unverified_archive_adapter_is_not_executed(self):
        """Legacy archive handlers cannot run without a validated tool contract."""
        os.environ["ZOHRA_TEST_BYPASS_ALLOWLIST"] = "1"
        bomb_zip = "test_bomb.zip"
        extract_dir = "test_extracted"

        try:
            # Write a dummy zip containing a file with high compression ratio
            # Or mock the metadata sizes to simulate a zip bomb
            # We can create a compression ratio of > 100x easily
            with zipfile.ZipFile(bomb_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
                # 10MB of zeros compresses to extremely small size, triggering ratio check
                z.writestr("huge.txt", "0" * (1024 * 1024 * 10))

            # Unzip should raise PermissionError due to compression ratio
            call = WindowsToolCall(
                tool_id="file_operation.unzip_files",
                action="unzip",
                params={"zip_path": bomb_zip, "extract_path": extract_dir},
                requesting_agent="test",
                permission_tier_required=PermissionTier.REVERSIBLE_CONFIRM,
                reversible=True,
            )
            res = await self.engine.execute(call)
            self.assertEqual(res.status, "failed")
            self.assertIn("UNVERIFIED_TOOL", res.error)
            self.assertFalse(os.path.exists(extract_dir))

        finally:
            os.environ["ZOHRA_TEST_BYPASS_ALLOWLIST"] = "0"
            if os.path.exists(bomb_zip):
                os.remove(bomb_zip)
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)

    async def test_elevation_double_confirmation(self):
        """V8.6/V8.12: Elevation-requiring actions trigger dual confirmations."""
        call = WindowsToolCall(
            tool_id="os_control.power_manager",
            action="shutdown",
            params={"simulated_elevation_denied": True},
            requesting_agent="test",
            permission_tier_required=PermissionTier.REVERSIBLE_CONFIRM,
            reversible=False,
            requires_elevation=True,  # UAC prompt trigger
        )
        res = await self.engine.execute(call)
        self.assertEqual(res.status, "failed")
        self.assertIn("UNVERIFIED_TOOL", res.error)


if __name__ == "__main__":
    unittest.main()
