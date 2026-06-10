"""
LLM abstraction for cmux-remote-tui.

Supports:
- Local CLIs: grok, claude, codex (via subprocess, non-interactive)
- OpenRouter API (OpenAI compatible)
- Any OpenAI-compatible API (custom base_url + api_key)

Usage:
    llm = get_llm("openrouter", api_key=..., model="anthropic/claude-3.5-sonnet")
    response = llm.synthesize(prompt, temperature=0.2)

For local:
    llm = get_llm("local-claude", cli_path="claude", model="claude-3-5-sonnet-20241022")
    # or auto-detect common CLIs

The synthesize method is designed for our use case:
- Input: a big context with multiple surface screens + metadata
- Output: structured or markdown summary (agent states, prioritized list, suggestions)
"""

from __future__ import annotations
import os
import subprocess
import shlex
from typing import Optional, Literal
from dataclasses import dataclass

Provider = Literal["local-grok", "local-claude", "local-codex", "openrouter", "openai-compatible"]

@dataclass
class LLMConfig:
    provider: Provider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None   # for openai-compatible / openrouter
    cli_path: Optional[str] = None   # for local CLIs, e.g. "claude", "grok", "/usr/local/bin/codex"
    timeout: int = 120

class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None  # lazy for API clients

    def synthesize(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        """High-level method for our 'what's happening across surfaces' use case."""
        if self.config.provider.startswith("local-"):
            return self._call_local_cli(prompt)
        else:
            return self._call_openai_compatible(prompt, temperature, max_tokens)

    def _call_local_cli(self, prompt: str) -> str:
        cli = self.config.cli_path or self._guess_cli_path()
        if not cli:
            raise RuntimeError(f"No CLI found for provider {self.config.provider}. Set CLI_PATH or install the CLI.")

        # Common patterns for non-interactive:
        # claude: claude -p "prompt" --print   or   claude --model ... -p "..."
        # grok / codex: similar, often have --print or output to stdout
        # We use a simple "pipe prompt" approach and hope for best.
        # Users can tune via env or later config.
        cmd = [cli]
        if "claude" in cli.lower():
            cmd += ["-p", prompt, "--print", "--model", self.config.model]
        elif "grok" in cli.lower():
            cmd += ["--prompt", prompt, "--model", self.config.model]
        else:
            # generic: assume it takes prompt as last arg or via stdin
            cmd += [prompt]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=os.environ.copy(),
            )
            if result.returncode != 0:
                return f"[CLI error {result.returncode}] {result.stderr.strip() or result.stdout.strip()}"
            return result.stdout.strip()
        except FileNotFoundError:
            return f"[ERROR] CLI not found: {cli}. Is it in PATH?"
        except subprocess.TimeoutExpired:
            return "[ERROR] LLM CLI timed out"

    def _guess_cli_path(self) -> Optional[str]:
        candidates = {
            "local-claude": ["claude", "anthropic", "claude-code"],
            "local-grok": ["grok", "grok-cli", "xai"],
            "local-codex": ["codex", "openai-codex", "codex-cli"],
        }.get(self.config.provider, [])

        for name in candidates:
            if shutil.which(name):  # type: ignore
                return name
        return None

    def _call_openai_compatible(self, prompt: str, temperature: float, max_tokens: int) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            return "[ERROR] 'openai' package not installed. pip install openai"

        if not self._client:
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
            base = self.config.base_url
            if self.config.provider == "openrouter":
                base = base or "https://openrouter.ai/api/v1"
                # OpenRouter recommends specific header
                default_headers = {"HTTP-Referer": "https://github.com/vizi2000/cmux-remote-tui", "X-Title": "cmux-remote-tui"}

            self._client = OpenAI(
                api_key=api_key,
                base_url=base,
                default_headers=default_headers if self.config.provider == "openrouter" else None,
            )

        messages = [
            {"role": "system", "content": "You are a helpful expert multi-agent coding orchestrator. Be concise and actionable."},
            {"role": "user", "content": prompt},
        ]

        try:
            resp = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip() or "[empty response]"
        except Exception as e:
            return f"[LLM API error] {str(e)}"


import shutil  # for which in _guess

def get_llm(provider: str = None, **kwargs) -> LLMClient:
    """
    Factory.
    provider: "local-claude" | "local-grok" | "local-codex" | "openrouter" | "openai-compatible"
    Or set via env CMUX_LLM_PROVIDER
    """
    provider = provider or os.getenv("CMUX_LLM_PROVIDER", "openai-compatible")
    if provider not in ("local-grok", "local-claude", "local-codex", "openrouter", "openai-compatible"):
        raise ValueError(f"Unsupported provider: {provider}")

    model = kwargs.get("model") or os.getenv("CMUX_LLM_MODEL", "anthropic/claude-3.5-sonnet" if provider == "openrouter" else "claude-3-5-sonnet-20241022")

    config = LLMConfig(
        provider=provider,  # type: ignore
        model=model,
        api_key=kwargs.get("api_key") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=kwargs.get("base_url") or os.getenv("OPENAI_BASE_URL"),
        cli_path=kwargs.get("cli_path") or os.getenv("CMUX_LLM_CLI_PATH"),
    )
    return LLMClient(config)
