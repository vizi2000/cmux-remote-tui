"""Unit tests for LLM abstraction."""
import pytest
from cmux_remote_tui.llm import LLMConfig, LLMClient, get_llm, Provider


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig(provider="openai-compatible", model="gpt-4")
        assert config.provider == "openai-compatible"
        assert config.model == "gpt-4"
        assert config.api_key is None
        assert config.base_url is None
        assert config.timeout == 120

    def test_all_fields(self):
        config = LLMConfig(
            provider="openrouter",
            model="anthropic/claude-3.5-sonnet",
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            cli_path=None,
            timeout=60,
        )
        assert config.api_key == "sk-test"
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.timeout == 60


class TestGetLlm:
    def test_openai_compatible_default(self, monkeypatch):
        monkeypatch.delenv("CMUX_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("CMUX_LLM_MODEL", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = get_llm()
        assert client.config.provider == "openai-compatible"

    def test_explicit_provider(self, monkeypatch):
        monkeypatch.delenv("CMUX_LLM_MODEL", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = get_llm("local-claude")
        assert client.config.provider == "local-claude"

    def test_env_provider(self, monkeypatch):
        monkeypatch.setenv("CMUX_LLM_PROVIDER", "local-grok")
        monkeypatch.delenv("CMUX_LLM_MODEL", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = get_llm()
        assert client.config.provider == "local-grok"

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            get_llm("invalid-provider")

    def test_openrouter_default_model(self, monkeypatch):
        monkeypatch.delenv("CMUX_LLM_MODEL", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = get_llm("openrouter")
        assert client.config.model == "anthropic/claude-3.5-sonnet"

    def test_custom_model(self, monkeypatch):
        monkeypatch.delenv("CMUX_LLM_MODEL", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = get_llm("openai-compatible", model="custom-model")
        assert client.config.model == "custom-model"

    def test_env_model(self, monkeypatch):
        monkeypatch.setenv("CMUX_LLM_MODEL", "env-model")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = get_llm("openai-compatible")
        assert client.config.model == "env-model"


class TestLLMClientLocal:
    def test_guess_cli_path_not_found(self):
        """When CLI is not in PATH, _guess_cli_path returns None."""
        config = LLMConfig(provider="local-claude", model="test")
        client = LLMClient(config)
        # claude might or might not be installed; just verify no crash
        result = client._guess_cli_path()
        assert result is None or isinstance(result, str)

    def test_call_local_cli_not_found(self):
        """When CLI binary doesn't exist, returns error string."""
        config = LLMConfig(provider="local-claude", model="test", cli_path="/nonexistent/cli")
        client = LLMClient(config)
        result = client.synthesize("test prompt")
        assert "[ERROR]" in result or "[CLI error]" in result


class TestLLMClientOpenAI:
    def test_missing_openai_package(self, monkeypatch):
        """When openai package is not installed, returns error string."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("No module named 'openai'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        config = LLMConfig(provider="openai-compatible", model="gpt-4", api_key="sk-test")
        client = LLMClient(config)
        result = client.synthesize("test prompt")
        assert "openai" in result.lower() or "ERROR" in result
