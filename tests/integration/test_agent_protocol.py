"""Integration tests for agent JSON protocol.

These test the agent.py ops by invoking them directly (not over SSH).
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from cmux_remote_tui.agent import op_tree, op_read, op_read_many, op_keys, op_cmux, OPS


class TestAgentOps:
    """Test agent operations with mocked cmux CLI."""

    def test_ops_registry(self):
        assert "tree" in OPS
        assert "read" in OPS
        assert "read_many" in OPS
        assert "cmux" in OPS
        assert "keys" in OPS

    def test_op_tree_missing_cmux(self):
        """op_tree raises RuntimeError if cmux is not available."""
        with patch("cmux_remote_tui.agent.subprocess.run", side_effect=FileNotFoundError("no cmux")):
            with pytest.raises((RuntimeError, FileNotFoundError)):
                op_tree({})

    def test_op_read_missing_cmux(self):
        """op_read returns error string if cmux fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "cmux not found"
        with patch("cmux_remote_tui.agent.subprocess.run", return_value=mock_result):
            result = op_read({"ref": "surface:1", "lines": 50})
            assert "error" in result.lower() or "read error" in result.lower()

    def test_op_read_many_missing_cmux(self):
        """op_read_many returns error strings for each ref."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "cmux not found"
        with patch("cmux_remote_tui.agent.subprocess.run", return_value=mock_result):
            result = op_read_many({"refs": ["surface:1", "surface:2"], "lines": 50})
            assert "surface:1" in result
            assert "surface:2" in result

    def test_op_cmux_missing_cmux(self):
        """op_cmux returns error dict if cmux fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "cmux not found"
        with patch("cmux_remote_tui.agent.subprocess.run", return_value=mock_result):
            result = op_cmux({"argv": ["tree"]})
            assert "rc" in result

    def test_op_keys_missing_cmux(self):
        """op_keys returns error string if cmux fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "cmux not found"
        with patch("cmux_remote_tui.agent.subprocess.run", return_value=mock_result):
            result = op_keys({"ref": "surface:1", "events": [["text", "ls"]]})
            assert isinstance(result, str)


class TestAgentProtocol:
    """Test the JSON protocol format."""

    def test_tree_returns_full_tree_key(self):
        """op_tree should return dict with 'full_tree', 'rows', and 'active' keys when cmux works."""
        import subprocess
        try:
            subprocess.run(
                ["/Applications/cmux.app/Contents/Resources/bin/cmux", "--version"],
                capture_output=True, timeout=5
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("cmux not available")

        # If cmux is available, verify the protocol shape
        result = op_tree({})
        assert "full_tree" in result
        assert "rows" in result
        assert "active" in result
